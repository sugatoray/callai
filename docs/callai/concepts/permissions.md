# Permissions

`--permission` gives every harness the same four levels, maps each to that harness's own controls,
and refuses any level a harness can't honour.

## The levels

| Level | Intent | What callai adds |
|---|---|---|
| `default` | The harness's own default | Nothing |
| `read-only` | Read and search, no writes, no shell | The harness's read-only mode or a read-only tool list |
| `auto` | Edit files in the working directory without asking | Its "accept edits" mode, sandbox or a file-tool list |
| `bypass` | Run every tool call without asking | Its "skip all permissions" flag, with a warning on stderr |

## Verified behaviour

Each cell was checked by running the real harness against a stub model that asked it to write a file
and run a shell command, both inside and outside the working directory, and observing what happened:

| Level | claude-code | codex | opencode | pi | grok | hermes |
|---|---|---|---|---|---|---|
| `read-only` | plan mode: no writes, no shell | read-only sandbox | **refused** | read tools only | read tools only | **refused** |
| `auto` | edits inside the workspace | writes inside the workspace (sandboxed shell) | **refused** | file writes/edits, no shell | file writes/edits, no shell | file writes/edits, no shell |
| `bypass` | everything | everything | everything | everything | everything | everything |

The flags behind each cell are in the [Harnesses reference](../reference/harnesses.md).

## The default isn't the same everywhere

With `default`, **opencode, pi and hermes write files and run shell commands without asking**.
claude-code, codex and grok ask, and since no one is there to answer, the call is refused. A refused
tool call doesn't fail the run: the model is told the tool was refused and carries on. For unattended
runs, always choose a level explicitly.

## Failing closed

When a harness has no way to honour a level, callai refuses with exit 2 before running anything:

- **opencode** has no read-only mode: its `plan` agent still allows shell commands. It has no
  "accept edits only" mode either: `--auto` approves everything.
- **hermes** has no read-only toolset: its `file` toolset can write.

The error message tells you what the harness *can* do (e.g. `-- --agent plan` for opencode), so you
can choose it deliberately. The same rule covers other options: a `--system-prompt` that opencode
can't take, or a `--continue` that hermes would apply to the wrong session.

## grok and the working directory

callai's `auto` for grok allows file writes and edits but no shell. grok writes them **anywhere** the
user can write, not just in the working directory. (codex's `auto` is sandboxed to the workspace.)

callai doesn't add grok's sandbox automatically. On Linux it needs
[bubblewrap](https://github.com/containers/bubblewrap), and grok refuses to start without it, so adding it
would break `auto` on machines that don't have it. Opt in:

```bash
sudo apt install -y bubblewrap                                                # Linux, once
callai -n grok -p "Fix the failing test" --permission auto -- --sandbox workspace
GROK_SANDBOX=workspace callai -n grok -p "Fix the failing test" --permission auto
```

All of grok's sandbox profiles, `read-only` and `strict` included, still allow writes inside the
working directory. Use callai's `--permission read-only` when you need read-only.

## Running as root

claude refuses `bypass` when run as root, unless `IS_SANDBOX=1` is set. callai never sets it for you:
setting it is your decision about your environment.

See also: [3. Control what the agent may do](../tutorial/03-permissions.md) · [`--permission` reference](../reference/cli.md#--permission-level)
