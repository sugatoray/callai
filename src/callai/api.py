"""The Python API: run a prompt through a harness from code (DESIGN.md §4).

``run()`` returns the same :class:`Result` as ``-o json``; ``on_event`` gets the same events as
``-o stream-json``. Unlike the CLI it reads no ``CALLAI_*`` variables and no config file: every
setting is an argument, so a call means the same thing on every machine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from . import runner
from .adapters import Adapter, get_adapter
from .request import Request
from .result import Completed, Result

EventHandler = Callable[[dict[str, Any]], None]


def run(
    harness_name: str,
    prompt: str,
    *,
    model: str | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
    permission: str = "default",
    system_prompt: str | None = None,
    extra_args: Sequence[str] = (),
    resume: str | None = None,
    continue_session: bool = False,
    binary: str | None = None,
    on_event: EventHandler | None = None,
) -> Result:
    """Run one prompt through a harness and return its normalised result.

    A harness that runs but fails (bad model, refused tool, non-zero exit) is a result with
    ``is_error=True``, not an exception. Exceptions are for runs that couldn't happen or finish:
    :class:`~callai.errors.UsageError` (bad arguments, or an option the harness can't honour),
    :class:`~callai.errors.HarnessNotFound`, :class:`~callai.errors.HarnessTimeout` and
    :class:`~callai.errors.Interrupted`, all subclasses of :class:`~callai.errors.CallaiError`.

    Args:
        harness_name: One of ``callai.adapters.HARNESS_NAMES``, e.g. ``"codex"``.
        prompt: The prompt.
        model: Model passed to the harness verbatim (no aliases), or ``None`` for its default.
        cwd: Working directory for the harness, or ``None`` for the current one.
        timeout: Seconds before the harness is killed, or ``None`` for no limit.
        permission: ``"default"``, ``"read-only"``, ``"auto"`` or ``"bypass"`` (DESIGN.md §7).
        system_prompt: Extra system prompt, where the harness supports one.
        extra_args: Arguments passed to the harness unchanged.
        resume: Session id to continue (a previous result's ``session_id``).
        continue_session: Continue the harness's most recent session.
        binary: Executable to run instead of the harness's usual one on PATH.
        on_event: Called with each event as it happens: ``start``, then ``text``/``tool_use``/
            ``tool_result``, then ``result`` (DESIGN.md §5). Runs the harness in its streaming mode.

    Returns:
        The normalised result.
    """
    adapter = get_adapter(harness_name)
    req = Request(
        harness_name=harness_name,
        prompt=prompt,
        model=model,
        output_format="json" if on_event is None else "stream-json",
        cwd=cwd,
        timeout=timeout,
        permission=permission,
        system_prompt=system_prompt,
        extra_args=tuple(extra_args),
        resume=resume,
        continue_session=continue_session,
    )
    argv = adapter.build_argv(req)
    if binary is not None:
        argv = [binary, *argv[1:]]
    result = adapter.parse(run_harness(adapter, req, argv, on_event=on_event), req)
    if on_event is not None:
        on_event({"type": "result", **result.to_dict()})
    return result


def run_harness(
    adapter: Adapter,
    req: Request,
    argv: Sequence[str],
    *,
    verbose: bool = False,
    on_event: EventHandler | None = None,
) -> Completed:
    """Run a built command line, turning stdout into events as it arrives when asked to.

    Shared by :func:`run` and the CLI. With ``on_event``, the binary is looked up first (a missing
    one raises before any event), then ``start`` and each line's events are sent; ``result`` is the
    caller's, since only it parses the output.

    Args:
        adapter: The harness's adapter.
        req: The request (for the environment, working directory and timeout).
        argv: The command line; ``argv[0]`` is the executable.
        verbose: Copy the harness's stderr to ours as it arrives.
        on_event: Event callback, or ``None``.

    Returns:
        The raw outcome.
    """
    argv = list(argv)
    on_line = None
    if on_event is not None:
        runner.resolve_binary(argv[0], harness_name=adapter.name, install_url=adapter.install_url)
        on_event({"type": "start", "harness_name": adapter.name, "model": req.model, "argv": argv})
        state: dict[str, Any] = {}

        def on_line(line: str) -> None:
            """Send the events for one harness stdout line.

            Args:
                line: The line.
            """
            for event in adapter.stream_events(line, state):
                on_event(event)

    return runner.run(
        argv,
        cwd=req.cwd,
        timeout=req.timeout,
        verbose=verbose,
        harness_name=adapter.name,
        install_url=adapter.install_url,
        env=adapter.build_env(req),
        on_stdout_line=on_line,
    )
