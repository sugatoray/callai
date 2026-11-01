"""What a harness run produced: the raw process outcome and the normalised result."""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Completed:
    """Raw outcome of running a harness process (filled in by the runner).

    Attributes:
        argv: The exact command line that ran.
        exit_code: The harness's exit status.
        stdout: Captured standard output.
        stderr: Captured standard error.
        duration_ms: Wall-clock run time in milliseconds, if measured.
    """

    argv: Sequence[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int | None = None


@dataclass(frozen=True)
class Result:
    """Harness-independent result of one run; ``to_dict()`` is the ``-o json`` schema (DESIGN.md §5).

    Attributes:
        harness_name: Harness name.
        text: The final assistant answer.
        exit_code: The harness's exit status.
        is_error: Whether the run failed, per the harness's own error signal.
        model: Model the harness reports it used, else the requested one.
        duration_ms: Wall-clock run time in milliseconds.
        session_id: Harness session id, if reported.
        usage: ``{"input_tokens": ..., "output_tokens": ...}``; input includes cached tokens.
        cost_usd: Reported cost in US dollars.
        argv: The command line that ran.
        raw_stdout: Unparsed harness stdout (for ``-o raw``; not part of ``to_dict()``).
        raw_stderr: Unparsed harness stderr (not part of ``to_dict()``).
    """

    harness_name: str
    text: str
    exit_code: int
    is_error: bool
    model: str | None = None
    duration_ms: int | None = None
    session_id: str | None = None
    usage: dict[str, int] | None = None
    cost_usd: float | None = None
    argv: tuple[str, ...] = ()
    raw_stdout: str = field(default="", repr=False)
    raw_stderr: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """Normalise ``argv`` to a tuple."""
        object.__setattr__(self, "argv", tuple(self.argv))

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable result, in the stable key order of DESIGN.md §5.

        Returns:
            A new dict; mutating it does not affect this result.
        """
        return {
            "harness_name": self.harness_name,
            "model": self.model,
            "text": self.text,
            "exit_code": self.exit_code,
            "is_error": self.is_error,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "usage": copy.deepcopy(self.usage),
            "cost_usd": self.cost_usd,
            "argv": list(self.argv),
        }

    def with_updates(self, **changes: Any) -> Result:
        """Return a copy with some fields replaced.

        Args:
            **changes: Field names and their new values.

        Returns:
            The updated copy.
        """
        return dataclasses.replace(self, **changes)
