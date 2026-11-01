"""Adapter for the opencode CLI (``opencode run``)."""

from __future__ import annotations

import re
from typing import Any

from ..errors import UsageError
from ..request import Request
from ..result import Completed, Result
from .base import Adapter, json_line, jsonl_events, tool_result, tool_use

# Verified against opencode 1.19.5. Levels opencode cannot honour fail closed (DESIGN.md §7).
_PERMISSION_FLAGS: dict[str, list[str]] = {"default": [], "bypass": ["--auto"]}
_UNSUPPORTED_PERMISSION = {
    "read-only": "opencode has no read-only mode (its plan agent still allows shell commands); "
    "pass `-- --agent plan` yourself if that is acceptable",
    "auto": "opencode has no 'auto-approve edits only' mode (--auto approves everything); "
    "use --permission bypass or the default",
}
# `--print-logs --log-level ERROR` puts the real failure reason on stderr, e.g.
#   level=ERROR ... error="ProviderModelNotFoundError: Model not found: ..." cause="..."
_ERROR_LOG_RE = re.compile(r'level=ERROR\b.*?\berror="((?:[^"\\]|\\.)*)"')


class OpenCode(Adapter):
    """``opencode run --format json`` — parses the JSONL event stream."""

    name = "opencode"
    binary = "opencode"
    install_url = "https://opencode.ai/docs/"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``opencode run`` command line.

        opencode wraps every message argument that contains a space in literal quotes before sending
        it to the model, so the prompt is passed split on single spaces; opencode joins the pieces
        with single spaces, which rebuilds the prompt exactly (all of it after ``--``).

        Args:
            req: The request to run.

        Returns:
            The argv list.

        Raises:
            UsageError: For permission levels or a system prompt opencode cannot honour.
        """
        if req.permission in _UNSUPPORTED_PERMISSION:
            raise UsageError(f"--permission {req.permission}: {_UNSUPPORTED_PERMISSION[req.permission]}")
        if req.system_prompt is not None:
            raise UsageError("opencode run has no system prompt option; drop --system-prompt")
        argv = [self.binary, "run", "--format", "json", "--print-logs", "--log-level", "ERROR"]
        if req.model:
            argv += ["--model", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        return [*argv, *_session_flags(req), *req.extra_args, "--", *req.prompt.split(" ")]

    def parse(self, completed: Completed, req: Request) -> Result:
        """Parse the JSONL events of ``opencode run --format json``.

        The answer is the text of the last step (earlier steps precede tool calls); tokens and cost
        are summed over all steps. An ``error`` event or a non-zero exit is a failure, reported with
        the ERROR log line from stderr when there is one (the event itself is often generic).

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        events = jsonl_events(completed.stdout)
        if not events:
            return self.text_result(completed, req).with_updates(is_error=True)
        texts: list[str] = []
        session_id = None
        usage: dict[str, int] | None = None
        cost: float | None = None
        failure: str | None = None
        for ev in events:
            session_id = session_id or ev.get("sessionID")
            part = ev.get("part") or {}
            kind = ev.get("type")
            if kind == "step_start":
                texts = []
            elif kind == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif kind == "step_finish":
                usage, cost = _add_step(usage, cost, part)
            elif kind == "error":
                err = ev.get("error") or {}
                failure = (err.get("data") or {}).get("message") or err.get("name") or "opencode error"
        log = _ERROR_LOG_RE.search(completed.stderr)
        if failure is not None and log:
            failure = log.group(1).replace('\\"', '"')
        text = "\n".join(texts)
        return Result(
            harness_name=self.name,
            model=req.model,
            text=failure if failure is not None else text,
            exit_code=completed.exit_code,
            is_error=failure is not None or completed.exit_code != 0,
            duration_ms=completed.duration_ms,
            session_id=session_id,
            usage=usage,
            cost_usd=cost,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map an ``opencode run --format json`` line: ``text`` parts, and ``tool_use`` parts.

        opencode 1.19.5 prints a tool part once the call has finished, with its input and output
        together, so both events come from one line. A part seen earlier (still running) isn't
        reported twice; ``state`` remembers it.

        Args:
            line: One stdout line.
            state: Remembers reported call ids (``"started"``).

        Returns:
            The events.
        """
        data = json_line(line)
        part = data.get("part") if data else None
        if not isinstance(part, dict):
            return []
        if data.get("type") == "text":
            return [{"type": "text", "text": part.get("text", "")}]
        call = part.get("state")
        if data.get("type") != "tool_use" or not isinstance(call, dict):
            return []
        call_id = part.get("callID")
        started = state.setdefault("started", set())
        events = []
        if call_id not in started:
            started.add(call_id)
            events.append(tool_use(call_id, part.get("tool"), call.get("input")))
        if call.get("status") in ("completed", "error"):
            failed = call["status"] == "error"
            output = call.get("error" if failed else "output")
            events.append(tool_result(call_id, failed, output if isinstance(output, str) else ""))
        return events


def _add_step(
    usage: dict[str, int] | None, cost: float | None, part: dict[str, Any]
) -> tuple[dict[str, int] | None, float | None]:
    """Add one ``step_finish`` part's tokens and cost to the running totals.

    opencode's ``input`` excludes cached tokens, so cache reads and writes are added back in.

    Args:
        usage: Totals so far, or ``None``.
        cost: Cost so far, or ``None``.
        part: The ``step_finish`` event's part.

    Returns:
        The updated ``(usage, cost)``.
    """
    tokens = part.get("tokens")
    if isinstance(tokens, dict):
        cache = tokens.get("cache") or {}
        usage = usage or {"input_tokens": 0, "output_tokens": 0}
        usage["input_tokens"] += sum(int(v or 0) for v in (tokens.get("input"), cache.get("read"), cache.get("write")))
        usage["output_tokens"] += int(tokens.get("output") or 0)
    if isinstance(part.get("cost"), int | float):
        cost = (cost or 0) + part["cost"]
    return usage, cost


def _session_flags(req: Request) -> list[str]:
    """The harness's flags for ``--resume ID`` / ``--continue`` (none for a new session).

    Args:
        req: The request.

    Returns:
        The flags.
    """
    if req.resume is not None:
        return ["--session", req.resume]
    return ["--continue"] if req.continue_session else []
