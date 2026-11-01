# 2. Get machine-readable output

`-o json` returns one normalised result object, and the exit code tells you whether the run worked.

**You'll need:** [step 1](01-first-prompt.md).

## One JSON object

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

callai prints it on one line; it's spread out here for reading. The fields you'll use most:

| Field | Meaning |
|---|---|
| `text` | The final answer, or the error message when `is_error` is true. |
| `is_error` | Whether the run failed: from the harness's own error signal, or a non-zero exit. |
| `exit_code` | The harness's exit code. |
| `session_id` | Pass it to `--resume` to continue the conversation ([step 5](05-sessions.md)). |
| `usage` | Tokens, with `input_tokens` counting cache reads and writes too. `null` if unknown. |
| `model` | The model the harness says it used, else the one you asked for. |

Every field is described in the [output reference](../reference/output.md#-o-json).

## Use it in a script

```bash
answer=$(callai -n codex -p "Reply with exactly: pong" -o json < /dev/null | jq -r .text)
echo "$answer"
```

```text
pong
```

Redirect stdin (`< /dev/null`) in scripts. With `-p`, callai waits up to 3 seconds for piped input
when stdin is a pipe with nothing on it. This happens when a script or agent runs callai with an open,
silent stdin. It then warns and carries on, but the redirect skips the wait.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The harness succeeded. |
| harness's own | The harness failed with that code; `is_error` is `true`. |
| `1` | The harness reported an error but exited 0 (e.g. grok refusing a tool call). |
| `2` | Usage error: bad flag, no prompt, an option the harness can't honour. Nothing ran. |
| `124` | `--timeout` expired; the harness and everything it started were killed. |
| `127` | The harness isn't installed. |
| `130` | Interrupted with Ctrl-C. |

A failure still prints a result with `-o json`:

```bash
callai -n claude-code -m not-a-real-model-xyz -p hi -o json
echo "exit=$?"
```

```text
{"harness_name": "claude-code", "model": "not-a-real-model-xyz", "text": "There's an issue with the selected model (not-a-real-model-xyz). It may not exist or you may not have access to it. Run --model to pick a different model.", "exit_code": 1, "is_error": true, …}
exit=1
```

The harness's own stderr is shown on callai's stderr when a run fails. Add `-v` to see it live
on every run.

## Raw output

`-o raw` skips parsing and prints the harness's own stdout and stderr unchanged, byte for byte. It's
useful for debugging an adapter, and nothing else.

## Recap

- `-o json` gives the same object for every harness; `text` and `is_error` are the essentials.
- Check the exit code: `2` means nothing ran, `124` timeout, `127` not installed.
- Use `< /dev/null` when a script runs callai.

Reference: [Output formats](../reference/output.md) · [Exit codes and errors](../reference/errors.md)

Next: [3. Control what the agent may do](03-permissions.md) · Previous: [1. Run your first prompt](01-first-prompt.md)
