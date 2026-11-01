"""Adapter for OpenAI's Codex CLI (``codex exec``)."""

from __future__ import annotations

import json
from typing import Any

from ..request import Request
from ..result import Completed, Result
from .base import Adapter, json_line, jsonl_events, tool_result, tool_use

# callai --permission level -> codex flags (DESIGN.md §7; verified against codex-cli 0.166.0 --help).
_PERMISSION_FLAGS: dict[str, list[str]] = {
    "default": [],
    "read-only": ["--sandbox", "read-only"],
    "auto": ["--sandbox", "workspace-write"],
    "bypass": ["--dangerously-bypass-approvals-and-sandbox"],
}


# Item types that are not tool calls; every other item type (command_execution, file_change,
# mcp_tool_call, web_search, ...) is reported as a tool call named after its type.
_NOT_TOOLS = {"agent_message", "reasoning", "error", "todo_list"}
# Item fields that describe the call's outcome rather than its input.
_OUTCOME_KEYS = {"id", "type", "status", "aggregated_output", "exit_code", "result", "error"}


def toml_string(text: str) -> str:
    """Encode text as a TOML basic string (for codex ``-c key=value`` overrides).

    JSON string escapes are valid TOML, except that TOML also forbids a raw DEL character.

    Args:
        text: Any text.

    Returns:
        The quoted TOML string.
    """
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


class Codex(Adapter):
    """``codex exec --json`` — parses the JSONL event stream rather than scraping text."""

    name = "codex"
    binary = "codex"
    install_url = "https://developers.openai.com/codex/cli"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``codex exec`` command line.

        ``--skip-git-repo-check`` is always added, so callai works in any directory like the other tools.

        Args:
            req: The request to run.

        Returns:
            The argv list, prompt last after ``--`` (so it can't be taken for a subcommand like ``review``).
        """
        argv = [self.binary, "exec", "--json", "--skip-git-repo-check"]
        if req.model:
            argv += ["--model", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        if req.system_prompt is not None:
            argv += ["-c", f"developer_instructions={toml_string(req.system_prompt)}"]
        # `resume` is a subcommand of exec that rejects --sandbox, so exec's own options (and any extra
        # args) go before it; only the session id or --last follow it.
        if req.resume is not None:
            resume = ["resume", req.resume]
        else:
            resume = ["resume", "--last"] if req.continue_session else []
        return [*argv, *req.extra_args, *resume, "--", req.prompt]

    def parse(self, completed: Completed, req: Request) -> Result:
        """Parse the JSONL events of ``codex exec --json``.

        The answer is the last ``agent_message`` item. Failure comes only from ``turn.failed`` or a
        non-zero exit: ``error`` events and ``item.type == "error"`` items are non-fatal warnings
        (reconnects, missing model metadata). codex does not report the model it used.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        events = jsonl_events(completed.stdout)
        if not events:
            return self.text_result(completed, req).with_updates(is_error=True)
        text, session_id, usage, failure = "", None, None, None
        for ev in events:
            kind = ev.get("type")
            if kind == "thread.started":
                session_id = ev.get("thread_id")
            elif kind == "item.completed":
                item = ev.get("item") or {}
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    text = item["text"]
            elif kind == "turn.completed" and isinstance(ev.get("usage"), dict):
                usage = {
                    # OpenAI semantics: input_tokens already includes cached_input_tokens.
                    "input_tokens": int(ev["usage"].get("input_tokens") or 0),
                    "output_tokens": int(ev["usage"].get("output_tokens") or 0),
                }
            elif kind == "turn.failed":
                failure = (ev.get("error") or {}).get("message") or text
        return Result(
            harness_name=self.name,
            model=req.model,
            text=failure if failure is not None else text,
            exit_code=completed.exit_code,
            is_error=failure is not None or completed.exit_code != 0,
            duration_ms=completed.duration_ms,
            session_id=session_id,
            usage=usage,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map a ``codex exec --json`` line: ``agent_message`` items are text, other items tool calls.

        A tool call is reported when its item starts (``item.started``) and its result when the item
        completes. Items that only arrive completed get both then; ``state`` remembers which calls
        were already reported. Verified for ``command_execution``; other item types follow the same
        event schema (their fields, minus outcome fields, become the input).

        Args:
            line: One stdout line.
            state: Remembers reported call ids (``"started"``).

        Returns:
            The events.
        """
        data = json_line(line)
        item = data.get("item") if data else None
        if not isinstance(item, dict):
            return []
        kind, item_id = item.get("type"), item.get("id")
        if data.get("type") == "item.completed" and kind == "agent_message":
            return [{"type": "text", "text": item.get("text", "")}]
        if kind in _NOT_TOOLS or data.get("type") not in ("item.started", "item.completed"):
            return []
        started = state.setdefault("started", set())
        events = []
        if item_id not in started:
            started.add(item_id)
            events.append(tool_use(item_id, kind, {k: v for k, v in item.items() if k not in _OUTCOME_KEYS}))
        if data["type"] == "item.completed":
            failed = item.get("status") == "failed" or item.get("exit_code") not in (None, 0) or bool(item.get("error"))
            output = item.get("aggregated_output")
            events.append(tool_result(item_id, failed, output if isinstance(output, str) else ""))
        return events
