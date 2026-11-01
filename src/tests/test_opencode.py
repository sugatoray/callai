"""CA-7: opencode parse() edge cases beyond the recorded conformance fixtures."""

import json

import pytest

from callai.adapters import get_adapter
from callai.errors import UsageError
from callai.request import Request
from callai.result import Completed

ADAPTER = get_adapter("opencode")


def _parse(events, exit_code=0, model=None, stderr=""):
    stdout = "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events)
    req = Request(harness_name="opencode", prompt="p", model=model)
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=6)
    return ADAPTER.parse(done, req)


def step():
    return {"type": "step_start", "sessionID": "ses_1", "part": {"type": "step-start"}}


def text(t):
    return {"type": "text", "sessionID": "ses_1", "part": {"type": "text", "text": t}}


def finish(inp=0, out=0, read=0, write=0, cost=0):
    tokens = {"input": inp, "output": out, "cache": {"read": read, "write": write}}
    return {
        "type": "step_finish",
        "sessionID": "ses_1",
        "part": {"type": "step-finish", "tokens": tokens, "cost": cost},
    }


def test_metadata():
    assert (ADAPTER.name, ADAPTER.binary) == ("opencode", "opencode")
    assert ADAPTER.install_url.startswith("https://")


def test_final_step_text_and_totals_across_steps():
    r = _parse(
        [
            step(),
            text("Let me look."),
            {"type": "tool_use", "part": {}},
            finish(10, 3, 1, 0, 0.01),
            step(),
            text("Done:"),
            text("all good"),
            finish(20, 5, 4, 2, 0.02),
        ],
        model="m",
    )
    assert (r.text, r.session_id, r.model, r.is_error, r.duration_ms) == ("Done:\nall good", "ses_1", "m", False, 6)
    assert r.usage == {"input_tokens": 37, "output_tokens": 8}
    assert r.cost_usd == pytest.approx(0.03)


def test_error_event_message_used_without_log_line():
    r = _parse([step(), {"type": "error", "error": {"name": "APIError", "data": {"message": "quota exceeded"}}}], 1)
    assert (r.is_error, r.text) == (True, "quota exceeded")


def test_error_event_name_used_without_message():
    assert _parse([{"type": "error", "error": {"name": "AbortError"}}], 1).text == "AbortError"


def test_error_log_line_beats_generic_event_message():
    log = 'timestamp=x level=ERROR message=failed error="RealCause: details" cause="..."\n'
    r = _parse([{"type": "error", "error": {"name": "UnknownError", "data": {"message": "Unexpected"}}}], 1, stderr=log)
    assert r.text == "RealCause: details"


def test_nonzero_exit_without_error_event_is_error():
    r = _parse([step(), text("partial"), finish()], exit_code=2)
    assert (r.is_error, r.text) == (True, "partial")


def test_non_json_lines_skipped_and_missing_usage():
    r = _parse(["some banner", step(), text("ok")])
    assert (r.text, r.usage, r.cost_usd) == ("ok", None, None)


def test_no_events_falls_back_to_text_error():
    r = _parse(["Error: something broke"], exit_code=1)
    assert (r.text, r.is_error) == ("Error: something broke", True)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"permission": "read-only"}, "read-only"),
        ({"permission": "auto"}, "auto"),
        ({"system_prompt": "x"}, "system prompt"),
    ],
)
def test_unsupported_options_fail_closed(kwargs, match):
    with pytest.raises(UsageError, match=match):
        ADAPTER.build_argv(Request(harness_name="opencode", prompt="p", **kwargs))


# --- -o stream-json (CA-14) ----------------------------------------------------


def _events(*objs):
    state = {}
    return [e for o in objs for e in ADAPTER.stream_events(json.dumps(o) + "\n", state)]


def _tool(status, **state):
    return {
        "type": "tool_use",
        "part": {
            "type": "tool",
            "tool": "bash",
            "callID": "c1",
            "state": {"status": status, "input": {"command": "x"}, **state},
        },
    }


def test_stream_running_then_completed_tool_emits_tool_use_once():
    assert _events(_tool("running"), _tool("completed", output="out")) == [
        {"type": "tool_use", "id": "c1", "name": "bash", "input": {"command": "x"}},
        {"type": "tool_result", "id": "c1", "is_error": False, "output": "out"},
    ]


def test_stream_tool_error_uses_error_text():
    assert _events(_tool("error", error="boom"))[1] == {
        "type": "tool_result",
        "id": "c1",
        "is_error": True,
        "output": "boom",
    }


def test_stream_skips_steps_and_empty_parts():
    assert _events({"type": "step_start", "part": {}}, {"type": "text"}, {"type": "tool_use", "part": "x"}) == []
