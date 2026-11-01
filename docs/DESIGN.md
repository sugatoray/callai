# callai — Design

> Status: **draft, pre-implementation**. All §11 decisions resolved 2026-10-30. The executable
> spec of this design is the shared suite in [`../conformance/`](../conformance/README.md).

## 1. Goal

One command line that runs a single, non-interactive prompt through any supported
coding-agent harness and prints the result. It works like `claude -p`, but you choose the harness:

```bash
callai -n claude-code -p "Summarise src/ in 3 bullets"
callai -n codex       -c "Add type hints to utils.py" -m gpt-5-codex
callai -n opencode    -p "List TODOs" -m anthropic/claude-sonnet-4-5
git diff | callai -n pi -p "Review this diff"          # prompt + stdin, like claude -p
```

`callai` is a **thin dispatcher**. It does not run an agent loop itself, call model APIs,
or manage credentials. Each harness keeps doing its own work (tools, auth, sessions,
sandboxing). `callai` does three things:

1. turns one common request into the right command line for the chosen harness,
2. runs it as a subprocess, with timeouts and a working directory,
3. turns the harness's output into one predictable shape, either text or JSON.

### Non-goals (v1)

- Interactive or TUI sessions. Use the harness directly for those.
- Installing, upgrading or logging into harnesses.
- Matching every harness flag. Uncommon flags go through `--` passthrough (see §3).
- Running several harnesses at once or comparing their results. This is a possible later feature (§10).

## 2. Supported harnesses and how each runs headless

Researched on 2026-10-30. Only `claude` is installed in the dev container, so the other
rows are taken from docs and **must be checked against `<tool> --help` before shipping**.
Their PLAN tickets include that check.

| `--name`      | Binary     | Headless invocation                         | Model flag                     | Native structured output            | Notes |
|---------------|------------|---------------------------------------------|--------------------------------|-------------------------------------|-------|
| `claude-code` | `claude`   | `claude -p PROMPT`                          | `--model M`                    | `--output-format json\|stream-json` | `json` gives `result`, `session_id`, `usage`, `total_cost_usd`. `-o stream-json` uses `--output-format stream-json --verbose` (claude requires `--verbose` with it); its last line is the same result object. Checked locally. |
| `codex`       | `codex`    | `codex exec --json --skip-git-repo-check -- PROMPT` | `--model M`            | `--json` (JSONL events)             | **Verified** (codex-cli 0.166.0). System prompt via `-c developer_instructions=<TOML string>`. No `--full-auto` in 0.166. Retries forever without network — use `--timeout`. |
| `opencode`    | `opencode` | `opencode run --format json --print-logs --log-level ERROR -- WORDS…` | `--model provider/model` | `--format json` (JSONL events) | **Verified** (1.19.5). Prompt passed split on spaces (opencode quotes any arg containing a space). No read-only/auto mode and no system prompt: refused. In `run`, `-p` = password and `-c` = continue. |
| `pi`          | `pi`       | `pi --mode json -- PROMPT`                  | `--model provider/id`          | `--mode json` (JSONL)               | **Verified** (1.4.0, npm `@earendil-works/pi-coding-agent`). Reports the model it used. Exits 0 on model errors (`stopReason: error`). Prompts starting with `@` are files: refused. `--system-prompt` replaces the default. |
| `hermes`      | `hermes`   | `hermes chat -Q --source tool --query=PROMPT` | `-m M` (provider from hermes config) | none (text; display lines end in `\r\n`) | **Verified** (hermes-agent 0.19.0, PyPI). Not `hermes -z`: it auto-approves every tool call. Answer = stdout minus `\r\n` display lines (diff previews, warnings); session id on stderr. No read-only toolset: refused. `--system-prompt` is passed as the `HERMES_EPHEMERAL_SYSTEM_PROMPT` env var (hermes has no flag for it). Prompt sent literally (no `/` or `@` handling). |
| `grok`        | `grok`     | `grok --output-format json --single=PROMPT` | `--model M`                    | `--output-format json` (one object); `streaming-json` for `-o stream-json` | **Verified** (1.0.70, npm `@xai-official/grok`, xAI's official Grok Build CLI). `-p`/`--single` has no `--` escape, so the prompt is one final `--single=PROMPT` element. Prompts starting with `/` (even after spaces) run as slash commands: refused. Errors are `{"type":"error","message"}` on stdout plus stderr, exit 1. Reports the model it used. `--system-prompt-override` replaces the default. `superagent-ai/grok-cli` (npm `@vibe-kit/grok-cli`) also installs `grok`, with different flags; not supported. |

Sources: [codex exec docs (mirror)](https://forge.lthn.ai/core/core-agent-ide/src/commit/1d17ca1fa3f485603c4a2e34ff89d489dceeb8e3/docs/exec.md),
[opencode CLI](https://learnopencode.com/en/appendix/cli),
[pi CLI integration](https://pi.dev/docs/latest/cli-integration),
[hermes cheat sheet](https://www.glukhov.org/ai-systems/hermes/hermes-agent-cli-cheatsheet/),
[xAI headless scripting](https://docs.x.ai/build/cli/headless-scripting),
[superagent grok-cli](https://github.com/superagent-ai/grok-cli/wiki).

## 3. CLI surface

```
callai -n HARNESS_NAME (-p | -c | --prompt | --command) PROMPT [options] [-- HARNESS_ARGS...]

Required
  -n, --name {claude-code,codex,opencode,pi,hermes,grok}
                         Harness to run. Default comes from $CALLAI_HARNESS_NAME or the config file.
                         Several (fan-out): a/b/c runs them at the same time, a,b,c one after another,
                         all = every installed harness at the same time (see "Fan-out" below).
  -p, --prompt, -c, --command PROMPT
                         The prompt (all four are aliases). Use "-" to read the prompt from stdin.

Common options
  -m, --model MODEL      Passed to the harness as-is (or resolved through an alias, §6).
  -o, --output-format {text,json,stream-json,raw}
                         text (default): final answer only, on stdout.
                         json: one normalised JSON object (§5).
                         stream-json: normalised JSON-lines events as they happen (§5).
                         raw: the harness's own stdout, unchanged.
  -C, --cwd DIR          Working directory for the harness (default: current dir).
      --timeout SECS     Kill the harness after SECS (default: none).
      --permission {default,read-only,auto,bypass}
                         One permission level, translated to each harness's flags (§7).
      --system-prompt S  Only where the harness supports it; otherwise refused (exit 2).
      --resume SESSION_ID
                         Continue that session (the session_id a previous run reported; §5).
      --continue         Continue the harness's most recent session. No -c: that is --command.
                         Can't be combined with --resume. Mapping below.
      --dry-run          Print the exact argv that would run, then exit 0 (doesn't need the binary).
                         Text: shell-quoted on one line (as Python shlex.join), preceded by NAME=value
                         for any env vars the adapter sets. -o json: {"argv": [...]}, plus "env": {...}
                         only when the adapter sets env vars.
  -v, --verbose          Copy the harness's stderr through as it arrives (default: buffer it, print only on failure).

Introspection
      --list-harnesses   Each harness, its binary, where it is on PATH, and its --version (-o json: JSON).
      --version
  --                     Anything after this goes to the harness unchanged.
```

Session flags (each checked with the real harness against the stub model: the resumed request carries
the earlier turns, and the run reports the same `session_id`):

| harness | `--resume ID` | `--continue` |
|---|---|---|
| claude-code | `--resume ID` | `--continue` (most recent in this directory) |
| codex | `exec [options] resume ID -- PROMPT` | `exec [options] resume --last -- PROMPT` |
| opencode | `--session ID` | `--continue` |
| pi | `--session ID` | `--continue` |
| hermes | `--resume ID` | refused: hermes continues only interactive (`cli`) sessions, never callai's `--source tool` runs |
| grok | `--resume=ID` | `--continue` (most recent for this directory) |

codex's `resume` subcommand rejects `--sandbox`, so exec's options (including `--sandbox` and anything after
`--`) go before it; the sandbox then applies to the resumed run (checked: read-only blocks a write, auto allows it).

Fan-out (`-n a/b/c`, `-n a,b,c`, `-n all`; syntax chosen by the owner):
- Before anything runs, every harness's options are checked and every binary is found. With an
  explicit list, a refusal (exit 2, prefixed with the harness name) or a missing binary (127) stops
  the call. `-n all` takes the installed harnesses and skips, with a note on stderr, those that refuse
  the options (e.g. `-n all --permission read-only` skips opencode and hermes).
- Refused with several harnesses: `-o raw` (outputs can't be told apart) and arguments after `--`
  (they'd be for one harness; use `[harnesses.<name>] extra_args`). Mixed separators, empty or repeated
  names, and `all` inside a list are usage errors.
- `-m` applies to every harness; a config alias gives each its own model. Stdin is read once and shared.
  All runs use the same working directory: parallel runs that edit files can collide.
- Output, in the order given: text = each answer under `== name ==` (`== name (failed, exit N) ==` for a
  failure); json = `{"results": [...]}`; stream-json = events as they happen, each with `harness_name`;
  `--dry-run` = one command line per harness (json: `{"runs": [{harness_name, argv, env?}]}`).
  A failed harness's own stderr follows on stderr under `--- name stderr ---`.
- One failure doesn't stop the others; a timeout is that harness's failed result (exit 124). Exit code:
  0 if all succeeded, else the first failure's in the order given. Ctrl-C stops every harness (130).

How the prompt is read, following `claude -p`:

- `-p TEXT`, and stdin is a TTY: the prompt is `TEXT`.
- `-p TEXT`, and stdin is piped: the prompt is `TEXT` + `\n\n` + stdin, so `cat f | callai -p "review"` works.
- `-p -`, or no `-p` and stdin is piped: the prompt is all of stdin.
- `-p TEXT`, and stdin is a pipe with no data yet: callai waits up to `$CALLAI_STDIN_WAIT` seconds
  (default 3, like `claude -p`) for the first data or EOF. If nothing arrives, it prints a warning and
  uses `TEXT` alone, so an agent's or script's stdin that never closes doesn't hang the run. Once data
  arrives, it reads to EOF. Not on Windows, where `select` can't watch pipes: stdin is read to EOF.
- With `-p -` or no `-p`, stdin *is* the prompt, so callai waits for EOF however long it takes. Usage
  errors that don't depend on the prompt text (tool, permission level, `--system-prompt`) are reported
  first, so they never wait behind stdin.
- No prompt at all: usage error, exit 2.

The prompt goes to the harness as **one argv element** (`subprocess` with a list, never
`shell=True`), so the shell never interprets it and no quoting is needed.

## 4. Architecture

```
src/callai/
  api.py          run(harness_name, prompt, *, model, …, on_event) -> Result: the Python API (no env/config);
                  run_harness(adapter, req, argv, on_event) -> Completed, shared with the CLI
  cli.py          argparse → Request (flags, CALLAI_* env, config) → run_harness; prints the Result; exit code
  fanout.py       split_harness_names(-n value); run_jobs(jobs, concurrent) -> outcomes in order (threads)
  errors.py       CallaiError(exit_code=1) ← UsageError(exit_code=2); more added with the runner
  request.py      @dataclass(frozen) Request(harness_name, prompt, model, output_format, cwd, timeout,
                                             permission, system_prompt, extra_args: tuple,
                                             resume, continue_session)
                  validates enums/timeout/extra_args → UsageError
  result.py       @dataclass(frozen) Completed(argv, exit_code, stdout, stderr, duration_ms)
                  @dataclass(frozen) Result(tool, text, exit_code, is_error, model, duration_ms,
                                            session_id, usage, cost_usd, argv, raw_stdout, raw_stderr)
                  Result.to_dict() → §5 JSON (stable key order, raw_* excluded)
  runner.py       run(argv, cwd, timeout, env, on_stdout_line) -> Completed; env is added to callai's own; process-group kill on timeout
  config.py       load_config(environ) -> Config (config.toml, strict); resolve_model(config, harness, model)
  adapters/
    base.py       class Adapter(ABC):
                      name: str; binary: str; install_url: str
                      def build_argv(req) -> list[str]           # abstract, pure
                      def parse(completed, req) -> Result        # abstract, pure
                      def build_env(req) -> dict[str, str]       # pure; default {} (hermes: system prompt)
                      def stream_events(line, state) -> list     # pure but for state; default [] (§5)
                      def text_result(completed, req) -> Result  # fallback: ANSI-stripped stdout
    claude_code.py codex.py opencode.py pi.py hermes.py grok.py
    __init__.py   HARNESS_NAMES = ("claude-code", …, "grok"); REGISTRY filled via register(adapter);
                  get_adapter(harness_name) → UsageError for unknown or not-yet-implemented harnesses
```

Python API: `callai.run(harness_name, prompt, *, model, cwd, timeout, permission, system_prompt,
extra_args, resume, continue_session, binary, on_event)` returns the same `Result` as `-o json`.
`on_event` gets the `-o stream-json` events live (the harness then runs in its streaming mode).
It reads no `CALLAI_*` variables and no config file, so a call means the same on every machine;
model aliases are a CLI feature. A harness that ran but failed is a `Result` with `is_error`; exceptions
(`CallaiError` subclasses) are for runs that couldn't start or finish: usage, not found, timeout, Ctrl-C.
The API is Python-only; ports expose their own (the conformance suite covers the CLI and adapters).

`--list-harnesses` asks each binary for `--version` through `runner.harness_version` (no per-adapter code).

How a run flows: `cli` → `Request` → `REGISTRY[harness_name].build_argv(req)` and `.build_env(req)` → `runner.run` →
`adapter.parse` → `Result` → output written as text, json or raw.

Why this layout:

- **One file per adapter, two pure functions each** (`build_argv`, `parse`). Both can be
  tested without the harness installed, and adding a harness means adding one file plus one registry line.
- **Adapters ask for the harness's structured output whenever it has one.** For example,
  `claude -p --output-format json` even when the user asked for `text`. The adapter then
  extracts the final answer from it, so finding the answer doesn't rely on scraping text.
  Harnesses with no JSON mode (hermes for now) fall back to stdout with ANSI codes and whitespace stripped.
- **No runtime dependencies.** Standard library only (`argparse`, `subprocess`,
  `tomllib`, `json`, `shutil`). This keeps start-up fast and installs easy.
  Requires Python ≥ 3.11 for `tomllib`.

## 5. Normalised output

`-o json` writes one object no matter which harness ran:

```json
{
  "harness_name": "codex",
  "model": "gpt-5-codex",
  "text": "final assistant answer",
  "exit_code": 0,
  "is_error": false,
  "duration_ms": 18342,
  "session_id": "…",        // null if the harness doesn't report one
  "usage": {"input_tokens": 0, "output_tokens": 0},   // null if unknown; input = ALL prompt tokens incl. cache
  "cost_usd": null,
  "argv": ["codex", "exec", "..."]
}
```

`-o stream-json` writes one JSON object per line, flushed as each happens:

```json
{"type": "start", "harness_name": "claude-code", "model": "haiku", "argv": ["claude", "…"]}
{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}
{"type": "tool_result", "id": "toolu_1", "is_error": false, "output": "README.md\n"}
{"type": "text", "text": "There is one file."}
{"type": "result", "harness_name": "claude-code", "text": "There is one file.", "is_error": false, "…": "same keys as -o json"}
```

- `start` comes first, once the harness binary is found (a missing binary writes nothing: exit 127).
  `result` comes last and is the `-o json` object plus `"type"`, also for a failed run. callai's own
  errors (timeout 124, Ctrl-C 130) end the stream without a `result`; the exit code and stderr say why.
- `text` is assistant text as the harness reports it: whole text blocks (claude, codex, opencode) or
  pieces of one (pi's text deltas, grok's chunks). Joined in order, they are everything the assistant
  said, across turns; the final answer is `result.text`.
- `tool_use` is a tool call, with the harness's own tool name and arguments (codex: the item type,
  e.g. `command_execution`). `tool_result` answers it by `id`; `is_error` is true for a failed or
  refused call, and `output` is its text output.
- Each adapter maps its harness's event stream with a pure `stream_events(line, state)`, called on
  every stdout line as it arrives. Harnesses without one (hermes) give only `start` and `result`.
- Exit codes and stderr are the same as with `-o json`.

## 6. Configuration and model aliases

Order of precedence: CLI flag > `CALLAI_*` env var > `config.toml` > built-in default.

| setting | flag | env | config.toml |
|---|---|---|---|
| harness | `-n` | `CALLAI_HARNESS_NAME` | `default_harness` |
| model | `-m` | `CALLAI_MODEL` | `[harnesses.<name>] model`, then top-level `model` |
| timeout | `--timeout` | `CALLAI_TIMEOUT` | `timeout` |
| extra harness args | after `--` | | `[harnesses.<name>] extra_args` (go first) |
| harness binary | | | `[harnesses.<name>] binary` (`~` expanded) |

The file is `$CALLAI_CONFIG` if set (must exist), else `$XDG_CONFIG_HOME/callai/config.toml`, else
`~/.config/callai/config.toml` (a missing default file is fine). It is read with Python's `tomllib`
(no dependency). Unknown keys, unknown harness names and wrong types are usage errors (exit 2) naming
the file, so a typo never silently does nothing.

```toml
default_harness = "claude-code"
model = "fast"
timeout = 600

[harnesses.codex]
binary = "/opt/homebrew/bin/codex"   # override PATH lookup
model = "gpt-5-codex"
extra_args = ["--skip-git-repo-check"]

[aliases]                           # optional; anything else passes through verbatim
fast  = { claude-code = "haiku", codex = "gpt-5-codex-mini", opencode = "anthropic/claude-haiku-4-5" }
smart = { claude-code = "opus",  codex = "gpt-5-codex" }
```

Aliases are resolved after precedence, so they work from `-m`, `CALLAI_MODEL` or the file. An alias
with no entry for the chosen harness is a usage error, not passed on as a model name.
`callai` never checks model names itself. Each harness owns its own model list and errors.

## 7. Permissions and safety

Harnesses default to very different permission behaviour when running headless. `--permission` is a single setting that `callai` translates per harness:

| level       | claude-code (verified 2.1.314)           | codex (verified 0.166.0)      | opencode (verified 1.19.5) | pi (verified 1.4.0; tool allowlists, no approvals) | grok (verified 1.0.70; headless refuses calls needing approval) | hermes (verified 0.19.0; asks only for dangerous commands) |
|-------------|------------------------------------------|-------------------------------|----------------------------|-----------------------------------|-----------------------------------|-----------------------------------|
| `default`   | (no flag)                                | (no flag)                     | (no flag)                  | (no flag) | (no flag) | (no flag; dangerous commands denied after the 60s approval timeout) |
| `read-only` | `--permission-mode plan`                 | `--sandbox read-only`         | **refused** (plan agent still runs shell) | `--tools read,grep,find,ls --no-mcp` | `--tools read_file,grep,list_dir --disallowed-tools search_tool,use_tool` | **refused** (no read-only toolset) |
| `auto`      | `--permission-mode acceptEdits`          | `--sandbox workspace-write`   | **refused** (no edits-only level) | `--tools read,grep,find,ls,edit,write --no-mcp` | `--allow Write --allow Edit` | `-t file` |
| `bypass`    | `--dangerously-skip-permissions`         | `--dangerously-bypass-approvals-and-sandbox` | `--auto` | (no flag: already pi's default) | `--permission-mode bypassPermissions` | `--yolo` |

What each level actually allows, checked with scripted tool calls (`conformance/tools/permission_probe.py`:
the stub model asks the harness to write a file and to run a shell command that writes one, inside and
outside the working directory; "outside" is not under `/tmp`). ✓ = the file appeared.

| level       | claude-code 2.1.314 | codex 0.166.0 (shell only¹) | opencode 1.19.5 | pi 1.4.0 | grok 1.0.70 | hermes 0.19.0 |
|-------------|---------------------|-----------------------------|-----------------|----------|-------------|---------------|
| `default`   | write ✗ · shell ✗ (refused, run still exits 0) | write ✗ · outside ✗ | write ✓ · shell ✓ · outside ✓ | write ✓ · shell ✓ · outside ✓ | write ✗ · shell ✗ (turn cancelled → exit 1) | write ✓ · shell ✓ · outside ✓ (only dangerous commands denied) |
| `read-only` | write ✗ · shell ✗ | write ✗ · outside ✗ | refused (exit 2) | write ✗ · shell ✗ (tools not offered) | write ✗ · shell ✗ (tools not offered) | refused (exit 2) |
| `auto`      | workspace ✓ (write, and shell redirects into it) · outside ✗ | workspace ✓ · outside ✗ | refused (exit 2) | write ✓ (also outside) · shell ✗ | write ✓ (also outside) · shell ✗ | write ✓ (also outside) · shell ✗ |
| `bypass`    | everything ✓² | workspace ✓ · outside ✓ | everything ✓ | everything ✓ | everything ✓ | everything ✓ |

¹ codex offered only its `exec_command` shell tool for the stub model; its sandbox (Landlock) does the
enforcing, and `workspace-write` also allows `/tmp`. pi, grok and hermes `auto` limit *which tools* run, not
*where* they write.

² As root, claude refuses `--dangerously-skip-permissions` (and `--permission-mode bypassPermissions`)
unless `IS_SANDBOX=1` is set; callai passes claude's error through (exit 1) and never sets it. The
probe ran with `IS_SANDBOX=1` in this sandboxed container.

grok's `--sandbox` profiles (`workspace`, `read-only`, `strict`; need bubblewrap on Linux, and grok
refuses to start without it) were probed too, with the working directory outside `/tmp`: every profile
still allows writes **inside** the working directory and blocks them outside it. So `--sandbox read-only`
adds nothing to callai's `read-only` (no write or shell tool is offered), and isn't added.

**Caveat (owner decision, CA-11): grok's sandbox stays opt-in.** grok `auto` and `bypass` can write
outside the working directory. Adding `--sandbox workspace` automatically would confine them, like
codex, but would make `auto` fail on Linux machines without bubblewrap. Users opt in:

```bash
callai -n grok -p "Fix the failing test" --permission auto -- --sandbox workspace
GROK_SANDBOX=workspace callai -n grok -p "Fix the failing test" --permission auto
```

See the README's caution box for the full explanation.

Rules:

- `callai` **never raises the permission level on its own**. `default` adds no flags.
- If a harness has no equivalent for the requested level, `callai` **errors out (exit 2)**
  instead of quietly running with more permission than was asked for.
- `bypass` prints a one-line warning on stderr before the harness runs (not with `--dry-run`).

## 8. Exit codes

| code | meaning |
|------|---------|
| harness's own | passed through when the harness ran |
| 2   | `callai` usage or config error |
| 124 | `--timeout` hit (same as GNU `timeout`) |
| 127 | harness binary not found; the message names the binary and links to install docs |
| 130 | interrupted (SIGINT is forwarded to the harness's process group) |

## 9. Testing strategy (Red/Green TDD)

1. **Unit, golden argv**: one table-driven test per adapter: `Request` → expected argv.
   This is where most of the coverage comes from.
2. **Unit, parsers**: recorded stdout/JSON fixtures per harness in
   `conformance/parse/<tool>/` feed `parse()`. Capture real fixtures whenever a harness is installed.
3. **Integration with fake harnesses**: small Python scripts named `claude`, `codex`, … put
   at the front of `PATH` in tests. They echo their argv and send canned output. These cover the runner,
   timeout, stdin, exit-code mapping and 127 handling, with no network.
4. **Live smoke** (`src/tests/test_live.py`, `@pytest.mark.live`; skipped unless `CALLAI_LIVE` is
   `all` or a comma list of harness names, and when the binary is missing):
   `callai -n X -p "Reply with exactly: pong" -o json` must exit 0, not report an error, and
   contain `pong`. The model is whatever callai would pick (`CALLAI_MODEL`, config, harness default).

Golden argv, parse fixtures and CLI cases are stored as data under `conformance/` so the later
TypeScript/Rust ports run the same suite (SCOPE §5).

Tooling follows `expt_svg2font`: setuptools `src/` layout, pytest with a coverage gate, ruff (google docstrings), interrogate.

## 10. Later (not v1)

- More harnesses: gemini-cli, aider, cursor-agent, amp, qwen-code, goose.

## 11. Open decisions

All resolved 2026-10-30 (owner accepted the recommendations):

1. **Implementation language:** Python first, then a TypeScript port, then possibly Rust
   ([`../SCOPE.md`](../SCOPE.md) §2–5).
2. **`grok`:** xAI's official Grok Build CLI. `superagent-ai/grok-cli` is not supported (it
   clashes on the binary name; it could be added as a separate `grok-superagent` tool later).
3. **Default `--output-format`:** `text`, the same as `claude -p`.
4. **Minimum Python:** 3.11. Stdlib-only (`tomllib`), which also keeps the "vendor the source
   into npm" option open (SCOPE §4).
5. **Package names:** PyPI distribution **`callai-cli`** (`callai` is taken on PyPI). The import
   package and the command stay **`callai`**. npm: both `callai` and `callai-cli` were free on
   2026-10-30; choose when the TypeScript port starts.
