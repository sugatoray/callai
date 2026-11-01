# How to build a live progress view

Use this to show what a coding agent is doing while it works: tool calls, their results and its
messages. It works for a terminal, a log or a UI.

## From Python, with `on_event`

```python
import callai


def show(event):
    kind = event["type"]
    if kind == "start":
        print(f"▶ {event['harness_name']} started")
    elif kind == "tool_use":
        print(f"  ⚙ {event['name']} {event['input']}")
    elif kind == "tool_result":
        status = "✗" if event["is_error"] else "✓"
        print(f"  {status} {event['output'][:60]!r}")
    elif kind == "text":
        print(f"  💬 {event['text']}")
    elif kind == "result":
        print(f"■ done in {event['duration_ms']} ms, error={event['is_error']}")


result = callai.run("claude-code", "Say hi.", permission="bypass", on_event=show)
```

```text
▶ claude-code started
  ⚙ Bash {'command': 'echo hi'}
  ✓ 'hi'
  💬 pong
■ done in 834 ms, error=False
```

The callback runs on a background thread, once per event, in order. Keep it quick, or hand events to
a queue.

## From any language, with `-o stream-json`

Read stdout line by line. Each line is one JSON object, flushed as it happens:

```python
import json
import subprocess

proc = subprocess.Popen(
    ["callai", "-n", "codex", "-p", "Reply with exactly: pong", "-o", "stream-json"],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True,
)
for line in proc.stdout:
    event = json.loads(line)
    print(event["type"], event.get("text", ""))
proc.wait()
print("exit", proc.returncode)
```

```text
start 
text pong
result pong
exit 0
```

## Things to handle

- **Text arrives in pieces for some harnesses** (pi, grok) and as whole messages for others. Append
  `text` events as they arrive; the final answer is in the `result` event.
- **hermes has no event stream:** you get `start` and `result` only.
- **No `result` event:** callai stopped the run (timeout 124, Ctrl-C 130). Use the exit code.
- **Several harnesses:** with `-n a/b`, events from all of them interleave. Group by `harness_name`,
  which every event carries in fan-out mode.

See also: [4. Watch a run as it happens](../tutorial/04-streaming.md) · [Stream events reference](../reference/output.md#-o-stream-json)
