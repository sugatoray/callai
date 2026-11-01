# 5. Continue a conversation

Every run reports a `session_id`. Pass it to `--resume` to continue that conversation, or use
`--continue` for the harness's most recent one.

**You'll need:** [step 2](02-json-output.md).

## Resume by id

```bash
SID=$(callai -n claude-code -p "Reply with exactly: pong" -o json < /dev/null | jq -r .session_id)
callai -n claude-code -p "And again?" --resume "$SID" -o json < /dev/null | jq --arg sid "$SID" '.text, .session_id == $sid'
```

```text
"pong"
true
```

The second run carries the first run's turns: the model sees the whole conversation. The run reports
the same `session_id`.

`--dry-run` shows the harness's own flag:

```bash
callai -n claude-code -p "And again?" --resume SESSION_ID --dry-run
```

```text
claude -p --output-format json --resume SESSION_ID -- 'And again?'
```

Each harness spells it differently, and callai maps it for you:

| Harness | `--resume ID` | `--continue` |
|---|---|---|
| claude-code | `--resume ID` | `--continue` (most recent in this directory) |
| codex | `exec … resume ID -- PROMPT` | `exec … resume --last -- PROMPT` |
| opencode | `--session ID` | `--continue` |
| pi | `--session ID` | `--continue` |
| hermes | `--resume ID` | refused, see below |
| grok | `--resume=ID` | `--continue` (most recent for this directory) |

This was checked with each real harness: the resumed request contains the earlier turns.

## Continue the most recent session

```bash
callai -n codex -p "Now add a test for it" --continue
```

"Most recent" is the harness's own idea of it, which usually means the most recent in the current
directory. If several things use the same harness in the same place, prefer `--resume` with an id.

> [!NOTE]
> **hermes refuses `--continue`.** `hermes chat --continue` only looks at interactive sessions, never
> at the non-interactive ones callai starts, so it would continue a different conversation. Use
> `--resume` with the `session_id` callai reported:
>
> ```text
> callai: error: --continue: hermes only continues its most recent interactive session, not callai's runs; use --resume with the session_id callai reported
> ```

## Rules

- `--resume` and `--continue` can't be combined.
- There's no `-c` short form for `--continue`, because `-c` already means `--command` (the prompt).
- A session id can't start with `-`, because the harness would read it as an option.
- Permissions apply to every run, resumed or not. For codex, callai checked that a resumed run gets
  the sandbox you ask for this time.

## Recap

- `session_id` from `-o json` → `--resume ID` continues that conversation.
- `--continue` picks the harness's latest session (not for hermes).

Reference: [`--resume`](../reference/cli.md#--resume-session_id) · [`--continue`](../reference/cli.md#--continue)

Next: [6. Ask several harnesses at once](06-fan-out.md) · Previous: [4. Watch a run as it happens](04-streaming.md)
