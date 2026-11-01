# 8. Use callai from Python

`callai.run()` runs a harness from Python and returns the same result as `-o json`. An optional
callback receives the stream events as they happen.

**You'll need:** callai installed in your Python environment ([Installation](../getting-started/installation.md)).

## Run and read the result

```python
import callai

result = callai.run("claude-code", "Reply with exactly: pong")
print(result.text, result.is_error, result.exit_code)
print(result.session_id is not None, result.usage)
```

```text
pong False 0
True {'input_tokens': 11, 'output_tokens': 2}
```

`result` is a frozen `callai.Result` with the same fields as the `-o json` object. `result.to_dict()`
gives that object.

## Pass options

The CLI's options become keyword arguments:

```python
result = callai.run(
    "codex",
    "Fix the failing test",
    model="gpt-5-codex",
    cwd="/path/to/repo",
    timeout=600,
    permission="auto",
    system_prompt="Keep changes minimal.",
    extra_args=["--ephemeral"],
)
```

## Continue the conversation

```python
again = callai.run("claude-code", "And again?", resume=result.session_id)
print(again.session_id == result.session_id)
```

```text
True
```

## Watch events

```python
import callai

def show(event):
    print(event["type"], event.get("text", ""))

callai.run("codex", "Reply with exactly: pong", on_event=show)
```

```text
start 
text pong
result pong
```

`on_event` receives the same dicts that `-o stream-json` prints, in order, from a background thread.
With it, the harness runs in its streaming mode.

## Handle failures

A harness that runs but fails returns a result with `is_error=True`. An exception means the run
couldn't start or finish:

```python
import callai

try:
    callai.run("codex", "hi", binary="/nonexistent/codex")
except callai.HarnessNotFound as exc:
    print("not installed:", exc)

result = callai.run("claude-code", "hi", model="not-a-real-model-xyz")
print(result.is_error, result.exit_code)
```

```text
not installed: harness binary '/nonexistent/codex' not found on PATH (needed for --name codex); install it: https://developers.openai.com/codex/cli
True 1
```

| Exception | When |
|---|---|
| `callai.UsageError` | Bad argument, or an option the harness can't honour |
| `callai.HarnessNotFound` | The binary isn't on `PATH` |
| `callai.HarnessTimeout` | `timeout` expired; the harness was killed |
| `callai.Interrupted` | Ctrl-C |

All four are subclasses of `callai.CallaiError`.

## Differences from the CLI

`callai.run()` ignores `CALLAI_*` environment variables and the config file, so a call does the same
thing on every machine. Pass everything explicitly. Model aliases are a CLI feature: `model=` is sent
as is. Use `binary=` to run a specific executable.

## Recap

- `callai.run(harness, prompt, **options)` → `Result`, the same as `-o json`.
- `on_event=` receives stream events; `resume=` continues a session.
- Failed runs are results; exceptions mean the run couldn't happen.

Reference: [Python API](../reference/python-api.md)

Previous: [7. Set your defaults](07-defaults.md) · Up: [Tutorial](README.md) · Next: [How-to guides](../guides/README.md)
