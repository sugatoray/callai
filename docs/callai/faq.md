# FAQ and troubleshooting

Short answers to common questions and problems.

## Questions

### Which harness should I use?

The one you already have access to. callai doesn't change what a harness can do; it gives them all the
same interface. To compare them on your own task, run them all:
[Compare harnesses side by side](guides/compare-harnesses.md).

### Does callai send my code or prompts anywhere?

No. callai talks only to the harness CLI on your machine. The harness talks to its model provider, as
it would without callai.

### Does callai handle API keys or sign-in?

No. Each harness uses its own configuration (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`, a
signed-in session, …), which callai passes through unchanged.

### Does callai retry, rewrite prompts or add system instructions?

No. It adds only what your flags ask for, and `--dry-run` shows exactly what will run. It doesn't
retry, because a retry might repeat side effects the agent already had.

### Why is `model` null in my JSON?

You didn't pass `-m`, and the harness (codex, opencode, hermes) doesn't report which model it used.
claude, pi and grok report it.

### Why does `-n all --permission read-only` skip some harnesses?

opencode and hermes have no read-only mode. Rather than run them with more access than you asked
for, `-n all` skips them and says so on stderr. An explicit list (`-n codex/opencode`) stops with an
error instead.

### Can I run the same harness with two different models at once?

Not with one `-n`: it lists harnesses, not models. Start two `callai` processes, or use
`callai.run()` from two threads.

### Is there a TypeScript or Rust version?

Not yet. A TypeScript port is planned, and both will be checked against the same
[conformance suite](../../conformance/README.md).

## Problems

### callai waits 3 seconds before starting

Your stdin is a pipe with nothing on it, which happens when a script or agent runs callai. With `-p`,
callai waits up to 3 seconds for piped input, then warns and continues. Add `< /dev/null`, or set
`CALLAI_STDIN_WAIT=0`.

### callai seems to hang

- Without `-p` (or with `-p -`), the prompt *is* stdin, so callai waits until the pipe closes. Pass
  `-p` or close the pipe.
- The agent may simply be working. Use `-v` to see its stderr live, or `-o stream-json` to see its
  steps. Use `--timeout` to put a limit on it.

### callai hangs on Windows when run from a script

On Windows, the 3-second stdin wait doesn't work on pipes, so `callai -p TEXT` with an open, silent
stdin waits until the pipe closes. Give it an empty stdin that closes, e.g. in `cmd.exe`:
`callai -n codex -p "…" < NUL`. (This case isn't tested on Windows yet.)

### "harness binary … not found on PATH" (exit 127)

Install the harness ([Installation](getting-started/installation.md)). If it's installed somewhere
unusual, set `[harnesses.<name>] binary = "/path/to/it"`. `callai --list-harnesses` shows what callai
finds.

### "--permission read-only: … has no read-only mode" (exit 2)

That harness can't honour the level ([Permissions](concepts/permissions.md#failing-closed)). Choose
another harness, or the alternative the message suggests.

### The answer is empty and `is_error` is true

The harness ran but failed. `text` has its reason, and callai's stderr has the harness's own stderr.
Common causes: a model name the harness doesn't know, a missing API key, or a tool call refused
because you didn't grant the permission.

### claude says `--dangerously-skip-permissions cannot be used with root/sudo privileges`

You're running as root with `--permission bypass`. claude refuses that unless `IS_SANDBOX=1` is set in
the environment. callai deliberately doesn't set it for you.

### grok wrote a file outside my project

grok's `auto` and `bypass` aren't limited to the working directory. Add its sandbox:
`callai -n grok … --permission auto -- --sandbox workspace` (Linux needs bubblewrap). See
[Permissions](concepts/permissions.md#grok-and-the-working-directory).

### hermes `--continue` is refused

hermes only continues interactive sessions, not the ones callai starts. Use
`--resume <session_id>` from the previous run's JSON.

### A harness updated and callai broke

callai was verified against specific harness versions (see [Harnesses](reference/harnesses.md#summary)).
Run `callai --dry-run …` and the harness's own `--help` to see what changed. From the project folder,
`make install.<harness>` reinstalls the verified version. Please report what changed.

See also: [Exit codes and errors](reference/errors.md)
