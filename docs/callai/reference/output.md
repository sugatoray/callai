# Output formats reference

Exactly what callai prints for each `-o` value, `--dry-run`, `--list-harnesses` and fan-out. JSON is
always UTF-8, one object per line.

## `-o text`

The default. The answer (`text`) followed by a newline, on stdout. On failure, stdout is empty and
stderr gets the harness's own stderr (unless `-v` already showed it) plus the error text, if it isn't
already in that stderr. Exit code as in [Exit codes](errors.md#exit-codes).

## `-o json`

One object, the same for every harness:

```json
{
  "harness_name": "codex",
  "model": null,
  "text": "pong",
  "exit_code": 0,
  "is_error": false,
  "duration_ms": 6979,
  "session_id": "01a19506-c5ee-7893-ab89-d0f6b04924a4",
  "usage": {"input_tokens": 11, "output_tokens": 2},
  "cost_usd": null,
  "argv": ["codex", "exec", "--json", "--skip-git-repo-check", "--", "Reply with exactly: pong"]
}
```

| Key | Type | Meaning |
|---|---|---|
| `harness_name` | string | The `-n` name that ran |
| `model` | string \| null | Model the harness reports using; else the requested `-m` (after alias resolution); else `null` |
| `text` | string | Final answer, or the error message when `is_error` |
| `exit_code` | integer | The harness's exit code |
| `is_error` | boolean | From the harness's explicit error signal, or a non-zero exit |
| `duration_ms` | integer | Wall-clock time of the harness run |
| `session_id` | string \| null | Use with `--resume` |
| `usage` | object \| null | `input_tokens` (all prompt tokens, cache reads and writes included) and `output_tokens` |
| `cost_usd` | number \| null | When the harness reports cost (claude, opencode, pi; codex, hermes and grok don't) |
| `argv` | array of strings | The exact command that ran |

Keys are always present, in this order. Unknown values are `null`. With a failure, stdout still has
the object, and stderr has the harness's stderr.

## `-o stream-json`

One JSON object per line, flushed as each event happens:

```json
{"type": "start", "harness_name": "pi", "model": "stub/stub-model", "argv": ["pi", "--mode", "json", "--model", "stub/stub-model", "--", "Reply with exactly: pong"]}
{"type": "text", "text": "pong"}
{"type": "result", "harness_name": "pi", "model": "stub/stub-model", "text": "pong", "exit_code": 0, "is_error": false, "duration_ms": 1047, "session_id": "01a19507-07fe-7550-b76e-7a5f6b29a908", "usage": {"input_tokens": 11, "output_tokens": 2}, "cost_usd": 0, "argv": ["pi", "--mode", "json", "--model", "stub/stub-model", "--", "Reply with exactly: pong"]}
```

| `type` | Keys | Notes |
|---|---|---|
| `start` | `harness_name`, `model`, `argv` | First, once the binary is found. Not written if it isn't (exit 127). |
| `text` | `text` | Assistant text: whole blocks (claude, codex, opencode) or pieces (pi, grok). |
| `tool_use` | `id`, `name`, `input` | `name` and `input` are the harness's own (`Bash`, `{"command": "ls"}`). |
| `tool_result` | `id`, `is_error`, `output` | `id` matches the `tool_use`. `is_error` for a failed or refused call. |
| `result` | every `-o json` key | Always last, failures included. Missing only on timeout (124) or Ctrl-C (130). |

hermes has no event stream: `start` and `result` only. In a [fan-out](#fan-out), every event also
carries `harness_name`.

## `-o raw`

The harness's own stdout and stderr, byte for byte, without parsing. The exit code is the harness's. Not
allowed with several harnesses.

## `--dry-run`

Text, one shell-quoted command per line, with environment variables first:

```text
HERMES_EPHEMERAL_SYSTEM_PROMPT='Be terse.' hermes chat -Q --source tool --query=hi
```

With `-o json` or `-o stream-json`:

```json
{"argv": ["hermes", "chat", "-Q", "--source", "tool", "--query=hi"], "env": {"HERMES_EPHEMERAL_SYSTEM_PROMPT": "Be terse."}}
```

`env` is present only when callai sets variables. With several harnesses: one text line each, or
`{"runs": [{"harness_name": "…", "argv": […], "env": {…}}, …]}`.

## `--list-harnesses`

Text, one line per harness:

```text
claude-code  claude     2.1.316 (Claude Code)  /opt/node22/bin/claude
```

A missing harness shows `not installed (see <install URL>)`. If the binary prints no version,
`version unknown` appears instead. With `-o json`:

```json
{"harnesses": [{"harness_name": "claude-code", "binary": "claude", "path": "/opt/node22/bin/claude", "version": "2.1.316 (Claude Code)", "install_url": "https://code.claude.com/docs/en/setup"}]}
```

(One entry per harness; `path` and `version` are `null` when it isn't installed.)

## Fan-out

With `-n a/b`, `-n a,b` or `-n all`, results come in the order given:

| Format | Shape |
|---|---|
| text | `== name ==` then the answer, per harness. A failure is `== name (failed, exit N) ==` then its error text. |
| json | `{"results": [<-o json object>, …]}` |
| stream-json | Every harness's events interleaved as they happen, each with `harness_name` |
| raw | Not allowed (exit 2) |

A failed harness's own stderr goes to stderr after a `--- name stderr ---` line. Harnesses skipped
by `-n all` are reported on stderr as `callai: skipping <name>: <reason>`.

See also: [Normalised output](../concepts/normalised-output.md) · [Exit codes and errors](errors.md)
