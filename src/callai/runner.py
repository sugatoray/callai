"""Runs a harness command line as a subprocess (DESIGN.md §4, §8).

The harness gets its own process group, so a timeout or Ctrl-C reaches the whole tree it
spawned, and an empty stdin, because the prompt always travels in argv.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import IO

from .adapters.base import strip_ansi
from .errors import HarnessNotFound, HarnessTimeout, Interrupted, UsageError
from .result import Completed

_POSIX = os.name == "posix"
_GRACE_SECONDS = 3
# Harnesses running right now, so a fan-out's Ctrl-C can stop the ones in other threads (stop_all).
_LIVE: set[subprocess.Popen] = set()
_LIVE_LOCK = threading.Lock()


def resolve_binary(binary: str, harness_name: str | None = None, install_url: str | None = None) -> str:
    """Find a harness executable on PATH.

    Args:
        binary: Executable name, e.g. ``"claude"``.
        harness_name: The ``--name`` (harness) that needs it (for the error message).
        install_url: Install docs (for the error message).

    Returns:
        The absolute path of the executable.

    Raises:
        HarnessNotFound: If it is not on PATH.
    """
    path = shutil.which(binary)
    if path is None:
        raise HarnessNotFound(binary, harness_name=harness_name, install_url=install_url)
    return path


def harness_version(path: str, timeout: float = 10) -> str | None:
    """Ask a harness binary for its version (``BINARY --version``).

    The version is the first non-empty line of stdout (else stderr), whatever the exit code:
    hermes 0.19.0 prints its version and exits 1.

    Args:
        path: The executable.
        timeout: Seconds to wait for it.

    Returns:
        The version line, or ``None`` if it printed nothing, failed to start or timed out.
    """
    try:
        proc = subprocess.run(
            [path, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for raw in (proc.stdout, proc.stderr):
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                return strip_ansi(line).strip()
    return None


def _pump(stream: IO[str], sink: list[str], tee: IO[str] | None, on_line: Callable[[str], None] | None = None) -> None:
    """Drain a pipe line by line into ``sink``, optionally copying each line to ``tee`` or ``on_line``.

    Args:
        stream: The harness's stdout or stderr pipe.
        sink: Collected lines.
        tee: Where to echo lines live, or ``None``.
        on_line: Called with each line as it arrives, or ``None``.
    """
    for line in iter(stream.readline, ""):
        sink.append(line)
        if tee is not None:
            tee.write(line)
            tee.flush()
        if on_line is not None:
            on_line(line)
    stream.close()


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    """Send ``sig`` to the harness's whole process group; a group that already exited is fine.

    Args:
        proc: The harness process (leader of its own group).
        sig: Signal to send (POSIX); Windows always kills the process.
    """
    if _POSIX:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, sig)
    else:  # pragma: no cover - Windows
        proc.kill()


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGTERM the harness's process group, then SIGKILL whatever is left after a grace period.

    Args:
        proc: The harness process (leader of its own group).
    """
    _signal_group(proc, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):  # harness ignored SIGTERM: SIGKILL below
        proc.wait(timeout=_GRACE_SECONDS)
    if _POSIX:
        _signal_group(proc, signal.SIGKILL)  # also reaps grandchildren that outlived the leader
    proc.wait()


def stop_all() -> None:
    """Stop every harness still running (Ctrl-C during a fan-out): SIGINT, then kill after a grace period.

    Each harness's own :func:`run` call then returns normally with the exit status it got.
    """
    with _LIVE_LOCK:
        procs = list(_LIVE)
    for proc in procs:
        _signal_group(proc, signal.SIGINT)
    deadline = time.monotonic() + _GRACE_SECONDS
    for proc in procs:
        with contextlib.suppress(subprocess.TimeoutExpired):  # ignored SIGINT: killed below
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    for proc in procs:
        if proc.poll() is None:
            _kill_group(proc)


def run(
    argv: Sequence[str],
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    verbose: bool = False,
    harness_name: str | None = None,
    install_url: str | None = None,
    env: Mapping[str, str] | None = None,
    on_stdout_line: Callable[[str], None] | None = None,
) -> Completed:
    """Run a harness and capture its output.

    Args:
        argv: Command line; ``argv[0]`` is the bare binary name, resolved on PATH.
        cwd: Working directory, or ``None`` for the current one.
        timeout: Seconds before the process group is killed, or ``None`` for no limit.
        verbose: Copy the harness's stderr to ours as it arrives (it is still captured).
        harness_name: The ``--name`` (harness) being run (for error messages).
        install_url: Install docs for the binary (for error messages).
        env: Variables to set for the harness on top of callai's environment (an adapter's ``build_env``).
        on_stdout_line: Called with each stdout line as it arrives (``-o stream-json``), from a reader
            thread; stdout is still captured in full.

    Returns:
        The captured outcome; ``argv`` is reported exactly as given.

    Raises:
        UsageError: If ``cwd`` is not a directory.
        HarnessTimeout: If ``timeout`` elapsed (the process group has been killed).
        Interrupted: On Ctrl-C (SIGINT was forwarded to the process group).
    """
    argv = list(argv)
    if cwd is not None and not os.path.isdir(cwd):
        raise UsageError(f"--cwd {cwd!r} is not a directory")
    executable = resolve_binary(argv[0], harness_name=harness_name, install_url=install_url)
    group_kw = {"start_new_session": True} if _POSIX else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}

    start = time.monotonic()
    proc = subprocess.Popen(
        argv,
        executable=executable,  # keeps argv[0] as the bare name the harness expects
        cwd=cwd,
        env={**os.environ, **env} if env else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **group_kw,
    )
    out: list[str] = []
    err: list[str] = []
    # Decode ourselves with newline="": text=True would translate \r\n to \n, and the output must be
    # the harness's own (hermes marks display lines with \r\n; -o raw must be byte-faithful).
    stdout, stderr = (
        io.TextIOWrapper(s, encoding="utf-8", errors="replace", newline="") for s in (proc.stdout, proc.stderr)
    )
    pumps = [
        threading.Thread(target=_pump, args=(stdout, out, None, on_stdout_line), daemon=True),
        threading.Thread(target=_pump, args=(stderr, err, sys.stderr if verbose else None), daemon=True),
    ]
    for t in pumps:
        t.start()
    with _LIVE_LOCK:
        _LIVE.add(proc)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        raise HarnessTimeout(argv[0], timeout) from None
    except KeyboardInterrupt:
        _signal_group(proc, signal.SIGINT)
        with contextlib.suppress(subprocess.TimeoutExpired):  # harness ignored SIGINT: killed below
            proc.wait(timeout=_GRACE_SECONDS)
        _kill_group(proc)
        raise Interrupted() from None
    finally:
        with _LIVE_LOCK:
            _LIVE.discard(proc)
    for t in pumps:
        t.join()
    return Completed(
        argv=argv,
        exit_code=proc.returncode,
        stdout="".join(out),
        stderr="".join(err),
        duration_ms=int((time.monotonic() - start) * 1000),
    )
