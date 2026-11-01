# Command line reference

Every flag `callai` accepts. This page is exhaustive; for a gentler introduction see the
[Tutorial](../tutorial/README.md).

```text
callai -n HARNESS_NAME -p PROMPT [-m MODEL] [-o {text,json,stream-json,raw}] [-C CWD]
       [--timeout SECS] [--permission {default,read-only,auto,bypass}] [--system-prompt S]
       [--resume SESSION_ID | --continue] [--dry-run] [-v] [-- HARNESS_ARGS...]
callai --list-harnesses [-o json]
callai --version | --help
```

## Choosing the harness and prompt

### `-n HARNESS_NAME`, `--name HARNESS_NAME`

The harness to run: `claude-code`, `codex`, `opencode`, `pi`, `hermes` or `grok`. For several at once
(fan-out):

| Value | Runs |
|---|---|
| `codex` | one harness |
| `codex/pi/grok` | all of them at the same time |
| `codex,pi,grok` | all of them, one after another |
| `all` | every installed harness, at the same time; harnesses that refuse the options are skipped with a note |

Default: `CALLAI_HARNESS_NAME`, then `default_harness` in the config file. Neither set and no `-n`:
exit 2. Mixed separators, empty or repeated names, and `all` inside a list are usage errors.
[Fan-out output](output.md#fan-out).

### `-p PROMPT`, `--prompt PROMPT`

The prompt. `-c` and `--command` are aliases.

| Form | Prompt |
|---|---|
| `-p TEXT` | `TEXT`. Piped stdin, if any, is appended after a blank line. |
| `-p TEXT` with an idle stdin pipe | `TEXT`, after waiting `CALLAI_STDIN_WAIT` seconds (default 3) for input, then a warning. |
| `-p -` | stdin, read until it closes. |
| no `-p`, piped stdin | stdin, read until it closes. |

Empty stdin counts as no input. No prompt at all: exit 2. The prompt always reaches the harness as one
final argument, after `--` or as `--opt=PROMPT`, so it can't be read as a flag. grok prompts starting
with `/` and pi prompts starting with `@` are refused, because those harnesses would run or attach
them instead of sending them.

## Model and output

### `-m MODEL`, `--model MODEL`

Model passed to the harness verbatim, unless it's an [alias](configuration.md#aliases) in the config
file. Each harness has its own names (opencode and pi: `provider/model`). Default: `CALLAI_MODEL`, then
`[harnesses.<name>] model`, then the top-level `model`, then the harness's own default.

### `-o FORMAT`, `--output-format FORMAT`

| Value | Prints |
|---|---|
| `text` (default) | The answer only. On failure, the harness's stderr and the error go to stderr. |
| `json` | One normalised result object. [Schema](output.md#-o-json). |
| `stream-json` | One event per line, as it happens. [Events](output.md#-o-stream-json). |
| `raw` | The harness's own stdout and stderr, unchanged. Single harness only. |

## Where and how long

### `-C CWD`, `--cwd CWD`

Working directory for the harness. Default: the current directory. Not a directory: exit 2.

### `--timeout SECS`

Kill the harness, and every process it started, after `SECS` seconds (it may be fractional). Exit 124.
Default: `CALLAI_TIMEOUT`, then `timeout` in the config file, then no limit. In a fan-out, a timeout is
that harness's failed result, and the others keep running.

## Behaviour

### `--permission LEVEL`

`default` (add nothing), `read-only`, `auto` or `bypass`, translated to each harness's flags. A level a
harness can't honour is refused (exit 2): opencode refuses `read-only` and `auto`, and hermes refuses
`read-only`. `bypass` prints a warning on stderr. What each level really allows:
[Permissions](../concepts/permissions.md). The exact flags: [Harnesses](harnesses.md).

### `--system-prompt SYSTEM_PROMPT`

Extra system instructions:

| Harness | Passed as |
|---|---|
| claude-code | `--system-prompt S` (replaces claude's own) |
| codex | `-c developer_instructions="S"` (a developer message) |
| pi | `--system-prompt S` (replaces pi's own) |
| hermes | the `HERMES_EPHEMERAL_SYSTEM_PROMPT` environment variable |
| grok | `--system-prompt-override S` (replaces grok's own) |
| opencode | refused (exit 2): `opencode run` has no such option |

### `--resume SESSION_ID`

Continue the session with this id (the `session_id` from `-o json` or a `result` event). Mapped per
harness: [table](harnesses.md#session-flags). An id that is empty or starts with `-` is refused.

### `--continue`

Continue the harness's most recent session. There's no `-c` short form, because `-c` is `--command`.
It can't be combined with `--resume`. hermes refuses it, because it only continues its interactive
sessions: use `--resume`.

## Inspecting

### `--dry-run`

Print the exact harness command line and exit 0, without running it or needing it installed. Text:
one shell-quoted line, preceded by `NAME=value` for any environment variables callai would set. With
`-o json` or `-o stream-json`: `{"argv": [...]}`, plus `"env": {...}` when there are any. In a fan-out:
one line per harness, or `{"runs": [...]}`. [Shapes](output.md#--dry-run).

### `-v`, `--verbose`

Copy the harness's stderr to callai's stderr as it arrives. It's still captured for the result.
Without `-v`, it's shown only when the run fails.

### `--list-harnesses`

List every supported harness: its binary (including one set in the config file), where it is on
`PATH`, and its `--version`, or where to install it. With `-o json`, one object. [Shape](output.md#--list-harnesses).

### `--version`, `-h` / `--help`

Print callai's version or help and exit 0.

## Passing arguments to the harness

### `--`

Everything after a bare `--` is passed to the harness unchanged, after callai's own flags and before
the prompt. callai's flags must come before it. Not allowed with several harnesses (exit 2); use
`[harnesses.<name>] extra_args` in the config file instead.

```bash
callai -n opencode -p "Explain main.py" --dry-run -- --agent build
```

```text
opencode run --format json --print-logs --log-level ERROR --agent build -- Explain main.py
```

## Environment variables

| Variable | Default for |
|---|---|
| `CALLAI_HARNESS_NAME` | `-n` |
| `CALLAI_MODEL` | `-m` |
| `CALLAI_TIMEOUT` | `--timeout` |
| `CALLAI_STDIN_WAIT` | seconds to wait for piped input with `-p` (default `3`, `0` = don't wait) |
| `CALLAI_CONFIG` | config file path (must exist) |

Details: [Configuration](configuration.md#environment-variables).

See also: [Exit codes and errors](errors.md) · [Output formats](output.md)
