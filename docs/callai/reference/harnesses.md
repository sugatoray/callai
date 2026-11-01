# Harnesses reference

Exactly how callai invokes each harness, and what each one supports. Every row was verified against the
real CLI at the version shown. `--dry-run` prints the full command for any combination.

## Summary

| `-n` | Binary | Base command | Model flag | Output mode used | Verified with |
|---|---|---|---|---|---|
| `claude-code` | `claude` | `claude -p --output-format json -- PROMPT` | `--model M` | one JSON object | claude 2.1.314 (and live) |
| `codex` | `codex` | `codex exec --json --skip-git-repo-check -- PROMPT` | `--model M` | JSON lines | codex-cli 0.166.0 |
| `opencode` | `opencode` | `opencode run --format json --print-logs --log-level ERROR -- WORDS…` | `--model provider/model` | JSON lines | opencode 1.19.5 |
| `pi` | `pi` | `pi --mode json -- PROMPT` | `--model provider/id` | JSON lines | pi 1.4.0 |
| `hermes` | `hermes` | `hermes chat -Q --source tool --query=PROMPT` | `-m M` (provider from hermes's config) | plain text | hermes-agent 0.19.0 |
| `grok` | `grok` | `grok --output-format json --single=PROMPT` | `--model M` | one JSON object | grok 1.0.70 |

## Permission flags

| `--permission` | claude-code | codex | opencode | pi | hermes | grok |
|---|---|---|---|---|---|---|
| `default` | — | — | — | — | — | — |
| `read-only` | `--permission-mode plan` | `--sandbox read-only` | refused | `--tools read,grep,find,ls --no-mcp` | refused | `--tools read_file,grep,list_dir --disallowed-tools search_tool,use_tool` |
| `auto` | `--permission-mode acceptEdits` | `--sandbox workspace-write` | refused | `--tools read,grep,find,ls,edit,write --no-mcp` | `-t file` | `--allow Write --allow Edit` |
| `bypass` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` | — (pi's default already allows everything) | `--yolo` | `--permission-mode bypassPermissions` |

What these really allow: [Permissions](../concepts/permissions.md#verified-behaviour).

## Session flags

| | claude-code | codex | opencode | pi | hermes | grok |
|---|---|---|---|---|---|---|
| `--resume ID` | `--resume ID` | `exec … resume ID -- PROMPT` | `--session ID` | `--session ID` | `--resume ID` | `--resume=ID` |
| `--continue` | `--continue` | `exec … resume --last -- PROMPT` | `--continue` | `--continue` | refused | `--continue` |

codex's `resume` subcommand rejects `--sandbox`. callai puts exec's own options (including `--sandbox`
and `extra_args`) before `resume`, so they still apply to the resumed run.

## Other options

| | claude-code | codex | opencode | pi | hermes | grok |
|---|---|---|---|---|---|---|
| `--system-prompt S` | `--system-prompt S` | `-c developer_instructions="S"` | refused | `--system-prompt S` | env `HERMES_EPHEMERAL_SYSTEM_PROMPT` | `--system-prompt-override S` |
| `-o stream-json` | `--output-format stream-json --verbose` | unchanged | unchanged | unchanged | unchanged (no events) | `--output-format streaming-json` |
| Refused prompts | — | — | — | starts with `@` | — | starts with `/` |
| Reports model used | yes | no | no | yes | no | yes |
| Reports tokens / cost | yes / yes | yes / no | yes / yes | yes / yes | no / no | yes / no |

## Per-harness notes

### claude-code

`claude -p` with JSON output. `is_error` comes from claude's `is_error`, not `subtype`: claude reports
`"subtype": "success"` alongside `"is_error": true` for an unknown model. Run as root, claude refuses
`bypass` unless you set `IS_SANDBOX=1`. Install: <https://code.claude.com/docs/en/setup>.

### codex

`codex exec --json`. The answer is the last `agent_message` item, and a failure is `turn.failed` or
a non-zero exit. `error` items such as "model metadata not found" are warnings, not failures.
`--skip-git-repo-check` lets codex run outside a git repository. Install: <https://developers.openai.com/codex/cli>.

### opencode

`opencode run --format json`. The prompt is passed as separate words, because opencode quotes any
argument containing a space. `--print-logs --log-level ERROR` puts the real failure reason on stderr,
which callai reports. In `opencode run`, `-p` means password and `-c` means continue: pass harness
flags after `--` with care. Install: <https://opencode.ai/docs/>.

### pi

`pi --mode json`. pi exits 0 even when the model call fails, so failure comes from the assistant
message's `stopReason`. A prompt starting with `@` would be read as a file to attach, so callai refuses
it. Install: <https://pi.dev/docs/latest/quickstart>.

### hermes

`hermes chat -Q --source tool`, not `hermes -z`, which approves every tool call. The answer is stdout
without hermes's display lines (those end in `\r\n`), and the session id comes from stderr.
`--source tool` keeps callai's runs out of your session list, which is also why hermes `--continue`
can't find them. It has no read-only toolset, and it reports no tokens or cost. Install:
<https://hermes-agent.nousresearch.com/docs/>.

### grok

xAI's official Grok Build CLI (`@xai-official/grok`). The prompt goes in one final `--single=PROMPT`
element, because `-p` has no `--` escape. A prompt starting with `/` is run as a slash command, even
after spaces, so callai refuses it. A refused tool call exits 0 with `stopReason: cancelled`, which
callai reports as an error (exit 1). Install: <https://x.ai/cli>.

> [!WARNING]
> `@vibe-kit/grok-cli` (superagent-ai) also installs a `grok` command with different flags. callai
> doesn't support it.

See also: [Add a new harness](../guides/add-a-harness.md) · [Installation](../getting-started/installation.md)
