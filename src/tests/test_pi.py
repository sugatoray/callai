"""CA-8: pi parse() edge cases beyond the recorded conformance fixtures."""

import json

import pytest

from callai.adapters import get_adapter
from callai.errors import UsageError
from callai.request import Request
from callai.result import Completed

ADAPTER = get_adapter("pi")


def _parse(events, exit_code=0, model=None, stderr=""):
    stdout = "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events)
    req = Request(harness_name="pi", prompt="p", model=model)
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=8)
    return ADAPTER.parse(done, req)


def assistant(text=None, stop="stop", provider="prov", model="m1", usage=None, error=None, blocks=None):
    content = blocks if blocks is not None else ([{"type": "text", "text": text}] if text is not None else [])
    msg = {"role": "assistant", "content": content, "provider": provider, "model": model, "stopReason": stop}
    if usage is not None:
        msg["usage"] = usage
    if error is not None:
        msg["errorMessage"] = error
    return {"type": "message_end", "message": msg}


def usage(inp, out, read=0, write=0, cost=0.0):
    return {"input": inp, "output": out, "cacheRead": read, "cacheWrite": write, "cost": {"total": cost}}


SESSION = {"type": "session", "id": "s-1"}
USER = {"type": "message_end", "message": {"role": "user", "content": [{"type": "text", "text": "p"}]}}


def test_metadata():
    assert (ADAPTER.name, ADAPTER.binary) == ("pi", "pi")
    assert ADAPTER.install_url.startswith("https://")


def test_last_assistant_message_wins_usage_and_cost_summed_over_turns():
    r = _parse(
        [
            SESSION,
            USER,
            assistant(
                blocks=[{"type": "thinking", "thinking": "hmm"}, {"type": "toolCall", "name": "read"}],
                stop="toolUse",
                usage=usage(10, 2, 5, 1, 0.01),
            ),
            assistant(
                blocks=[{"type": "text", "text": "Done:"}, {"type": "text", "text": "ok"}],
                usage=usage(20, 3, 0, 0, 0.02),
            ),
        ]
    )
    assert (r.text, r.session_id, r.model, r.is_error, r.duration_ms) == ("Done:\nok", "s-1", "prov/m1", False, 8)
    assert r.usage == {"input_tokens": 36, "output_tokens": 5}
    assert r.cost_usd == pytest.approx(0.03)


def test_error_stop_reason_is_error_even_with_exit_0():
    r = _parse([SESSION, assistant(stop="error", error="429: rate limited")], model="prov/m1")
    assert (r.is_error, r.text, r.exit_code) == (True, "429: rate limited", 0)
    assert r.model == "prov/m1"


def test_aborted_without_message_uses_stop_reason():
    assert _parse([assistant(stop="aborted")]).text == "aborted"


def test_length_stop_keeps_partial_text_but_is_error():
    r = _parse([assistant("partial", stop="length")])
    assert (r.is_error, r.text) == (True, "partial")


def test_nonzero_exit_is_error():
    assert _parse([assistant("x")], exit_code=1).is_error is True


def test_no_assistant_message_is_error():
    r = _parse([SESSION, USER, {"type": "agent_settled", "aborted": True}], model="a/b")
    assert (r.is_error, r.text, r.model, r.session_id) == (True, "", "a/b", "s-1")


def test_reported_model_needs_provider_and_model():
    assert _parse([assistant("x", provider=None)], model="req").model == "req"


def test_no_events_uses_stderr_then_stdout():
    r = _parse([], exit_code=1, stderr="\nError: boom\n", model="x/y")
    assert (r.text, r.is_error, r.model) == ("Error: boom", True, "x/y")
    assert _parse(["plain crash text"], exit_code=1).text == "plain crash text"


@pytest.mark.parametrize("prompt", ["@team", "@file.py explain"])
def test_at_sign_prompt_refused(prompt):
    with pytest.raises(UsageError, match="@"):
        ADAPTER.build_argv(Request(harness_name="pi", prompt=prompt))


def test_at_sign_later_in_prompt_is_fine():
    assert ADAPTER.build_argv(Request(harness_name="pi", prompt="ask @team"))[-1] == "ask @team"


# --- -o stream-json (CA-14) ----------------------------------------------------


def _events(*objs):
    state = {}
    return [e for o in objs for e in ADAPTER.stream_events(json.dumps(o) + "\n", state)]


def test_stream_tool_error_and_non_text_content():
    end = {
        "type": "tool_execution_end",
        "toolCallId": "c",
        "toolName": "bash",
        "result": {"content": [{"type": "image"}, {"type": "text", "text": "no"}]},
        "isError": True,
    }
    assert _events(end) == [{"type": "tool_result", "id": "c", "is_error": True, "output": "no"}]


def test_stream_skips_thinking_and_whole_messages():
    delta = {"type": "message_update", "assistantMessageEvent": {"type": "thinking_delta", "delta": "hm"}}
    whole = {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "pong"}]}}
    assert _events(delta, whole, {"type": "message_update"}) == []
