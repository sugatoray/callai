# Quickstart

Run a prompt, get JSON back, and see exactly what callai runs, in five minutes.

**You'll need:** callai and at least one harness installed and signed in ([Installation](installation.md)).
The examples use `codex`; any `-n` name works.

## 1. Ask something

```bash
callai -n codex -p "Reply with exactly: pong"
```

```text
pong
```

Only the answer is printed. Tool previews, banners and progress output are removed. The exit code is
the harness's own: `0` here.

## 2. Get JSON

```bash
callai -n codex -p "Reply with exactly: pong" -o json
```

```json
{
  "harness_name": "codex",
  "model": null,
  "text": "pong",
  "exit_code": 0,
  "is_error": false,
  "duration_ms": 6979,
  "session_id": "01a19506-c5ee-7893-ab89-d0f6b04924a4",
  "usage": {"input_tokens": 11, "output_tokens": 2},
  "cost_usd": null,
  "argv": ["codex", "exec", "--json", "--skip-git-repo-check", "--", "Reply with exactly: pong"]
}
```

The same keys come back for every harness. A value the harness doesn't report is `null`: `model` is
`null` here because no `-m` was given and codex doesn't report the model it used. `argv` is the exact
command that ran.

## 3. See the command without running it

```bash
callai -n claude-code -m haiku -p "Explain main.py" --permission auto --dry-run
```

```text
claude -p --output-format json --model haiku --permission-mode acceptEdits -- 'Explain main.py'
```

`--dry-run` doesn't need the harness to be installed. Use it to check what a flag turns into.

## 4. Pipe something in

```bash
git diff | callai -n codex -p "Review this diff"
```

Piped text is appended to the prompt after a blank line. With no `-p` at all, the piped text *is* the
prompt.

## 5. Try another harness

```bash
callai -n claude-code -p "Reply with exactly: pong"
callai -n claude-code/codex -p "Reply with exactly: pong"      # both, at the same time
```

```text
pong
== claude-code ==
pong
== codex ==
pong
```

## Where next

- Learn everything step by step: [Tutorial](../tutorial/README.md).
- Calling callai from another agent? [Call callai from an AI agent](../guides/use-from-an-ai-agent.md).
- Look up a flag: [Command line reference](../reference/cli.md).

Previous: [Installation](installation.md)
