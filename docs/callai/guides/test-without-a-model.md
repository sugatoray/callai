# How to test without a real model

Use this to test code that calls callai without spending tokens or needing network access. There are
two levels, depending on what you need to be real.

## Level 1: a fake harness binary

Your tests don't need a harness at all, just something that prints what a harness prints. Point callai
at a script that replays recorded output:

```bash
cat > fake-codex <<'EOF'
#!/bin/sh
cat <<'OUT'
{"type":"thread.started","thread_id":"t-1"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"pong"}}
{"type":"turn.completed","usage":{"input_tokens":11,"output_tokens":2}}
OUT
EOF
chmod +x fake-codex
```

```python
import callai

result = callai.run("codex", "anything", binary="./fake-codex")
print(result.text, result.session_id, result.usage)
```

```text
pong t-1 {'input_tokens': 11, 'output_tokens': 2}
```

From the CLI, set the binary in a test config file:

```toml
# test-callai.toml, used with CALLAI_CONFIG=test-callai.toml
[harnesses.codex]
binary = "./fake-codex"
```

Real recorded outputs for every harness, including failures, are in
[`conformance/parse/`](../../../conformance/parse/). Replaying one tests your code against exactly what
that harness prints.

## Level 2: real harnesses, stub model

To test the harness too (its flags, tools and permissions), keep the real harness CLI and replace only
the model. [`conformance/tools/stub_llm_server.py`](../../../conformance/tools/stub_llm_server.py) is a
local stub that speaks the OpenAI Responses, OpenAI Chat Completions and Anthropic Messages APIs:

```bash
python3 conformance/tools/stub_llm_server.py --port 8765 --reply pong
```

Then point each harness at `http://127.0.0.1:8765`. For example, claude:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8765 ANTHROPIC_API_KEY=stub callai -n claude-code -m stub-model -p "Say hi."
```

```text
pong
```

The other harnesses are configured through their provider settings. The exact settings for codex,
opencode, pi, hermes and grok are in the
[conformance README](../../../conformance/README.md), under "Recording without network or API keys".

The stub can also script a tool call, so you can test what a permission level really allows:

```bash
python3 conformance/tools/stub_llm_server.py --port 8765 \
  --tool-call '{"name": "Bash", "arguments": {"command": "echo hi"}}'
```

The stub returns that call to the first request that offers tools, and plain text once the harness
sends the tool's result back. It replies with text, not a new tool call, to any request that already
contains a tool result.

> [!TIP]
> Run claude against the stub with a clean environment (`env -i PATH="$PATH" HOME=…`), so your own
> `ANTHROPIC_*` or `CLAUDE_*` variables don't leak in.

See also: [Use callai in scripts and CI](scripts-and-ci.md) · [Python API](../reference/python-api.md)
