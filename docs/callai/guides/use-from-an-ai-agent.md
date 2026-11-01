# How to call callai from an AI agent

Use this when an agent or orchestrator hands work to another coding agent (a "sub-agent") and needs a
reliable answer and status back.

## The safe invocation

```bash
callai -n codex -p "TASK" -o json --permission read-only --timeout 600 -C /path/to/repo < /dev/null
```

| Part | Why |
|---|---|
| `-o json` | One object to parse: `text`, `is_error`, `exit_code`, `session_id`. |
| `--permission read-only` | Choose the level explicitly. The default is the harness's own, which for opencode, pi and hermes already allows writes and shell. Use `auto` when the sub-agent should edit files. |
| `--timeout 600` | A stuck harness is killed, with everything it started (exit 124). |
| `-C /path/to/repo` | The directory the sub-agent works in. |
| `< /dev/null` | Your agent's stdin may be an open, silent pipe. callai would otherwise wait 3 seconds for it, then warn. |

## Decide what happened

Branch on the exit code first, then on the JSON:

| Exit code | Meaning | What the agent should do |
|---|---|---|
| `0` | Success | Use `text`. |
| `2` | Usage error; nothing ran | Read stderr. Fix the call (e.g. that harness can't do `read-only`). Don't retry as is. |
| `124` | Timed out | Retry with a longer `--timeout` or a smaller task. |
| `127` | Harness not installed | Pick another harness (`callai --list-harnesses -o json`). |
| `130` | Interrupted | Stop. |
| other | The harness failed | `is_error` is true. `text` is the reason (e.g. a bad model name). |

## From Python

```python
import json
import subprocess

proc = subprocess.run(
    ["callai", "-n", "codex", "-p", "Reply with exactly: pong", "-o", "json",
     "--permission", "read-only", "--timeout", "600"],
    stdin=subprocess.DEVNULL, capture_output=True, text=True,
)
if proc.returncode == 2:
    raise ValueError(proc.stderr.strip().splitlines()[-1])   # the "callai: error: ..." line
result = json.loads(proc.stdout) if proc.stdout else None
print(proc.returncode, result and result["text"])
```

```text
0 pong
```

Or skip the subprocess and use [`callai.run()`](../reference/python-api.md), which raises `UsageError`,
`HarnessNotFound` or `HarnessTimeout` instead of returning those exit codes.

## Patterns

**Keep a sub-agent's context across steps:** save `session_id` and pass `--resume`:

```bash
callai -n claude-code -p "Read src/ and summarise the architecture" -o json < /dev/null > step1.json
callai -n claude-code -p "Now list the riskiest module" --resume "$(jq -r .session_id step1.json)" -o json < /dev/null
```

**Get a second opinion:** run several harnesses on the same question and compare the answers:

```bash
callai -n claude-code/codex -p "Is this migration safe? $(cat migration.sql)" -o json < /dev/null \
  | jq -r '.results[] | "\(.harness_name): \(.text)"'
```

**Follow long runs:** use `-o stream-json` and read line by line; see
[Build a live progress view](live-progress.md).

## Instructions to give your agent

Paste this into the agent's instructions (e.g. `AGENTS.md` or `CLAUDE.md`) and adjust the harnesses and
levels:

```markdown
## Delegating to other coding agents

Use `callai` to run a prompt through another coding agent:

    callai -n <claude-code|codex|opencode|pi|hermes|grok> -p "<task>" -o json --permission <read-only|auto> --timeout 900 -C <dir> < /dev/null

- Parse stdout as JSON: `text` is the answer, `is_error` says whether it failed, `session_id` continues
  the conversation with `--resume <id>`.
- Exit 2 means the call was invalid and nothing ran: read stderr and fix the call. 124 = timed out,
  127 = harness not installed.
- Never use `--permission bypass` unless the user asked for it.
- `callai --dry-run ...` shows the exact command without running it.
```

## Troubleshooting

- **It waits 3 seconds before starting:** stdin is an open pipe. Add `< /dev/null`, or set
  `CALLAI_STDIN_WAIT=0`.
- **`--permission read-only` is refused:** opencode and hermes have no read-only mode. Pick another
  harness, or accept their default knowingly.
- **The answer is empty and `is_error` is true:** read `text` (the harness's error) and callai's
  stderr, where the harness's own stderr is copied on failure.

See also: [Use callai in scripts and CI](scripts-and-ci.md) · [Exit codes and errors](../reference/errors.md) · [Permissions](../concepts/permissions.md)
