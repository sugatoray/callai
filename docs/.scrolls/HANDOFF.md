# HANDOFF.md — Change of Guard

Snapshot of where the project stands *right now*. This file is short-lived: **overwrite** it at the end of every session rather than appending — it's a state snapshot, not a changelog.

## Current state
- Repository `sugatoray/callai` is now the primary home (imported from `sugatoray/devx` `src/experiments/expt_callai` at 0.8.0; the devx copy is no longer where it is developed). The import branch `feat/import-callai` was merged and deleted. Version **0.8.0** (CHANGELOG 0.1.0…0.5.0 cut 2026-10-30, 0.6.0 on 2026-10-31, 0.7.0 (docs) and 0.8.0 (`make docs.html`) on 2026-11-01; no git tags yet). `[Unreleased]` is empty.
- CA-0…CA-15c, CA-19…CA-27 done. Remaining backlog is Later only: CA-16 TypeScript port, CA-17/18 Rust.
- CLI: `callai -n HARNESS_NAME|a/b|a,b|all -p PROMPT [...]`, `-o text|json|stream-json|raw`, `--resume ID`/`--continue`; Python API `callai.run(...)`.
- User docs: `docs/callai/` (32 pages, 5 SVGs, `llms.txt`/`llms-full.txt`), written with the `/create-lib-docs` skill (published in `sugatoray/aiskills`). `make docs.html` bundles them into `build/docs.html` (gitignored).
- All six harness CLIs are installed in the dev container (ephemeral). In a new session run `make install.harnesses` from the repository root; pinned versions are in the `Makefile`.
- Network policy denies api.openai.com, api.x.ai and router.huggingface.co (cdnjs, jsDelivr and Google Fonts are allowed), and there are no model API keys, so non-claude fixtures come from `conformance/tools/stub_llm_server.py` (labelled STUB MODEL). `conformance/README.md` → "Recording without network" has every harness's config.
- Python: develop on 3.11 (`.python-version`, `make test`); `make test.matrix` and CI (`.github/workflows/tests.yml`; runs on master pushes and manual dispatch, and on PRs labelled `ci::run-tests` via `run-tests-on-label.yml`) cover 3.11–3.14, all passing locally.
- 578 tests (+13 skipped: 12 live, 1 runs only when PyYAML is installed), 99% coverage, ruff and interrogate clean. 74 conformance CLI cases. The suite takes ~35–42 s (fan-out timing tests sleep). `testpaths` now includes `src/tools/banner/tests`.
- Maintainer tools live in `src/tools/` (not packaged). The first is the banner builder `src/tools/banner/` (CA-27), with its own `README.md` and `CHANGELOG.md`.

## What just happened
- CA-27 banner, on branch `claude/friendly-darwin-kqdygb`, PR https://github.com/sugatoray/callai/pull/46 (opened from the Claude Code UI):
  - The editable banner page (1280 × 640: Edit/Save toggle, PNG export as is/white/black/transparent at 1x/2x/4x via `html-to-image` 1.11.11 from jsDelivr) became the template `src/tools/banner/assets/callai-banner-template.html`. It was first committed at `docs/callai/images/callai-banner.html`, which no longer exists.
  - `src/tools/banner/create_banner.py` (stdlib only) fills the template's `{{ name }}` placeholders from `src/tools/banner/config.yaml`. Every value is double-quoted (a strict YAML-subset parser; a test checks it matches PyYAML). `"auto"` values come from `pyproject.toml` and `HARNESS_NAMES` (read with `ast`, not imported). Flags `--package-version` etc. and `--set KEY=VALUE` override the config; `--check` exits 1 when stale.
  - Output `src/tools/banner/callai-banner.html` is committed. `make maint.banner` (`BANNER_PACKAGE_VERSION=`, `BANNER_ARGS=`, `BANNER_PYTHON=`) rebuilds it; `make maint.banner.check` checks it.
  - `make maint.banner.png` (`create_banner.py --png`) renders the page in headless Chrome (page's `?export` mode) to `docs/assets/images/banner_2x.png`, **2x (2560×1280) by default** (`BANNER_SCALE`, `BANNER_BACKGROUND`, `BANNER_INK`, `BANNER_PNG`, `BANNER_CHROME`). The PNG is committed.
  - `make docs.html` opens the landing page with the banner's static HTML + CSS, copied by `build_docs_html.py` from `src/tools/banner/callai-banner.html` between `banner:html:*`/`banner:css:*` markers (no `data-edit`, no `id="pills"`, wordmark `<h1>` → `<div>`), in a `#hero` slot outside `.doc` scaled by a ResizeObserver (`--banner PATH`/`--no-banner`). ~187 KB. Checked in Chromium at 1280 px (light) and 390 px (dark): no errors, no horizontal scroll, not in the outline, hidden on other pages. (An earlier version embedded the PNG, ~1 MB; replaced at the owner's request.) README.md also starts with the banner (absolute raw.githubusercontent URL on master, for PyPI), so it shows broken until the branch is merged.
  - `make docs.html` header: GitHub button (`{{REPO}}` placeholder filled from `REPO` in `build_docs_html.py`; never a branch) before the theme toggle, and a magnifying-glass icon in the search box; at ≤560 px the placeholder text is transparent (aria-label keeps the name). Owner approved three mockups first. Checked in Chromium at 1280/390 px, both themes: no errors, no horizontal scroll, Tab reaches the button.
  - `MANIFEST.in` has `prune src/tools` + `recursive-exclude src/tools *` (owner's explicit request; see open threads). Root `CHANGELOG.md` has a one-line pointer to `src/tools/banner/CHANGELOG.md`.
- Before that: CA-26 packaging (PR https://github.com/sugatoray/callai/pull/35): classifiers + `py.typed`, single-sourced version, `make pkg.*`, `MANIFEST.in`, opt-in CI (`ci::run-tests` label), `docs.yml` for GitHub Pages; and the agent skills from `sugatoray/aiskills` (PR https://github.com/sugatoray/callai/pull/30).

## Known issues / open threads
- `docs/assets/images/banner_2x.png` is **not** covered by the up-to-date test (PNG bytes aren't reproducible across browsers/fonts). Re-run `make maint.banner.png` after `make maint.banner` changes the page.
- **Bumping the version in `pyproject.toml` now fails `test_committed_banner_is_up_to_date` until `make maint.banner` is run** (same for changing `HARNESS_NAMES`, `config.yaml` or the template). Deliberate drift guard; the owner was told it can be dropped.
- `uv build` warns "no previously-included … matching 'src/tools'": setuptools never packs `src/tools` (not a `callai*` package), so the two `MANIFEST.in` lines have no effect today. The owner confirmed (2026-11-04): keep them as a failsafe; don't remove them to silence the warnings.
- CA-26 open items still stand: create the `ci::run-tests` label, run `docs.yml` once on master, confirm both workflows on GitHub, try `pkg.publish` on TestPyPI.
- When a docs page is added, link it from a `### Section` list in `docs/callai/README.md`, then re-run `check_docs.py`, `build_llms_txt.py` (skill scripts) and `make docs.html`.
- Live tests verified only for claude-code (no model access for the others here).
- Windows still blocks on an idle stdin pipe.
- Fan-out: shared working directory; `-v` stderr not prefixed in parallel.
- After a fresh clone run `uv sync --extra test --extra dev` (the version now comes from installed metadata; an uninstalled source tree reports `0.0.0+unknown`).
- Next: CA-16 (TypeScript port) if wanted, or tag v0.1.0…v0.8.0 (or just v0.8.0), since the import is merged.
- Gemma via Hugging Face: needs `router.huggingface.co` allowed and an HF_TOKEN. Untested.
