# Configuration reference

Every setting callai reads outside its flags: the config file and environment variables. The Python
API ignores both.

## Precedence

For each setting, the first source that sets it wins:

| Setting | 1. Flag | 2. Environment | 3. Config, per harness | 4. Config, top level | 5. Default |
|---|---|---|---|---|---|
| harness | `-n` | `CALLAI_HARNESS_NAME` | — | `default_harness` | none (error) |
| model | `-m` | `CALLAI_MODEL` | `[harnesses.<name>] model` | `model` | the harness's own |
| timeout | `--timeout` | `CALLAI_TIMEOUT` | — | `timeout` | no limit |
| harness binary | — | — | `[harnesses.<name>] binary` | — | from `PATH` |
| extra harness args | after `--` (added last) | — | `[harnesses.<name>] extra_args` (added first) | — | none |

Model [aliases](#aliases) are resolved after the model is chosen.

## The config file

Location, first that applies:

1. `$CALLAI_CONFIG`: must exist, or exit 2;
2. `$XDG_CONFIG_HOME/callai/config.toml`;
3. `~/.config/callai/config.toml`.

The file is optional, and a missing default file is fine. It's TOML, read with Python's `tomllib`.
Unknown keys, unknown harness names and wrong types stop callai (exit 2) with a message naming the file.

```toml
default_harness = "claude-code"
model = "fast"
timeout = 600

[harnesses.codex]
binary = "~/bin/codex"
model = "gpt-5-codex"
extra_args = ["--skip-git-repo-check"]

[aliases]
fast  = { claude-code = "haiku", codex = "gpt-5-codex-mini", opencode = "anthropic/claude-haiku-4-5" }
smart = { claude-code = "opus",  codex = "gpt-5-codex" }
```

### `default_harness`

String: one of `claude-code`, `codex`, `opencode`, `pi`, `hermes`, `grok`. Used when there's no `-n` and
no `CALLAI_HARNESS_NAME`.

### `model`

String: the default model for every harness, usually an alias.

### `timeout`

Positive number of seconds.

### `[harnesses.<name>]`

One table per harness (the name must be a supported harness):

| Key | Type | Meaning |
|---|---|---|
| `binary` | non-empty string | Executable to run instead of the usual binary from `PATH`; `~` is expanded. Also used by `--list-harnesses` and `-n all`. |
| `model` | string | This harness's default model; beats the top-level `model`. |
| `extra_args` | list of strings | Passed to the harness before any arguments after `--`. Also used in fan-out, where `--` isn't allowed. |

### `[aliases]`

Each key is an alias name; its value maps harness names to that harness's model:

```toml
[aliases]
fast = { claude-code = "haiku", codex = "gpt-5-codex-mini" }
```

When the chosen model (from any source) is an alias name, it's replaced by the entry for the harness
being run. A model that isn't an alias passes through unchanged. An alias without an entry for that
harness is an error (`model alias 'fast' has no entry for pi`), rather than sending `fast` as a model
name.

## Environment variables

| Variable | Value | Meaning |
|---|---|---|
| `CALLAI_HARNESS_NAME` | a harness name, `a/b`, `a,b` or `all` | Default for `-n` |
| `CALLAI_MODEL` | model or alias | Default for `-m` |
| `CALLAI_TIMEOUT` | positive number | Default for `--timeout`; anything else is exit 2 |
| `CALLAI_STDIN_WAIT` | number ≥ 0 (default `3`) | With `-p`, how long to wait for input on an idle stdin pipe before warning and continuing |
| `CALLAI_CONFIG` | path | Config file to use; must exist |
| `CALLAI_LIVE`, `CALLAI_LIVE_TIMEOUT` | `all` or names; seconds | Test suite only: enable live smoke tests |

An empty value counts as unset. `CALLAI_TOOL`, the old name of `CALLAI_HARNESS_NAME`, is rejected
with a message telling you to rename it.

Variables the **harnesses** read (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`, `HERMES_HOME`, …)
pass through to them unchanged. callai adds only what an option needs, for example
`HERMES_EPHEMERAL_SYSTEM_PROMPT` for hermes's `--system-prompt`.

See also: [7. Set your defaults](../tutorial/07-defaults.md) · [Command line](cli.md)
