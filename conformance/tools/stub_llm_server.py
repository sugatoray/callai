"""Tiny local OpenAI-compatible model stub, for recording *real* harness output without network access.

The harness CLI is real; only the model's reply is canned. Point a harness at it through its
custom-provider settings (base URL ``http://127.0.0.1:PORT/v1``), run it, and save the harness's
stdout/stderr as a ``conformance/parse/<tool>/`` fixture. Say "stub model" in the fixture's
description, so nobody mistakes it for a live-model recording.

Supports:
  POST /v1/responses          OpenAI Responses API, streamed as SSE (codex)
  POST /v1/chat/completions   Chat Completions, streamed SSE or plain JSON (opencode, pi, hermes, ...)
  POST /v1/messages           Anthropic Messages, streamed SSE or plain JSON (claude-code, via
                              ANTHROPIC_BASE_URL=http://127.0.0.1:PORT; also /v1/messages/count_tokens)

The reply text is ``--reply`` (default "pong"). Model names containing ``not-a-real-model`` get an
HTTP 404 error, to record each harness's unknown-model path.

``--tool-call '{"name": "write", "arguments": {...}}'`` scripts one tool call, to check what a
harness's permission settings really allow: a request that offers tools and carries no tool result
yet gets that call; once the harness sends the tool's result back, the reply is the text as usual.
Requests offering no tools (e.g. title generation) always get text.

Usage:
    python stub_llm_server.py --port 8765 [--reply pong] [--tool-call JSON] [--log requests.jsonl]
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

USAGE = {"input": 11, "cached": 3, "output": 2}


class StubHandler(BaseHTTPRequestHandler):
    """Answers every request with the configured reply."""

    reply = "pong"
    tool_call: dict[str, Any] | None = None
    log_path: str | None = None
    protocol_version = "HTTP/1.1"

    # --- plumbing -----------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D102 - silence default stderr logging
        pass

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"path": self.path, "body": data}) + "\n")
        return data

    def _json(self, status: int, obj: dict[str, Any]) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _sse(self, events: list[tuple[str | None, dict[str, Any] | str]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for name, data in events:
            chunk = ""
            if name:
                chunk += f"event: {name}\n"
            chunk += f"data: {data if isinstance(data, str) else json.dumps(data)}\n\n"
            self.wfile.write(chunk.encode())
            self.wfile.flush()
        self.close_connection = True

    def _unknown_model(self, model: str) -> bool:
        if "not-a-real-model" not in (model or ""):
            return False
        if "/messages" in self.path:
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": f"model: {model}"}})
            return True
        self._json(
            404,
            {
                "error": {
                    "message": f"The model `{model}` does not exist.",
                    "type": "invalid_request_error",
                    "code": "model_not_found",
                }
            },
        )
        return True

    def _wants_tool_call(self, body: dict[str, Any]) -> bool:
        if not self.tool_call or not body.get("tools"):
            return False
        items = body.get("messages") or body.get("input") or []
        answered = any(
            isinstance(m, dict)
            and (
                m.get("role") == "tool"
                or str(m.get("type", "")).endswith("_output")
                or any(isinstance(c, dict) and c.get("type") == "tool_result" for c in m.get("content") or [])
            )
            for m in items
        )
        return not answered

    def _call_args(self) -> str:
        return json.dumps(self.tool_call["arguments"])

    # --- endpoints ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802, D102
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "stub-model", "object": "model", "owned_by": "stub"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802, D102
        body = self._body()
        model = body.get("model", "stub-model")
        if self._unknown_model(model):
            return
        if self.path.split("?")[0].endswith("/messages/count_tokens"):
            self._json(200, {"input_tokens": USAGE["input"]})
            return
        call = self._wants_tool_call(body)
        if self.path.split("?")[0].endswith("/messages"):
            self._messages(model, stream=bool(body.get("stream")), call=call)
        elif self.path.endswith("/responses"):
            self._responses(model, call)
        elif self.path.endswith("/chat/completions"):
            self._chat(model, stream=bool(body.get("stream")), call=call)
        else:
            self._json(404, {"error": {"message": f"unsupported path {self.path}"}})

    def _responses(self, model: str, call: bool = False) -> None:
        rid, mid = "resp_stub_1", "msg_stub_1"
        item = {
            "type": "message",
            "id": mid,
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": self.reply, "annotations": []}],
        }
        if call:
            item = {
                "type": "function_call",
                "id": "fc_stub_1",
                "call_id": "call_stub_1",
                "name": self.tool_call["name"],
                "arguments": self._call_args(),
                "status": "completed",
            }
        usage = {
            "input_tokens": USAGE["input"],
            "input_tokens_details": {"cached_tokens": USAGE["cached"]},
            "output_tokens": USAGE["output"],
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": USAGE["input"] + USAGE["output"],
        }
        base = {"id": rid, "object": "response", "created_at": int(time.time()), "model": model}
        added = {**item, "status": "in_progress"}
        if call:
            added["arguments"] = ""
            delta = ("response.function_call_arguments.delta", {"item_id": item["id"], "delta": item["arguments"]})
        else:
            added["content"] = []
            delta = ("response.output_text.delta", {"item_id": mid, "content_index": 0, "delta": self.reply})
        self._sse(
            [
                ("response.created", {"type": "response.created", "response": {**base, "status": "in_progress"}}),
                (
                    "response.output_item.added",
                    {"type": "response.output_item.added", "output_index": 0, "item": added},
                ),
                (delta[0], {"type": delta[0], "output_index": 0, **delta[1]}),
                ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
                (
                    "response.completed",
                    {
                        "type": "response.completed",
                        "response": {**base, "status": "completed", "output": [item], "usage": usage},
                    },
                ),
            ]
        )

    def _chat(self, model: str, stream: bool, call: bool = False) -> None:
        cid, created = "chatcmpl-stub-1", int(time.time())
        usage = {
            "prompt_tokens": USAGE["input"],
            "completion_tokens": USAGE["output"],
            "total_tokens": USAGE["input"] + USAGE["output"],
            "prompt_tokens_details": {"cached_tokens": USAGE["cached"]},
        }
        tool_call = {"id": "call_stub_1", "type": "function", "function": {"name": "", "arguments": ""}}
        if call:
            tool_call["function"] = {"name": self.tool_call["name"], "arguments": self._call_args()}
        finish = "tool_calls" if call else "stop"
        if not stream:
            message: dict[str, Any] = {"role": "assistant", "content": None if call else self.reply}
            if call:
                message["tool_calls"] = [tool_call]
            self._json(
                200,
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                    "usage": usage,
                },
            )
            return
        base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}
        body_delta = {"tool_calls": [{"index": 0, **tool_call}]} if call else {"content": self.reply}
        self._sse(
            [
                (
                    None,
                    {
                        **base,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
                    },
                ),
                (None, {**base, "choices": [{"index": 0, "delta": body_delta, "finish_reason": None}]}),
                (None, {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}),
                (None, {**base, "choices": [], "usage": usage}),
                (None, "[DONE]"),
            ]
        )

    def _messages(self, model: str, stream: bool, call: bool = False) -> None:
        usage = {
            "input_tokens": USAGE["input"] - USAGE["cached"],
            "cache_read_input_tokens": USAGE["cached"],
            "cache_creation_input_tokens": 0,
            "output_tokens": USAGE["output"],
        }
        block: dict[str, Any] = {"type": "text", "text": self.reply}
        if call:
            block = {"type": "tool_use", "id": "toolu_stub_1", "name": self.tool_call["name"]}
            block["input"] = self.tool_call["arguments"]
        stop = "tool_use" if call else "end_turn"
        msg = {"id": "msg_stub_1", "type": "message", "role": "assistant", "model": model}
        if not stream:
            self._json(200, {**msg, "content": [block], "stop_reason": stop, "stop_sequence": None, "usage": usage})
            return
        if call:
            start = {**block, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": self._call_args()}
        else:
            start, delta = {"type": "text", "text": ""}, {"type": "text_delta", "text": self.reply}
        events: list[dict[str, Any]] = [
            {
                "type": "message_start",
                "message": {
                    **msg,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {**usage, "output_tokens": 1},
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": start},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop, "stop_sequence": None},
                "usage": {"output_tokens": USAGE["output"]},
            },
            {"type": "message_stop"},
        ]
        self._sse([(e["type"], e) for e in events])


def main() -> None:
    """Serve until interrupted."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reply", default="pong")
    ap.add_argument("--tool-call", type=json.loads, help='one scripted tool call: {"name": ..., "arguments": {...}}')
    ap.add_argument("--log", help="append each request (path + JSON body) to this JSONL file")
    args = ap.parse_args()
    StubHandler.reply = args.reply
    StubHandler.tool_call = args.tool_call
    StubHandler.log_path = args.log
    server = ThreadingHTTPServer(("127.0.0.1", args.port), StubHandler)
    print(f"stub LLM on http://127.0.0.1:{args.port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
