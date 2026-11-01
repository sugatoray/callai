# Tutorial

A step-by-step path through callai, from the first prompt to fan-out and the Python API.

Each step builds on the one before and takes a few minutes. Every command can be pasted into a
terminal as-is, and each one shows its real output. Read in order the first time; afterwards, the
[Reference](../reference/README.md) is quicker for looking things up.

**You'll need:** callai and at least one harness installed and signed in. See
[Installation](../getting-started/installation.md). Most steps use `codex` or `claude-code`, but any
harness works; where one behaves differently, the step says so.

1. [Run your first prompt](01-first-prompt.md): choose a harness, pass a prompt, read the answer.
2. [Get machine-readable output](02-json-output.md): `-o json`, exit codes and using the result in scripts.
3. [Control what the agent may do](03-permissions.md): `--permission` levels.
4. [Watch a run as it happens](04-streaming.md): `-o stream-json` events.
5. [Continue a conversation](05-sessions.md): `--resume` and `--continue`.
6. [Ask several harnesses at once](06-fan-out.md): `-n a/b/c`, `-n a,b,c`, `-n all`.
7. [Set your defaults](07-defaults.md): environment variables, the config file and model aliases.
8. [Use callai from Python](08-python-api.md): `callai.run()` and event callbacks.

Start: [1. Run your first prompt](01-first-prompt.md)
