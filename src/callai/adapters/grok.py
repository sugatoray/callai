"""Adapter for xAI's Grok Build CLI (``grok --output-format json --single=PROMPT``)."""

from __future__ import annotations

import json
from typing import Any

from ..errors import UsageError
from ..request import Request
from ..result import Completed, Result
from .base import Adapter, content_text, json_line, jsonl_events, strip_ansi, tool_result, tool_use

# Verified against grok 1.0.70 with scripted tool calls from the stub (write, edit, shell). A headless
# run refuses (and cancels the turn on) any call that needs approval, so "default" already blocks
# writes and shell. read-only also removes every tool but grok's read tools; --tools keeps
# search_tool/use_tool (the gateway to MCP and deferred tools), so those are removed explicitly.
# auto uses allow rules: grok accepts --permission-mode acceptEdits but still refused a headless write,
# and --permission-mode auto lets a model-based safety check approve calls (shell included).
_PERMISSION_FLAGS: dict[str, list[str]] = {
    "default": [],
    "read-only": ["--tools", "read_file,grep,list_dir", "--disallowed-tools", "search_tool,use_tool"],
    "auto": ["--allow", "Write", "--allow", "Edit"],  # writes and edits yes; shell etc. refused
    "bypass": ["--permission-mode", "bypassPermissions"],
}


class Grok(Adapter):
    """``grok --output-format json`` — parses the single JSON result object."""

    name = "grok"
    binary = "grok"
    install_url = "https://x.ai/cli"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``grok`` command line.

        grok's ``-p``/``--single`` has no ``--`` escape (``-p --help`` is a parser error), so the prompt
        goes last as one ``--single=PROMPT`` element, which takes any text as the value.

        Args:
            req: The request to run.

        ``-o stream-json`` uses ``--output-format streaming-json`` (JSON lines; see :meth:`parse`).

        Returns:
            The argv list, prompt last.

        Raises:
            UsageError: If the prompt starts with ``/``, which grok runs as a slash command.
        """
        if req.prompt.lstrip().startswith("/"):
            raise UsageError(
                "grok runs a prompt starting with '/' as a slash command (e.g. /compact), even after "
                "leading spaces, and has no escape; start the prompt with other text"
            )
        fmt = "streaming-json" if req.output_format == "stream-json" else "json"
        argv = [self.binary, "--output-format", fmt]
        if req.model:
            argv += ["--model", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        if req.system_prompt is not None:
            argv += ["--system-prompt-override", req.system_prompt]
        return [*argv, *_session_flags(req), *req.extra_args, f"--single={req.prompt}"]

    def parse(self, completed: Completed, req: Request) -> Result:
        """Parse the JSON object printed by ``grok --output-format json`` (or rebuilt from ``streaming-json``).

        Success is ``{"text", "stopReason": "end_turn", "sessionId", "usage", "modelUsage", ...}``.
        Failure is ``{"type": "error", "message"}`` (also on stderr, exit 1), or a result whose
        ``stopReason`` isn't ``end_turn``: ``cancelled`` when grok refused a tool call that needs
        approval (exit **0**), ``max_turn_requests`` for ``--max-turns`` (exit 1). Those carry no
        text; the reason is on stderr.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        obj = _result_object(completed.stdout)
        is_error_obj = isinstance(obj, dict) and obj.get("type") == "error"
        text = obj.get("message" if is_error_obj else "text") if isinstance(obj, dict) else None
        if not isinstance(text, str):  # no JSON result (e.g. a crash): the reason is on stderr
            text = strip_ansi(completed.stderr).strip() or strip_ansi(completed.stdout).strip()
            return self.text_result(completed, req).with_updates(text=text, is_error=True)
        stop = obj.get("stopReason")
        failed = is_error_obj or completed.exit_code != 0 or stop not in (None, "end_turn")
        if failed and not text:
            text = strip_ansi(completed.stderr).strip() or str(stop or "")
        cost = obj.get("total_cost_usd")
        return Result(
            harness_name=self.name,
            model=_model(obj.get("modelUsage")) or req.model,
            text=text,
            exit_code=completed.exit_code,
            is_error=failed,
            duration_ms=completed.duration_ms,
            session_id=obj.get("sessionId"),
            usage=_usage(obj.get("usage")),
            cost_usd=cost if isinstance(cost, int | float) else None,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map a ``grok --output-format streaming-json`` line: text pieces and tool calls.

        A call is reported from ``tool_call`` and its result from the ``tool_call_update`` whose
        status is ``completed`` or ``failed`` (a refused call fails with "User cancelled ...").

        Args:
            line: One stdout line.
            state: Unused.

        Returns:
            The events.
        """
        data = json_line(line)
        kind = data.get("type") if data else None
        if kind == "text":
            return [{"type": "text", "text": data.get("data", "")}]
        if kind == "tool_call":
            return [tool_use(data.get("toolCallId"), data.get("toolName"), data.get("rawInput"))]
        if kind == "tool_call_update" and data.get("status") in ("completed", "failed"):
            blocks = data.get("content") if isinstance(data.get("content"), list) else []
            output = "".join(content_text([b.get("content")]) for b in blocks if isinstance(b, dict))
            return [tool_result(data.get("toolCallId"), data["status"] == "failed", output)]
        return []


def _result_object(stdout: str) -> dict[str, Any] | None:
    """The run's result object, from ``--output-format json`` or ``streaming-json`` output.

    json mode prints one object. streaming-json prints JSON lines: ``text`` pieces, then an ``end``
    object that is the json-mode object without ``text``, or the same ``{"type": "error"}`` object.

    Args:
        stdout: grok's stdout.

    Returns:
        The object (for a stream, ``end`` with the joined text added), or ``None`` if there is none.
    """
    try:
        whole = json.loads(stdout)
    except ValueError:
        whole = None
    if isinstance(whole, dict) and whole.get("type") != "end":
        return whole
    events = jsonl_events(stdout)
    last = next((e for e in reversed(events) if e.get("type") in ("end", "error")), None)
    if last is None or last["type"] == "error":
        return last
    text = "".join(e["data"] for e in events if e.get("type") == "text" and isinstance(e.get("data"), str))
    return {**last, "text": text}


def _usage(raw: Any) -> dict[str, int] | None:
    """Normalise grok's usage; its ``input_tokens`` excludes cache reads and writes, so add them back.

    Args:
        raw: The result's ``usage`` object.

    Returns:
        ``{"input_tokens", "output_tokens"}`` or ``None``.
    """
    if not isinstance(raw, dict):
        return None
    keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {
        "input_tokens": sum(int(raw.get(k) or 0) for k in keys),
        "output_tokens": int(raw.get("output_tokens") or 0),
    }


def _model(model_usage: Any) -> str | None:
    """The model that did most of the work, by tokens, from ``modelUsage``.

    Args:
        model_usage: The result's ``modelUsage`` object (model id → counts).

    Returns:
        The model id, or ``None`` if none is reported.
    """
    if not isinstance(model_usage, dict):
        return None
    sizes = {
        m: int(u.get("inputTokens") or 0) + int(u.get("outputTokens") or 0)
        for m, u in model_usage.items()
        if isinstance(u, dict)
    }
    return max(sizes, key=sizes.__getitem__) if sizes else None


def _session_flags(req: Request) -> list[str]:
    """The harness's flags for ``--resume ID`` / ``--continue`` (none for a new session).

    Args:
        req: The request.

    Returns:
        The flags.
    """
    if req.resume is not None:
        return [f"--resume={req.resume}"]
    return ["--continue"] if req.continue_session else []
