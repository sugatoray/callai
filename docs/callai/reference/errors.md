# Exit codes and errors reference

Every exit code and every message callai prints, with its cause and fix. Errors appear on stderr as
`callai: error: <message>`. Usage errors (exit 2) are preceded by the usage line. In Python, the same
message is `str(exc)`.

## Exit codes

| Code | Meaning | Python |
|---|---|---|
| `0` | Success (every harness, in a fan-out) | — |
| `1` | The harness reported an error but exited 0 | `result.is_error`, `result.exit_code == 0` |
| `2` | [Usage error](#usage-errors): nothing ran | `UsageError` |
| `124` | [Timed out](#timed-out) | `HarnessTimeout` |
| `127` | [Harness not installed](#harness-not-installed) | `HarnessNotFound` |
| `130` | [Interrupted](#interrupted) | `Interrupted` |
| other | The harness's own failure code | `result.is_error`, `result.exit_code` |

In a fan-out, the exit code is 0 if every harness succeeded, otherwise the first failure's in the order
given.

## Usage errors

All exit 2, before any harness runs.

### No harness given

```text
no harness given: use -n/--name, set CALLAI_HARNESS_NAME, or set default_harness in the config file
```

**Fix:** pass `-n`, or set a default ([Configuration](configuration.md)).

### Unknown harness

```text
unknown harness '<name>'; choose from claude-code, codex, opencode, pi, hermes, grok
```

**Fix:** use one of the listed names. The names are callai's (`claude-code`), not the binary's
(`claude`).

### No prompt

```text
a prompt is required: use -p PROMPT or pipe it on stdin
```

**Cause:** no `-p`, and stdin was empty or a terminal. **Fix:** pass `-p`, or pipe the prompt in.

### Permission level not supported

```text
--permission read-only: opencode has no read-only mode (its plan agent still allows shell commands); pass `-- --agent plan` yourself if that is acceptable
--permission auto: opencode has no 'auto-approve edits only' mode (--auto approves everything); use --permission bypass or the default
--permission read-only: hermes has no read-only toolset (its `file` toolset can write); use the default or --permission auto
```

**Cause:** the harness has no way to honour the level, and callai won't give it more access than you
asked for. **Fix:** choose another level or another harness, or accept the alternative the message
names. [Permissions](../concepts/permissions.md#failing-closed).

### System prompt not supported

```text
opencode run has no system prompt option; drop --system-prompt
```

### Prompt would be run as a command

```text
grok runs a prompt starting with '/' as a slash command (e.g. /compact), even after leading spaces, and has no escape; start the prompt with other text
pi reads a prompt starting with '@' as a file to attach, and has no escape; start the prompt with other text (e.g. a space)
```

**Fix:** start the prompt with other text.

### `--resume` and `--continue`

```text
use --resume or --continue, not both
--resume: empty session id
--resume: a session id can't start with '-' (the harness would read it as an option)
--continue: hermes only continues its most recent interactive session, not callai's runs; use --resume with the session_id callai reported
```

### Fan-out

```text
-n <value>: use '/' (parallel) or ',' (one after another), not both
-n <value>: empty harness name
-n <value>: <name> is listed twice
-n <value>: 'all' can't be combined with other harnesses
-o raw needs a single harness (several raw outputs can't be told apart)
arguments after -- go to one harness; for several, set [harnesses.<name>] extra_args in the config file
-n all: every installed harness refused these options
<harness>: <reason>
```

The last form is a harness in an explicit list refusing an option. The whole call stops before
anything runs. With `-n all`, the harness is skipped instead, and stderr says
`callai: skipping <harness>: <reason>`.

### Working directory

```text
--cwd '<dir>' is not a directory
```

### Environment variables

```text
CALLAI_TIMEOUT must be a positive number of seconds, got '<value>'
CALLAI_STDIN_WAIT must be a number of seconds >= 0, got '<value>'
CALLAI_TOOL was renamed to CALLAI_HARNESS_NAME; set that instead
```

### Config file

Each of these is prefixed with the file's path (`<path>: …`):

```text
CALLAI_CONFIG points at <path>, which doesn't exist
<path>: invalid TOML (<details>)
<path>: cannot read config (<reason>)
<path>: unknown key '<key>'; allowed: aliases, default_harness, harnesses, model, timeout
<path>: [harnesses.<name>]: unknown key '<key>'; allowed: binary, extra_args, model
<path>: default_harness: unknown harness '<name>'; choose from …
<path>: [harnesses.<name>]: unknown harness; choose from …
<path>: [harnesses.<name>]: binary must be a non-empty string
<path>: [harnesses.<name>]: extra_args must be a list of strings
<path>: timeout must be a positive number of seconds, got <value>
<path>: model must be a string
<path>: [aliases] <alias> must map harness names to models, e.g. { codex = 'o3' }
<path>: [aliases] <alias>: unknown harness '<name>'; choose from …
```

**Fix:** correct the key or value the message names. Typos are errors on purpose, so a misspelled
setting never silently does nothing.

### Invalid arguments (Python API)

The CLI's parser catches these first, so in practice you see them only from `callai.run()`:

```text
invalid output format '<value>'; choose from text, json, stream-json, raw
invalid permission '<value>'; choose from default, read-only, auto, bypass
timeout must be a positive number of seconds, got <value>
prompt must be a string
extra_args must be a sequence of strings
resume must be a session id string
```

### Model alias without an entry

```text
model alias '<alias>' has no entry for <harness>
```

**Fix:** add the harness to the alias in `[aliases]`, or pass a model name with `-m`.

## Harness not installed

```text
harness binary '<binary>' not found on PATH (needed for --name <harness>); install it: <install URL>
-n all: none of the supported harnesses is installed (see callai --list-harnesses)
```

Exit 127. **Fix:** install the harness ([Installation](../getting-started/installation.md)), or point
`[harnesses.<name>] binary` at it.

## Timed out

```text
'<binary>' timed out after <secs>s and was killed
```

Exit 124. The harness and every process it started were killed. **Fix:** a larger `--timeout`, or a
smaller task. In a fan-out, this becomes that harness's failed result (`== name (failed, exit 124) ==`),
and the others carry on.

## Interrupted

```text
interrupted
```

Exit 130, after Ctrl-C. callai forwards SIGINT to the harness's process group, waits briefly, then
kills whatever is left. In a fan-out it stops every harness.

## Warnings

These go to stderr and don't change the exit code:

```text
callai: warning: no stdin data received in 3s, proceeding without it. Redirect stdin (< /dev/null) to skip the wait, or set CALLAI_STDIN_WAIT to wait longer.
callai: warning: --permission bypass: <harness> will run every tool call without asking, including shell commands and writes outside the working directory.
callai: skipping <harness>: <reason>
```

## When the harness fails

The run happened, but the harness reported an error (bad model, refused tool, API error):
- `is_error` is `true`, and `text` is the harness's reason;
- the exit code is the harness's own, or 1 if it exited 0;
- callai copies the harness's stderr to its own stderr.

Example:

```text
There's an issue with the selected model (not-a-real-model-xyz). It may not exist or you may not have access to it. Run --model to pick a different model.
```

See also: [Use callai in scripts and CI](../guides/scripts-and-ci.md) · [FAQ](../faq.md)
