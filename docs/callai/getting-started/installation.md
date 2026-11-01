# Installation

Install callai itself, then the harness CLIs you want it to drive.

## Requirements

- Python 3.11 or newer. callai has no runtime dependencies.
- macOS or Linux. Windows works, except that `callai -p TEXT` can block on a stdin pipe that never
  closes. See the [FAQ](../faq.md#callai-hangs-on-windows-when-run-from-a-script).
- At least one harness CLI on your `PATH`, signed in or configured with an API key.

## Install callai

callai is not on PyPI yet (its distribution name will be `callai-cli`). Install it from a clone of the
repository, as a tool on your `PATH`:

```bash
git clone https://github.com/sugatoray/callai.git
uv tool install ./callai
callai --version
```

```text
callai 0.8.0
```

Or into a virtual environment with pip, which also makes the Python API importable:

```bash
python3 -m venv .venv
.venv/bin/pip install ./callai
.venv/bin/callai --version
```

## Install the harnesses

Install only the ones you'll use. Each harness needs its own sign-in or API key: callai uses whatever
the harness is already configured with.

| `-n` name | Binary | Install |
|---|---|---|
| `claude-code` | `claude` | `npm install -g @anthropic-ai/claude-code` ([docs](https://code.claude.com/docs/en/setup)) |
| `codex` | `codex` | `npm install -g @openai/codex` ([docs](https://developers.openai.com/codex/cli)) |
| `opencode` | `opencode` | `npm install -g opencode-ai` ([docs](https://opencode.ai/docs/)) |
| `pi` | `pi` | `npm install -g @earendil-works/pi-coding-agent` ([docs](https://pi.dev/docs/latest/quickstart)) |
| `hermes` | `hermes` | `uv tool install hermes-agent` ([docs](https://hermes-agent.nousresearch.com/docs/)) |
| `grok` | `grok` | `npm install -g @xai-official/grok` ([docs](https://x.ai/cli)) |

From the project folder, the Makefile installs all of them at the versions callai was verified
against:

```bash
cd callai
make install.harnesses        # or one: make install.codex
```

> [!WARNING]
> `npm install -g @vibe-kit/grok-cli` also installs a `grok` command, but it is a different program
> with different flags, and callai doesn't support it. Use xAI's `@xai-official/grok`.

## Check what's installed

```bash
callai --list-harnesses
```

```text
claude-code  claude     2.1.316 (Claude Code)  /opt/node22/bin/claude
codex        codex      codex-cli 0.166.0  /opt/node22/bin/codex
opencode     opencode   1.19.5  /opt/node22/bin/opencode
pi           pi         1.4.0  /opt/node22/bin/pi
hermes       hermes     Hermes Agent v0.19.0 (2026.7.20)  /root/.local/bin/hermes
grok         grok       grok 1.0.70 (f50904eaee6c)  /opt/node22/bin/grok
```

A harness that isn't installed shows `not installed (see <install URL>)` instead.

Next: [Quickstart](quickstart.md) · Previous: [Why callai](why-callai.md)
