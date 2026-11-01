"""Exceptions raised by callai, each carrying the process exit code it maps to (DESIGN.md §8)."""


class CallaiError(Exception):
    """Base class for errors callai reports to the user instead of a traceback."""

    exit_code = 1


class UsageError(CallaiError):
    """Invalid command line, configuration or request (exit code 2)."""

    exit_code = 2


class HarnessNotFound(CallaiError):
    """The harness executable is not on PATH (exit code 127, like a shell)."""

    exit_code = 127

    def __init__(self, binary: str, harness_name: str | None = None, install_url: str | None = None) -> None:
        """Build the message.

        Args:
            binary: Executable that was looked up.
            harness_name: The ``--name`` (harness) that needs it, if known.
            install_url: Where to get it, if known.
        """
        msg = f"harness binary {binary!r} not found on PATH"
        if harness_name:
            msg += f" (needed for --name {harness_name})"
        if install_url:
            msg += f"; install it: {install_url}"
        super().__init__(msg)


class NoHarnessInstalled(CallaiError):
    """``-n all`` found none of the supported harnesses on PATH (exit code 127)."""

    exit_code = 127


class HarnessTimeout(CallaiError):
    """The harness ran longer than ``--timeout`` and was killed (exit code 124, like GNU timeout)."""

    exit_code = 124

    def __init__(self, binary: str, timeout: float) -> None:
        """Build the message.

        Args:
            binary: Executable that was killed.
            timeout: The limit, in seconds.
        """
        super().__init__(f"{binary!r} timed out after {timeout:g}s and was killed")


class Interrupted(CallaiError):
    """The user interrupted the run (exit code 130, like SIGINT in a shell)."""

    exit_code = 130

    def __init__(self) -> None:
        """Build the message."""
        super().__init__("interrupted")
