"""The recording stub (conformance/tools/stub_llm_server.py): canned replies and scripted tool calls."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "conformance" / "tools" / "stub_llm_server.py"
_spec = importlib.util.spec_from_file_location("stub_llm_server", _PATH)
stub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stub)

CALL = {"name": "write", "arguments": {"path": "x.txt", "content": "hi"}}
TOOLS = [{"type": "function", "function": {"name": "write", "parameters": {}}}]


@pytest.fixture
def server():
    def start(tool_call=None):
        handler = type("H", (stub.StubHandler,), {"reply": "pong", "tool_call": tool_call, "log_path": None})
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}/v1"

    started = []
    yield start
    for srv in started:
        srv.shutdown()
        srv.server_close()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode()


def sse(raw):
    return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]


def chat(base, messages, stream=False, tools=TOOLS):
    body = {"model": "stub-model", "messages": messages, "stream": stream, "tools": tools}
    raw = post(f"{base}/chat/completions", body)
    return sse(raw) if stream else json.loads(raw)


USER = [{"role": "user", "content": "go"}]
AFTER_TOOL = [*USER, {"role": "assistant", "tool_calls": []}, {"role": "tool", "tool_call_id": "c", "content": "ok"}]


def test_chat_without_script_replies_text(server):
    msg = chat(server(), USER)["choices"][0]
    assert (msg["message"]["content"], msg["finish_reason"]) == ("pong", "stop")


def test_chat_json_tool_call_then_text(server):
    base = server(CALL)
    choice = chat(base, USER)["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    (tc,) = choice["message"]["tool_calls"]
    assert (tc["type"], tc["function"]["name"]) == ("function", "write")
    assert json.loads(tc["function"]["arguments"]) == CALL["arguments"]
    assert chat(base, AFTER_TOOL)["choices"][0]["message"]["content"] == "pong"


def test_chat_stream_tool_call(server):
    chunks = chat(server(CALL), USER, stream=True)
    deltas = [c["choices"][0] for c in chunks if c["choices"]]
    calls = [tc for d in deltas for tc in d["delta"].get("tool_calls", [])]
    assert calls[0]["function"]["name"] == "write"
    assert json.loads("".join(tc["function"].get("arguments", "") for tc in calls)) == CALL["arguments"]
    assert deltas[-1]["finish_reason"] == "tool_calls"
    assert any("usage" in c for c in chunks)


def test_requests_without_tools_get_text(server):
    # e.g. grok's title-generation call: no tools offered, so no tool call
    assert chat(server(CALL), USER, tools=[])["choices"][0]["message"]["content"] == "pong"


def test_responses_tool_call_then_text(server):
    base = server(CALL)
    body = {"model": "stub-model", "input": [{"type": "message", "role": "user", "content": "go"}], "tools": TOOLS}
    events = sse(post(f"{base}/responses", body))
    done = [e for e in events if e["type"] == "response.completed"][0]["response"]
    (item,) = done["output"]
    assert (item["type"], item["name"]) == ("function_call", "write")
    assert json.loads(item["arguments"]) == CALL["arguments"]
    body["input"] += [item, {"type": "function_call_output", "call_id": item["call_id"], "output": "ok"}]
    done = [e for e in sse(post(f"{base}/responses", body)) if e["type"] == "response.completed"][0]["response"]
    assert done["output"][0]["content"][0]["text"] == "pong"


# --- Anthropic Messages API (claude-code) -------------------------------------

A_TOOLS = [{"name": "write", "description": "w", "input_schema": {"type": "object"}}]
A_USER = [{"role": "user", "content": [{"type": "text", "text": "go"}]}]


def messages(base, msgs, stream=False, tools=A_TOOLS, model="stub-model"):
    body = {"model": model, "max_tokens": 100, "messages": msgs, "stream": stream, "tools": tools}
    raw = post(f"{base}/messages", body)
    return sse(raw) if stream else json.loads(raw)


def test_messages_json_tool_use_then_text(server):
    base = server(CALL)
    msg = messages(base, A_USER)
    assert (msg["type"], msg["role"], msg["stop_reason"]) == ("message", "assistant", "tool_use")
    (block,) = msg["content"]
    assert (block["type"], block["name"], block["input"]) == ("tool_use", "write", CALL["arguments"])
    after = [
        *A_USER,
        {"role": "assistant", "content": [block]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": block["id"], "content": "ok"}]},
    ]
    msg = messages(base, after)
    assert (msg["content"], msg["stop_reason"]) == ([{"type": "text", "text": "pong"}], "end_turn")
    assert msg["usage"]["input_tokens"] > 0


def test_messages_stream_text(server):
    events = messages(server(), A_USER, stream=True)
    types = [e["type"] for e in events]
    assert types[0] == "message_start" and types[-1] == "message_stop"
    text = "".join(e["delta"]["text"] for e in events if e["type"] == "content_block_delta")
    assert text == "pong"
    (delta,) = [e for e in events if e["type"] == "message_delta"]
    assert delta["delta"]["stop_reason"] == "end_turn"


def test_messages_stream_tool_use(server):
    events = messages(server(CALL), A_USER, stream=True)
    (start,) = [e for e in events if e["type"] == "content_block_start"]
    assert (start["content_block"]["type"], start["content_block"]["name"]) == ("tool_use", "write")
    parts = "".join(e["delta"]["partial_json"] for e in events if e["type"] == "content_block_delta")
    assert json.loads(parts) == CALL["arguments"]
    assert [e for e in events if e["type"] == "message_delta"][0]["delta"]["stop_reason"] == "tool_use"


def test_messages_count_tokens(server):
    got = json.loads(post(f"{server()}/messages/count_tokens", {"model": "stub-model", "messages": A_USER}))
    assert got == {"input_tokens": stub.USAGE["input"]}


def test_messages_unknown_model_is_anthropic_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        messages(server(), A_USER, model="not-a-real-model")
    assert exc.value.code == 404
    assert json.loads(exc.value.read())["error"]["type"] == "not_found_error"
