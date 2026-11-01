# How to use callai in scripts and CI

Use this when a shell script or CI job calls a coding agent and must handle every outcome.

## A robust script

```bash
#!/usr/bin/env bash
set -uo pipefail

out=$(callai -n codex -p "Reply with exactly: pong" -o json --timeout 900 < /dev/null)
code=$?

case $code in
  0)   jq -r .text <<<"$out" ;;
  2)   echo "callai usage error (nothing ran)" >&2; exit 2 ;;
  124) echo "agent timed out" >&2; exit 1 ;;
  127) echo "harness not installed" >&2; exit 1 ;;
  *)   echo "agent failed: $(jq -r .text <<<"$out")" >&2; exit 1 ;;
esac
```

```text
pong
```

- **No `set -e`:** the script needs to see callai's exit code, not stop on it.
- **`< /dev/null`:** CI runners often give jobs an open stdin. Without the redirect, callai waits 3
  seconds for input, then warns and carries on.
- **`--timeout`:** a stuck harness and everything it started are killed (exit 124), so the job doesn't
  hang until the CI limit.

## Feed files and diffs in

```bash
echo "def add(a, b): return a - b" | callai -n codex -p "Review this code" --dry-run
```

```text
codex exec --json --skip-git-repo-check -- 'Review this code

def add(a, b): return a - b'
```

Piped stdin is appended to the `-p` prompt after a blank line. To use only stdin as the prompt, use
`-p -` or leave `-p` out; callai then waits for the pipe to close, however long that takes.

## Keep the answer and the logs apart

- stdout has the answer (or the JSON).
- stderr has callai's warnings and errors, plus the harness's stderr when it fails.
- `-v` copies the harness's stderr live on every run, which is useful in CI logs.

```bash
callai -n codex -p "…" -o json -v < /dev/null > result.json 2> agent.log
```

## Pin the behaviour

- Use `--permission` explicitly in CI. `read-only` for review jobs, `auto` for fix-up jobs.
- Set the model with `-m`, or with a config file committed to the repo and selected through
  `CALLAI_CONFIG=ci/callai.toml`. An unknown key in that file fails the job (exit 2) instead of being
  ignored.
- `callai --dry-run …` in a CI step prints the exact harness command for the log.

## Credentials

callai never handles credentials: each harness reads its own (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`XAI_API_KEY`, a signed-in config, …). Provide them to the job the way that harness documents.

See also: [Call callai from an AI agent](use-from-an-ai-agent.md) · [Exit codes and errors](../reference/errors.md) · [Configuration](../reference/configuration.md)
