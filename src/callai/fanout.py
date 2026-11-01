"""Fan-out: one prompt through several harnesses (DESIGN.md §3).

``-n a/b/c`` runs them at the same time, ``-n a,b,c`` one after another, ``-n all`` every installed
harness at the same time. Results come back in the order given, whatever order the runs finish in.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import runner
from .adapters import HARNESS_NAMES, Adapter
from .api import EventHandler, run_harness
from .errors import CallaiError, Interrupted, UsageError
from .request import Request
from .result import Completed, Result

SINGLE, PARALLEL, SEQUENTIAL, ALL = "single", "parallel", "sequential", "all"


def split_harness_names(value: str) -> tuple[list[str], str]:
    """Split a ``-n`` value into harness names and how to run them.

    Args:
        value: ``"codex"``, ``"a/b/c"`` (parallel), ``"a,b,c"`` (one after another) or ``"all"``.

    Returns:
        ``(names, mode)``; mode is ``SINGLE``, ``PARALLEL``, ``SEQUENTIAL`` or ``ALL``. Names aren't
        checked against the registry here.

    Raises:
        UsageError: For mixed separators, empty or repeated names, or ``all`` inside a list.
    """
    if "/" in value and "," in value:
        raise UsageError(f"-n {value}: use '/' (parallel) or ',' (one after another), not both")
    sep = "/" if "/" in value else ","
    names = [n.strip() for n in value.split(sep)]
    if any(not n for n in names):
        raise UsageError(f"-n {value}: empty harness name")
    if len(names) == 1:
        return (list(HARNESS_NAMES), ALL) if names[0] == "all" else (names, SINGLE)
    if "all" in names:
        raise UsageError(f"-n {value}: 'all' can't be combined with other harnesses")
    for name in names:
        if names.count(name) > 1:
            raise UsageError(f"-n {value}: {name} is listed twice")
    return names, PARALLEL if sep == "/" else SEQUENTIAL


@dataclass(frozen=True)
class Job:
    """One harness's part of a fan-out.

    Attributes:
        adapter: The harness's adapter.
        req: Its request.
        argv: Its command line (binary already resolved from the config).
    """

    adapter: Adapter
    req: Request
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Outcome:
    """How one job ended.

    Attributes:
        result: The normalised result (a timeout is a failed result, exit 124).
        completed: The raw process outcome, or ``None`` if the run didn't finish.
    """

    result: Result
    completed: Completed | None


def run_jobs(
    jobs: Sequence[Job],
    *,
    concurrent: bool,
    verbose: bool = False,
    event_handler: Callable[[Job], EventHandler | None] = lambda job: None,
) -> list[Outcome]:
    """Run every job, at the same time or one after another; one failure doesn't stop the rest.

    Args:
        jobs: The jobs, in output order.
        concurrent: Run them all at once (one thread each) instead of in order.
        verbose: Copy each harness's stderr to ours as it arrives.
        event_handler: Gives each job its ``-o stream-json`` event callback, or ``None``.

    Returns:
        One outcome per job, in the same order.

    Raises:
        Interrupted: On Ctrl-C, after every running harness was stopped.
    """
    if not concurrent:
        return [_run_one(job, verbose, event_handler(job)) for job in jobs]
    outcomes: list[Outcome | None] = [None] * len(jobs)
    errors: list[BaseException] = []

    def work(i: int) -> None:
        """Run job ``i`` in its thread, keeping its outcome or unexpected error.

        Args:
            i: The job's index.
        """
        try:
            outcomes[i] = _run_one(jobs[i], verbose, event_handler(jobs[i]))
        except BaseException as exc:  # noqa: BLE001 - re-raised in the main thread below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(len(jobs))]
    for t in threads:
        t.start()
    try:
        for t in threads:
            while t.is_alive():
                t.join(0.1)  # short joins, so Ctrl-C reaches this thread
    except KeyboardInterrupt:
        runner.stop_all()
        for t in threads:
            t.join()
        raise Interrupted() from None
    if errors:
        raise errors[0]
    return [o for o in outcomes if o is not None]


def _run_one(job: Job, verbose: bool, on_event: EventHandler | None) -> Outcome:
    """Run one job; a callai error (e.g. a timeout) becomes a failed result instead of stopping the others.

    Args:
        job: The job.
        verbose: Copy the harness's stderr to ours as it arrives.
        on_event: ``-o stream-json`` event callback, or ``None``.

    Returns:
        Its outcome.

    Raises:
        Interrupted: On Ctrl-C while it ran (one after another), so the rest don't start.
    """
    try:
        completed = run_harness(job.adapter, job.req, job.argv, verbose=verbose, on_event=on_event)
    except Interrupted:
        raise
    except CallaiError as exc:
        result = Result(
            harness_name=job.adapter.name,
            model=job.req.model,
            text=str(exc),
            exit_code=exc.exit_code,
            is_error=True,
            argv=job.argv,
        )
        completed = None
    else:
        result = job.adapter.parse(completed, job.req)
    if on_event is not None:
        on_event({"type": "result", **result.to_dict()})
    return Outcome(result, completed)
