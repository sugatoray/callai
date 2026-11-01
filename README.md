# expt_callai

`callai` is one command line for every coding-agent harness. It runs a single prompt non-interactively, like `claude -p`, through the harness you pick and prints the result:

```bash
callai -n {claude-code,codex,opencode,pi,hermes,grok} -p "PROMPT" [-m MODEL]
```

**User documentation:** [`docs/callai/`](docs/callai/README.md) has a tutorial, how-to guides, concepts and a full reference, with `llms.txt` for AI agents.

**Status:** Python implementation, version 0.8.0 (Red/Green TDD). All six harnesses work: `claude-code`, `codex`, `opencode`, `pi`, `grok` and `hermes`. The shared test suite is in [`conformance/`](conformance/README.md). PyPI distribution name: `callai-cli` (command `callai`). See [`SCOPE.md`](SCOPE.md) for scope, language/distribution decisions and the roadmap. See [`docs/DESIGN.md`](docs/DESIGN.md) for the CLI surface, adapter architecture, output schema and open decisions, and [`docs/.scrolls/PLAN.md`](docs/.scrolls/PLAN.md) for the build order.

## Usage

```bash
callai -n claude-code -p "Summarise README.md"            # prints the answer
callai -n codex -p "Fix the failing test" --permission auto
git diff | callai -n grok -p "Review this diff" -o json   # piped stdin is appended to the prompt
callai -n codex -p "Fix the test" -o stream-json          # JSON-lines events (tool calls, text) as they happen
callai -n pi -p "hello" -m stub/stub-model --dry-run      # show the harness command, don't run it
callai -n opencode -p "hello" -- --agent build            # args after -- go to the harness unchanged
callai -n codex -p "hello" -m fast                        # a model alias from the config file
callai -n claude-code -p "and the tests?" --resume SESSION_ID   # continue a session (-o json reports session_id)
callai -n pi -p "and now?" --continue                     # continue the harness's most recent session
callai -n codex/claude-code/grok -p "Explain main.py"     # several harnesses at the same time ('/' = parallel)
callai -n codex,pi -p "Explain main.py"                   # one after another (',' = sequential)
callai -n all -p "Explain main.py" -o json                # every installed harness, at the same time
callai --list-harnesses                                   # which harnesses are installed, and their versions
```

Harnesses: `claude-code`, `codex`, `opencode`, `pi`, `grok`, `hermes`. `-o text|json|stream-json|raw`
(json is one normalised object: `harness_name`, `text`, `is_error`, `session_id`, `usage`, `cost_usd`, `model`, ...;
stream-json is one event per line, `start`, then `text`/`tool_use`/`tool_result` as they happen, then `result`,
the json object; hermes has no event stream, so it gives only `start` and `result`; see DESIGN §5).
With several harnesses, each answer is printed under a `== name ==` header (`-o json`: `{"results": [...]}`;
stream-json events carry `harness_name`). One failure doesn't stop the others; the exit code is the first
failure's. `-n all` skips harnesses that can't honour the options, with a note. Parallel runs share the
working directory, so prefer `,` for tasks that edit files. See DESIGN §3 "Fan-out".
Exit codes: the harness's own; 1 if it reported an error but exited 0; 2 usage error; 124 timeout;
127 harness not installed; 130 interrupted.

Stdin: with `-p TEXT`, piped stdin is optional. If it's a pipe that stays open with nothing on it
(common when an agent or script runs callai), callai waits 3 seconds (`CALLAI_STDIN_WAIT`), warns and
runs with the prompt alone, like `claude -p`. Use `< /dev/null` to skip the wait. With `-p -` or no
`-p`, stdin is the prompt, so callai waits for it to close.

### Defaults: environment and config file

Each option comes from the first of: command-line flag, `CALLAI_*` environment variable, config
file, built-in default.

| setting | flag | environment | config file |
|---|---|---|---|
| harness | `-n/--name` | `CALLAI_HARNESS_NAME` | `default_harness` |
| model | `-m/--model` | `CALLAI_MODEL` | `[harnesses.<name>] model`, then top-level `model` |
| timeout | `--timeout` | `CALLAI_TIMEOUT` | `timeout` |
| stdin wait | | `CALLAI_STDIN_WAIT` | |

The config file is `~/.config/callai/config.toml` (or `$XDG_CONFIG_HOME/callai/config.toml`, or the
path in `CALLAI_CONFIG`). It is optional; unknown keys are an error (exit 2), so a typo never
silently does nothing.

```toml
default_harness = "claude-code"
model = "fast"                       # default model for every harness (here an alias)
timeout = 600

[harnesses.codex]
binary = "~/bin/codex"               # run this instead of `codex` from PATH
model = "gpt-5-codex"                # codex's default; beats the top-level model
extra_args = ["--skip-git-repo-check"]   # passed before anything after --

[aliases]                            # -m fast / -m smart, resolved per harness
fast  = { claude-code = "haiku", codex = "gpt-5-codex-mini", opencode = "anthropic/claude-haiku-4-5" }
smart = { claude-code = "opus",  codex = "gpt-5-codex" }
```

Any model that isn't an alias goes to the harness unchanged. An alias with no entry for the chosen
harness is an error (`model alias 'smart' has no entry for pi`) rather than passing `smart` on.

`callai --list-harnesses` shows each harness's binary (including a configured one), where it is on
PATH and its `--version`, or where to install it; `-o json` gives the same as JSON.

`--permission default|read-only|auto|bypass` is translated per harness; a level a harness can't honour
is refused (exit 2) rather than run with more access. What each level really allows was checked with
scripted tool calls; see [DESIGN.md §7](docs/DESIGN.md#7-permissions-and-safety):

| level | claude-code | codex | opencode | pi | grok | hermes |
|---|---|---|---|---|---|---|
| `read-only` | plan mode: no writes, no shell | read-only sandbox | refused | read tools only | read tools only | refused |
| `auto` | edits inside the workspace | writes inside the workspace (sandboxed shell) | refused | file writes/edits, no shell | file writes/edits, no shell | file writes/edits, no shell |
| `bypass` | everything | everything | everything | everything | everything | everything |

With `default`, opencode, pi and hermes already write files and run shell commands without asking;
claude-code, codex and grok don't. `bypass` prints a warning on stderr. As root, claude refuses
`bypass` unless `IS_SANDBOX=1` is set (callai never sets it).

> [!CAUTION]
> **grok `auto` and `bypass` can write outside the working directory.** callai's `auto` for grok
> allows only file writes and edits (no shell), but grok will write them **anywhere** the user
> running it can write, not just in the working directory. Unlike codex's `auto`, which is sandboxed
> to the workspace. callai does not add a sandbox for you: grok's sandbox needs
> [bubblewrap](https://github.com/containers/bubblewrap) on Linux, and grok refuses to start without
> it, so adding it would break `auto` on machines that don't have it.
>
> To confine grok's writes to the working directory, opt in with grok's `workspace` sandbox:
>
> ```bash
> sudo apt install -y bubblewrap                                      # Linux only, once
> callai -n grok -p "Fix the failing test" --permission auto -- --sandbox workspace
> callai -n grok -p "Refactor utils.py" --permission bypass -C ~/proj -- --sandbox workspace
> GROK_SANDBOX=workspace callai -n grok -p "Fix the failing test" --permission auto   # same, via grok's env var
> ```
>
> Writes inside the working directory (`-C`, or the current directory) still work; writes elsewhere
> fail with "Permission denied", and so do shell commands that write outside it under `bypass`.
> Without bubblewrap, grok exits 1 with "bwrap exec failed ... Install bubblewrap" instead of
> running unconfined. grok's other profiles (`read-only`, `strict`) behave the same way for the
> working directory: they also allow writes inside it, so `-- --sandbox read-only` does **not** make
> grok read-only. Use callai's `--permission read-only` for that (no write or shell tools are offered).

A few prompts are refused because the harness would not send them as text: pi reads a prompt starting
with `@` as a file, and grok runs one starting with `/` as a slash command.

## From Python

```python
import callai

result = callai.run("codex", "Fix the failing test", permission="auto", timeout=600)
print(result.text, result.is_error, result.session_id, result.usage)

# Continue that session, and watch tool calls as they happen
callai.run("codex", "Now add a test for it", resume=result.session_id, on_event=print)
```

`run()` takes the CLI's options as keyword arguments (`model`, `cwd`, `timeout`, `permission`,
`system_prompt`, `extra_args`, `resume`, `continue_session`, `binary`, `on_event`) and returns the same
result as `-o json`. It ignores `CALLAI_*` variables and the config file: pass what you want. A harness
that fails gives a result with `is_error=True`; `callai.CallaiError` subclasses (`UsageError`,
`HarnessNotFound`, `HarnessTimeout`, `Interrupted`) mean the run couldn't start or finish.

## Development

```bash
make install.harnesses             # all harness CLIs at their verified versions (or make install.<tool>)
make docs.html                     # the docs as one HTML page with tabs and a theme toggle -> build/docs.html
uv sync --extra test --extra dev   # Python >= 3.11, no runtime dependencies
uv run pytest                      # tests + coverage gate (95%)
uv run ruff check . && uv run ruff format --check .
uv run interrogate src             # docstring coverage (100%)
uv run callai --version
CALLAI_LIVE=claude-code uv run pytest -m live   # live smoke test: real harness, real model (or CALLAI_LIVE=all)
```

Development follows Red/Green TDD. Shared behaviour cases live in [`conformance/`](conformance/README.md).

## Layout

- `docs/` — the user documentation in [`docs/callai/`](docs/callai/README.md), [`DESIGN.md`](docs/DESIGN.md), plus this experiment's own [`docs/.scrolls/`](docs/.scrolls/STARTER.md) working-memory system.
- `.trash/` — scratch/disposable files local to this experiment (git-ignored).
- `conformance/` — language-agnostic test cases (argv, parse, CLI) shared by every implementation, plus `tools/`: a local stub model (with scripted tool calls) and the permission probe.
- `src/` — `src/callai/` (CLI, runner, one adapter per harness in `adapters/`) and `src/tests/`.
- [`CHANGELOG.md`](CHANGELOG.md) — notable changes to this experiment, [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style with [SemVer](https://semver.org/) versions.

See [SCROLLS.md](SCROLLS.md) for how the memory system works.

## License

[Apache-2.0](LICENSE).
