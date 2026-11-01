# conformance/ — language-agnostic test suite

Shared test cases for every `callai` implementation: Python now, then the TypeScript port and
possibly a Rust port (see [`../SCOPE.md`](../SCOPE.md) §5). Cases are stored as **data** (JSON plus
recorded output files), not as test code, so each implementation writes only a small loader and runs
exactly the same cases. **An implementation conforms when it passes every case here.**

- Python loader: [`src/tests/conformance.py`](../src/tests/conformance.py). It validates strictly:
  unknown keys are errors, so typos fail loudly.
- Behaviour is specified in [`../docs/DESIGN.md`](../docs/DESIGN.md). When this suite and DESIGN.md
  disagree, fix one of them in the same commit.

```
conformance/
  argv/<harness_name>/<case>.json        Request → exact harness argv (adapter.build_argv)
  parse/<harness_name>/<case>.json       Recorded harness output → normalised Result (adapter.parse)
  parse/<harness_name>/<case>.stdout     …the recorded stdout it points to (plus optional .stderr)
  cli/<case>.json                End-to-end `callai …` invocation → exit code / stdout / stderr
```

A case's id is its path relative to the kind directory, without `.json`, e.g. `claude-code/basic`
or `dry_run_json`. The `<harness_name>` directory name must equal the case's `harness_name` field.

## Common: `request` object

Used by `argv` (required, `prompt` required) and `parse` (optional). Missing keys take these defaults:

| key | type | default |
|---|---|---|
| `prompt` | string | — (required in argv cases; `""` in parse cases) |
| `model` | string \| null | `null` |
| `output_format` | `text` \| `json` \| `stream-json` \| `raw` | `text` |
| `cwd` | string \| null | `null` |
| `timeout` | number \| null | `null` |
| `permission` | `default` \| `read-only` \| `auto` \| `bypass` | `default` |
| `system_prompt` | string \| null | `null` |
| `extra_args` | string[] | `[]` |
| `resume` | string \| null (a session id) | `null` |
| `continue_session` | boolean (continue the most recent session) | `false` |

## `argv/<harness_name>/<case>.json`

```json
{
  "description": "why this case exists",
  "harness_name": "claude-code",
  "request": {"prompt": "hello", "model": "haiku"},
  "expected_argv": ["claude", "-p", "--output-format", "json", "--model", "haiku", "--", "hello"]
}
```

Exactly one of:
- `expected_argv`: the exact list `build_argv(request)` must return. `argv[0]` is the bare
  binary name; resolving it on PATH is the runner's job.
- `expected_error`: `{"message_contains": "..."}`. `build_argv` must raise or return a usage error
  whose message contains that substring. Used for fail-closed cases, e.g. a permission level the
  harness can't honour (DESIGN §7). The CLI maps these errors to exit code 2.

Optional with `expected_argv`: `expected_env`, the exact object `build_env(request)` must return
(env vars the adapter sets for the harness, e.g. hermes's `HERMES_EPHEMERAL_SYSTEM_PROMPT`).
Missing means `{}`.

Invariant checked for every case: the prompt comes **last**, where no part of it can be read as a
harness flag. Either it follows a `"--"` and the elements after that `"--"` joined with single spaces
equal the prompt (usually one element; opencode needs it split on spaces), or, for a harness whose
prompt option has no `--` escape (grok), it is the value of a final `--option=PROMPT` element.

## `parse/<harness_name>/<case>.json`

```json
{
  "description": "what was recorded, with which harness version and command line",
  "harness_name": "claude-code",
  "request": {"prompt": "Reply with exactly: pong", "model": "haiku"},
  "exit_code": 0,
  "stdout_file": "success_pong.stdout",
  "stderr_file": "success_pong.stderr",
  "expected": {"text": "pong", "is_error": false, "session_id": "…"}
}
```

`stderr_file` is optional and defaults to empty. Recorded files are **byte-exact**: read them without newline
translation (hermes marks its display lines with `\r\n`), and capture harness output the same way. `expected` is a **subset** of the normalised
Result (DESIGN §5). Only the keys present are compared. Allowed keys: `harness_name`, `model`, `text`,
`exit_code`, `is_error`, `session_id`, `usage`, `cost_usd`. Runtime-only fields (`duration_ms`,
`argv`) are never asserted here.

`expected_events` (optional) checks `-o stream-json`: feed every stdout line, in order and with its
newline, through the adapter's `stream_events(line, state)` with one fresh `state` per case, and compare
the events produced with this list exactly. Allowed events (DESIGN §5; `start` and `result` are the
CLI's, not the adapter's):

| type | keys |
|---|---|
| `text` | `type`, `text` |
| `tool_use` | `type`, `id`, `name`, `input` |
| `tool_result` | `type`, `id`, `is_error`, `output` |

Leave it out to skip the check (most older fixtures were recorded without stream-json).

Normalisation rules these cases pin down:
- `model`: the model the harness **reports** it used, if it reports one (claude: the key of
  `modelUsage`); otherwise the requested model.
- `usage.input_tokens` = **all** prompt tokens, including cache reads and cache writes
  (claude: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`), so the
  figure is comparable across harnesses. `usage.output_tokens` as reported.
  codex reports OpenAI-style `input_tokens`, which already include `cached_input_tokens`, so it is used as-is.
  opencode's per-step `tokens.input` **excludes** cache, so `input + cache.read + cache.write` is summed over all steps.
  pi's per-message `usage.input` also excludes cache: `input + cacheRead + cacheWrite`, summed over assistant messages.
  grok's `usage.input_tokens` excludes cache too: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
  grok's model is the `modelUsage` key with the most tokens.
- `is_error` comes from the harness's explicit error signal (claude: `is_error`), **not**
  `subtype`. See `claude-code/error_unknown_model`.

**Recording without network or API keys:** `tools/stub_llm_server.py` is a local OpenAI-compatible
model stub (Responses API and Chat Completions, SSE), which also speaks Anthropic Messages
(`/v1/messages`, for claude-code). Point the harness's custom-provider settings at
`http://127.0.0.1:PORT/v1`. The harness and its output format are real; only the model reply is
canned. Model names containing `not-a-real-model` return HTTP 404, for recording the unknown-model path.
`--tool-call '{"name": ..., "arguments": {...}}'` scripts one tool call: the stub returns it to any
request that offers tools and has no tool result yet, then answers with text once the harness sends
the result back. That is how refused-call fixtures (e.g. `grok/error_permission_refused`) are recorded,
and how `tools/permission_probe.py` checks what each `--permission` level really allows (DESIGN §7).
Fixtures recorded this way must say **STUB MODEL** in their description. Example for codex
(`$CODEX_HOME/config.toml`):

```toml
model_provider = "stub"
model = "stub-model"
[model_providers.stub]
name = "Local stub"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
```

For opencode, add a provider to `$XDG_CONFIG_HOME/opencode/opencode.json` (opencode downloads the
`@ai-sdk/openai-compatible` package from npm on first use):

```json
{"provider": {"stub": {"npm": "@ai-sdk/openai-compatible", "name": "Local stub",
  "options": {"baseURL": "http://127.0.0.1:8765/v1"}, "models": {"stub-model": {"name": "Stub model"}}}},
 "model": "stub/stub-model"}
```

For pi, point `PI_CODING_AGENT_DIR` at a folder whose `models.json` adds the stub. List
`not-a-real-model-xyz` as a model too, so the request reaches the stub and records its 404:

```json
{"providers": {"stub": {"baseUrl": "http://127.0.0.1:8765/v1", "api": "openai-completions", "apiKey": "stub",
  "models": [{"id": "stub-model"}, {"id": "not-a-real-model-xyz"}]}}}
```

For claude-code, run it with a clean environment (no inherited `CLAUDE_*`/`ANTHROPIC_*` variables),
an empty `HOME`, `ANTHROPIC_BASE_URL=http://127.0.0.1:8765` (no `/v1`), `ANTHROPIC_API_KEY=stub` and
`-m stub-model`.

For grok, set `GROK_XAI_API_BASE_URL=http://127.0.0.1:8765/v1` and `XAI_API_KEY=stub` (with an empty `HOME`).
grok fetches `/v1/models` and rejects a model the provider doesn't list before calling it, so the
unknown-model fixture is grok's own error, not the stub's 404.

For hermes, add a provider to `$HERMES_HOME/config.yaml` and make it the default:

```yaml
model: {provider: stub, default: stub-model}
providers:
  stub: {name: Local stub, api: "http://127.0.0.1:8765/v1", api_key: stub, default_model: stub-model, models: [stub-model]}
```

**Recording fixtures:** run the real harness with the exact argv the adapter builds, save the
stdout and stderr byte-for-byte, then replace session and message ids with fixed placeholder
UUIDs (`00000000-0000-4000-8000-00000000000N`). Record the harness version in `description`.

## `cli/<case>.json`

```json
{
  "description": "…",
  "args": ["-n", "claude-code", "-p", "hello", "--dry-run", "-o", "json"],
  "stdin": null,
  "stdin_open": false,
  "config": "default_harness = \"codex\"\n",
  "env": {"CALLAI_HARNESS_NAME": "claude-code"},
  "fake_harnesses": {
    "claude": {"stdout_file": "x.stdout", "stderr": "", "exit_code": 0, "sleep": 0}
  },
  "expected": {
    "exit_code": 0,
    "stdout": "exact stdout",
    "stdout_json": {"argv": ["…"]},
    "stdout_json_subset": {"text": "pong"},
    "stdout_events": [{"type": "start"}, {"type": "text", "text": "pong"}, {"type": "result"}],
    "stdout_contains": ["…"],
    "stderr_contains": ["…"],
    "harness_argv": ["claude", "…"],
    "harness_env": {"NAME": "value"}
  }
}
```

- `stdin`: a string is piped to `callai`; `null` (the default) means empty, non-TTY stdin.
  Empty stdin counts as **no** stdin input.
- `config`: TOML text the runner writes to `$XDG_CONFIG_HOME/callai/config.toml` before running
  (the isolated config dir from requirement 2 below), to test the config file and aliases.
- `stdin_open: true`: stdin is a pipe whose writer stays open and silent until `callai` exits (an
  agent's or script's stdin). Can't be combined with `stdin`. The runner must still time out such a run.
- `env`: overrides applied on top of the runner's isolated environment. An empty-string value
  means "set but empty", which `callai` treats as unset (e.g. `CALLAI_HARNESS_NAME=""`).
- `fake_harnesses`: binary name → a fake executable in the runner's fake-bin dir. It
  prints `stdout` or `stdout_file` (a path relative to the case file, so cases can reuse
  recorded `parse/` fixtures) and `stderr` or `stderr_file`, sleeps `sleep` seconds, exits with
  `exit_code`, and records the argv and environment it was called with, so `expected.harness_argv`
  (exact) and `expected.harness_env` (only the listed variables) can be checked. Either one needs
  exactly one fake harness.
- `expected.exit_code` is required. At most one of `stdout` (exact match), `stdout_json` (parse, then
  compare for equality), `stdout_json_subset` (parse, then compare only the listed keys, for
  output with run-time values such as `duration_ms`) and `stdout_events` (for `-o stream-json`: one
  object per stdout line, same number of lines, each compared on its listed keys only). The
  `*_contains` keys are substring checks.

Requirements for each implementation's runner:
1. Run `callai` with an absolute interpreter or binary path. Set `PATH` to **only** the fake-bin dir,
   so a real harness can never run by accident; `"PATH": ""` in `env` hides the fakes too.
2. Isolate configuration: point `XDG_CONFIG_HOME` and `HOME` at an empty temp dir and remove
   inherited `CALLAI_*` variables before applying `env`.
3. Use the system temp dir as the working directory unless the case says otherwise.

## Coverage today

| kind | claude-code | codex | opencode | pi | hermes | grok |
|---|---|---|---|---|---|---|
| argv  | ✓ (15) | ✓ (14) | ✓ (13, 3 refusals) | ✓ (14, 2 refusals) | ✓ (13, 2 refusals, 1 with `expected_env`) | ✓ (17, 2 refusals) |
| parse | ✓ (3: 2 live claude 2.1.314, 1 stream + stub) | ✓ (3, codex 0.166.0 + stub model, 1 stream) | ✓ (3, opencode 1.19.5 + stub model, 1 stream) | ✓ (4, pi 1.4.0 + stub model, 1 stream) | ✓ (4, hermes-agent 0.19.0 + stub model) | ✓ (8, grok 1.0.70 + stub model, 3 stream) |
| cli   | 74 cases (incl. 4 for --resume/--continue, 18 fan-out): 33 tool-independent (incl. 5 config, 2 --list-harnesses) (driven via claude-code) + replays for the other five, `bypass_warns` (codex), 3 env cases (hermes `--system-prompt`, incl. 2 `--dry-run`), and 5 stream-json cases | | | | | |

Other tools get cases in their adapter tickets (CA-6…CA-10), each **after** checking
`<tool> --help` against an installed binary (WISDOM.md: docs are hints, `--help` and
recordings are the source of truth).
