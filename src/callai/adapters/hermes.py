"""Adapter for Nous Research's Hermes Agent (``hermes chat -Q --query=PROMPT``)."""

from __future__ import annotations

import re

from ..errors import UsageError
from ..request import Request
from ..result import Completed, Result
from .base import Adapter, strip_ansi

# Verified against hermes-agent 0.19.0 with scripted tool calls from the stub. hermes runs file writes
# and ordinary shell commands without asking; only "dangerous" commands need approval, which a
# non-interactive run denies on timeout. -t takes toolset names, and no toolset is read-only.
_PERMISSION_FLAGS: dict[str, list[str]] = {
    "default": [],
    "auto": ["-t", "file"],  # read_file, write_file, patch, search_files: edits yes, shell no
    "bypass": ["--yolo"],
}
_SESSION_RE = re.compile(r"^session_id: (\S+)$", re.MULTILINE)


class Hermes(Adapter):
    """``hermes chat -Q`` — the answer is stdout minus hermes's display lines."""

    name = "hermes"
    binary = "hermes"
    install_url = "https://hermes-agent.nousresearch.com/docs/"

    def build_argv(self, req: Request) -> list[str]:
        """Build the ``hermes`` command line.

        Not ``hermes -z``: one-shot mode auto-approves every tool call. ``--source tool`` keeps callai
        runs out of the user's session list. The prompt goes last as one ``--query=PROMPT`` element,
        so a prompt starting with ``-`` can't be read as an option.

        Args:
            req: The request to run.

        Returns:
            The argv list, prompt last.

        Raises:
            UsageError: For ``--permission read-only`` (no read-only toolset) or ``--continue`` (hermes
                would continue the user's interactive session, not callai's last run).
        """
        if req.permission == "read-only":
            raise UsageError(
                "--permission read-only: hermes has no read-only toolset (its `file` toolset can write); "
                "use the default or --permission auto"
            )
        if req.continue_session:
            raise UsageError(
                "--continue: hermes only continues its most recent interactive session, not callai's runs; "
                "use --resume with the session_id callai reported"
            )
        argv = [self.binary, "chat", "-Q", "--source", "tool"]
        if req.model:
            argv += ["-m", req.model]
        argv += _PERMISSION_FLAGS[req.permission]
        return [*argv, *_session_flags(req), *req.extra_args, f"--query={req.prompt}"]

    def build_env(self, req: Request) -> dict[str, str]:
        """Pass ``--system-prompt`` as ``HERMES_EPHEMERAL_SYSTEM_PROMPT``.

        hermes has no flag for it; it reads this variable (before ``agent.system_prompt`` in its
        config) and never saves it to the session history.

        Args:
            req: The request to run.

        Returns:
            The variable when a system prompt is given, else nothing (an inherited one is kept).
        """
        return {} if req.system_prompt is None else {"HERMES_EPHEMERAL_SYSTEM_PROMPT": req.system_prompt}

    def parse(self, completed: Completed, req: Request) -> Result:
        r"""Parse ``hermes chat -Q`` output.

        hermes prints the answer with a plain ``print`` (``\n`` line ends) after the run. Its display
        lines (tool diff previews, warnings, "denying command") go through prompt_toolkit and end in
        ``\r\n``, so those are dropped. The session id is on stderr. Failure is a non-zero exit, or
        no answer at all, whose reason ("Error: ...") is then on stderr.

        Args:
            completed: Raw process outcome.
            req: The request that produced it.

        Returns:
            The normalised result.
        """
        answer = "".join(line for line in completed.stdout.splitlines(keepends=True) if not line.endswith("\r\n"))
        text = strip_ansi(answer).strip()
        failed = completed.exit_code != 0 or not text
        if not text:
            text = strip_ansi(_SESSION_RE.sub("", completed.stderr)).strip()
        match = _SESSION_RE.search(completed.stderr)
        return self.text_result(completed, req).with_updates(
            text=text, is_error=failed, session_id=match.group(1) if match else None
        )


def _session_flags(req: Request) -> list[str]:
    """The harness's flag for ``--resume ID`` (``--continue`` is refused in ``build_argv``).

    Args:
        req: The request.

    Returns:
        The flags.
    """
    return ["--resume", req.resume] if req.resume is not None else []
