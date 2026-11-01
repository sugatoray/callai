# Makefile for callai.
#
# Installs the coding-agent harness CLIs that callai drives, pinned to the versions the
# adapters and conformance fixtures were verified against. Override a version on the
# command line, e.g.  make install.codex CODEX_VERSION=0.170.0
#
#   make install.harnesses     install all of them
#   make install.<tool>        install one (tool = the callai --name value)
#   make docs.html             bundle docs/callai/ into one HTML page (build/docs.html)

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

.PHONY: help docs.html install.harnesses $(addprefix install.,$(HARNESSES)) require.npm require.uv

help: ## Show this help
	@echo "Targets:"
	@grep -E '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-24s %s\n", $$1, $$2}'

# Single-page HTML docs. Links to files outside docs/ point at GitHub on DOCS_REF (default: this branch).
DOCS_HTML ?= build/docs.html
DOCS_REF ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)

docs.html: ## Bundle docs/callai/ into one HTML page with tabs, page list, outline and theme toggle (DOCS_HTML=build/docs.html)
	python3 docs/site/build_docs_html.py docs/callai --out $(DOCS_HTML) --ref $(DOCS_REF)

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
