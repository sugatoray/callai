# Makefile for callai.
#
# Installs the coding-agent harness CLIs that callai drives, pinned to the versions the
# adapters and conformance fixtures were verified against. Override a version on the
# command line, e.g.  make install.codex CODEX_VERSION=0.170.0
#
#   make install.harnesses     install all of them
#   make install.<tool>        install one (tool = the callai --name value)
#   make docs.html             bundle docs/callai/ into one HTML page (build/docs.html)
#   make maint.banner          rebuild src/tools/banner/callai-banner.html from its template + config.yaml
#   make maint.banner.png      ...and render it to docs/assets/images/banner_2x.png (headless Chrome)
#   make test                  run the tests on the pinned development Python (.python-version)
#   make test.matrix           run the tests on every supported Python (PYTHON_VERSIONS)
#   make pkg.build             build the sdist + wheel into dist/ (uv build)
#   make pkg.publish           build, then upload dist/ to PyPI (uv publish; needs UV_PUBLISH_TOKEN)
#   make pkg.install.e         editable install of this checkout into .venv
#   make pkg.install.local     install callai-cli from the built dist/ (builds first)
#   make pkg.install.pypi      install callai-cli from PyPI

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Package managers (override e.g. NPM_INSTALL="sudo npm install -g" if your global prefix needs it).
NPM_INSTALL ?= npm install -g
UV_TOOL_INSTALL ?= uv tool install --force

# Verified versions (see docs/.scrolls/HANDOFF.md and conformance/ fixture descriptions).
# `:=`, not `?=`: environment variables must not override these. Claude Code itself exports
# CLAUDE_CODE_VERSION, which silently pinned the wrong version. `make VAR=x` still overrides.
CLAUDE_CODE_VERSION := 2.1.314
CODEX_VERSION := 0.166.0
OPENCODE_VERSION := 1.19.5
PI_VERSION := 1.4.0
HERMES_VERSION := 0.19.0
GROK_VERSION := 1.0.70

HARNESSES := claude-code codex opencode pi hermes grok

.PHONY: help test test.matrix docs.html maint.banner maint.banner.check maint.banner.png pkg.build pkg.publish pkg.install.e pkg.install.local pkg.install.pypi install.harnesses $(addprefix install.,$(HARNESSES)) require.npm require.uv

help: ## Show this help
	@echo "Targets:"
	@grep -E '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-24s %s\n", $$1, $$2}'

# Tests. `make test` uses the development Python pinned in .python-version. `make test.matrix` runs
# the suite once per supported Python, each in a fresh isolated environment (your .venv is untouched);
# uv downloads any Python it doesn't have. One version: make test.matrix PYTHON_VERSIONS=3.14
# Keep PYTHON_VERSIONS, the classifiers in pyproject.toml and .github/workflows/tests.yml in step.
PYTHON_VERSIONS ?= 3.11 3.12 3.13 3.14

test: ## Run the tests on the pinned development Python (.python-version)
	uv run --extra test pytest

test.matrix: ## Run the tests on every supported Python, each isolated (PYTHON_VERSIONS="3.11 3.12 3.13 3.14")
	@set -e; for py in $(PYTHON_VERSIONS); do \
	  echo "== Python $$py"; \
	  uv run --isolated --python $$py --extra test pytest -q; \
	done

# Packaging. Everything goes through uv. Every knob is a variable, override on the command line, e.g.
#   make pkg.install.pypi PKG_VERSION=0.8.0
#   make pkg.publish PUBLISH_URL=https://test.pypi.org/legacy/ PUBLISH_CHECK_URL=https://test.pypi.org/simple/
#   make pkg.install.e VENV=/tmp/v
PKG_NAME ?= callai-cli
# optional pin: installs callai-cli==PKG_VERSION
PKG_VERSION ?=
PKG_SPEC ?= $(PKG_NAME)$(if $(PKG_VERSION),==$(PKG_VERSION))
DIST_DIR ?= dist
# environment the pkg.install.* targets install into
VENV ?= .venv
VENV_PYTHON ?= $(VENV)/bin/python
# optional --index-url for pkg.install.pypi (e.g. TestPyPI)
PYPI_INDEX ?=
# optional upload endpoint (default: PyPI)
PUBLISH_URL ?=
# optional index to verify the upload against
PUBLISH_CHECK_URL ?=
UV_BUILD ?= uv build --out-dir $(DIST_DIR)
UV_PUBLISH ?= uv publish
UV_VENV ?= uv venv --allow-existing
UV_PIP_INSTALL ?= uv pip install --python $(VENV_PYTHON)

pkg.build: require.uv ## Build the sdist and wheel into DIST_DIR (default dist/)
	rm -rf $(DIST_DIR)
	$(UV_BUILD)

pkg.publish: pkg.build ## Build, then upload DIST_DIR to PyPI (UV_PUBLISH_TOKEN, or PUBLISH_URL for another index)
	$(UV_PUBLISH) $(if $(PUBLISH_URL),--publish-url $(PUBLISH_URL)) $(if $(PUBLISH_CHECK_URL),--check-url $(PUBLISH_CHECK_URL)) $(DIST_DIR)/*

pkg.install.e: require.uv ## Editable install of this checkout (with the dev/test extras) into VENV
	$(UV_VENV) $(VENV)
	$(UV_PIP_INSTALL) -e ".[test,dev]"

pkg.install.local: pkg.build ## Install callai-cli from the built DIST_DIR into VENV (no index lookups)
	$(UV_VENV) $(VENV)
	$(UV_PIP_INSTALL) --reinstall-package $(PKG_NAME) --no-index --find-links $(DIST_DIR) $(PKG_SPEC)

pkg.install.pypi: require.uv ## Install callai-cli from PyPI into VENV (PYPI_INDEX for another index)
	$(UV_VENV) $(VENV)
	$(UV_PIP_INSTALL) --reinstall-package $(PKG_NAME) $(if $(PYPI_INDEX),--index-url $(PYPI_INDEX)) $(PKG_SPEC)

# Single-page HTML docs. Links to files outside docs/ point at GitHub on DOCS_REF (default: this branch).
DOCS_HTML ?= build/docs.html
DOCS_REF ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)

docs.html: ## Bundle docs/callai/ into one HTML page with tabs, page list, outline and theme toggle (DOCS_HTML=build/docs.html)
	python3 docs/site/build_docs_html.py docs/callai --out $(DOCS_HTML) --ref $(DOCS_REF)

# Banner (maintainer tool, not packaged). Fills src/tools/banner/assets/callai-banner-template.html with the
# values in src/tools/banner/config.yaml; "auto" values come from pyproject.toml and the harness registry.
# Override on the command line, e.g.
#   make maint.banner BANNER_PACKAGE_VERSION=0.9.0
#   make maint.banner BANNER_ARGS='--set tagline="Hello" --harnesses codex,pi'
#   make maint.banner.png BANNER_SCALE=4                      (-> docs/assets/images/banner_4x.png)
#   make maint.banner.png BANNER_BACKGROUND=transparent BANNER_PNG=build/banner_2x_transparent.png
BANNER_PYTHON ?= uv run --no-project python
BANNER_PACKAGE_VERSION ?=
BANNER_ARGS ?=
BANNER_CMD = $(BANNER_PYTHON) src/tools/banner/create_banner.py $(if $(BANNER_PACKAGE_VERSION),--package-version $(BANNER_PACKAGE_VERSION)) $(BANNER_ARGS)

maint.banner: ## Rebuild src/tools/banner/callai-banner.html from the template and config.yaml (BANNER_PACKAGE_VERSION=, BANNER_ARGS=)
	$(BANNER_CMD)

maint.banner.check: ## Exit 1 if src/tools/banner/callai-banner.html is out of date
	$(BANNER_CMD) --check

# PNG of the banner via headless Chrome (prefers chrome-headless-shell; BANNER_CHROME or $$CHROME to choose).
# The file name carries the scale: banner_1x.png, banner_2x.png, banner_4x.png.
BANNER_PNG ?= docs/assets/images/banner_$(BANNER_SCALE)x.png
BANNER_SCALE ?= 2
BANNER_BACKGROUND ?= as-is
BANNER_INK ?= auto
BANNER_CHROME ?=

maint.banner.png: ## Rebuild the banner and render it to BANNER_PNG (default docs/assets/images/banner_2x.png)
	$(BANNER_CMD) --png $(BANNER_PNG) --scale $(BANNER_SCALE) --background $(BANNER_BACKGROUND) --ink $(BANNER_INK) $(if $(BANNER_CHROME),--chrome "$(BANNER_CHROME)")

install.harnesses: $(addprefix install.,$(HARNESSES)) ## Install every harness CLI callai supports
	@echo "All harnesses installed: $(HARNESSES)"

install.claude-code: require.npm ## Claude Code (npm @anthropic-ai/claude-code) -> claude
	$(NPM_INSTALL) @anthropic-ai/claude-code@$(CLAUDE_CODE_VERSION)
	claude --version

install.codex: require.npm ## OpenAI Codex CLI (npm @openai/codex) -> codex
	$(NPM_INSTALL) @openai/codex@$(CODEX_VERSION)
	codex --version

install.opencode: require.npm ## opencode (npm opencode-ai) -> opencode
	$(NPM_INSTALL) opencode-ai@$(OPENCODE_VERSION)
	opencode --version

install.pi: require.npm ## pi coding agent (npm @earendil-works/pi-coding-agent) -> pi
	$(NPM_INSTALL) @earendil-works/pi-coding-agent@$(PI_VERSION)
	pi --version

install.hermes: require.uv ## Nous Research Hermes Agent (PyPI hermes-agent) -> hermes
	$(UV_TOOL_INSTALL) hermes-agent==$(HERMES_VERSION)
	hermes --version

install.grok: require.npm ## xAI Grok Build CLI (npm @xai-official/grok, official) -> grok
	$(NPM_INSTALL) @xai-official/grok@$(GROK_VERSION)
	grok --version

require.npm:
	@command -v npm >/dev/null || { echo "npm not found: install Node.js (https://nodejs.org)" >&2; exit 1; }

require.uv:
	@command -v uv >/dev/null || { echo "uv not found: see https://docs.astral.sh/uv/" >&2; exit 1; }
