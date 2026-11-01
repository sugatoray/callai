# 3. Control what the agent may do

`--permission` sets one level (`read-only`, `auto` or `bypass`) that callai translates into each
harness's own flags.

**You'll need:** [step 2](02-json-output.md).

## The four levels

| Level | Intent |
|---|---|
| `default` | Add nothing: the harness's own default applies. |
| `read-only` | Read and search files; no writes, no shell. |
| `auto` | Edit files in the working directory without asking. |
| `bypass` | Run every tool call without asking, shell included. |

## See what a level turns into

```bash
callai -n codex -p "Fix the failing test" --permission read-only --dry-run
callai -n codex -p "Fix the failing test" --permission auto --dry-run
callai -n pi -p "Fix the failing test" --permission auto --dry-run
```

```text
codex exec --json --skip-git-repo-check --sandbox read-only -- 'Fix the failing test'
codex exec --json --skip-git-repo-check --sandbox workspace-write -- 'Fix the failing test'
pi --mode json --tools read,grep,find,ls,edit,write --no-mcp -- 'Fix the failing test'
```

codex uses its sandbox. pi gets a tool allowlist: read and search tools, plus `edit` and `write`, but
no shell.

## When a harness can't honour a level

callai refuses instead of running with more access than you asked for:

```bash
callai -n opencode -p "Fix the failing test" --permission read-only
```

```text
callai: error: --permission read-only: opencode has no read-only mode (its plan agent still allows shell commands); pass `-- --agent plan` yourself if that is acceptable
```

The exit code is 2, and nothing ran. Some refusals mention a harness flag you can pass yourself after
`--` if its behaviour is acceptable to you.

## What each level really allows

callai's levels were checked by running scripted tool calls (file writes and shell commands, inside
and outside the working directory) against every harness:

| Level | claude-code | codex | opencode | pi | grok | hermes |
|---|---|---|---|---|---|---|
| `read-only` | plan mode: no writes, no shell | read-only sandbox | refused | read tools only | read tools only | refused |
| `auto` | edits inside the workspace | writes inside the workspace (sandboxed shell) | refused | file writes/edits, no shell | file writes/edits, no shell | file writes/edits, no shell |
| `bypass` | everything | everything | everything | everything | everything | everything |

> [!WARNING]
> With `default`, opencode, pi and hermes already write files and run shell commands without asking.
> claude-code, codex and grok don't. If an unattended run must not change anything, ask for
> `read-only` explicitly.

> [!CAUTION]
> grok's `auto` and `bypass` can write **outside** the working directory. To confine grok to the
> workspace, add its sandbox yourself (Linux needs bubblewrap):
> `callai -n grok -p "…" --permission auto -- --sandbox workspace`.
> See [Permissions](../concepts/permissions.md#grok-and-the-working-directory).

## `bypass` warns you

```bash
callai -n codex -p "Reply with exactly: pong" --permission bypass
```

```text
callai: warning: --permission bypass: codex will run every tool call without asking, including shell commands and writes outside the working directory.
pong
```

The warning goes to stderr, so it doesn't mix into the answer.

## Recap

- One flag, four levels, translated per harness; `--dry-run` shows the translation.
- A level a harness can't honour is refused with exit 2. callai never quietly grants more access.
- `default` means the harness's own default, which for some harnesses is permissive.

Reference: [`--permission`](../reference/cli.md#--permission-level) · Concept: [Permissions](../concepts/permissions.md)

Next: [4. Watch a run as it happens](04-streaming.md) · Previous: [2. Get machine-readable output](02-json-output.md)
