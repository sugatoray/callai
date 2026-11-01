"""Adapter for the pi coding agent (``pi --mode json``)."""

from __future__ import annotations

from typing import Any

from ..errors import UsageError
from ..request import Request
from ..result import Completed, Result
from .base import Adapter, content_text, json_line, jsonl_events, strip_ansi, tool_result, tool_use

# pi has no approval prompts, only tool allowlists (verified against pi 1.4.0 and the stub's request
# log). --tools keeps MCP tools, so restricted levels also pass --no-mcp.
_READ_TOOLS = "read,grep,find,ls"
_PERMISSION_FLAGS: dict[str, list[str]] = {
    "default": [],
    "read-only": ["--tools", _READ_TOOLS, "--no-mcp"],
    "auto": ["--tools", f"{_READ_TOOLS},edit,write", "--no-mcp"],  # edits yes, shell no
    "bypass": [],  # pi's default already runs every tool without asking
}
_FAILED_STOPS = {"error", "aborted", "length"}


class Pi(Adapter):
    """``pi --mode json`` — parses the JSONL session events."""

    name = "pi"
    binary = "pi"
    install_url = "https://pi.dev/docs/latest/quickstart"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``pi`` command line.

        Args:
            req: The request to run.

        Returns:
            The argv list, prompt last after ``--``.

        Raises:
            UsageError: If the prompt starts with ``@``, which pi always reads as a file to attach.
        """
        if req.prompt.startswith("@"):
            raise UsageError(
                "pi reads a prompt starting with '@' as a file to attach, and has no escape; "
                "start the prompt with other text (e.g. a space)"
            )
        argv = [self.binary, "--mode", "json"]
        if req.model:
            argv += ["--model", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        if req.system_prompt is not None:
            argv += ["--system-prompt", req.system_prompt]
        return [*argv, *_session_flags(req), *req.extra_args, "--", req.prompt]

    def parse(self, completed: Completed, req: Request) -> Result:
        """Parse the JSONL events of ``pi --mode json``.

        The answer is the text of the last assistant ``message_end``. pi exits 0 even when the model
        call fails, so failure comes from that message's ``stopReason`` (error, aborted or length),
        a missing assistant message, or a non-zero exit. Usage and cost are summed over all turns.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        events = jsonl_events(completed.stdout)
        if not events:  # e.g. a model pi doesn't know: the reason is only on stderr
            text = strip_ansi(completed.stderr).strip() or strip_ansi(completed.stdout).strip()
            return self.text_result(completed, req).with_updates(text=text, is_error=True)
        session_id = None
        last: dict[str, Any] | None = None
        usage: dict[str, int] | None = None
        cost: float | None = None
        for ev in events:
            if ev.get("type") == "session":
                session_id = ev.get("id")
            message = ev.get("message") or {}
            if ev.get("type") == "message_end" and message.get("role") == "assistant":
                last = message
                usage, cost = _add_usage(usage, cost, message.get("usage"))
        text, failed, model = "", last is None, req.model
        if last is not None:
            text = "\n".join(
                b["text"]
                for b in last.get("content") or []
                if b.get("type") == "text" and isinstance(b.get("text"), str)
            )
            stop = last.get("stopReason")
            if stop in _FAILED_STOPS:
                failed = True
                if stop != "length":
                    text = last.get("errorMessage") or stop
            if last.get("provider") and last.get("model"):
                model = f"{last['provider']}/{last['model']}"
        return Result(
            harness_name=self.name,
            model=model,
            text=text,
            exit_code=completed.exit_code,
            is_error=failed or completed.exit_code != 0,
            duration_ms=completed.duration_ms,
            session_id=session_id,
            usage=usage,
            cost_usd=cost,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map a ``pi --mode json`` line: text deltas, and tool executions.

        Text comes from ``text_delta`` updates (pieces of a message as the model writes them), not
        from the whole messages pi repeats in ``message_end``/``turn_end``, so nothing is reported twice.

        Args:
            line: One stdout line.
            state: Unused.

        Returns:
            The events.
        """
        data = json_line(line)
        kind = data.get("type") if data else None
        if kind == "message_update":
            update = data.get("assistantMessageEvent")
            if isinstance(update, dict) and update.get("type") == "text_delta":
                return [{"type": "text", "text": update.get("delta", "")}]
        elif kind == "tool_execution_start":
            return [tool_use(data.get("toolCallId"), data.get("toolName"), data.get("args"))]
        elif kind == "tool_execution_end":
            result = data.get("result")
            output = content_text(result.get("content")) if isinstance(result, dict) else ""
            return [tool_result(data.get("toolCallId"), bool(data.get("isError")), output)]
        return []


def _add_usage(
    usage: dict[str, int] | None, cost: float | None, raw: Any
) -> tuple[dict[str, int] | None, float | None]:
    """Add one assistant message's usage to the running totals.

    pi's ``input`` excludes cached tokens, so ``cacheRead`` and ``cacheWrite`` are added back in.

    Args:
        usage: Totals so far, or ``None``.
        cost: Cost so far, or ``None``.
        raw: The message's ``usage`` object.

    Returns:
        The updated ``(usage, cost)``.
    """
    if not isinstance(raw, dict):
        return usage, cost
    usage = usage or {"input_tokens": 0, "output_tokens": 0}
    usage["input_tokens"] += sum(int(raw.get(k) or 0) for k in ("input", "cacheRead", "cacheWrite"))
    usage["output_tokens"] += int(raw.get("output") or 0)
    total = (raw.get("cost") or {}).get("total")
    if isinstance(total, int | float):
        cost = (cost or 0) + total
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
