"""CA-6: codex parse() edge cases beyond the recorded conformance fixtures."""

import json

import pytest

from callai.adapters import get_adapter
from callai.request import Request
from callai.result import Completed

ADAPTER = get_adapter("codex")


def _parse(events, exit_code=0, model=None, stderr=""):
    stdout = "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events)
    req = Request(harness_name="codex", prompt="p", model=model)
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=4)
    return ADAPTER.parse(done, req)


def msg(text):
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}


def test_metadata():
    assert (ADAPTER.name, ADAPTER.binary) == ("codex", "codex")
    assert ADAPTER.install_url.startswith("https://")


def test_last_agent_message_wins_and_runtime_fields_kept():
    r = _parse(
        [
            {"type": "thread.started", "thread_id": "t1"},
            msg("thinking out loud"),
            msg("final"),
            {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 1}},
        ],
        model="o4",
    )
    assert (r.text, r.session_id, r.model, r.is_error, r.duration_ms) == ("final", "t1", "o4", False, 4)
    assert r.usage == {"input_tokens": 5, "output_tokens": 1}
    assert r.argv[:2] == ("codex", "exec")


def test_non_fatal_error_events_do_not_fail_the_run():
    r = _parse(
        [
            {"type": "error", "message": "Reconnecting... 2/5"},
            {"type": "item.completed", "item": {"type": "error", "message": "metadata warning"}},
            msg("ok"),
        ]
    )
    assert (r.text, r.is_error) == ("ok", False)


def test_turn_failed_is_error_even_with_exit_0():
    r = _parse([msg("partial"), {"type": "turn.failed", "error": {"message": "quota exceeded"}}])
    assert (r.is_error, r.text) == (True, "quota exceeded")


def test_turn_failed_without_message_keeps_last_agent_text():
    r = _parse([msg("partial"), {"type": "turn.failed", "error": {}}], exit_code=1)
    assert (r.is_error, r.text) == (True, "partial")


def test_nonzero_exit_without_turn_failed_is_error():
    assert _parse([msg("x")], exit_code=2).is_error is True


def test_non_json_lines_are_skipped():
    r = _parse(["Reading additional input from stdin...", msg("pong"), "[1,2]"])
    assert r.text == "pong"


def test_no_events_falls_back_to_text_error():
    r = _parse(["panic: something broke"], exit_code=101)
    assert (r.text, r.is_error, r.exit_code) == ("panic: something broke", True, 101)


def test_missing_usage_and_thread():
    r = _parse([msg("x"), {"type": "turn.completed"}])
    assert (r.usage, r.session_id, r.cost_usd) == (None, None, None)


@pytest.mark.parametrize(
    "text", ["plain", 'q"uote', "back\\slash", "new\nline", "tab\t", "uni ✓", "emoji 😀", "del\x7fchar"]
)
def test_system_prompt_is_a_valid_toml_basic_string(text):
    import tomllib

    argv = ADAPTER.build_argv(Request(harness_name="codex", prompt="p", system_prompt=text))
    key, _, value = argv[argv.index("-c") + 1].partition("=")
    assert key == "developer_instructions"
    assert tomllib.loads(f"v = {value}")["v"] == text


# --- -o stream-json (CA-14) ----------------------------------------------------


def _events(*objs):
    state = {}
    return [e for o in objs for e in ADAPTER.stream_events(json.dumps(o) + "\n", state)]


def test_stream_completed_without_started_emits_tool_use_first():
    item = {"id": "i1", "type": "file_change", "changes": [{"path": "a.txt", "kind": "add"}], "status": "completed"}
    assert _events({"type": "item.completed", "item": item}) == [
        {
            "type": "tool_use",
            "id": "i1",
            "name": "file_change",
            "input": {"changes": [{"path": "a.txt", "kind": "add"}]},
        },
        {"type": "tool_result", "id": "i1", "is_error": False, "output": ""},
    ]


def test_stream_failed_command_is_error():
    item = {
        "id": "i1",
        "type": "command_execution",
        "command": "false",
        "aggregated_output": "",
        "exit_code": 1,
        "status": "failed",
    }
    events = _events(
        {"type": "item.started", "item": {**item, "status": "in_progress"}}, {"type": "item.completed", "item": item}
    )
    assert [e["type"] for e in events] == ["tool_use", "tool_result"]
    assert events[1]["is_error"] is True


def test_stream_skips_reasoning_errors_and_turn_events():
    assert (
        _events(
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "hm"}},
            {"type": "item.completed", "item": {"id": "e", "type": "error", "message": "warn"}},
            {"type": "item.completed"},
        )
        == []
    )
