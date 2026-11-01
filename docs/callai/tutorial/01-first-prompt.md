# 1. Run your first prompt

Choose a harness with `-n`, pass a prompt with `-p`, and read the answer on stdout.

**You'll need:** callai and one harness installed ([Installation](../getting-started/installation.md)).

## Run it

```bash
callai -n claude-code -p "Reply with exactly: pong"
```

```text
pong
```

Here is what happened:

1. `-n claude-code` chose the harness. The names are `claude-code`, `codex`, `opencode`, `pi`, `hermes`
   and `grok`.
2. callai built the command `claude -p --output-format json -- 'Reply with exactly: pong'`. It asks
   every harness for its structured output, so the answer is never scraped from screen text.
3. It ran `claude` with no interactive input, in its own process group, and waited for it to finish.
4. It took the answer out of claude's JSON and printed only that, followed by a newline.

`-p` has three aliases (`-c`, `--prompt` and `--command`), so `claude -p` habits carry over.

## Choose a model

`-m` passes a model to the harness exactly as you type it:

```bash
callai -n claude-code -m haiku -p "Reply with exactly: pong"
callai -n opencode -m anthropic/claude-haiku-4-5 -p "Reply with exactly: pong"
```

Each harness has its own model names. opencode and pi want `provider/model`, and the others take a
name or id. Without `-m`, the harness uses its own default. To give one name a different meaning per
harness, see [model aliases](07-defaults.md#name-models-once-with-aliases).

## See the exact command

```bash
callai -n claude-code -m haiku -p "Reply with exactly: pong" --dry-run
```

```text
claude -p --output-format json --model haiku -- 'Reply with exactly: pong'
```

`--dry-run` prints the command and exits 0 without running anything. The harness doesn't even need
to be installed.

## Prompts that look like flags

callai always puts the prompt last, after `--` or as one `--option=PROMPT` argument, so a prompt such
as `-v is broken` reaches the model as text. Three harnesses would treat certain prompts as commands,
and callai refuses those (exit 2) rather than send them:

- grok runs a prompt starting with `/` as a slash command;
- pi reads a prompt starting with `@` as a file to attach;
- both have no escape, so start the prompt with other text.

## Pass extra flags to the harness

Anything after a bare `--` goes to the harness unchanged:

```bash
callai -n opencode -p "Explain main.py" --dry-run -- --agent build
```

```text
opencode run --format json --print-logs --log-level ERROR --agent build -- Explain main.py
```

Put callai's own flags before `--`. Everything after it belongs to the harness: had `--dry-run` come
after `--`, opencode would have received it, and callai would have run opencode instead of printing
the command.

## Recap

- `callai -n HARNESS -p PROMPT` runs one prompt and prints the answer.
- `-m` is passed through verbatim; each harness has its own model names.
- `--dry-run` shows the exact command; arguments after `--` go to the harness.

Reference: [`-n`](../reference/cli.md#-n-harness_name---name-harness_name) · [`-p`](../reference/cli.md#-p-prompt---prompt-prompt) · [`--dry-run`](../reference/cli.md#--dry-run)

Next: [2. Get machine-readable output](02-json-output.md) · Up: [Tutorial](README.md)
