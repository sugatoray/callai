# SPEC.md — Feature Spec

What callai does, feature by feature. Add a section per feature when it ships — describe *what* it does and *why* it matters to a user, not the implementation detail (that belongs in code comments or `WISDOM.md`).

## Run a prompt through Claude Code
`callai -n claude-code -p PROMPT [-m MODEL]` runs `claude -p` non-interactively and prints just the answer.
Works with `-o json` (normalised result: text, is_error, session id, cost, token usage, the model actually used),
`-o raw` (claude's own output), `--dry-run`, piped stdin (`cat f | callai -n claude-code -p "review"`),
`--timeout`, `-C DIR`, `--permission`, `--system-prompt`, and `-- extra claude args`. Harness errors keep
claude's exit code; callai's own are 2 (usage), 124 (timeout), 127 (not installed), 130 (interrupted).
`--permission bypass` warns on stderr before running. With `-p TEXT`, a stdin pipe that stays open and silent doesn't block: callai waits `CALLAI_STDIN_WAIT` seconds
(default 3), warns, and runs with the prompt alone. Usage errors come before any stdin read.
Code: `src/callai/cli.py`, `runner.py`, `adapters/claude_code.py`.

## Run a prompt through Codex
`callai -n codex -p PROMPT [-m MODEL]` runs `codex exec --json --skip-git-repo-check` (works outside git repos) and prints
the agent's final message. Same options as claude-code; `--permission` maps to codex's `--sandbox` modes, and
`--system-prompt` becomes a developer message. codex doesn't report the model it used, so `model` is the requested one.
Use `--timeout`: codex retries forever when the network is down. Code: `src/callai/adapters/codex.py`.

## Run a prompt through opencode
`callai -n opencode -p PROMPT [-m provider/model]` runs `opencode run --format json` and prints the final answer;
the prompt reaches the model exactly as typed. Token usage and cost are totalled across all steps, and failures
report opencode's real reason (e.g. "Model not found … Did you mean …") instead of its generic "Unexpected server
error". `--permission bypass` maps to `--auto`; `read-only`, `auto` and `--system-prompt` are refused with exit 2
because opencode can't honour them. Code: `src/callai/adapters/opencode.py`.

## Run a prompt through pi
`callai -n pi -p PROMPT [-m provider/id]` runs `pi --mode json` and prints the final answer. pi reports the model it
actually used, so `-o json` shows it, with token usage and cost summed over turns. Model errors fail the run (exit 1)
even though pi itself exits 0. `--permission read-only` / `auto` restrict pi's tools (read-only tools; plus edit/write),
`bypass` is pi's default, and `--system-prompt` replaces pi's own. Prompts starting with `@` are refused, because pi
would read them as files to attach. Code: `src/callai/adapters/pi.py`.

## Run a prompt through hermes
`callai -n hermes -p PROMPT [-m MODEL]` runs Nous Research's Hermes Agent (`hermes chat -Q --source tool --query=PROMPT`)
and prints the answer without hermes's tool previews; the session id comes from stderr. hermes reports no tokens or
cost. By default hermes writes files and runs ordinary shell commands; dangerous ones are denied (no one to approve).
`--permission auto` limits it to file tools, `bypass` adds `--yolo`; `read-only` is refused. `--system-prompt` is passed
in hermes's environment as `HERMES_EPHEMERAL_SYSTEM_PROMPT` (hermes has no flag for it); `--dry-run` shows it.
Code: `src/callai/adapters/hermes.py`.

## Run a prompt through grok
`callai -n grok -p PROMPT [-m MODEL]` runs xAI's Grok Build CLI (`grok --output-format json --single=PROMPT`) and prints
the answer; errors (e.g. not signed in, unknown model) exit 1 with grok's message once on stderr. grok reports the model
it used. `--permission read-only` offers only grok's read tools (read_file, grep, list_dir), `auto` allows file writes and edits
(shell and other calls needing approval are refused, as headless grok can't ask; such a refused run is reported as a
failure with grok's reason, though grok exits 0), `bypass` approves everything, and
`--system-prompt` replaces grok's own. Prompts starting with `/` are refused, because grok would run them as slash
commands. Code: `src/callai/adapters/grok.py`.

## Defaults from the environment and a config file
Every option can have a default: command-line flag > `CALLAI_*` environment variable (`CALLAI_HARNESS_NAME`,
`CALLAI_MODEL`, `CALLAI_TIMEOUT`, `CALLAI_STDIN_WAIT`) > `~/.config/callai/config.toml` > built-in default. The config
file sets `default_harness`, `model`, `timeout`, and per harness a `binary`, default `model` and `extra_args`.
Model aliases (`-m fast`) map one name to each harness's own model; an alias missing for the chosen harness is an
error. Unknown keys or bad values are an error naming the file (exit 2). Code: `src/callai/config.py`, `cli.py`.

## List the installed harnesses
`callai --list-harnesses` prints every supported harness with its binary (a configured one if set), where it is on
PATH and its `--version`, or "not installed" with the install docs link; `-o json` prints
`{"harnesses": [{harness_name, binary, path, version, install_url}, ...]}`. Code: `src/callai/cli.py`,
`runner.harness_version`.

## Stream events as they happen (`-o stream-json`)
`callai -n HARNESS -p PROMPT -o stream-json` writes one JSON object per line, flushed immediately:
`start` (harness, model, argv), then the harness's own events normalised to `text`, `tool_use` (id, the
harness's tool name, input) and `tool_result` (id, is_error, output) as they happen, then `result` (the
`-o json` object). Same shape for every harness, so a script or UI can show progress from any of them.
claude uses `--output-format stream-json --verbose`, grok `--output-format streaming-json`; codex, opencode
and pi already stream JSON lines. hermes has no event stream: only `start` and `result`. A missing binary
writes nothing (exit 127). Code: `Adapter.stream_events` in each adapter, `runner.run(on_stdout_line=...)`.

## Continue a session (`--resume`, `--continue`)
`callai -n HARNESS -p PROMPT --resume SESSION_ID` continues a conversation, using the `session_id` that
`-o json` (or the stream's `result` event) reported; `--continue` continues the harness's most recent
session. Each harness gets its own flags (codex: `codex exec ... resume ID|--last`); `--dry-run` shows them.
hermes refuses `--continue` (it would pick the user's interactive session), but `--resume` works.
A session id starting with `-` is refused. Code: `Request.resume`/`continue_session`, `_session_flags` in each adapter.

## Use callai from Python
`callai.run("codex", "prompt", permission="auto", ...)` runs a harness and returns the same result as `-o json`
(`text`, `is_error`, `session_id`, `usage`, ...); `on_event=callback` receives the `-o stream-json` events as they
happen; `resume=result.session_id` continues the conversation. Library calls ignore `CALLAI_*` variables and
the config file, so they behave the same everywhere. A failed harness run is a result with `is_error`; exceptions
(`callai.CallaiError` subclasses) mean the run couldn't start or finish. Code: `src/callai/api.py`.

## Ask several harnesses at once (fan-out)
`callai -n codex/claude-code/grok -p PROMPT` runs the prompt through several harnesses at the same time;
`-n codex,pi` runs them one after another; `-n all` runs every installed harness at the same time. Answers come
back in the order given: under `== name ==` headers (text), as `{"results": [...]}` (json), or as live events
tagged with `harness_name` (stream-json). Everything is checked before anything runs; `-n all` skips harnesses
that can't honour the options. One failure or timeout doesn't stop the others; exit code = first failure's;
Ctrl-C stops all. Code: `src/callai/fanout.py`, `cli._execute_many`.

## Docs as one HTML page (`make docs.html`)
`make docs.html` writes `build/docs.html`: every page and diagram of `docs/callai/` in one self-contained page,
with a tab per docs section, a page list, an on-this-page outline that follows your scroll, search (`/`), copy
buttons on code, and a light/dark toggle that remembers your choice. Links between pages stay in the page; links
to other repo files open on GitHub at `DOCS_REF` (default: the current branch). The landing page opens with the
project banner as live HTML (copied from `src/tools/banner/callai-banner.html` without the editing features,
scaled to the column; `--banner PATH` / `--no-banner`). Markdown is rendered in the
browser (marked + highlight.js from cdnjs). Code: `docs/site/build_docs_html.py`, `docs/site/template.html`.

## Project banner (`make maint.banner`)

A maintainer tool, not shipped in the package. `make maint.banner` writes `src/tools/banner/callai-banner.html`:
a 1280 × 640 banner page showing the wordmark, version/Python/license badges, tagline, install command, a
terminal demo and the harness row. All its text comes from `src/tools/banner/config.yaml`; `"auto"` values
track the repository (version, Python requirement, license and URL from `pyproject.toml`, harnesses from the
registry). `make maint.banner BANNER_PACKAGE_VERSION=X.Y.Z` shows another version. In a browser the page has an
Edit/Save toggle (saved per build in browser storage), Save HTML, Reset, and PNG export with the banner's own,
white, black or transparent background at 1x, 2x (default) or 4x ("Export all 12" for every combination).
`make maint.banner.png` renders it with headless Chrome to `docs/assets/images/banner_2x.png` at 2x. Details:
`src/tools/banner/README.md`.

## Changelog convention

`CHANGELOG.md` tracks notable changes to callai, in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format with [Semantic Versioning](https://semver.org/) version numbers. It starts with an `[Unreleased]` section; add a dated, versioned section (`## [x.y.z] - YYYY-MM-DD`) once callai cuts an actual release/milestone worth naming.

<!--
## <Feature name>
What it does, from a user's perspective. A pointer to where it lives in the code
(`path/to/file.ext:line`) if that saves the next reader time.
-->
