# Concepts

How callai works and why it behaves as it does. Read these when you want the reasoning; the
[Reference](../reference/README.md) has the exact contracts.

- [Architecture](architecture.md): adapters, the runner, and the one run path the CLI and the API share.
- [Permissions](permissions.md): what each level allows per harness, and why callai fails closed.
- [Normalised output](normalised-output.md): how six output formats become one result and one event stream.

## Glossary

| Term | Meaning |
|---|---|
| **harness** | A coding-agent CLI that callai drives: `claude-code`, `codex`, `opencode`, `pi`, `hermes`, `grok`. Chosen with `-n`. |
| **harness name** | The `-n` value (`claude-code`), which isn't always the binary name (`claude`). |
| **adapter** | The callai module for one harness. It turns a request into that harness's command line and the harness's output into a result. |
| **request** | Everything about one run: harness, prompt, model, permission, session, extra args. |
| **result** | The normalised outcome: the `-o json` object, or a `callai.Result` in Python. |
| **event** | One line of `-o stream-json`: `start`, `text`, `tool_use`, `tool_result` or `result`. |
| **permission level** | `default`, `read-only`, `auto` or `bypass`; translated per harness. |
| **session** | A harness conversation, identified by `session_id`, that `--resume` continues. |
| **fan-out** | One prompt through several harnesses: `-n a/b` (at the same time), `-n a,b` (one after another), `-n all`. |
| **model alias** | A config name (`fast`) that maps to a different model per harness. |
| **fail closed** | Refusing (exit 2) rather than running with more access than asked for, or silently ignoring an option. |
| **stub model** | `conformance/tools/stub_llm_server.py`: a local fake model API for testing real harnesses offline. |
