# Why callai

callai gives every coding-agent CLI the same non-interactive interface, so you can switch harnesses
or use several without rewriting the code that calls them.

## The problem

Each coding agent can run a single prompt without a chat window. They all do it differently:

| You want | claude | codex | opencode | grok |
|---|---|---|---|---|
| Run one prompt | `claude -p -- P` | `codex exec -- P` | `opencode run -- P` | `grok --single=P` |
| JSON output | `--output-format json` (one object) | `--json` (event lines) | `--format json` (event lines) | `--output-format json` (one object) |
| Read-only | `--permission-mode plan` | `--sandbox read-only` | none | `--tools read_file,grep,list_dir …` |
| Continue a session | `--resume ID` | `exec … resume ID` | `--session ID` | `--resume=ID` |
| Where the answer is | `.result` | last `agent_message` item | `text` parts | `.text` |

Each harness also has its own edge cases:
- a prompt starting with `-` can be taken as a flag;
- grok runs a prompt starting with `/` as a slash command;
- opencode wraps any argument containing a space in quotes before sending it;
- hermes prints tool previews mixed into the answer;
- some harnesses read your stdin, so a script's open pipe can stall them.

Code that drives one harness doesn't carry over to the next.

## What callai does

You write the call once:

```bash
callai -n codex -p "Fix the failing test" --permission auto -o json
```

callai builds the exact command line for the harness you chose, runs it with no prompts and no
interactive input, and turns whatever it prints into the same result:

```json
{"harness_name": "codex", "text": "…", "is_error": false, "exit_code": 0, "session_id": "…", "usage": {"input_tokens": 11, "output_tokens": 2}, "…": "…"}
```

Change `-n codex` to `-n grok` and nothing else changes, including the JSON your code reads.

## When to use it

- **Scripts and CI** that call a coding agent and need a reliable answer and exit code.
- **AI agents and orchestrators** that hand subtasks to other agents and parse the result.
- **Comparing harnesses or models** on the same prompt (`-n all`).
- **Not being locked in**: switch harness with one flag.

## When you don't need it

- You only ever use one harness interactively: use that harness directly.
- You need a harness feature callai doesn't model: pass it through after `--`
  (`callai -n opencode -p "…" -- --agent build`), or call the harness itself.
- You want an SDK for building agents (tools, memory, planning). callai drives existing agent CLIs; it
  doesn't build new ones.

## Design principles

- **Thin.** callai adds no behaviour of its own between you and the harness: no retries, no prompt
  rewriting, no hidden flags. `--dry-run` prints exactly what will run.
- **Fail closed.** If a harness can't honour an option, callai refuses (exit 2) instead of running with
  more access or quietly ignoring it.
- **Verified.** Every adapter is checked against the real harness CLI, and every permission level by
  scripted tool calls. A shared conformance suite pins the behaviour.
- **No dependencies.** Python standard library only.

Next: [Installation](installation.md) · See also: [Architecture](../concepts/architecture.md)
