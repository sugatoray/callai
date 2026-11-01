# Changelog

All notable changes to callai are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- callai now lives in its own repository, [sugatoray/callai](https://github.com/sugatoray/callai), imported
  from `sugatoray/devx` (`src/experiments/expt_callai`) at 0.8.0. Paths and links in the docs, the HTML docs
  builder and the project notes point at this repository; `pyproject.toml` gains `[project.urls]`.

### Fixed

- `test_old_tool_flag_is_gone` failed on Python 3.13, whose `--help` prints `-n, --name HARNESS_NAME`
  instead of `-n HARNESS_NAME, --name HARNESS_NAME`. It now checks the parser's options directly. The
  suite passes on 3.11 and 3.13.

## [0.8.0] - 2026-11-01

The docs as one HTML page. No changes to callai itself; nothing here breaks existing use.

### Added

- `make docs.html` bundles `docs/callai/` into one self-contained HTML page (`build/docs.html`): a tab per
  docs section, a page list, an on-this-page outline, search, and a light/dark toggle. The builder and
  template are in `docs/site/`; it fails if a page isn't linked from the docs' landing page.

## [0.7.0] - 2026-11-01

User documentation. No code changes; nothing here breaks existing use.

### Added

- User documentation in `docs/callai/` (32 pages), written with the `/create-lib-docs` skill (now published in [sugatoray/aiskills](https://github.com/sugatoray/aiskills)).
  - **Sections:** Getting Started, an 8-step tutorial, 6 how-to guides, Concepts with a glossary,
    a full reference (CLI, Python API, output formats, configuration, harnesses, every error message),
    and a FAQ.
  - **Diagrams:** 5 SVGs, each with a text equivalent.
  - **For AI agents:** `llms.txt` and `llms-full.txt`.
  - **Checks:** every example was run against the real harness CLIs connected to the stub model, and
    the `--dry-run` examples are checked mechanically.

## [0.6.0] - 2026-10-31

Resume sessions, a Python API (`callai.run`), and fan-out to several harnesses with `-n a/b`, `-n a,b`
or `-n all`. Nothing here breaks existing use.

### Added

- `--resume SESSION_ID` and `--continue`: continue a session (the `session_id` a run reported) or the
  harness's most recent one, mapped to each harness's own flags (codex: `exec ... resume ID|--last`).
  Checked with every harness against the stub model: the resumed request carries the earlier turns.
  `--continue` is refused for hermes, which only continues its interactive sessions. No `-c` short
  form, because `-c` is `--command`.
- Python API: `callai.run(harness_name, prompt, *, model, cwd, timeout, permission, system_prompt,
  extra_args, resume, continue_session, binary, on_event)` returns the `-o json` result; `on_event` gets
  the `-o stream-json` events live. It reads no `CALLAI_*` variables or config file. `Result` and the
  error classes are exported from `callai`. The CLI now runs harnesses through the same code.
- Fan-out: `-n a/b/c` runs one prompt through several harnesses at the same time, `-n a,b,c` one after
  another, `-n all` every installed harness at the same time. Everything is checked before anything
  runs; `-n all` skips harnesses that refuse the options. Text output puts each answer under a
  `== name ==` header, `-o json` gives `{"results": [...]}`, stream-json events carry `harness_name`.
  One failure (or timeout) doesn't stop the others; the exit code is the first failure's; Ctrl-C
  stops them all. `-o raw` and arguments after `--` need a single harness.

## [0.5.0] - 2026-10-30

`-o stream-json`: every harness's run as normalised JSON events, live. Nothing here breaks existing use.

### Added

- `-o stream-json`: one JSON event per line as the run happens: `start`, then `text`, `tool_use` and
  `tool_result` mapped from each harness's own event stream, then `result` (the `-o json` object).
  claude runs with `--output-format stream-json --verbose`, grok with `--output-format streaming-json`;
  codex, opencode and pi already stream. hermes has no event stream, so it gives `start` and `result`.
  Checked end to end with each harness (stub model, a real tool call) and live with claude.
- `Adapter.stream_events(line, state)`, and `runner.run(on_stdout_line=...)` to see output as it arrives.
- Conformance: `expected_events` in parse cases, `expected.stdout_events` in CLI cases, and
  `stderr_file` for fake harnesses; 7 recorded stream fixtures and 5 CLI cases.

### Fixed

- Test fake harnesses write their call record atomically; a test polling for it could read it half-written.

## [0.4.0] - 2026-10-30

Adapters can set environment variables for the harness, so hermes now accepts `--system-prompt`.
Nothing here breaks existing use.

### Added

- Adapters can set environment variables for the harness (`Adapter.build_env`, pure like
  `build_argv`); they are added on top of callai's own environment.
- hermes: `--system-prompt` now works, passed as `HERMES_EPHEMERAL_SYSTEM_PROMPT`. It was refused
  before. Checked against hermes-agent 0.19.0 with the stub model: the text lands in the system message.
- `--dry-run` shows those variables: as `NAME=value` before the command in text, and as an `"env"`
  object in `-o json` (left out when there are none, so existing output is unchanged).
- Conformance: `expected_env` in argv cases; `expected.harness_env` in CLI cases (the fake harness
  now records its environment).

## [0.3.0] - 2026-10-30

Defaults from the environment and a config file, model aliases, and `--list-harnesses`. Nothing
here breaks existing use.

### Added

- Config file `~/.config/callai/config.toml` (or `$XDG_CONFIG_HOME/callai/…`, or `CALLAI_CONFIG`):
  `default_harness`, `model`, `timeout`, per-harness `binary` / `model` / `extra_args`, and model
  aliases (`-m fast` → each harness's own model). Unknown keys are an error (exit 2).
- `CALLAI_MODEL` and `CALLAI_TIMEOUT` environment defaults. Precedence: flag > `CALLAI_*` > config
  file > built-in default.
- `--list-harnesses`: each harness's binary, where it is on PATH and its version, or where to
  install it (`-o json` for JSON).
- Live smoke tests (`CALLAI_LIVE=all uv run pytest -m live`): each real harness answers a real model.
- README: defaults and config file section.

### Fixed

- DESIGN.md said `--system-prompt` only warns where a harness lacks it; callai refuses it (exit 2).

## [0.2.0] - 2026-10-30

Names the harness consistently as `harness_name`, so it isn't confused with the harnesses' own
`--tool(s)` flags or the tools a model calls. Every change below is breaking.

### Changed

- **Breaking:** the harness is chosen with `-n/--name HARNESS_NAME` instead of `-t/--tool`,
  because several harnesses have their own `--tool`/`--tools` flags. `-t` and `--tool` are no
  longer accepted (exit 2).
- **Breaking:** the default-harness environment variable `CALLAI_TOOL` is now
  `CALLAI_HARNESS_NAME`. A leftover `CALLAI_TOOL` is not used; if no harness is given, the usage
  error says it was renamed.
- **Breaking:** the `-o json` result key `tool` is now `harness_name` (same value, e.g.
  `"claude-code"`). In the code, `Request.tool` and `Result.tool` are now `harness_name`, and the
  conformance argv/parse cases name their harness in a `harness_name` field.
- **Breaking:** `callai.adapters.TOOLS` is now `callai.adapters.HARNESS_NAMES`; usage errors say "harness"
  (`unknown harness 'x'`, `no harness given: use -n/--name ...`).

## [0.1.0] - 2026-10-30

First release: `callai -t TOOL -p PROMPT` runs claude-code, codex, opencode, pi, grok and hermes.

### Added

- Initial scaffold copied from `expt_template`: `docs/` (with its own `docs/.scrolls/`
  memory system), `.trash/`, and `src/`.
- `docs/DESIGN.md`: design for the `callai` dispatcher CLI (CLI surface, adapter
  architecture, normalised output, permissions, exit codes, test strategy).
- `SCOPE.md`: language/distribution analysis and agreed roadmap (Python → TypeScript
  port → optional Rust core with PyPI/npm thin wrappers).
- `conformance/` language-agnostic test suite (argv, parse, CLI cases; recorded
  claude fixtures) with a strict pytest loader in `src/tests/conformance.py`.
- Python package skeleton: `pyproject.toml` (PyPI name `callai-cli`, Python ≥ 3.11,
  stdlib-only), `callai --version`, `python -m callai`. Licensed Apache-2.0.
- Core types: `Request`, `Completed`, `Result` (with the `-o json` schema), `UsageError`,
  the `Adapter` base class and the tool registry.
- `claude-code` adapter command line (`claude -p --output-format json … -- PROMPT`).
- Full CLI (`-t`, `-p/-c/--prompt/--command`, `-m`, `-o text|json|raw`, `-C`, `--timeout`,
  `--permission`, `--system-prompt`, `--dry-run`, `-v`, `--` passthrough, stdin prompts,
  `CALLAI_TOOL`) and subprocess runner (process-group kill, exit codes 124/127/130).
- `claude-code` output parsing: answer, error flag, session id, cost, token usage and the
  model actually used, from `claude -p --output-format json`. **First working tool.**
- `codex` adapter: `codex exec --json`, sandbox permission mapping, `--system-prompt` via
  `developer_instructions`, JSONL event parsing.
- `opencode` adapter: `opencode run --format json`, prompt passed so opencode doesn't quote it,
  real error reasons from opencode's ERROR log, token/cost totals across steps. `read-only`/`auto`
  permissions and `--system-prompt` are refused (opencode can't honour them).
- `pi` adapter: `pi --mode json`, tool-allowlist permission mapping, `--system-prompt`,
  model errors detected from `stopReason` (pi exits 0 on them), prompts starting with `@`
  refused (pi would read them as files). Error text that the harness already printed on
  stderr is no longer repeated.
- `grok` adapter (xAI's Grok Build CLI): `grok --output-format json --single=PROMPT`, permission
  mapping (read-only tools only / `--allow Write --allow Edit` / `bypassPermissions`),
  `--system-prompt` via `--system-prompt-override`, token usage and the model actually used.
  Prompts starting with `/` are refused (grok would run them as slash commands). A run where grok
  refused a tool call (it cancels the turn but exits 0) or hit `--max-turns` is reported as a
  failure, with grok's reason.
- `hermes` adapter (Nous Research Hermes Agent): `hermes chat -Q --source tool --query=PROMPT`
  (not `-z`, which approves every tool call), the answer separated from hermes's tool previews,
  session id, `auto` = file tools only, `bypass` = `--yolo`. `read-only` and `--system-prompt` are
  refused (hermes can't honour them from the command line). All six tools now work.
- README usage section, with what each `--permission` level allows per harness.
- `--permission bypass` prints a one-line warning on stderr before the harness runs.
- Stub model speaks Anthropic Messages (`/v1/messages`, JSON and SSE, scripted `tool_use`), so the
  permission probe covers claude-code too; its results are in DESIGN §7 and the README.
- README caution: grok `auto`/`bypass` can write outside the working directory; how to opt in to
  grok's `workspace` sandbox (needs bubblewrap on Linux), with examples.
- Stub model `--tool-call`: scripts one tool call, so permission behaviour can be recorded.
- `conformance/tools/permission_probe.py`: runs a harness at every `--permission` level with
  scripted file-write and shell calls (inside and outside the working directory) and reports what
  actually happened. Results are in DESIGN §7.
- `Makefile`: `make install.harnesses` installs every supported harness CLI at its verified
  version; `make install.<tool>` (claude-code, codex, opencode, pi, hermes, grok) installs one.
- `conformance/tools/stub_llm_server.py`: local OpenAI-compatible model stub for recording
  real harness output without network access.

### Fixed

- `callai -p TEXT` no longer hangs when stdin is a pipe that never closes (common when an agent
  or script runs it): it waits 3 seconds for data (`CALLAI_STDIN_WAIT`), warns and runs with the
  prompt alone, like `claude -p`. Usage errors are reported before stdin is read.
- Harness output is captured byte-for-byte: `\r\n` line endings were translated to `\n`,
  so `-o raw` wasn't the harness's real output.

<!--
## [x.y.z] - YYYY-MM-DD

### Added
- What was added, from a user's perspective.

### Changed
- What changed in existing behavior.

### Fixed
- What bug was fixed.

### Removed
- What was removed and why.
-->
