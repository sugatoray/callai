# callai

callai runs one prompt through any coding-agent CLI and gives you the answer in one consistent shape.

Claude Code, Codex, opencode, pi, Hermes and Grok each have their own flags, output formats, permission
models and quirks. callai turns one command into the right invocation for each, runs it without
interaction, and returns the same text, JSON or event stream whichever harness answered. Use it from a
shell, a script, CI, another AI agent, or Python.

```bash
callai -n codex -p "Reply with exactly: pong"
```

```text
pong
```

```bash
callai -n claude-code/codex/grok -p "Explain main.py" -o json     # three harnesses at once
```

## Features

- **One interface, six harnesses:** `claude-code`, `codex`, `opencode`, `pi`, `hermes`, `grok`, chosen
  with `-n`. Everything else (prompt, model, permissions, sessions) is spelled the same for all of them.
- **Machine-readable output:** `-o json` gives one normalised result (`text`, `is_error`,
  `session_id`, `usage`, …). `-o stream-json` streams `start`, `text`, `tool_use`, `tool_result` and
  `result` events as they happen.
- **Permission levels:** `--permission read-only|auto|bypass`, mapped to each harness's own flags and
  checked by running real tool calls. callai refuses a level a harness can't honour rather than run
  with more access.
- **Sessions:** `--resume SESSION_ID` and `--continue` pick a conversation back up.
- **Fan-out:** `-n a/b/c` runs several harnesses at the same time, `-n a,b,c` one after another, and
  `-n all` every installed one.
- **Scriptable:** predictable exit codes, `--dry-run` to see the exact command, and it never hangs on
  an idle stdin.
- **Python API:** `callai.run("codex", "…")` returns the same result. No runtime dependencies.

## Documentation

### Getting started

- [Why callai](getting-started/why-callai.md): what problem callai solves, and when you don't need it.
- [Installation](getting-started/installation.md): install callai and the harness CLIs you want to use.
- [Quickstart](getting-started/quickstart.md): your first prompt, JSON output and a dry run, in five minutes.

### Tutorial

- [Tutorial overview](tutorial/README.md): a step-by-step path through everything callai does.
- [1. Run your first prompt](tutorial/01-first-prompt.md): choose a harness, pass a prompt, read the answer.
- [2. Get machine-readable output](tutorial/02-json-output.md): `-o json`, exit codes and using the result in scripts.
- [3. Control what the agent may do](tutorial/03-permissions.md): `--permission` levels and how each harness honours them.
- [4. Watch a run as it happens](tutorial/04-streaming.md): `-o stream-json` events.
- [5. Continue a conversation](tutorial/05-sessions.md): `--resume` and `--continue`.
- [6. Ask several harnesses at once](tutorial/06-fan-out.md): `-n a/b/c`, `-n a,b,c` and `-n all`.
- [7. Set your defaults](tutorial/07-defaults.md): environment variables, the config file and model aliases.
- [8. Use callai from Python](tutorial/08-python-api.md): `callai.run()` and event callbacks.

### How-to guides

- [Guides overview](guides/README.md): task-focused recipes.
- [Call callai from an AI agent](guides/use-from-an-ai-agent.md): run harnesses as sub-agents safely and parse what comes back.
- [Use callai in scripts and CI](guides/scripts-and-ci.md): stdin, timeouts, exit codes and JSON in shell pipelines.
- [Compare harnesses side by side](guides/compare-harnesses.md): one prompt, every harness, a model alias each.
- [Build a live progress view](guides/live-progress.md): turn stream events into a progress display.
- [Test without a real model](guides/test-without-a-model.md): run real harnesses against the local stub model.
- [Add a new harness](guides/add-a-harness.md): write an adapter and prove it with the conformance suite.

### Concepts

- [Concepts overview](concepts/README.md): the ideas behind callai, and a glossary.
- [Architecture](concepts/architecture.md): adapters, the runner, and the one run path the CLI and the API share.
- [Permissions](concepts/permissions.md): what each level allows per harness, and why callai fails closed.
- [Normalised output](concepts/normalised-output.md): how six output formats become one result and one event stream.

### Reference

- [Reference overview](reference/README.md): exhaustive, one page per surface.
- [Command line](reference/cli.md): every flag of `callai`.
- [Python API](reference/python-api.md): `callai.run()`, `Result` and the exceptions.
- [Output formats](reference/output.md): text, JSON, stream events, raw, dry run and fan-out shapes.
- [Configuration](reference/configuration.md): `config.toml`, environment variables and precedence.
- [Harnesses](reference/harnesses.md): exactly how callai invokes each harness.
- [Exit codes and errors](reference/errors.md): every exit code and error message, with its cause and fix.

### Help

- [FAQ and troubleshooting](faq.md): common questions and problems, with answers.

> [!NOTE]
> The example output in these docs was recorded with the real harness CLIs (claude 2.1.316, codex-cli
> 0.166.0, opencode 1.19.5, pi 1.4.0, hermes-agent 0.19.0, grok 1.0.70) talking to a local stub model,
> so answers are short canned replies such as `pong`. The commands, flags, JSON shapes and errors
> are real. Durations and session ids differ on every run.

For AI agents: [`llms.txt`](llms.txt) indexes these pages, and [`llms-full.txt`](llms-full.txt) holds all of
them in one file. Project design notes are in [`docs/DESIGN.md`](../DESIGN.md), and release history is in
[`CHANGELOG.md`](../../CHANGELOG.md).
