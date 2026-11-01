# How to compare harnesses side by side

Use this to ask several coding agents the same question and compare their answers, speed and token use.

## 1. Give each harness a model under one name

Model names differ per harness, so define an alias in `~/.config/callai/config.toml`:

```toml
[aliases]
best = { claude-code = "opus", codex = "gpt-5-codex", opencode = "anthropic/claude-opus-4-1", pi = "anthropic/claude-opus-4-1", hermes = "anthropic/claude-opus-4-1", grok = "grok-4" }
```

Now `-m best` means the right model for each. An alias missing an entry for one of the harnesses in
your run is an error, so you notice before anything runs.

## 2. Run them all at once

```bash
callai -n all -m best -p "Explain what src/main.py does in two sentences" -o json --permission read-only < /dev/null > compare.json
```

`-n all` runs every installed harness at the same time and skips those that can't honour
`--permission read-only` (opencode and hermes), saying so on stderr. To choose exactly which harnesses
run, list them instead: `-n claude-code/codex/grok`.

## 3. Tabulate

```bash
jq -r '.results[] | [.harness_name, (if .is_error then "FAILED" else "ok" end), .duration_ms, (.usage.input_tokens // "-"), (.usage.output_tokens // "-")] | @tsv' compare.json
```

```text
claude-code	ok	932	11	2
codex	ok	298	11	2
pi	ok	545	11	2
grok	ok	523	11	2
```

The columns are harness, status, duration in ms, input tokens and output tokens. Pipe through
`column -t` to align them. These numbers come from the stub model, so yours will be much larger.

And the answers:

```bash
jq -r '.results[] | "## \(.harness_name)\n\(.text)\n"' compare.json
```

## Variations

- **Same harness, several models:** run one command per model. `-n` lists harnesses, not models.
- **Watch them work:** `-o stream-json` interleaves every harness's events live, each tagged with
  `harness_name`.
- **Files may change:** harnesses that edit files share one working directory. Run them one after
  another (`-n claude-code,codex`) and reset the tree between runs, or give each its own clone with
  separate commands using `-C`.

See also: [6. Ask several harnesses at once](../tutorial/06-fan-out.md) · [Model aliases](../reference/configuration.md#aliases)
