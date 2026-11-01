"""Adapter for Anthropic's Claude Code CLI (``claude -p``)."""

from __future__ import annotations

import json
from typing import Any

from ..request import Request
from ..result import Completed, Result
from .base import Adapter, content_text, json_line, tool_result, tool_use

# callai --permission level -> claude flags (DESIGN.md §7).
_PERMISSION_FLAGS: dict[str, list[str]] = {
    "default": [],
    "read-only": ["--permission-mode", "plan"],
    "auto": ["--permission-mode", "acceptEdits"],
    "bypass": ["--dangerously-skip-permissions"],
}


class ClaudeCode(Adapter):
    """``claude -p --output-format json`` — always asks for JSON so the answer is never scraped from text."""

    name = "claude-code"
    binary = "claude"
    install_url = "https://code.claude.com/docs/en/setup"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``claude`` command line.

        Args:
            req: The request to run.

        ``-o stream-json`` asks for claude's own event stream, which needs ``--verbose`` with ``-p``;
        its last line is the same result object ``--output-format json`` prints.

        Returns:
            The argv list, prompt last after ``--``.
        """
        stream = req.output_format == "stream-json"
        argv = [self.binary, "-p", "--output-format", *(["stream-json", "--verbose"] if stream else ["json"])]
        if req.model:
            argv += ["--model", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        if req.system_prompt is not None:
            argv += ["--system-prompt", req.system_prompt]
        return [*argv, *_session_flags(req), *req.extra_args, "--", req.prompt]

    def parse(self, completed: Completed, req: Request) -> Result:
        """Parse the JSON result object ``claude -p`` prints (alone, or as the last stream-json line).

        Errors come from ``is_error`` or a non-zero exit, never ``subtype`` (claude reports
        ``"subtype": "success"`` with ``"is_error": true``, e.g. for an unknown model).
        Output that is not a JSON object falls back to plain text.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        data = _last_json_object(completed.stdout)
        if data is None:
            return self.text_result(completed, req).with_updates(is_error=True)
        is_error = bool(data.get("is_error")) or completed.exit_code != 0
        text = data.get("result")
        cost = data.get("total_cost_usd")
        return Result(
            harness_name=self.name,
            model=req.model if is_error else (_main_model(data.get("modelUsage")) or req.model),
            text=text if isinstance(text, str) else "",
            exit_code=completed.exit_code,
            is_error=is_error,
            duration_ms=completed.duration_ms,
            session_id=data.get("session_id"),
            usage=_usage(data.get("usage")),
            cost_usd=cost if isinstance(cost, int | float) else None,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map a ``--output-format stream-json`` line: assistant text and tool calls, then tool results.

        claude sends whole messages (no ``--include-partial-messages``), so each text event is one
        complete text block.

        Args:
            line: One stdout line.
            state: Unused.

        Returns:
            The events.
        """
        data = json_line(line)
        message = data.get("message") if data else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            return []
        events = []
        for block in message["content"]:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if data.get("type") == "assistant" and kind == "text":
                events.append({"type": "text", "text": block.get("text", "")})
            elif data.get("type") == "assistant" and kind == "tool_use":
                events.append(tool_use(block.get("id"), block.get("name"), block.get("input")))
            elif data.get("type") == "user" and kind == "tool_result":
                events.append(
                    tool_result(
                        block.get("tool_use_id"), bool(block.get("is_error")), content_text(block.get("content"))
                    )
                )
        return events


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    """Find the result object: the whole output, else the last line that is a JSON object.

    Args:
        stdout: The harness's stdout.

    Returns:
        The parsed object, or ``None`` if there is none.
    """
    for candidate in (stdout, *reversed(stdout.splitlines())):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _usage(raw: Any) -> dict[str, int] | None:
    """Normalise claude's usage: input counts cache reads and writes too (conformance/README.md).

    Args:
        raw: claude's ``usage`` value.

    Returns:
        ``{"input_tokens", "output_tokens"}``, or ``None`` if absent.
    """
    if not isinstance(raw, dict):
        return None
    keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {
        "input_tokens": sum(int(raw.get(k) or 0) for k in keys),
        "output_tokens": int(raw.get("output_tokens") or 0),
    }


def _main_model(model_usage: Any) -> str | None:
    """Pick the model that did the work from ``modelUsage`` (claude also lists side-call models).

    Args:
        model_usage: claude's ``modelUsage`` mapping of model id to stats.

    Returns:
        The model with the highest cost (then output tokens), or ``None``.
    """
    if not isinstance(model_usage, dict) or not model_usage:
        return None

    def weight(item: tuple[str, Any]) -> tuple[float, float]:
        """Sort key: (cost, output tokens).

        Args:
            item: A ``(model id, stats)`` pair.

        Returns:
            The key.
        """
        stats = item[1] if isinstance(item[1], dict) else {}
        return (float(stats.get("costUSD") or 0), float(stats.get("outputTokens") or 0))

    return max(model_usage.items(), key=weight)[0]


def _session_flags(req: Request) -> list[str]:
    """The harness's flags for ``--resume ID`` / ``--continue`` (none for a new session).

    Args:
        req: The request.

    Returns:
        The flags.
    """
    if req.resume is not None:
        return ["--resume", req.resume]
    return ["--continue"] if req.continue_session else []
