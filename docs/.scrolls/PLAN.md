# PLAN.md — Prioritized Backlog

The ordered, ticketed backlog. Highest priority first. Update ticket status (`[ ]` → `[x]`) as work completes, and re-prioritize when new requests change the calculus — this file reflects what's next, not a permanent record (that's what git history is for).

Design reference: `docs/DESIGN.md` (section numbers below point there).

> **Scope & roadmap note (2026-10-30):** see [`SCOPE.md`](../../SCOPE.md) (next to `SCROLLS.md`) for the
> full record of the language/distribution discussion. Agreed order: **Python first** (Red/Green TDD,
> PyPI) → **TypeScript port** maintained alongside Python → **Rust port** if it makes sense →
> possibly **Rust core distributed to PyPI + npm via thin wrappers**. Keep language-agnostic tests in
> a shared `conformance/` suite (golden argv, recorded parse fixtures, CLI cases) so every port is
> verifiable against the same data. Tickets below cover the Python implementation; later phases are
> placeholders until Python is stable.

## Phase 0 — decisions
- [x] CA-0: Resolve DESIGN §11 open decisions → xAI grok, default `text`, Python ≥ 3.11, PyPI name `callai-cli`.

## Phase 1 — skeleton (MVP with claude-code)
- [x] CA-1a: `conformance/` suite (format spec in `conformance/README.md`) + strict pytest loader `src/tests/conformance.py`. Seeded with 12 claude-code argv cases, 2 recorded claude parse fixtures, 16 CLI cases. Tests that run these against the implementation land in CA-3/4/5.
- [x] CA-1: `pyproject.toml` (distribution `callai-cli` 0.1.0.dev0, import/command `callai`, Python ≥ 3.11, no runtime deps, coverage gate 95%), `src/callai/{__init__,__main__,cli}.py` skeleton (`--version`; anything else → usage error, exit 2). (setuptools src layout, `callai` console script, pytest+cov, ruff, interrogate — mirror `expt_svg2font`), `src/callai/__init__.py`, `__main__.py`.
- [x] CA-2: frozen `Request`/`Completed`/`Result` dataclasses, `errors.py` (`UsageError` → exit 2), `Adapter` ABC (+ `text_result` fallback, `strip_ansi`), `TOOLS` + registry (§4). Tests also assert the types agree with `conformance/` defaults and keys.
- [x] CA-3: `cli.py` argparse surface (§3): `-t`, `-p/-c/--prompt/--command` aliases, `-m`, `-o`, `-C`, `--timeout`, `--dry-run`, `--`, stdin prompt rules.
- [x] CA-4: `runner.py`: list-argv subprocess, cwd, timeout → 124, missing binary → 127, SIGINT forwarding (§8). Fake-harness integration tests.
- [x] CA-5: `claude-code` adapter: argv golden tests + JSON parser from real recorded fixtures (§2, §5). Verified live against claude 2.1.314.

## Phase 2 — remaining adapters (each: verify `--help` first, record fixtures, golden argv tests)
- [x] CA-6: `codex` adapter (`codex exec --json --skip-git-repo-check`, sandbox mapping, system prompt via `-c developer_instructions`). Verified against codex-cli 0.166.0 + local stub model.
- [x] CA-7: `opencode` adapter (`opencode run --format json --print-logs --log-level ERROR`, prompt split on spaces, `--auto` for bypass; read-only/auto/system prompt refused). Verified against opencode 1.19.5 + stub model.
- [x] CA-8: `pi` adapter (`pi --mode json`, `--tools` allowlists for read-only/auto, `--system-prompt`, `@` prompts refused). Verified against pi 1.4.0 + stub model.
- [x] CA-9: `grok` adapter (`grok --output-format json --single=PROMPT`, `--tools` allowlist for read-only, `--allow Write --allow Edit` for auto, `bypassPermissions`, `--system-prompt-override`, `/` prompts refused). Verified against grok 1.0.70 (npm `@xai-official/grok`) + stub model via `GROK_XAI_API_BASE_URL`.
- [x] CA-20: stub model `--tool-call` (scripted tool calls) + `conformance/tools/permission_probe.py`; verified what every `--permission` level allows for codex, opencode, pi, grok (DESIGN §7). Found and fixed: grok `acceptEdits` doesn't approve headless writes; grok refused calls exit 0.
- [x] CA-10: `hermes` adapter (`hermes chat -Q --source tool --query=PROMPT`; answer = stdout minus `\r\n` display lines; `-t file` for auto, `--yolo` for bypass; read-only and system prompt refused). Verified against hermes-agent 0.19.0 + stub model, incl. permission probe. Also fixed: runner now captures output byte-exact (no `\r\n` translation).
- [x] CA-21: adapters set environment variables (`build_env`); hermes `--system-prompt` via `HERMES_EPHEMERAL_SYSTEM_PROMPT`; `expected_env` (argv) and `harness_env` (cli) conformance fields; `--dry-run` shows env. Verified against hermes-agent 0.19.0 + stub model.

## Phase 3 — polish
- [x] CA-19: Don't hang on an idle non-TTY stdin. With `-p TEXT`, wait `CALLAI_STDIN_WAIT` (3s) for stdin data, then warn and proceed (as `claude -p` 2.1.314 does); with `-p -`/no `-p`, wait for EOF. Usage errors are checked before stdin is read (`cli.preflight`). Conformance key `stdin_open`.
- [x] CA-11: `--permission` leftovers (§7): `bypass` stderr warning; claude-code probed (stub speaks Anthropic Messages); grok `--sandbox` probed and deliberately not mapped (every profile allows workspace writes; needs bwrap).
- [x] CA-22: rename callai's harness flag `-t/--tool` → `-n/--name HARNESS_NAME` (harnesses have their own `--tool(s)` flags) and `adapters.TOOLS` → `HARNESS_NAMES`. No `-t` alias. Env var `CALLAI_TOOL` → `CALLAI_HARNESS_NAME` (a leftover `CALLAI_TOOL` gets a "renamed" usage error). `-o json` key `tool`, `Request.tool`/`Result.tool` and the conformance case field `tool` → `harness_name`.
- [x] CA-12: config file (`config.toml`: `default_harness`, `model`, `timeout`, `[harnesses.<name>] binary/model/extra_args`, `[aliases]`) + `CALLAI_MODEL`/`CALLAI_TIMEOUT` + model aliases (§6). Strict: unknown keys → exit 2. Conformance case key `config`.
- [x] CA-13: `--list-harnesses` (owner chose the name; `-o json` too), README usage/config docs, live smoke tests (`src/tests/test_live.py`, `CALLAI_LIVE=all|<names>`, marker `live`). `--version` already existed.
- [x] CA-14: `-o stream-json`: start/text/tool_use/tool_result/result events, live (`runner.run(on_stdout_line)`), pure `Adapter.stream_events(line, state)` per harness; claude `stream-json --verbose`, grok `streaming-json`. Conformance `expected_events` (parse) and `stdout_events` (cli). Verified end to end for all five streaming harnesses + stub, and live claude.

## Phase 4 — sessions, library, fan-out (CA-15, split 2026-10-30; owner chose all three, in this order)
- [x] CA-15a: `--resume SESSION_ID` / `--continue` mapped to each harness's session flags (codex: `exec ... resume ID|--last`); hermes `--continue` refused. Verified with all six harnesses + stub (resumed request carries earlier turns; codex sandbox still applies).
- [x] CA-15b: Python API `callai.run(...)` → the `-o json` `Result`; `on_event` = stream-json events; no env/config (explicit only); `binary` override; `api.run_harness` shared with the CLI. Checked live with claude (incl. `resume=`).
- [x] CA-15c: fan-out. Owner's syntax: `-n a/b/c` parallel, `-n a,b,c` sequential, `-n all` every installed harness concurrently. Preflight all before running; `-n all` skips refusals; text headers / `{"results"}` / tagged stream events; first failure's exit code; Ctrl-C stops all (`runner.stop_all`). Checked with all six real harnesses + stub.

## Docs
- [x] CA-23: user documentation `docs/callai/` via `/create-lib-docs` (skill now in `sugatoray/aiskills`; Getting Started, Tutorial, Guides, Concepts, Reference, FAQ, llms.txt). Keep `reference/*.md` in sync with flags, errors and output whenever they change.
- [x] CA-24: `make docs.html` bundles `docs/callai/` into one HTML page (`build/docs.html`): section tabs, page list, on-this-page outline, search, light/dark toggle. Builder + template in `docs/site/`; tabs come from the landing page's `### Section` lists, so a new page must be linked there or the build fails.

- [x] CA-25: supported Pythons 3.11–3.14. `.python-version` pins 3.11 for development (`make test`); `make test.matrix` (`PYTHON_VERSIONS`) runs every version via `uv run --isolated --python`; `.github/workflows/tests.yml` runs the same per version plus lint. `requires-python` stays `>=3.11` (no cap: it breaks resolution for dependents); classifiers list the tested versions. Add a version: Makefile, workflow matrix and classifiers together.

- [x] CA-26: packaging metadata and opt-in CI (PR #35, draft until merged). Single-sourced version (`pyproject.toml` → installed metadata), valid trove classifiers + `py.typed`, `.editorconfig`, uv `exclude-newer` cooldown, tests run on master/manual/`ci::run-tests` label only. `make pkg.*` targets and `MANIFEST.in` added. `docs.yml` publishes the docs on GitHub Pages. Open: create the `ci::run-tests` label; run `docs.yml` once on master and check the site; confirm both workflows on GitHub; try `pkg.publish` on TestPyPI before the first real release.

## Maintainer tools (`src/tools/`, never packaged)
- [x] CA-27: callai-cli banner. `src/tools/banner/`: template (`assets/callai-banner-template.html`) + `config.yaml` (double-quoted values, `"auto"` from `pyproject.toml`/`HARNESS_NAMES`) → `create_banner.py` → committed `callai-banner.html`. `make maint.banner` / `maint.banner.check`; tests in `src/tools/banner/tests` run with `make test` and fail while the committed page is stale. `make maint.banner.png` → `docs/assets/images/banner_2x.png` (2x, headless Chrome), shown at the top of README.md; the `make docs.html` landing page shows the banner's static HTML instead. Install commands: `install_commands` + `install_style` box (option A, default) / chips (option B), live toolbar switch, examples `assets/option_{a_box,b_chip}.png` refreshed by `make maint.banner.png` (or `maint.banner.examples`). Own `README.md` and `CHANGELOG.md`. PR https://github.com/sugatoray/callai/pull/46 (branch `claude/friendly-darwin-kqdygb`), open.

## Later
- [ ] CA-16: TypeScript port, module by module, passing the full `conformance/` suite (vitest); publish to npm. Maintained alongside Python.
- [ ] CA-17: (if it makes sense) Rust port passing `conformance/`.
- [ ] CA-18: (if it makes sense) Rust core as single implementation; distribute to PyPI (maturin `bin`) + npm (per-platform `optionalDependencies`) with thin Python/TS wrappers (SCOPE §3–4).
