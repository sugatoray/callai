"""The harness-independent request every adapter turns into a command line."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import UsageError

OUTPUT_FORMATS = ("text", "json", "stream-json", "raw")
PERMISSIONS = ("default", "read-only", "auto", "bypass")


@dataclass(frozen=True)
class Request:
    """One non-interactive prompt to run through a harness.

    Attributes:
        harness_name: Harness name, e.g. ``"claude-code"`` (validated by the adapter registry).
        prompt: Final prompt text, after stdin has been merged in.
        model: Model passed to the harness verbatim, or ``None`` for its default.
        output_format: How callai prints the result (not how the harness is invoked).
        cwd: Working directory for the harness, or ``None`` for the current directory.
        timeout: Seconds before the harness is killed, or ``None`` for no limit.
        permission: Harness-neutral permission level (DESIGN.md §7).
        system_prompt: Optional system prompt, where the harness supports one.
        extra_args: Arguments passed through to the harness unchanged.
        resume: Session id to continue (the ``session_id`` a previous run reported), or ``None``.
        continue_session: Continue the harness's most recent session instead of starting a new one.
    """

    harness_name: str
    prompt: str
    model: str | None = None
    output_format: str = "text"
    cwd: str | None = None
    timeout: float | None = None
    permission: str = "default"
    system_prompt: str | None = None
    extra_args: tuple[str, ...] = ()
    resume: str | None = None
    continue_session: bool = False

    def __post_init__(self) -> None:
        """Validate fields and normalise ``extra_args`` to a tuple.

        Raises:
            UsageError: If any field has an invalid value.
        """
        if not isinstance(self.prompt, str):
            raise UsageError("prompt must be a string")
        if self.output_format not in OUTPUT_FORMATS:
            raise UsageError(f"invalid output format {self.output_format!r}; choose from {', '.join(OUTPUT_FORMATS)}")
        if self.permission not in PERMISSIONS:
            raise UsageError(f"invalid permission {self.permission!r}; choose from {', '.join(PERMISSIONS)}")
        if self.timeout is not None and (
            isinstance(self.timeout, bool) or not isinstance(self.timeout, int | float) or self.timeout <= 0
        ):
            raise UsageError(f"timeout must be a positive number of seconds, got {self.timeout!r}")
        if isinstance(self.extra_args, str) or not all(isinstance(a, str) for a in self.extra_args):
            raise UsageError("extra_args must be a sequence of strings")
        object.__setattr__(self, "extra_args", tuple(self.extra_args))
        if self.resume is not None:
            if not isinstance(self.resume, str):
                raise UsageError("resume must be a session id string")
            if not self.resume:
                raise UsageError("--resume: empty session id")
            if self.resume.startswith("-"):
                raise UsageError("--resume: a session id can't start with '-' (the harness would read it as an option)")
            if self.continue_session:
                raise UsageError("use --resume or --continue, not both")
