"""Unit tests for the conformance-suite loader (src/tests/conformance.py)."""

import json

import pytest

from tests import conformance as cf


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


# --- argv cases -------------------------------------------------------------


def test_argv_case_fills_request_defaults(tmp_path):
    _write(
        tmp_path / "argv/claude-code/basic.json",
        {
            "description": "d",
            "harness_name": "claude-code",
            "request": {"prompt": "hi"},
            "expected_argv": ["claude", "hi"],
        },
    )
    (case,) = cf.load_argv_cases(root=tmp_path)
    assert case.id == "claude-code/basic"
    assert case.harness_name == "claude-code"
    assert case.request == {
        "prompt": "hi",
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
    assert case.expected_argv == ["claude", "hi"]
    assert case.expected_env == {}
    assert case.expected_error is None


def test_argv_case_expected_env(tmp_path):
    _write(
        tmp_path / "argv/hermes/sp.json",
        {
            "description": "d",
            "harness_name": "hermes",
            "request": {"prompt": "hi", "system_prompt": "S"},
            "expected_argv": ["hermes", "hi"],
            "expected_env": {"HERMES_EPHEMERAL_SYSTEM_PROMPT": "S"},
        },
    )
    (case,) = cf.load_argv_cases(root=tmp_path)
    assert case.expected_env == {"HERMES_EPHEMERAL_SYSTEM_PROMPT": "S"}


def test_argv_cases_filter_by_tool_and_sorted(tmp_path):
    for tool, name in [("codex", "a"), ("claude-code", "b"), ("claude-code", "a")]:
        _write(
            tmp_path / f"argv/{tool}/{name}.json",
            {"description": "d", "harness_name": tool, "request": {"prompt": "p"}, "expected_argv": ["x"]},
        )
    assert [c.id for c in cf.load_argv_cases(root=tmp_path)] == ["claude-code/a", "claude-code/b", "codex/a"]
    assert [c.id for c in cf.load_argv_cases("claude-code", root=tmp_path)] == ["claude-code/a", "claude-code/b"]


def test_argv_case_expected_error(tmp_path):
    _write(
        tmp_path / "argv/claude-code/err.json",
        {
            "description": "d",
            "harness_name": "claude-code",
            "request": {"prompt": "p", "permission": "bypass"},
            "expected_error": {"message_contains": "bypass"},
        },
    )
    (case,) = cf.load_argv_cases(root=tmp_path)
    assert case.expected_argv is None
    assert case.expected_error == {"message_contains": "bypass"}


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"harness_name": "claude-code", "request": {"prompt": "p"}, "expected_argv": []}, "description"),
        ({"description": "d", "harness_name": "claude-code", "request": {}, "expected_argv": ["x"]}, "prompt"),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p", "modle": "x"},
                "expected_argv": ["x"],
            },
            "modle",
        ),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p"},
                "expected_argv": ["x"],
                "extra": 1,
            },
            "extra",
        ),
        ({"description": "d", "harness_name": "claude-code", "request": {"prompt": "p"}}, "expected_argv"),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p"},
                "expected_argv": ["x"],
                "expected_error": {"message_contains": "y"},
            },
            "expected_argv",
        ),
        (
            {"description": "d", "harness_name": "codex", "request": {"prompt": "p"}, "expected_argv": ["x"]},
            "directory",
        ),
        (
            {"description": "d", "harness_name": "claude-code", "request": {"prompt": "p"}, "expected_argv": "claude"},
            "list",
        ),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p", "output_format": "xml"},
                "expected_argv": ["x"],
            },
            "output_format",
        ),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p"},
                "expected_argv": ["x"],
                "expected_env": {"X": 1},
            },
            "expected_env must map",
        ),
        (
            {
                "description": "d",
                "harness_name": "claude-code",
                "request": {"prompt": "p"},
                "expected_error": {"message_contains": "y"},
                "expected_env": {"X": "1"},
            },
            "expected_env goes with expected_argv",
        ),
    ],
)
def test_argv_case_validation_errors(tmp_path, data, match):
    _write(tmp_path / "argv/claude-code/bad.json", data)
    with pytest.raises(cf.ConformanceError, match=match):
        cf.load_argv_cases(root=tmp_path)


def test_invalid_json_reports_path(tmp_path):
    _write(tmp_path / "argv/claude-code/broken.json", "{not json")
    with pytest.raises(cf.ConformanceError, match="broken.json"):
        cf.load_argv_cases(root=tmp_path)


# --- parse cases ------------------------------------------------------------


def test_parse_case_reads_sibling_output_files(tmp_path):
    _write(tmp_path / "parse/claude-code/ok.stdout", '{"result": "pong"}\n')
    _write(tmp_path / "parse/claude-code/ok.stderr", "warn\n")
    _write(
        tmp_path / "parse/claude-code/ok.json",
        {
            "description": "d",
            "harness_name": "claude-code",
            "exit_code": 0,
            "stdout_file": "ok.stdout",
            "stderr_file": "ok.stderr",
            "expected": {"text": "pong", "is_error": False},
        },
    )
    (case,) = cf.load_parse_cases(root=tmp_path)
    assert case.id == "claude-code/ok"
    assert case.stdout == '{"result": "pong"}\n'
    assert case.stderr == "warn\n"
    assert case.exit_code == 0
    assert case.request["prompt"] == ""
    assert case.expected == {"text": "pong", "is_error": False}


def test_parse_case_stderr_optional(tmp_path):
    _write(tmp_path / "parse/claude-code/ok.stdout", "x")
    _write(
        tmp_path / "parse/claude-code/ok.json",
        {"description": "d", "harness_name": "claude-code", "exit_code": 1, "stdout_file": "ok.stdout", "expected": {}},
    )
    (case,) = cf.load_parse_cases("claude-code", root=tmp_path)
    assert case.stderr == ""
    assert case.expected_events is None  # stream events not checked unless given


def test_parse_case_expected_events(tmp_path):
    _write(tmp_path / "parse/claude-code/ok.stdout", "x")
    events = [
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
        {"type": "tool_result", "id": "t1", "is_error": False, "output": "a"},
        {"type": "text", "text": "hi"},
    ]
    _write(
        tmp_path / "parse/claude-code/ok.json",
        {
            "description": "d",
            "harness_name": "claude-code",
            "exit_code": 0,
            "stdout_file": "ok.stdout",
            "expected": {},
            "expected_events": events,
        },
    )
    (case,) = cf.load_parse_cases(root=tmp_path)
    assert case.expected_events == events


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        ({"stdout_file": "missing.stdout"}, "missing.stdout"),
        ({"expected_events": {}}, "expected_events must be a list"),
        ({"expected_events": [{"type": "start"}]}, r"expected_events\[0\] must be an object whose type"),
        ({"expected_events": [{"type": "text"}]}, r"expected_events\[0\].*text"),
        ({"expected_events": [{"type": "text", "text": "a", "delta": "a"}]}, "delta"),
        ({"expected": {"txt": "x"}}, "txt"),
        ({"exit_code": "0"}, "exit_code"),
    ],
)
def test_parse_case_validation_errors(tmp_path, patch, match):
    _write(tmp_path / "parse/claude-code/ok.stdout", "x")
    data = {
        "description": "d",
        "harness_name": "claude-code",
        "exit_code": 0,
        "stdout_file": "ok.stdout",
        "expected": {},
    }
    data.update(patch)
    _write(tmp_path / "parse/claude-code/ok.json", data)
    with pytest.raises(cf.ConformanceError, match=match):
        cf.load_parse_cases(root=tmp_path)


# --- cli cases --------------------------------------------------------------


def test_cli_case_defaults(tmp_path):
    _write(
        tmp_path / "cli/no_prompt.json",
        {"description": "d", "args": ["-n", "claude-code"], "expected": {"exit_code": 2}},
    )
    (case,) = cf.load_cli_cases(root=tmp_path)
    assert case.id == "no_prompt"
    assert case.args == ["-n", "claude-code"]
    assert case.stdin is None
    assert case.stdin_open is False
    assert case.config is None
    assert case.env == {}
    assert case.fake_harnesses == {}
    assert case.expected == {
        "exit_code": 2,
        "stdout": None,
        "stdout_json": None,
        "stdout_json_subset": None,
        "stdout_events": None,
        "stdout_contains": [],
        "stderr_contains": [],
        "harness_argv": None,
        "harness_env": None,
    }


def test_cli_case_full(tmp_path):
    _write(
        tmp_path / "cli/full.json",
        {
            "description": "d",
            "args": ["-p", "hi"],
            "stdin": "piped",
            "env": {"CALLAI_HARNESS_NAME": "claude-code"},
            "fake_harnesses": {
                "claude": {"stdout_file": "full.stdout", "exit_code": 3, "stderr": "boom", "sleep": 0.1}
            },
            "expected": {"exit_code": 3, "stderr_contains": ["boom"], "harness_argv": ["claude", "hi"]},
        },
    )
    _write(tmp_path / "cli/full.stdout", "out")
    (case,) = cf.load_cli_cases(root=tmp_path)
    assert case.stdin == "piped"
    assert case.env == {"CALLAI_HARNESS_NAME": "claude-code"}
    assert case.fake_harnesses == {"claude": {"stdout": "out", "stderr": "boom", "exit_code": 3, "sleep": 0.1}}
    assert case.expected["harness_argv"] == ["claude", "hi"]


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"description": "d", "args": [], "expected": {}}, "exit_code"),
        ({"description": "d", "args": "-p hi", "expected": {"exit_code": 0}}, "args"),
        ({"description": "d", "args": [], "env": {"X": 1}, "expected": {"exit_code": 0}}, "env"),
        ({"description": "d", "args": [], "stdin_open": "yes", "expected": {"exit_code": 0}}, "stdin_open"),
        ({"description": "d", "args": [], "config": {"a": 1}, "expected": {"exit_code": 0}}, "config must be a string"),
        (
            {"description": "d", "args": [], "stdin": "x", "stdin_open": True, "expected": {"exit_code": 0}},
            "stdin_open",
        ),
        ({"description": "d", "args": [], "expected": {"exit_code": 0, "stdout": "a", "stdout_json": {}}}, "stdout"),
        (
            {"description": "d", "args": [], "expected": {"exit_code": 0, "stdout": "a", "stdout_events": []}},
            "only one of",
        ),
        ({"description": "d", "args": [], "expected": {"exit_code": 0, "stdout_events": [1]}}, "stdout_events must"),
        (
            {
                "description": "d",
                "args": [],
                "fake_harnesses": {"claude": {"exitcode": 1}},
                "expected": {"exit_code": 0},
            },
            "exitcode",
        ),
        (
            {
                "description": "d",
                "args": [],
                "fake_harnesses": {"claude": {"stderr": "a", "stderr_file": "b"}},
                "expected": {"exit_code": 0},
            },
            "use stderr or stderr_file",
        ),
        (
            {
                "description": "d",
                "args": [],
                "fake_harnesses": {"hermes": {}},
                "expected": {"exit_code": 0, "harness_env": {"X": 1}},
            },
            "harness_env must map",
        ),
        ({"description": "d", "args": [], "expected": {"exit_code": 0, "harness_env": {}}}, "exactly one fake"),
    ],
)
def test_cli_case_validation_errors(tmp_path, data, match):
    _write(tmp_path / "cli/bad.json", data)
    with pytest.raises(cf.ConformanceError, match=match):
        cf.load_cli_cases(root=tmp_path)


def test_cli_case_fake_stderr_file(tmp_path):
    _write(tmp_path / "cli/f.stderr", "warn\n")
    _write(
        tmp_path / "cli/f.json",
        {
            "description": "d",
            "args": [],
            "fake_harnesses": {"x": {"stderr_file": "f.stderr"}},
            "expected": {"exit_code": 0},
        },
    )
    (case,) = cf.load_cli_cases(root=tmp_path)
    assert case.fake_harnesses["x"]["stderr"] == "warn\n"


def test_cli_case_stdin_open(tmp_path):
    _write(
        tmp_path / "cli/idle.json", {"description": "d", "args": [], "stdin_open": True, "expected": {"exit_code": 0}}
    )
    (case,) = cf.load_cli_cases(root=tmp_path)
    assert case.stdin_open is True


def test_missing_root_dirs_yield_no_cases(tmp_path):
    assert cf.load_argv_cases(root=tmp_path) == []
    assert cf.load_parse_cases(root=tmp_path) == []
    assert cf.load_cli_cases(root=tmp_path) == []


def test_default_root_points_at_conformance_dir():
    assert cf.CONFORMANCE_DIR.name == "conformance"
    assert (cf.CONFORMANCE_DIR / "README.md").is_file()


def test_cli_case_stdout_json_subset_exclusive_with_exact_forms(tmp_path):
    _write(
        tmp_path / "cli/ok.json",
        {"description": "d", "args": [], "expected": {"exit_code": 0, "stdout_json_subset": {"a": 1}}},
    )
    (case,) = cf.load_cli_cases(root=tmp_path)
    assert case.expected["stdout_json_subset"] == {"a": 1}
    _write(
        tmp_path / "cli/ok.json",
        {"description": "d", "args": [], "expected": {"exit_code": 0, "stdout_json": {}, "stdout_json_subset": {}}},
    )
    with pytest.raises(cf.ConformanceError, match="stdout"):
        cf.load_cli_cases(root=tmp_path)
