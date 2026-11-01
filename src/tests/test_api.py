"""CA-15b: the Python API, ``callai.run()``: the same Result as ``-o json``, events like ``-o stream-json``."""

from pathlib import Path

import pytest

import callai
from callai import CallaiError, HarnessNotFound, Result, UsageError

PARSE = Path(__file__).resolve().parents[2] / "conformance" / "parse"


def _fixture(name):
    return (PARSE / name).read_text(encoding="utf-8")


@pytest.fixture
def claude(fake_bin, monkeypatch):
    """A fake ``claude`` on PATH; ``add(stdout)`` sets what it prints."""
    monkeypatch.setenv("PATH", str(fake_bin.dir))

    def add(stdout, **kw):
        fake_bin.add("claude", stdout=stdout, **kw)

    return add


def test_public_names():
    assert callai.run is not None
    assert issubclass(HarnessNotFound, CallaiError) and issubclass(UsageError, CallaiError)
    assert {"run", "Result", "CallaiError", "UsageError", "HarnessNotFound", "HarnessTimeout"} <= set(callai.__all__)


def test_run_returns_the_json_result(claude, fake_bin):
    claude(_fixture("claude-code/success_pong.stdout"))
    result = callai.run("claude-code", "Reply with exactly: pong", model="haiku")
    assert isinstance(result, Result)
    assert (result.harness_name, result.text, result.is_error) == ("claude-code", "pong", False)
    assert fake_bin.record("claude")["argv"] == [
        "claude", "-p", "--output-format", "json", "--model", "haiku", "--", "Reply with exactly: pong",
    ]  # fmt: skip


def test_run_passes_every_option(claude, fake_bin, tmp_path):
    claude(_fixture("claude-code/success_pong.stdout"))
    callai.run(
        "claude-code", "hi", cwd=str(tmp_path), timeout=30, permission="auto", system_prompt="S",
        extra_args=["--x"], resume="S1",
    )  # fmt: skip
    record = fake_bin.record("claude")
    assert record["argv"] == [
        "claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--system-prompt", "S",
        "--resume", "S1", "--x", "--", "hi",
    ]  # fmt: skip
    assert record["cwd"] == str(tmp_path)


def test_run_on_event_streams_start_events_and_result(claude, fake_bin):
    claude(_fixture("claude-code/stream_tool_call.stdout"))
    events = []
    result = callai.run("claude-code", "Say hi.", on_event=events.append)
    assert "stream-json" in fake_bin.record("claude")["argv"]  # live events need the harness's stream format
    assert [e["type"] for e in events] == ["start", "tool_use", "tool_result", "text", "result"]
    assert events[0]["argv"][0] == "claude"
    assert events[-1] == {"type": "result", **result.to_dict()}


def test_run_ignores_callai_env_and_config(claude, fake_bin, monkeypatch, tmp_path):
    # A library call means what it says: no CALLAI_* defaults, no config file.
    claude(_fixture("claude-code/success_pong.stdout"))
    monkeypatch.setenv("CALLAI_MODEL", "opus")
    monkeypatch.setenv("CALLAI_TIMEOUT", "nope")
    conf = tmp_path / "config.toml"
    conf.write_text('model = "fast"\n', encoding="utf-8")
    monkeypatch.setenv("CALLAI_CONFIG", str(conf))
    callai.run("claude-code", "hi")
    assert "--model" not in fake_bin.record("claude")["argv"]


def test_run_binary_override(fake_bin, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "")
    exe = fake_bin.add("claude", stdout=_fixture("claude-code/success_pong.stdout"))
    assert callai.run("claude-code", "hi", binary=str(exe)).text == "pong"


def test_run_errors_raise(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(HarnessNotFound, match="claude"):
        callai.run("claude-code", "hi")
    with pytest.raises(UsageError, match="unknown harness"):
        callai.run("nope", "hi")
    with pytest.raises(UsageError, match="permission"):
        callai.run("claude-code", "hi", permission="root")


def test_run_harness_failure_is_a_result_not_an_exception(claude):
    claude(_fixture("claude-code/error_unknown_model.stdout"), exit_code=1)
    result = callai.run("claude-code", "hi", model="not-a-real-model-xyz")
    assert result.is_error and result.exit_code == 1
