"""Command-line interface: ``callai -n HARNESS_NAME -p PROMPT [options] [-- HARNESS_ARGS...]`` (DESIGN.md §3)."""

from __future__ import annotations

import argparse
import json
import math
import os
import select
import shlex
import shutil
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import IO, Any

from . import runner
from .adapters import HARNESS_NAMES, Adapter, get_adapter
from .api import run_harness
from .config import Config, load_config, resolve_model
from .errors import CallaiError, NoHarnessInstalled, UsageError
from .fanout import ALL, PARALLEL, SINGLE, Job, Outcome, run_jobs, split_harness_names
from .request import PERMISSIONS, Request
from .result import Completed

OUTPUT_CHOICES = ("text", "json", "stream-json", "raw")
_WRITE_LOCK = threading.Lock()
# Seconds to wait for the first stdin data when -p TEXT is given (claude -p waits 3s too).
DEFAULT_STDIN_WAIT = 3.0


def build_parser() -> argparse.ArgumentParser:
    """Build the ``callai`` argument parser.

    Returns:
        The configured parser.
    """
    from . import __version__

    p = argparse.ArgumentParser(
        prog="callai",
        description="Run a prompt non-interactively through a coding-agent harness.",
        epilog="Arguments after a bare `--` are passed to the harness unchanged.",
    )
    p.add_argument(
        "-n",
        "--name",
        metavar="HARNESS_NAME",
        help=f"harness to run: {', '.join(HARNESS_NAMES)} (default: $CALLAI_HARNESS_NAME)",
    )
    p.add_argument(
        "-p",
        "-c",
        "--prompt",
        "--command",
        dest="prompt",
        metavar="PROMPT",
        help="the prompt; '-' reads it from stdin. Piped stdin is appended after a blank line.",
    )
    p.add_argument("-m", "--model", help="model, passed to the harness verbatim")
    p.add_argument("-o", "--output-format", choices=OUTPUT_CHOICES, default="text", help="default: text")
    p.add_argument("-C", "--cwd", help="working directory for the harness")
    p.add_argument("--timeout", type=float, metavar="SECS", help="kill the harness after SECS (exit 124)")
    p.add_argument("--permission", choices=PERMISSIONS, default="default", help="default: the harness's own")
    p.add_argument("--system-prompt", help="system prompt, where the harness supports one")
    p.add_argument("--resume", metavar="SESSION_ID", help="continue this session (a session_id callai reported)")
    p.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="continue the harness's most recent session (no -c: that's --command)",
    )
    p.add_argument("--dry-run", action="store_true", help="print the harness command line and exit")
    p.add_argument("-v", "--verbose", action="store_true", help="stream the harness's stderr live")
    p.add_argument(
        "--list-harnesses",
        action="store_true",
        help="list every harness: its binary, where it is on PATH, and its version (-o json for JSON)",
    )
    p.add_argument("--version", action="version", version=f"callai {__version__}")
    return p


def split_passthrough(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split callai's own arguments from harness passthrough arguments at the first bare ``--``.

    Args:
        argv: Arguments excluding the program name.

    Returns:
        ``(own, passthrough)``.
    """
    argv = list(argv)
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, []


def stdin_wait(environ: Mapping[str, str]) -> float:
    """Seconds to wait for stdin data when ``-p TEXT`` is given, from ``CALLAI_STDIN_WAIT``.

    Args:
        environ: Environment to read ``CALLAI_STDIN_WAIT`` from.

    Returns:
        The wait; :data:`DEFAULT_STDIN_WAIT` if unset or empty.

    Raises:
        UsageError: If the value isn't a finite number of seconds >= 0.
    """
    raw = environ.get("CALLAI_STDIN_WAIT") or ""
    if not raw:
        return DEFAULT_STDIN_WAIT
    try:
        wait = float(raw)
    except ValueError:
        wait = -1.0
    if not math.isfinite(wait) or wait < 0:
        raise UsageError(f"CALLAI_STDIN_WAIT must be a number of seconds >= 0, got {raw!r}")
    return wait


def _stdin_ready(stream: IO[str], wait: float) -> bool:
    """Whether ``stream`` has data or EOF within ``wait`` seconds.

    Streams without a real file descriptor, and platforms where ``select`` can't watch pipes
    (Windows), count as ready, so they are read as before.

    Args:
        stream: A non-TTY stdin.
        wait: Seconds to wait.

    Returns:
        ``False`` only if nothing arrived in time.
    """
    if os.name == "nt":
        return True
    try:
        fd = stream.fileno()
        ready, _, _ = select.select([fd], [], [], wait)
    except (AttributeError, OSError, ValueError):  # io.UnsupportedOperation is both OSError and ValueError
        return True
    return bool(ready)


def read_stdin(stream: IO[str] | None, wait: float | None = None) -> str:
    """Read piped stdin; a terminal or unreadable stdin counts as no input.

    Args:
        stream: Usually ``sys.stdin``.
        wait: If given, seconds to wait for the first data (or EOF) before giving up with a
            warning, so a pipe that stays open and silent doesn't block. ``None`` waits for EOF.

    Returns:
        The text with trailing newlines stripped, or ``""``.
    """
    if stream is None or stream.isatty():
        return ""
    if wait is not None and not _stdin_ready(stream, wait):
        sys.stderr.write(
            f"callai: warning: no stdin data received in {wait:g}s, proceeding without it. "
            "Redirect stdin (< /dev/null) to skip the wait, or set CALLAI_STDIN_WAIT to wait longer.\n"
        )
        return ""
    try:
        return stream.read().rstrip("\r\n")
    except (OSError, ValueError):
        return ""


def resolve_prompt(prompt: str | None, stdin_text: str) -> str:
    """Combine ``-p`` and piped stdin like ``claude -p`` (DESIGN.md §3).

    Args:
        prompt: The ``-p`` value, ``"-"`` for stdin, or ``None``.
        stdin_text: Piped stdin, ``""`` if none.

    Returns:
        The final prompt.

    Raises:
        UsageError: If there is no prompt at all.
    """
    if prompt == "-":
        prompt = stdin_text
    elif prompt and stdin_text:
        prompt = f"{prompt}\n\n{stdin_text}"
    elif not prompt:
        prompt = stdin_text
    if not prompt:
        raise UsageError("a prompt is required: use -p PROMPT or pipe it on stdin")
    return prompt


def resolve_harness_name(ns: argparse.Namespace, environ: Mapping[str, str], config: Config | None = None) -> str:
    """The harness name from ``-n``, then ``CALLAI_HARNESS_NAME``, then the config's ``default_harness``.

    Args:
        ns: Parsed callai arguments.
        environ: Environment for the ``CALLAI_HARNESS_NAME`` default.
        config: User config, if loaded.

    Returns:
        The harness name (not yet checked against the registry).

    Raises:
        UsageError: If none of them is set.
    """
    config = config or Config()
    harness_name = ns.name or environ.get("CALLAI_HARNESS_NAME") or config.default_harness
    if harness_name is None:
        if environ.get("CALLAI_TOOL"):
            raise UsageError("CALLAI_TOOL was renamed to CALLAI_HARNESS_NAME; set that instead")
        raise UsageError(
            "no harness given: use -n/--name, set CALLAI_HARNESS_NAME, or set default_harness in the config file"
        )
    return harness_name


def env_timeout(environ: Mapping[str, str]) -> float | None:
    """``CALLAI_TIMEOUT`` in seconds, or ``None`` if unset or empty.

    Args:
        environ: Environment to read it from.

    Returns:
        The timeout.

    Raises:
        UsageError: If it isn't a finite number of seconds > 0.
    """
    raw = environ.get("CALLAI_TIMEOUT") or ""
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not math.isfinite(value) or value <= 0:
        raise UsageError(f"CALLAI_TIMEOUT must be a positive number of seconds, got {raw!r}")
    return value


def harness_binary(adapter: Adapter, config: Config) -> str:
    """The executable to run: ``[harnesses.<name>] binary`` from the config, else the adapter's own.

    Args:
        adapter: The harness's adapter.
        config: User config.

    Returns:
        The binary name or path (``~`` expanded).
    """
    configured = config.harnesses.get(adapter.name)
    if configured and configured.binary:
        return os.path.expanduser(configured.binary)
    return adapter.binary


def _request(
    ns: argparse.Namespace,
    extra: Sequence[str],
    harness_name: str,
    prompt: str,
    environ: Mapping[str, str],
    config: Config,
) -> Request:
    """Build a :class:`Request`, filling unset options from ``CALLAI_*`` and the config (DESIGN.md §6).

    Precedence for each option: flag > environment variable > ``[harnesses.<name>]`` > top level.
    Model aliases are resolved last, so they work from any of those.

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments for the harness.
        harness_name: Harness name.
        prompt: The final prompt (or a placeholder, for :func:`preflight`).
        environ: Environment for ``CALLAI_MODEL`` / ``CALLAI_TIMEOUT``.
        config: User config.

    Returns:
        The request.
    """
    per_harness = config.harnesses.get(harness_name)
    model = ns.model or environ.get("CALLAI_MODEL") or (per_harness and per_harness.model) or config.model
    timeout = ns.timeout if ns.timeout is not None else env_timeout(environ)
    return Request(
        harness_name=harness_name,
        prompt=prompt,
        model=resolve_model(config, harness_name, model or None),
        output_format=ns.output_format,
        cwd=ns.cwd,
        timeout=timeout if timeout is not None else config.timeout,
        permission=ns.permission,
        system_prompt=ns.system_prompt,
        extra_args=(*(per_harness.extra_args if per_harness else ()), *extra),
        resume=ns.resume,
        continue_session=ns.continue_session,
    )


def make_request(
    ns: argparse.Namespace,
    extra: Sequence[str],
    stdin_text: str,
    environ: Mapping[str, str],
    config: Config | None = None,
) -> Request:
    """Build a validated :class:`Request` from parsed arguments (missing or invalid harness or prompt: UsageError).

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments for the harness.
        stdin_text: Piped stdin, ``""`` if none.
        environ: Environment for defaults such as ``CALLAI_HARNESS_NAME``.
        config: User config; ``None`` means none.

    Returns:
        The request.
    """
    config = config or Config()
    harness_name = resolve_harness_name(ns, environ, config)
    get_adapter(harness_name)  # unknown / unimplemented harness -> UsageError before reading anything else
    return _request(ns, extra, harness_name, resolve_prompt(ns.prompt, stdin_text), environ, config)


def preflight(
    ns: argparse.Namespace, extra: Sequence[str], environ: Mapping[str, str], config: Config | None = None
) -> Adapter:
    """Raise every usage error that doesn't depend on the prompt, before stdin is read.

    Reading stdin can block (the prompt may come only from a slow pipe), so a refused
    permission level or option shouldn't have to wait for it. Errors that depend on the
    prompt text (e.g. grok's slash commands) still come after. Errors are raised as UsageError.

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments for the harness.
        environ: Environment for defaults such as ``CALLAI_HARNESS_NAME``.
        config: User config; ``None`` means none.

    Returns:
        The adapter for the harness.
    """
    config = config or Config()
    return _check_harness(ns, extra, resolve_harness_name(ns, environ, config), environ, config)


def _check_harness(
    ns: argparse.Namespace, extra: Sequence[str], harness_name: str, environ: Mapping[str, str], config: Config
) -> Adapter:
    """Raise the usage errors one harness has for these options, with a placeholder prompt.

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments for the harness.
        harness_name: The harness.
        environ: Environment for defaults.
        config: User config.

    Returns:
        The harness's adapter.
    """
    adapter = get_adapter(harness_name)
    adapter.build_argv(_request(ns, extra, harness_name, "callai preflight", environ, config))
    return adapter


def _render(completed: Completed, adapter: Adapter, req: Request, verbose: bool) -> int:
    """Print a finished run in the requested output format and pick the exit code.

    Harness stderr is shown only on failure, unless ``verbose`` already streamed it.

    Args:
        completed: Raw process outcome.
        adapter: Adapter that parses it.
        req: The request (its ``output_format`` decides the rendering).
        verbose: Whether stderr was already streamed live.

    Returns:
        The harness's exit code, or 1 if it exited 0 but reported an error.
    """
    if req.output_format == "raw":
        sys.stdout.write(completed.stdout)
        if not verbose:
            sys.stderr.write(completed.stderr)
        return completed.exit_code
    result = adapter.parse(completed, req)
    if result.is_error and not verbose and completed.stderr:
        sys.stderr.write(completed.stderr)
    if req.output_format == "json":
        sys.stdout.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
    elif req.output_format == "stream-json":
        _write_event({"type": "result", **result.to_dict()})
    elif result.is_error:
        # Harness stderr was already shown (buffered above, or live with -v); don't repeat what it said.
        if result.text and result.text not in completed.stderr:  # e.g. pi: the error text *is* its stderr
            sys.stderr.write(result.text + "\n")
    else:
        sys.stdout.write(result.text + "\n")
    return completed.exit_code or (1 if result.is_error else 0)


def _write_event(event: dict[str, Any]) -> None:
    """Write one ``-o stream-json`` event as a JSON line and flush, so readers see it at once.

    Thread-safe: a parallel fan-out writes from several threads.

    Args:
        event: The event.
    """
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with _WRITE_LOCK:
        sys.stdout.write(line)
        sys.stdout.flush()


def dry_run_line(argv: Sequence[str], env: Mapping[str, str], output_format: str) -> str:
    """What ``--dry-run`` prints: the harness command line and the env vars callai would set for it.

    Args:
        argv: The harness command line.
        env: Variables the adapter sets for the harness.
        output_format: ``"json"`` or ``"stream-json"`` for ``{"argv": [...], "env": {...}}`` (``env`` only
            when non-empty), anything else for a shell line with ``NAME=value`` assignments before the command.

    Returns:
        The line, without a trailing newline.
    """
    if output_format in ("json", "stream-json"):
        return json.dumps({"argv": list(argv), **({"env": dict(env)} if env else {})}, ensure_ascii=False)
    return " ".join([*(f"{k}={shlex.quote(v)}" for k, v in env.items()), shlex.join(argv)])


def _execute(ns: argparse.Namespace, extra: Sequence[str]) -> int:
    """Build the request, then dry-run it or run the harness and render the result.

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments for the harness.

    Returns:
        The process exit code.
    """
    config = load_config(os.environ)
    names, mode = split_harness_names(resolve_harness_name(ns, os.environ, config))
    if mode != SINGLE:
        return _execute_many(ns, extra, names, mode, config)
    adapter = preflight(ns, extra, os.environ, config)
    # With -p TEXT, stdin is optional extra input: don't let a pipe that never closes block the run.
    # Without it (or with -p -), stdin is the prompt, so wait for EOF however long it takes.
    wait = stdin_wait(os.environ) if ns.prompt and ns.prompt != "-" else None
    req = make_request(ns, extra, read_stdin(sys.stdin, wait), os.environ, config)
    argv = [harness_binary(adapter, config), *adapter.build_argv(req)[1:]]
    if ns.dry_run:
        sys.stdout.write(dry_run_line(argv, adapter.build_env(req), req.output_format) + "\n")
        return 0
    if req.permission == "bypass":
        _warn_bypass(adapter)
    # A harness that can't start writes no stream events: a missing binary is exit 127 with no start.
    on_event = _write_event if req.output_format == "stream-json" else None
    completed = run_harness(adapter, req, argv, verbose=ns.verbose, on_event=on_event)
    return _render(completed, adapter, req, ns.verbose)


def _warn_bypass(adapter: Adapter) -> None:
    """Warn on stderr that a harness is about to run with every permission.

    Args:
        adapter: The harness's adapter.
    """
    sys.stderr.write(
        f"callai: warning: --permission bypass: {adapter.name} will run every tool call without asking, "
        "including shell commands and writes outside the working directory.\n"
    )


def _execute_many(ns: argparse.Namespace, extra: Sequence[str], names: list[str], mode: str, config: Config) -> int:
    """Run one prompt through several harnesses (``-n a/b``, ``-n a,b``, ``-n all``) and render the results.

    Everything that can be checked is checked before any harness starts. With an explicit list, a
    harness that refuses the options or isn't installed is an error; ``-n all`` takes the installed
    harnesses and skips (with a note) those that refuse the options.

    Args:
        ns: Parsed callai arguments.
        extra: Passthrough arguments (refused: they'd be for one harness).
        names: The harnesses, in output order.
        mode: ``PARALLEL``, ``SEQUENTIAL`` or ``ALL``.
        config: User config.

    Returns:
        0 if every run succeeded, else the first failed run's exit code (in the order given).

    Raises:
        UsageError: For ``-o raw``, arguments after ``--``, or a refused option (explicit list).
        NoHarnessInstalled: For ``-n all`` when no supported harness is installed.
    """
    if ns.output_format == "raw":
        raise UsageError("-o raw needs a single harness (several raw outputs can't be told apart)")
    if extra:
        raise UsageError(
            "arguments after -- go to one harness; for several, set [harnesses.<name>] extra_args in the config file"
        )

    def refused(name: str, exc: UsageError) -> None:
        """Skip a harness under ``-n all``; anywhere else its refusal is the error.

        Args:
            name: The harness.
            exc: Its usage error.

        Raises:
            UsageError: Unless ``-n all``: the refusal, prefixed with the harness name.
        """
        if mode != ALL:
            raise UsageError(f"{name}: {exc}") from None
        sys.stderr.write(f"callai: skipping {name}: {exc}\n")

    adapters = []
    for name in names:
        adapter = get_adapter(name)
        if mode == ALL and shutil.which(harness_binary(adapter, config)) is None:
            continue
        try:
            _check_harness(ns, extra, name, os.environ, config)
        except UsageError as exc:
            refused(name, exc)
            continue
        adapters.append(adapter)
    if mode == ALL and not adapters and not any(shutil.which(harness_binary(get_adapter(n), config)) for n in names):
        raise NoHarnessInstalled("-n all: none of the supported harnesses is installed (see callai --list-harnesses)")
    wait = stdin_wait(os.environ) if ns.prompt and ns.prompt != "-" else None
    prompt = resolve_prompt(ns.prompt, read_stdin(sys.stdin, wait))
    jobs = []
    for adapter in adapters:
        try:
            req = _request(ns, extra, adapter.name, prompt, os.environ, config)
            argv = (harness_binary(adapter, config), *adapter.build_argv(req)[1:])
        except UsageError as exc:  # prompt-dependent refusals, e.g. grok's slash commands
            refused(adapter.name, exc)
            continue
        jobs.append(Job(adapter, req, argv))
    if not jobs:
        raise UsageError("-n all: every installed harness refused these options")
    if ns.dry_run:
        if ns.output_format in ("json", "stream-json"):
            runs = [
                {
                    "harness_name": j.adapter.name,
                    "argv": list(j.argv),
                    **({"env": env} if (env := j.adapter.build_env(j.req)) else {}),
                }
                for j in jobs
            ]
            sys.stdout.write(json.dumps({"runs": runs}, ensure_ascii=False) + "\n")
        else:
            for j in jobs:
                sys.stdout.write(dry_run_line(j.argv, j.adapter.build_env(j.req), "text") + "\n")
        return 0
    for j in jobs:  # a missing binary in an explicit list stops the call before anything runs
        runner.resolve_binary(j.argv[0], harness_name=j.adapter.name, install_url=j.adapter.install_url)
    for j in jobs:
        if j.req.permission == "bypass":
            _warn_bypass(j.adapter)

    def handler(job: Job) -> Callable[[dict[str, Any]], None] | None:
        """Event callback for one harness: its events, tagged with its name.

        Args:
            job: The harness's job.

        Returns:
            The callback, or ``None`` unless ``-o stream-json``.
        """
        if ns.output_format != "stream-json":
            return None
        return lambda event: _write_event({"type": event["type"], "harness_name": job.adapter.name, **event})

    outcomes = run_jobs(jobs, concurrent=mode in (PARALLEL, ALL), verbose=ns.verbose, event_handler=handler)
    return _render_many(outcomes, ns.output_format, ns.verbose)


def _render_many(outcomes: Sequence[Outcome], output_format: str, verbose: bool) -> int:
    """Print a fan-out's results in the order given, and pick the exit code.

    Text gives each answer under a ``== name ==`` header (``== name (failed, exit N) ==`` for a
    failure, with its error under it); json gives ``{"results": [...]}``; stream-json was written
    as it happened. A failed harness's own stderr follows on stderr, unless ``-v`` showed it live.

    Args:
        outcomes: One per harness.
        output_format: ``text``, ``json`` or ``stream-json``.
        verbose: Whether stderr was already shown live.

    Returns:
        0 if every run succeeded, else the first failed run's exit code (1 if it exited 0).
    """
    if output_format == "json":
        sys.stdout.write(json.dumps({"results": [o.result.to_dict() for o in outcomes]}, ensure_ascii=False) + "\n")
    for o in outcomes:
        r = o.result
        if output_format == "text":
            status = f" (failed, exit {r.exit_code})" if r.is_error else ""
            sys.stdout.write(f"== {r.harness_name}{status} ==\n{r.text}\n")
        if r.is_error and not verbose and o.completed is not None and o.completed.stderr:
            err = o.completed.stderr
            sys.stderr.write(f"--- {r.harness_name} stderr ---\n{err}{'' if err.endswith(chr(10)) else chr(10)}")
    failed = next((o.result for o in outcomes if o.result.is_error), None)
    return 0 if failed is None else (failed.exit_code or 1)


def list_harnesses(output_format: str, config: Config) -> int:
    """Print every harness callai supports, whether its binary is installed, and its version.

    Args:
        output_format: ``"json"`` for one JSON object, anything else for one line per harness.
        config: User config (``[harnesses.<name>] binary`` overrides the binary looked up).

    Returns:
        Exit code 0.
    """
    rows = []
    for name in HARNESS_NAMES:
        adapter = get_adapter(name)
        binary = harness_binary(adapter, config)
        path = shutil.which(binary)
        version = runner.harness_version(path) if path else None
        rows.append(
            {
                "harness_name": name,
                "binary": binary,
                "path": path,
                "version": version,
                "install_url": adapter.install_url,
            }
        )
    if output_format == "json":
        sys.stdout.write(json.dumps({"harnesses": rows}, ensure_ascii=False) + "\n")
        return 0
    for row in rows:
        if row["path"] is None:
            status = f"not installed (see {row['install_url']})"
        else:
            status = f"{row['version'] or 'version unknown'}  {row['path']}"
        sys.stdout.write(f"{row['harness_name']:<12} {row['binary']:<10} {status}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments excluding the program name; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code (DESIGN.md §8).
    """
    own, extra = split_passthrough(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        ns = parser.parse_args(own)
    except SystemExit as exc:  # --help / --version / argparse usage errors
        return int(exc.code or 0)
    try:
        if ns.list_harnesses:
            return list_harnesses(ns.output_format, load_config(os.environ))
        return _execute(ns, extra)
    except CallaiError as exc:
        if isinstance(exc, UsageError):
            parser.print_usage(sys.stderr)
        sys.stderr.write(f"callai: error: {exc}\n")
        return exc.exit_code
