"""CA-5: claude-code parse() edge cases beyond the recorded conformance fixtures."""

import json

import pytest

from callai.adapters import get_adapter
from callai.request import Request
from callai.result import Completed

ADAPTER = get_adapter("claude-code")


def _parse(stdout, exit_code=0, stderr="", model=None):
    req = Request(harness_name="claude-code", prompt="p", model=model)
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=9)
    return ADAPTER.parse(done, req)


def _payload(**overrides):
    base = {"type": "result", "subtype": "success", "is_error": False, "result": "ok", "session_id": "s1"}
    base.update(overrides)
    return json.dumps(base)


def test_runtime_fields_and_raw_streams_carried_through():
    r = _parse(_payload(), stderr="warn")
    assert (r.duration_ms, r.raw_stdout, r.raw_stderr) == (9, _payload(), "warn")
    assert r.argv[-2:] == ("--", "p")


def test_is_error_flag_wins_over_subtype_and_exit_code():
    assert _parse(_payload(is_error=True), exit_code=0).is_error is True


def test_nonzero_exit_is_error_even_if_json_says_ok():
    assert _parse(_payload(), exit_code=1).is_error is True


def test_missing_optional_fields():
    r = _parse(json.dumps({"type": "result", "is_error": False}), model="opus")
    assert (r.text, r.session_id, r.usage, r.cost_usd, r.model) == ("", None, None, None, "opus")


def test_non_string_result_and_non_dict_usage_are_ignored():
    r = _parse(_payload(result=None, usage="n/a", modelUsage=[]))
    assert (r.text, r.usage, r.model) == ("", None, None)


def test_usage_counts_cached_input_tokens():
    r = _parse(_payload(usage={"input_tokens": 3, "cache_read_input_tokens": 100, "output_tokens": 7}))
    assert r.usage == {"input_tokens": 103, "output_tokens": 7}


def test_model_is_the_biggest_spender_in_model_usage():
    usage = {
        "claude-haiku-5-5": {"costUSD": 0.0001, "outputTokens": 20},  # side calls (titles etc.)
        "claude-opus-5-5": {"costUSD": 0.05, "outputTokens": 900},
    }
    assert _parse(_payload(modelUsage=usage), model="opus").model == "claude-opus-5-5"


def test_model_falls_back_to_request_on_error():
    usage = {"claude-haiku-5-5": {"costUSD": 0.0001}}
    assert _parse(_payload(is_error=True, modelUsage=usage), exit_code=1, model="bogus").model == "bogus"


def test_json_after_noise_lines_is_found():
    r = _parse("Warning: something\n" + _payload(result="pong") + "\n")
    assert (r.text, r.is_error) == ("pong", False)


@pytest.mark.parametrize(("stdout", "exit_code"), [("Segmentation fault\n", 139), ("", 1), ("[1, 2]\n", 1)])
def test_non_json_output_falls_back_to_text(stdout, exit_code):
    r = _parse(stdout, exit_code=exit_code, model="m")
    assert (r.text, r.is_error, r.exit_code, r.model) == (stdout.strip(), True, exit_code, "m")


# --- -o stream-json (CA-14) ----------------------------------------------------


def _events(*objs):
    state = {}
    return [e for o in objs for e in ADAPTER.stream_events(json.dumps(o) + "\n", state)]


def test_stream_skips_non_json_and_other_types():
    state = {}
    assert ADAPTER.stream_events("not json\n", state) == []
    assert ADAPTER.stream_events("[1]\n", state) == []
    assert _events({"type": "system", "subtype": "init"}, {"type": "result", "result": "x"}) == []


def test_stream_tool_result_content_blocks_are_joined():
    msg = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "is_error": True,
                    "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
                },
                "junk",
            ]
        },
    }
    assert _events(msg) == [{"type": "tool_result", "id": "t", "is_error": True, "output": "ab"}]


def test_stream_ignores_thinking_blocks():
    msg = {
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": "hm"}, {"type": "text", "text": "hi"}]},
    }
    assert _events(msg) == [{"type": "text", "text": "hi"}]
