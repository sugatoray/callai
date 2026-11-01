# Python API reference

Everything `import callai` gives you. Standard library only; Python 3.11+.

```python
import callai

result = callai.run("codex", "Fix the failing test", permission="auto", timeout=600)
```

## `callai.run`

```python
callai.run(
    harness_name: str,
    prompt: str,
    *,
    model: str | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
    permission: str = "default",
    system_prompt: str | None = None,
    extra_args: Sequence[str] = (),
    resume: str | None = None,
    continue_session: bool = False,
    binary: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Result
```

Run one prompt through one harness and return its normalised result. The call blocks until the
harness finishes.

| Parameter | Meaning | CLI equivalent |
|---|---|---|
| `harness_name` | `"claude-code"`, `"codex"`, `"opencode"`, `"pi"`, `"hermes"` or `"grok"` | `-n` |
| `prompt` | The prompt, sent verbatim | `-p` |
| `model` | Passed to the harness verbatim (no alias resolution) | `-m` |
| `cwd` | Working directory for the harness | `-C` |
| `timeout` | Seconds before the harness and its children are killed | `--timeout` |
| `permission` | `"default"`, `"read-only"`, `"auto"` or `"bypass"` | `--permission` |
| `system_prompt` | Extra system instructions, where supported | `--system-prompt` |
| `extra_args` | Passed to the harness unchanged | after `--` |
| `resume` | Session id to continue | `--resume` |
| `continue_session` | Continue the harness's most recent session | `--continue` |
| `binary` | Executable to run instead of the harness's usual one on `PATH` | `[harnesses.<name>] binary` |
| `on_event` | Called with each [stream event](output.md#-o-stream-json) as it happens, from a background thread | `-o stream-json` |

**Returns** a [`Result`](#callairesult). A harness that ran and failed (bad model, refused tool,
non-zero exit) is a result with `is_error=True`, not an exception.

**Raises** a subclass of [`CallaiError`](#exceptions) when the run couldn't start or finish.

`run()` reads **no** `CALLAI_*` environment variables and **no** config file. There are no
`bypass` warnings either: what you pass is what runs. With `on_event`, the harness runs in its
streaming mode (claude `stream-json`, grok `streaming-json`). The last event is
`{"type": "result", **result.to_dict()}`.

## `callai.Result`

A frozen dataclass: the same data as the [`-o json` object](output.md#-o-json).

| Attribute | Type | Meaning |
|---|---|---|
| `harness_name` | `str` | Harness that ran |
| `text` | `str` | Final answer, or the error message when `is_error` |
| `exit_code` | `int` | The harness's exit code |
| `is_error` | `bool` | Whether the run failed |
| `model` | `str \| None` | Model the harness reports using, else the requested one |
| `duration_ms` | `int \| None` | Wall-clock run time |
| `session_id` | `str \| None` | For `resume=` |
| `usage` | `dict[str, int] \| None` | `{"input_tokens", "output_tokens"}`; input counts cache reads and writes |
| `cost_usd` | `float \| None` | Cost, when the harness reports it (claude, opencode, pi) |
| `argv` | `tuple[str, ...]` | The exact command that ran |
| `raw_stdout`, `raw_stderr` | `str` | The harness's own output, unparsed (not in `to_dict()`) |

| Method | Returns |
|---|---|
| `to_dict()` | The `-o json` object as a new `dict` (key order as documented) |
| `with_updates(**changes)` | A copy with some fields changed |

## Exceptions

| Class | Raised when | `exit_code` |
|---|---|---|
| `callai.CallaiError` | Base class of all below | 1 |
| `callai.UsageError` | Invalid argument; an option the harness can't honour; unknown harness | 2 |
| `callai.HarnessNotFound` | The binary isn't on `PATH` (or `binary=` doesn't exist) | 127 |
| `callai.HarnessTimeout` | `timeout` expired; the process group was killed | 124 |
| `callai.Interrupted` | Ctrl-C (SIGINT forwarded to the harness) | 130 |

`str(exc)` is the message the CLI prints after `callai: error:`. Every message is listed in
[Exit codes and errors](errors.md).

```python
import callai

try:
    result = callai.run("opencode", "Explain main.py", permission="read-only")
except callai.UsageError as exc:
    print("can't do that:", exc)
```

```text
can't do that: --permission read-only: opencode has no read-only mode (its plan agent still allows shell commands); pass `-- --agent plan` yourself if that is acceptable
```

## Other names

`callai.main(argv=None) -> int` runs the CLI in-process (what the `callai` command calls) and returns its
exit code. The adapter registry (`callai.adapters`) is internal; see
[Add a new harness](../guides/add-a-harness.md).

See also: [8. Use callai from Python](../tutorial/08-python-api.md) · [Output formats](output.md)
