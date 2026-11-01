"""CA-9: grok build_argv()/parse() edge cases beyond the recorded conformance fixtures."""

import json

import pytest

from callai.adapters import get_adapter
from callai.errors import UsageError
from callai.request import Request
from callai.result import Completed
from tests.conftest import isolated_env, run_callai

ADAPTER = get_adapter("grok")


def _parse(stdout, exit_code=0, model=None, stderr=""):
    if not isinstance(stdout, str):
        stdout = json.dumps(stdout)
    req = Request(harness_name="grok", prompt="p", model=model)
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=8)
    return ADAPTER.parse(done, req)


def answer(text="ok", **extra):
    return {"text": text, "stopReason": "end_turn", "sessionId": "s-1", **extra}


def test_metadata():
    assert (ADAPTER.name, ADAPTER.binary) == ("grok", "grok")
    assert ADAPTER.install_url.startswith("https://")


@pytest.mark.parametrize("prompt", ["/compact", "/", "\n\t/model x", " /help"])
def test_slash_prompts_refused(prompt):
    with pytest.raises(UsageError, match="slash command"):
        ADAPTER.build_argv(Request(harness_name="grok", prompt=prompt))


def test_prompt_is_one_final_single_element():
    argv = ADAPTER.build_argv(Request(harness_name="grok", prompt="-x --help", extra_args=("--max-turns", "2")))
    assert argv[-1] == "--single=-x --help"
    assert "-p" not in argv and "--" not in argv


def test_usage_adds_cache_reads_and_writes():
    u = {"input_tokens": 8, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 4, "output_tokens": 2}
    assert _parse(answer(usage=u)).usage == {"input_tokens": 15, "output_tokens": 2}


def test_usage_missing_or_malformed_is_none():
    assert _parse(answer()).usage is None
    assert _parse(answer(usage="x")).usage is None


def test_model_is_the_one_with_most_tokens():
    mu = {
        "small": {"inputTokens": 5, "outputTokens": 1},
        "big": {"inputTokens": 50, "outputTokens": 9},
        "junk": "x",
    }
    assert _parse(answer(modelUsage=mu), model="req").model == "big"


def test_model_falls_back_to_request():
    assert _parse(answer(), model="req").model == "req"
    assert _parse(answer(modelUsage={}), model="req").model == "req"


def test_cost_taken_when_reported():
    assert _parse(answer(total_cost_usd=0.25)).cost_usd == 0.25
    assert _parse(answer()).cost_usd is None


def test_error_object_with_exit_0_is_still_an_error():
    r = _parse({"type": "error", "message": "boom"}, exit_code=0)
    assert (r.is_error, r.text, r.session_id) == (True, "boom", None)


def test_nonzero_exit_is_error_even_with_text():
    r = _parse(answer("partial"), exit_code=1)
    assert (r.is_error, r.text, r.exit_code) == (True, "partial", 1)


@pytest.mark.parametrize("stop", ["cancelled", "max_turn_requests", "something_new"])
def test_stop_reason_other_than_end_turn_is_error(stop):
    r = _parse(answer("partial", stopReason=stop), exit_code=0, stderr="why\n")
    assert (r.is_error, r.text) == (True, "partial")


def test_failed_with_empty_text_takes_reason_from_stderr_or_stop_reason():
    assert _parse(answer("", stopReason="cancelled"), stderr="\x1b[1mpermission required: X\x1b[0m\n").text == (
        "permission required: X"
    )
    assert _parse(answer("", stopReason="cancelled")).text == "cancelled"


def test_missing_stop_reason_with_text_is_success():
    r = _parse({"text": "ok"})
    assert (r.is_error, r.text) == (False, "ok")


def test_success_shape_without_text_is_error():
    assert _parse({"stopReason": "end_turn"}).is_error


@pytest.mark.parametrize("stdout", ["", "not json", "[1, 2]", '{"text": 3}'])
def test_unparseable_output_falls_back_to_stderr(stdout):
    r = _parse(stdout, exit_code=1, stderr="\x1b[31mError: bad\x1b[0m\n")
    assert r.is_error
    assert r.text == "Error: bad"


def test_unparseable_output_without_stderr_uses_stdout():
    r = _parse("panic: oops\n", exit_code=101)
    assert (r.is_error, r.text) == (True, "panic: oops")


def test_cli_error_printed_once(tmp_path, fake_bin):
    msg = "Couldn't set model 'x': unknown model id"
    fake_bin.add("grok", stdout=json.dumps({"type": "error", "message": msg}), stderr=f"Error: {msg}\n", exit_code=1)
    p = run_callai(["-n", "grok", "-p", "hi"], env=isolated_env(tmp_path, fake_bin.dir), cwd=tmp_path)
    assert (p.returncode, p.stdout) == (1, "")
    assert p.stderr.count("unknown model id") == 1


# --- -o stream-json (CA-14) ----------------------------------------------------


def _events(*objs):
    state = {}
    return [e for o in objs for e in ADAPTER.stream_events(json.dumps(o) + "\n", state)]


def test_stream_in_progress_updates_emit_nothing():
    update = {"type": "tool_call_update", "toolCallId": "c", "status": "in_progress", "content": []}
    assert _events(update, {"type": "usage"}, {"type": "end"}) == []


def test_stream_parse_joins_text_pieces():
    req = Request(harness_name="grok", prompt="p", output_format="stream-json")
    stdout = "".join(
        json.dumps(o) + "\n"
        for o in (
            {"type": "text", "data": "po"},
            {"type": "text", "data": "ng"},
            {"type": "end", "stopReason": "end_turn", "sessionId": "s"},
        )
    )
    done = Completed(argv=["grok"], exit_code=0, stdout=stdout, stderr="")
    result = ADAPTER.parse(done, req)
    assert (result.text, result.is_error, result.session_id) == ("pong", False, "s")


def test_stream_parse_without_end_event_is_error():
    req = Request(harness_name="grok", prompt="p", output_format="stream-json")
    done = Completed(argv=["grok"], exit_code=1, stdout='{"type": "text", "data": "po"}\n', stderr="crashed\n")
    result = ADAPTER.parse(done, req)
    assert (result.text, result.is_error) == ("crashed", True)
