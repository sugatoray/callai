# How to add a new harness

Use this to teach callai a new coding-agent CLI. An adapter is one Python file with a few pure
functions, plus conformance cases that prove it matches the real CLI.

## 1. Learn the CLI from the CLI

Read its `--help`. Docs and memory are hints; `--help` and real output are the truth. Find:

- how to run one prompt non-interactively, and how to stop the prompt being read as a flag (`--`, or
  one `--opt=PROMPT` argument);
- its structured output mode (JSON, or JSON lines);
- its model flag, permission or sandbox flags, system-prompt option, and session resume flags;
- whether it reads stdin (callai gives it an empty one) and how it reports failure.

## 2. Write the adapter

Create `src/callai/adapters/<name>.py`:

```python
from ..request import Request
from ..result import Completed, Result
from .base import Adapter


class MyAgent(Adapter):
    name = "my-agent"                       # the -n value
    binary = "myagent"                      # looked up on PATH
    install_url = "https://example.com/install"

    def build_argv(self, req: Request) -> list[str]:
        argv = [self.binary, "run", "--json"]
        if req.model:
            argv += ["--model", req.model]
        return [*argv, *req.extra_args, "--", req.prompt]   # prompt last, after --

    def parse(self, completed: Completed, req: Request) -> Result:
        ...                                  # turn stdout into a Result
```

| Method | Required | Job |
|---|---|---|
| `build_argv(req)` | yes | The exact command line. Raise `UsageError` for anything the CLI can't honour (fail closed). |
| `parse(completed, req)` | yes | Stdout/stderr/exit code → `Result`. Take `is_error` from the CLI's own error signal. |
| `stream_events(line, state)` | for `-o stream-json` | One stdout line → `text` / `tool_use` / `tool_result` events. |
| `build_env(req)` | if needed | Environment variables, for settings the CLI only takes that way. |

All four are pure: no I/O. That's what lets `--dry-run` and the tests work without the CLI installed.
Map each `--permission` level to the CLI's flags, then prove it in step 4.

## 3. Register it

In `src/callai/adapters/__init__.py`, add the name to `HARNESS_NAMES` and register an instance next to
the others:

```python
from .my_agent import MyAgent  # noqa: E402

register(MyAgent())
```

## 4. Prove it with the conformance suite

The suite in [`conformance/`](../../../conformance/README.md) is plain JSON, shared by every
implementation of callai:

- `argv/<name>/*.json`: request → the exact argv (or the expected refusal);
- `parse/<name>/*.json` + recorded stdout/stderr: real output → the expected `Result` fields, and
  optionally `expected_events`;
- `cli/*.json`: end-to-end cases that replay recorded output through a fake binary.

Record the parse fixtures from the real CLI. Without network access or API keys, run it against the
[stub model](test-without-a-model.md#level-2-real-harnesses-stub-model) and label the fixture
"STUB MODEL". Then check every permission level with
`python conformance/tools/permission_probe.py --name <name> --model <model> --outside <dir>`, which
runs scripted writes and shell commands and reports what really happened.

## 5. Document it

Add the harness to [Harnesses](../reference/harnesses.md), the permission table in
[Permissions](../concepts/permissions.md), and the install table in
[Installation](../getting-started/installation.md).

See also: [Architecture](../concepts/architecture.md) · [Harnesses reference](../reference/harnesses.md)
