"""Loader for the language-agnostic conformance suite in ``<experiment>/conformance/``.

The suite is plain JSON (plus recorded output files) so the later TypeScript and Rust
ports can run exactly the same cases. File formats are documented in
``conformance/README.md``; this module validates them strictly (unknown keys are
errors, to catch typos) and fills in documented defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFORMANCE_DIR = Path(__file__).resolve().parents[2] / "conformance"

OUTPUT_FORMATS = {"text", "json", "stream-json", "raw"}
PERMISSIONS = {"default", "read-only", "auto", "bypass"}

REQUEST_DEFAULTS: dict[str, Any] = {
    "prompt": None,  # required in argv cases; "" default in parse cases
    "model": None,
    "output_format": "text",
    "cwd": None,
    "timeout": None,
    "permission": "default",
    "system_prompt": None,
    "extra_args": [],
    "resume": None,
    "continue_session": False,
}

RESULT_KEYS = {"harness_name", "model", "text", "exit_code", "is_error", "session_id", "usage", "cost_usd"}

# Normalised -o stream-json events an adapter's stream_events() produces, by type -> exact keys
# (start and result are written by the CLI, not adapters).
EVENT_KEYS: dict[str, set[str]] = {
    "text": {"type", "text"},
    "tool_use": {"type", "id", "name", "input"},
    "tool_result": {"type", "id", "is_error", "output"},
}

CLI_EXPECTED_DEFAULTS: dict[str, Any] = {
    "exit_code": None,  # required
    "stdout": None,
    "stdout_json": None,
    "stdout_json_subset": None,
    "stdout_events": None,
    "stdout_contains": [],
    "stderr_contains": [],
    "harness_argv": None,
    "harness_env": None,
}

FAKE_HARNESS_DEFAULTS: dict[str, Any] = {"stdout": "", "stderr": "", "exit_code": 0, "sleep": 0}


class ConformanceError(ValueError):
    """A conformance case file is missing, unreadable or malformed."""


@dataclass(frozen=True)
class ArgvCase:
    """Request -> expected harness argv (or expected adapter error)."""

    id: str
    path: Path
    description: str
    harness_name: str
    request: dict[str, Any]
    expected_argv: list[str] | None
    expected_env: dict[str, str]
    expected_error: dict[str, Any] | None


@dataclass(frozen=True)
class ParseCase:
    """Recorded harness output -> expected subset of the normalised Result."""

    id: str
    path: Path
    description: str
    harness_name: str
    request: dict[str, Any]
    exit_code: int
    stdout: str
    stderr: str
    expected: dict[str, Any]
    expected_events: list[dict[str, Any]] | None


@dataclass(frozen=True)
class CliCase:
    """End-to-end ``callai`` invocation -> expected exit code / output."""

    id: str
    path: Path
    description: str
    args: list[str]
    stdin: str | None
    stdin_open: bool
    config: str | None
    env: dict[str, str]
    fake_harnesses: dict[str, dict[str, Any]]
    expected: dict[str, Any]


# --- helpers ----------------------------------------------------------------


def _fail(path: Path, msg: str) -> ConformanceError:
    return ConformanceError(f"{path}: {msg}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _fail(path, f"invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise _fail(path, "top level must be a JSON object")
    return data


def _check_keys(path: Path, data: dict[str, Any], required: set[str], optional: set[str], where: str = "") -> None:
    prefix = f"{where}: " if where else ""
    missing = required - data.keys()
    if missing:
        raise _fail(path, f"{prefix}missing key(s) {sorted(missing)}")
    unknown = data.keys() - required - optional
    if unknown:
        raise _fail(path, f"{prefix}unknown key(s) {sorted(unknown)}")


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_str_map(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def _read_sibling(path: Path, name: str) -> str:
    target = path.parent / name
    if not target.is_file():
        raise _fail(path, f"referenced file not found: {name}")
    with target.open(encoding="utf-8", newline="") as fh:  # recorded output is byte-exact: keep \r\n
        return fh.read()


def _request(path: Path, raw: Any, prompt_required: bool) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _fail(path, "'request' must be an object")
    _check_keys(path, raw, {"prompt"} if prompt_required else set(), set(REQUEST_DEFAULTS), "request")
    req = {**REQUEST_DEFAULTS, "prompt": "", **raw}
    if not isinstance(req["prompt"], str):
        raise _fail(path, "request.prompt must be a string")
    if req["output_format"] not in OUTPUT_FORMATS:
        raise _fail(path, f"request.output_format must be one of {sorted(OUTPUT_FORMATS)}")
    if req["permission"] not in PERMISSIONS:
        raise _fail(path, f"request.permission must be one of {sorted(PERMISSIONS)}")
    if not _is_str_list(req["extra_args"]):
        raise _fail(path, "request.extra_args must be a list of strings")
    if req["resume"] is not None and not isinstance(req["resume"], str):
        raise _fail(path, "request.resume must be a string or null")
    if not isinstance(req["continue_session"], bool):
        raise _fail(path, "request.continue_session must be true or false")
    return req


def _files(root: Path, sub: str) -> list[Path]:
    base = root / sub
    return sorted(base.rglob("*.json")) if base.is_dir() else []


def _case_id(root: Path, sub: str, path: Path) -> str:
    return path.relative_to(root / sub).with_suffix("").as_posix()


def _harness_name_from_dir(root: Path, sub: str, path: Path, data: dict[str, Any]) -> str:
    harness_name = data["harness_name"]
    if path.parent.name != harness_name or path.parent.parent != root / sub:
        raise _fail(path, f"harness_name {harness_name!r} must match its directory {sub}/<harness_name>/")
    return harness_name


# --- loaders ----------------------------------------------------------------


def load_argv_cases(harness_name: str | None = None, root: Path = CONFORMANCE_DIR) -> list[ArgvCase]:
    """Load ``argv/<harness_name>/*.json`` cases, optionally for a single harness."""
    cases = []
    for path in _files(root, "argv"):
        data = _read_json(path)
        _check_keys(
            path, data, {"description", "harness_name", "request"}, {"expected_argv", "expected_env", "expected_error"}
        )
        if ("expected_argv" in data) == ("expected_error" in data):
            raise _fail(path, "exactly one of expected_argv / expected_error is required")
        case_harness_name = _harness_name_from_dir(root, "argv", path, data)
        argv = data.get("expected_argv")
        if argv is not None and not _is_str_list(argv):
            raise _fail(path, "expected_argv must be a list of strings")
        env = data.get("expected_env", {})
        if not _is_str_map(env):
            raise _fail(path, "expected_env must map strings to strings")
        if env and argv is None:
            raise _fail(path, "expected_env goes with expected_argv, not expected_error")
        error = data.get("expected_error")
        if error is not None:
            if not isinstance(error, dict):
                raise _fail(path, "expected_error must be an object")
            _check_keys(path, error, {"message_contains"}, set(), "expected_error")
        cases.append(
            ArgvCase(
                id=_case_id(root, "argv", path),
                path=path,
                description=data["description"],
                harness_name=case_harness_name,
                request=_request(path, data["request"], prompt_required=True),
                expected_argv=argv,
                expected_env=env,
                expected_error=error,
            )
        )
    return [c for c in cases if harness_name is None or c.harness_name == harness_name]


def load_parse_cases(harness_name: str | None = None, root: Path = CONFORMANCE_DIR) -> list[ParseCase]:
    """Load ``parse/<harness_name>/*.json`` cases with their recorded stdout/stderr files."""
    cases = []
    for path in _files(root, "parse"):
        data = _read_json(path)
        _check_keys(
            path,
            data,
            {"description", "harness_name", "exit_code", "stdout_file", "expected"},
            {"request", "stderr_file", "expected_events"},
        )
        case_harness_name = _harness_name_from_dir(root, "parse", path, data)
        if not isinstance(data["exit_code"], int) or isinstance(data["exit_code"], bool):
            raise _fail(path, "exit_code must be an integer")
        expected = data["expected"]
        if not isinstance(expected, dict):
            raise _fail(path, "expected must be an object")
        _check_keys(path, expected, set(), RESULT_KEYS, "expected")
        events = data.get("expected_events")
        if events is not None:
            _check_events(path, events)
        cases.append(
            ParseCase(
                id=_case_id(root, "parse", path),
                path=path,
                description=data["description"],
                harness_name=case_harness_name,
                request=_request(path, data.get("request", {}), prompt_required=False),
                exit_code=data["exit_code"],
                stdout=_read_sibling(path, data["stdout_file"]),
                stderr=_read_sibling(path, data["stderr_file"]) if "stderr_file" in data else "",
                expected=expected,
                expected_events=events,
            )
        )
    return [c for c in cases if harness_name is None or c.harness_name == harness_name]


def _check_events(path: Path, events: Any) -> None:
    if not isinstance(events, list):
        raise _fail(path, "expected_events must be a list")
    for i, event in enumerate(events):
        where = f"expected_events[{i}]"
        if not isinstance(event, dict) or event.get("type") not in EVENT_KEYS:
            raise _fail(path, f"{where} must be an object whose type is one of {', '.join(EVENT_KEYS)}")
        keys = EVENT_KEYS[event["type"]]
        _check_keys(path, event, keys, set(), where)


def _fake_harness(path: Path, name: str, raw: Any) -> dict[str, Any]:
    where = f"fake_harnesses.{name}"
    if not isinstance(raw, dict):
        raise _fail(path, f"{where} must be an object")
    _check_keys(path, raw, set(), {"stdout", "stdout_file", "stderr", "stderr_file", "exit_code", "sleep"}, where)
    for stream in ("stdout", "stderr"):
        if stream in raw and f"{stream}_file" in raw:
            raise _fail(path, f"{where}: use {stream} or {stream}_file, not both")
    spec = {**FAKE_HARNESS_DEFAULTS, **{k: v for k, v in raw.items() if not k.endswith("_file")}}
    for stream in ("stdout", "stderr"):
        if f"{stream}_file" in raw:
            spec[stream] = _read_sibling(path, raw[f"{stream}_file"])
    return spec


def load_cli_cases(root: Path = CONFORMANCE_DIR) -> list[CliCase]:
    """Load ``cli/*.json`` end-to-end cases."""
    cases = []
    for path in _files(root, "cli"):
        data = _read_json(path)
        _check_keys(
            path, data, {"description", "args", "expected"}, {"stdin", "stdin_open", "config", "env", "fake_harnesses"}
        )
        if not _is_str_list(data["args"]):
            raise _fail(path, "args must be a list of strings")
        stdin = data.get("stdin")
        if stdin is not None and not isinstance(stdin, str):
            raise _fail(path, "stdin must be a string or null")
        stdin_open = data.get("stdin_open", False)
        if not isinstance(stdin_open, bool):
            raise _fail(path, "stdin_open must be true or false")
        if stdin_open and stdin is not None:
            raise _fail(path, "stdin_open means stdin never gets data; it can't be combined with stdin")
        config = data.get("config")
        if config is not None and not isinstance(config, str):
            raise _fail(path, "config must be a string (TOML text) or null")
        env = data.get("env", {})
        if not _is_str_map(env):
            raise _fail(path, "env must map strings to strings")
        fakes_raw = data.get("fake_harnesses", {})
        if not isinstance(fakes_raw, dict):
            raise _fail(path, "fake_harnesses must be an object")
        fakes = {name: _fake_harness(path, name, spec) for name, spec in fakes_raw.items()}
        exp_raw = data["expected"]
        if not isinstance(exp_raw, dict):
            raise _fail(path, "expected must be an object")
        _check_keys(path, exp_raw, {"exit_code"}, set(CLI_EXPECTED_DEFAULTS), "expected")
        if sum(k in exp_raw for k in ("stdout", "stdout_json", "stdout_json_subset", "stdout_events")) > 1:
            raise _fail(path, "expected: use only one of stdout / stdout_json / stdout_json_subset / stdout_events")
        if "stdout_events" in exp_raw and not (
            isinstance(exp_raw["stdout_events"], list) and all(isinstance(e, dict) for e in exp_raw["stdout_events"])
        ):
            raise _fail(path, "expected.stdout_events must be a list of objects")
        if "harness_env" in exp_raw and not _is_str_map(exp_raw["harness_env"]):
            raise _fail(path, "expected.harness_env must map strings to strings")
        if ("harness_argv" in exp_raw or "harness_env" in exp_raw) and len(fakes) != 1:
            raise _fail(path, "expected.harness_argv / harness_env need exactly one fake harness")
        for key in ("stdout_contains", "stderr_contains"):
            if key in exp_raw and not _is_str_list(exp_raw[key]):
                raise _fail(path, f"expected.{key} must be a list of strings")
        cases.append(
            CliCase(
                id=_case_id(root, "cli", path),
                path=path,
                description=data["description"],
                args=data["args"],
                stdin=stdin,
                stdin_open=stdin_open,
                config=config,
                env=env,
                fake_harnesses=fakes,
                expected={**CLI_EXPECTED_DEFAULTS, **exp_raw},
            )
        )
    return cases
