"""The interface every harness adapter implements (DESIGN.md §4)."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from ..request import Request
from ..result import Completed, Result

# CSI sequences (colours, cursor moves) and OSC sequences (titles, hyperlinks).
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from terminal output.

    Args:
        text: Text that may contain escape sequences.

    Returns:
        The text without them.
    """
    return _ANSI_RE.sub("", text)


def jsonl_events(stdout: str) -> list[dict[str, Any]]:
    """Parse JSON-lines output, skipping lines that are not JSON objects (banners, warnings).

    Args:
        stdout: The harness's stdout.

    Returns:
        The event objects, in order.
    """
    return [data for line in stdout.splitlines() if (data := json_line(line)) is not None]


def json_line(line: str) -> dict[str, Any] | None:
    """Parse one line of JSON-lines output.

    Args:
        line: One stdout line (a trailing newline is fine).

    Returns:
        The object, or ``None`` if the line isn't a JSON object (a banner, a warning).
    """
    try:
        data = json.loads(line)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def content_text(blocks: Any) -> str:
    """Join the text of a content value: a string, or a list of ``{"type": "text", "text"}`` blocks.

    Args:
        blocks: A tool result's content.

    Returns:
        The text; non-text blocks are skipped.
    """
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    return "".join(b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str))


def tool_use(call_id: Any, name: Any, tool_input: Any) -> dict[str, Any]:
    """A normalised ``tool_use`` event (DESIGN.md §5).

    Args:
        call_id: The harness's id for the call.
        name: The harness's own tool name.
        tool_input: The tool's arguments.

    Returns:
        The event.
    """
    return {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}


def tool_result(call_id: Any, is_error: bool, output: str) -> dict[str, Any]:
    """A normalised ``tool_result`` event (DESIGN.md §5).

    Args:
        call_id: The id of the ``tool_use`` it answers.
        is_error: Whether the tool failed or was refused.
        output: What the tool returned, as text.

    Returns:
        The event.
    """
    return {"type": "tool_result", "id": call_id, "is_error": is_error, "output": output}


class Adapter(ABC):
    """Translates a :class:`Request` into one harness's command line and its output back into a :class:`Result`.

    Both methods are pure (no I/O), so adapters are tested without the harness installed.

    Attributes:
        name: Harness name used with ``--name`` (one of ``callai.adapters.HARNESS_NAMES``).
        binary: Executable looked up on PATH.
        install_url: Where to point users when the binary is missing.
    """

    name: str
    binary: str
    install_url: str

    @abstractmethod
    def build_argv(self, req: Request) -> list[str]:
        """Build the exact harness command line, with the prompt last after ``--``.

        Args:
            req: The request to run.

        Returns:
            The argv list; ``argv[0]`` is the bare binary name.
        """

    @abstractmethod
    def parse(self, completed: Completed, req: Request) -> Result:
        """Turn the harness's raw output into a normalised result.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """

    def build_env(self, req: Request) -> dict[str, str]:
        """Environment variables the harness needs for this request, set on top of callai's own.

        For settings a harness takes only from its environment (hermes's extra system prompt).
        Pure, like :meth:`build_argv`.

        Args:
            req: The request to run.

        Returns:
            Variables to set; empty (the default) leaves the inherited environment unchanged.
        """
        return {}

    def stream_events(self, line: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Map one stdout line of a running harness to normalised ``-o stream-json`` events.

        Called for every stdout line in order, as it arrives, with one ``state`` dict per run for
        adapters that need to remember earlier lines. Returns ``text``, ``tool_use`` and
        ``tool_result`` events (DESIGN.md §5); the CLI writes ``start`` and ``result`` itself.
        Pure apart from ``state``. The default, for harnesses without an event stream, returns none.

        Args:
            line: One stdout line, newline included.
            state: Scratch space shared by the calls of one run.

        Returns:
            The events, possibly none.
        """
        return []

    def text_result(self, completed: Completed, req: Request) -> Result:
        """Fallback parser for harnesses without structured output: cleaned stdout is the answer.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            A result whose text is stdout without ANSI codes or surrounding whitespace.
        """
        return Result(
            harness_name=self.name,
            model=req.model,
            text=strip_ansi(completed.stdout).strip(),
            exit_code=completed.exit_code,
            is_error=completed.exit_code != 0,
            duration_ms=completed.duration_ms,
            argv=completed.argv,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )
