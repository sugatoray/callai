# HANDOFF.md — Change of Guard

Snapshot of where the project stands *right now*. This file is short-lived: **overwrite** it at the end of every session rather than appending — it's a state snapshot, not a changelog.

## Current state
- Repository `sugatoray/callai` is now the primary home (imported from `sugatoray/devx` `src/experiments/expt_callai` at 0.8.0; the devx copy is no longer where it is developed). The import branch `feat/import-callai` was merged and deleted. Version **0.8.0** (CHANGELOG 0.1.0…0.5.0 cut 2026-10-30, 0.6.0 on 2026-10-31, 0.7.0 (docs) and 0.8.0 (`make docs.html`) on 2026-11-01; no git tags yet). `[Unreleased]` is empty.
- CA-0…CA-15c, CA-19…CA-24 done. Remaining backlog is Later only: CA-16 TypeScript port, CA-17/18 Rust.
- CLI: `callai -n HARNESS_NAME|a/b|a,b|all -p PROMPT [...]`, `-o text|json|stream-json|raw`, `--resume ID`/`--continue`; Python API `callai.run(...)`.
- User docs: `docs/callai/` (32 pages, 5 SVGs, `llms.txt`/`llms-full.txt`), written with the `/create-lib-docs` skill (published in `sugatoray/aiskills`). `make docs.html` bundles them into `build/docs.html` (gitignored).
- All six harness CLIs are installed in the dev container (ephemeral). In a new session run `make install.harnesses` from the repository root; pinned versions are in the `Makefile`.
- Network policy denies api.openai.com, api.x.ai and router.huggingface.co (cdnjs, jsDelivr and Google Fonts are allowed), and there are no model API keys, so non-claude fixtures come from `conformance/tools/stub_llm_server.py` (labelled STUB MODEL). `conformance/README.md` → "Recording without network" has every harness's config.
- Python: develop on 3.11 (`.python-version`, `make test`); `make test.matrix` and CI (`.github/workflows/tests.yml`, not yet run on GitHub) cover 3.11–3.14, all passing locally.
- 531 tests (+12 live, skipped by default), 99% coverage, ruff and interrogate clean. 74 conformance CLI cases. The suite takes ~42 s (fan-out timing tests sleep).

## What just happened
- Installed agent skills from `sugatoray/aiskills` with `npx skills add` for Codex and Claude Code: scrolls-setup/-update/-help/-hide/-unhide, create-issues-update-pr, create-lib-docs (`create-lob-docs` was a typo for `create-lib-docs`). Files are in `.agents/skills/` (Claude Code symlinks via `.claude/skills/`), pinned in `skills-lock.json`. Pushed on branch `claude/blissful-bell-tqq4l2`, PR https://github.com/sugatoray/callai/pull/30.
- CA-25: Python 3.11–3.14 support made explicit (pin, `make test.matrix`, CI workflow, classifiers). Fixed a test that failed on 3.13 (argparse help layout).
- Moved to `sugatoray/callai`: `expt_callai`/"this experiment" wording replaced with callai / the repository root; `pyproject.toml` `[project.urls]` now point here; docs links point here.
- 0.8.0 cut (`make docs.html`); the artifact was republished from the 0.8.0 build.
- CA-24 `make docs.html`: `docs/site/build_docs_html.py` + `template.html`, tests in `src/tests/test_docs_html.py`. The same page was published as a private claude.ai artifact (https://claude.ai/artifact/GMbkLnE6SNvudiPsjYAM6w); republish it from `build/docs.html` if the docs change.
  - Checked in headless Chromium with local copies of marked 12.0.2 / highlight.js 11.9.0: every link to another page and heading resolves; no horizontal scroll at 400–1440 px in either theme. Re-checked 2026-11-01 against the live cdnjs (after the owner allowed it): same results.
- Before that: 0.7.0 cut (docs only), CA-23 docs, CA-15a/b/c (sessions, Python API, fan-out).

## Known issues / open threads
- When a docs page is added, link it from a `### Section` list in `docs/callai/README.md`, then re-run `check_docs.py`, `build_llms_txt.py` (skill scripts) and `make docs.html`.
- Live tests verified only for claude-code (no model access for the others here).
- Windows still blocks on an idle stdin pipe.
- Fan-out: shared working directory; `-v` stderr not prefixed in parallel.
- Next: CA-16 (TypeScript port) if wanted, or tag v0.1.0…v0.8.0 (or just v0.8.0), since the import is merged.
- Gemma via Hugging Face: needs `router.huggingface.co` allowed and an HF_TOKEN. Untested.
