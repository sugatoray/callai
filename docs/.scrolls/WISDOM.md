# WISDOM.md — Constraints, Traps, Ditches, and Wisdom

Hard-won lessons for this project. Read this LAST, right before editing code, so it's freshest in mind.

## Constraints — respect and conform to them
Things you must respect or conform to (external requirements, API contracts, platform limits).

- Always pass the prompt as a single argv element via list-form `subprocess` — never `shell=True`.
- `callai` must never escalate permissions on its own; unsupported `--permission` levels fail closed (exit 2).
- Harness CLIs change flags often — treat docs as hints; `<tool> --help` and recorded fixtures are the source of truth.

## Traps — avoid them always
Specific bugs that have bitten this project before — avoid repeating them.

- Agent skills installed into `.agents/` (symlinked from `.claude/skills/`) ship their own Python files, and `ruff check .` in CI lints them. `[tool.ruff] extend-exclude` lists `.agents` and `.claude`; keep that when installing more skills, and exclude any other new third-party folder the same way.
- A prompt starting with `-` gets parsed as a harness flag unless it is guarded: always put the prompt **last, after `--`** (verified with claude 2.1.314; enforced by `test_conformance_data.py`).
- `claude -p --output-format json` reports failures as `"subtype": "success"` **with** `"is_error": true` (e.g. unknown model, exit 1). Decide errors from `is_error` and the exit code, never from `subtype`.
- The harness must get `stdin=DEVNULL`: `claude -p` reads piped stdin and would append callai's stdin to the prompt a second time.
- A tool that ends its own process but leaves children behind can keep pipes open; the runner puts each harness in its own process group and kills the **group** on timeout or Ctrl-C (`test_run_timeout_kills_whole_process_group`).
- Tests **and manual checks** should still run callai with stdin redirected (`</dev/null` or an empty pipe), never the inherited stdin. Since CA-19 an idle pipe only costs `-p TEXT` a 3s wait, but `-p -` / no `-p` still wait for EOF forever (this hung a CA-7 manual check for 5 minutes).
- `claude -p` (2.1.314) waits 3s for the first piped stdin data, then warns "no stdin data received in 3s, proceeding without it" (found with `strings` on the binary). callai copies that behaviour and wording; Python's `select` on the stdin fd does the wait without a thread (an abandoned thread blocked in `sys.stdin.read()` can crash interpreter shutdown).
- To simulate an idle stdin in a shell, `(sleep N) | callai ...` works, but the shell waits for `sleep` to finish even after callai exits: keep N short or the tool call looks hung.
- codex: `item.completed` items of `type: "error"` and top-level `error` events are **non-fatal** (missing model metadata, reconnects). Only `turn.failed` or a non-zero exit is a failure.
- codex without network retries forever ("waiting for network") instead of failing; only `--timeout` stops it.
- codex `exec` has subcommands (`resume`, `fork`, `review`, `help`); the `--` before the prompt keeps a prompt like "review" from becoming a subcommand (verified).
- The CLIs' real `--help` disagreed with the web docs (codex 0.166 has no `--full-auto`). Always start an adapter from `--help` on an installed binary.
- opencode wraps any message argument that contains a space in literal quotes (and escapes inner quotes) before sending it to the model. Pass the prompt split on single spaces after `--`; its `join(" ")` rebuilds it exactly. Found only by reading the stub's request log: the output looked fine.
- opencode's `error` event is often a generic "Unexpected server error"; the real reason is in the ERROR log line (`--print-logs --log-level ERROR` → `error="..."` on stderr).
- opencode `run`: `-p` is `--password` and `-c` is `--continue`. Never assume callai's short flags mean the same thing in a harness.
- Makefile version pins use `:=`, never `?=`: `?=` lets environment variables win, and Claude Code exports `CLAUDE_CODE_VERSION` (2.1.42 here), which silently installed an older claude over the 2.1.314 on PATH. Command-line `make VAR=x` still overrides `:=`.
- Before running a vendor's `curl | bash` installer, search the npm registry (`/-/v1/search?text=…`) for an official package. xAI publishes grok as `@xai-official/grok`, which plain name guesses (`@xai/grok`, `grok-cli`) missed. Check the publisher, then read the `postinstall` script before installing.
- An agent named "plan" is not necessarily read-only: check its permission rules (`opencode agent list`) before mapping a permission level to it.
- `pkill -f PATTERN` in a shell command matches that shell's own command line and kills it. Use a regex the literal text can't match, e.g. `pkill -f "stub_llm_server.py --port 876[5]"`.
- pi exits **0** when the model call fails (`--mode json`). The failure is only in the last assistant message's `stopReason` (`error`/`aborted`; `length` = truncated) and `errorMessage`. A model pi doesn't know gives exit 1, no events, and the reason only on stderr.
- pi reads any message argument starting with `@` as a file to attach, even after `--` (no escape). If a file with that name exists it is silently attached instead of sent as text, so callai refuses such prompts.
- pi's `--tools` allowlist keeps MCP tools unless told otherwise. Restricted permission levels need `--no-mcp` too; the stub's request log (the `tools` array) is the way to confirm what the model is really offered.
- grok's `-p`/`--single` takes the next argument as its value and has no `--` escape (`-p --help` and `-p -- x` are parser errors; `-p -` reads stdin). `--single=PROMPT` as one element takes any text. The conformance invariant allows this final `--option=PROMPT` form.
- grok runs a prompt starting with a known slash command (`/compact`) as that command, after trimming whitespace, even with `--verbatim` or `--prompt-json`. Unknown ones (`/help`, `/flush`) go through as text. Check every harness for prompt prefixes it interprets (`@` for pi, `/` for grok).
- grok's custom backend: `GROK_XAI_API_BASE_URL` + `XAI_API_KEY` point it at any OpenAI-compatible server (found via `strings` on the binary; `--help` doesn't list env vars). Its `--tools` allowlist keeps `search_tool`/`use_tool` (gateway to MCP and deferred tools); remove them with `--disallowed-tools`.
- Verify permission mappings by behaviour, not by docs or flag names: `stub_llm_server.py --tool-call` + `conformance/tools/permission_probe.py`. grok accepts `--permission-mode acceptEdits` but, headless, still refused a write; `--allow Write` works. An "outside the workspace" probe must avoid `/tmp`, which codex's `workspace-write` allows.
- grok, headless, refuses a tool call needing approval by cancelling the whole turn: `stopReason: "cancelled"`, empty text, **exit 0**, reason only on stderr ("permission required: ..."). `--max-turns` gives `max_turn_requests`, exit 1. Treat any stopReason other than `end_turn` as failure.
- `pkill -f` self-match also bites when the *same* shell command started the process: its own command line then contains the full pattern. Kill by PID (`cmd & PID=$!` … `kill $PID`) or in a separate command.
- A one-shot flag can carry hidden permission semantics: `hermes -z` auto-approves every tool call ("approvals are auto-bypassed" is in its --help), so it can only back `bypass`. Read each candidate mode's help for approvals before picking one.
- Never decode harness output with universal newlines (`subprocess` `text=True` turns `\r\n` into `\n`). hermes's display lines are only distinguishable from its answer by `\r\n` endings; the runner wraps the pipes in `io.TextIOWrapper(newline="")`, and fixtures are read with `newline=""`.
- When `--help` doesn't say how to point a harness at a custom endpoint, read its installed source or `strings` the binary (hermes: `providers:` in `$HERMES_HOME/config.yaml`; `OPENAI_BASE_URL` alone was ignored). With no provider configured, hermes silently picked up AWS credentials from the environment and called Bedrock.
- When the harness's error text comes from its own stderr, printing both duplicates it. `_render` skips the error text if stderr already contains it.
- Recorded fixtures contain real session ids: redact them to placeholder UUIDs before committing.
- Don't assert on argparse's `--help` layout: Python 3.13 changed it (`-n, --name X` instead of `-n X, --name X`). Check `parser._actions` option strings, and run `make test.matrix` (every supported Python) before a release.
- The project targets Python 3.11 (`uv run`), even though system `python3` is 3.13: no backslashes inside f-string `{…}` (3.12+ only). Run new scripts under `uv run` before committing.
- If a CDN is blocked, a page that loads libraries from it renders blank in a local Playwright check. Ask the owner to allow the host (an Allowed domains change reached this running session after a few minutes; launch Chromium with `proxy: { server: process.env.HTTPS_PROXY }`), or route the CDN URLs to local copies from `npm pack` (marked's `marked.min.js`; for highlight.js use `@highlightjs/cdn-assets`, since the `highlight.js` package has no browser build) at the same versions.
- The PyPI distribution is `callai-cli`, the import package is `callai`: `importlib.metadata.version()` takes the **distribution** name. Using `"callai"` raised `PackageNotFoundError` at import and broke every test module. Don't regex `__version__` out of `__init__.py` either (it's no longer a literal); read `pyproject.toml` in build scripts.
- Only valid trove classifiers (https://pypi.org/classifiers/) — PyPI rejects an upload with an unknown one (`AI Engineers`, `Agentic Harness`, `Software Development :: CLI` are not real). `Typing :: Typed` needs a `py.typed` file listed in `package-data`.
- Changing `[tool.uv]` (e.g. `exclude-newer`) makes `uv sync --locked` fail until `uv lock` is re-run and committed.
- A reusable workflow evaluates `concurrency` itself, with the *caller's* `github.workflow`/`github.ref`: give the caller a different group than the called workflow, or the callee cancels itself.

## Ditches — bad patterns or decisions to avoid
Bad patterns or decisions to never take, and why they were rejected.

- (none recorded yet)

## Wisdom — best practices and Red/Green TDD
Best practices worth reusing.

- Always use Red/Green TDD while developing or fixing code.
- Share code between adapters once two need it (`jsonl_events` moved into `adapters/base.py` when opencode duplicated codex's parser).
- No network or API key? Record real harness output against `conformance/tools/stub_llm_server.py` through the harness's custom-provider config, and say STUB MODEL in the fixture description. The request log (`--log`) shows exactly what the harness sent; that is how codex's `developer_instructions` system prompt was verified.
- End-to-end tests run `python -m callai` in a subprocess; `patch = ["subprocess"]` in `[tool.coverage.run]` makes them count towards coverage.
- `Request` defaults/enums and `Result` keys are pinned to `conformance/` by `test_types.py`. Change both together, never one alone.
- Write language-agnostic test cases as data in `conformance/` (not only as pytest code) — future TS/Rust ports must pass the same suite.
- Keep `CHANGELOG.md` in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format with [SemVer](https://semver.org/) version numbers — start entries under `[Unreleased]` and cut a dated, versioned section only once there's an actual release/milestone.
- claude-code against the stub: `ANTHROPIC_BASE_URL=http://127.0.0.1:PORT` (no `/v1`; it calls `/v1/messages?beta=true`), `ANTHROPIC_API_KEY=stub`, `-m stub-model`, run under `env -i` so the host session's own `CLAUDE_*`/`ANTHROPIC_*` variables (this container sets `ANTHROPIC_BASE_URL`) don't leak in.
- claude refuses `--dangerously-skip-permissions` and `--permission-mode bypassPermissions` when run as root, unless `IS_SANDBOX=1`. A refused tool call (default/plan/acceptEdits) doesn't fail the run: the model gets the refusal as the tool result and claude exits 0.
- grok's `--sandbox` profiles all allow writes inside the working directory (`read-only` and `strict` included); they only block outside it. Probe sandboxes with the working directory **outside `/tmp`** too (`TMPDIR=~/x python permission_probe.py ...`): sandboxes commonly allow `/tmp`, which hides what they do to the workspace.
- `cmd1 && cmd2 & PID=$!` backgrounds the whole `&&` chain in a subshell: variables set in it (e.g. `S=...`) don't exist afterwards, and `$!` is the subshell, not the server. Start background servers on their own line.
- When a harness takes a setting only from its environment, set it with the adapter's `build_env` (pure, tested with `expected_env`), not by mutating `os.environ`. Add only what the request asks for: an empty `build_env` leaves the user's own inherited value alone. Text `--dry-run` must print `NAME=value` with only the value quoted (`shlex.quote("N=v")` quotes the name too, which is no longer an assignment).
- A fake harness that writes its call record while a test polls for it must write a temp file and `os.replace` it: polling for "file exists" otherwise reads half-written JSON (only showed up once the record grew to include the environment).
- Write conformance `expected` values from the parser's established rules and the recorded bytes, not from memory: two hand-written stream expectations were wrong (grok's first redacted UUID is not the session id; pi's model is `provider/id`).
- Before committing a recorded fixture, `grep -rn` it for the recording machine's paths (scratch dir, home, socket paths): harnesses echo them in places you don't expect (claude's init `memory_paths`, grok's `output_file`), some URL-encoded or with `/` turned into `-`.
- The stub's `--tool-call` fires only while a request has **no** tool result yet. When resuming a session that already holds one, the stub answers with text and no tool runs: a "write didn't happen" result then says nothing about permissions. Start a fresh session per probe.
- Some harnesses make side requests after the main one (grok sends a small request with only the latest message, likely a title). When checking what reached the model, look at every request in the stub log, not just the last.
- Check how a harness's "continue latest" picks the session before mapping to it: hermes `--continue` filters by session source, so tagged non-interactive runs (`--source tool`) are invisible to it.
- Harnesses run in their own process group (`start_new_session`), so a terminal Ctrl-C reaches only callai. With harnesses in worker threads, the main thread must wait with short `join(0.1)` loops (a bare `join()` can't be interrupted), then stop every live process group itself (`runner.stop_all`, fed by the `_LIVE` registry).
- In a fan-out, check every harness (options, binaries) before starting any: half a fan-out run because the third harness refused an option is worse than failing up front.
- Docs examples must come from real runs. Hand-written outputs in this repo's docs were wrong four times while writing them:
  - placeholder durations;
  - a `jq` comparing an unexported variable;
  - a `--dry-run` placed after `--`;
  - a guessed claude error message.

  Capture outputs with the stub sandbox, then re-run the `--dry-run` blocks mechanically.
- Don't name a dispatcher's own flags after flags its targets also use (`--tool`: grok `--tools`, pi `--tools`, hermes `-t`). Readers of `callai -t grok -- --tools x` can't tell which program a flag belongs to. callai uses `-n/--name` for the harness.
