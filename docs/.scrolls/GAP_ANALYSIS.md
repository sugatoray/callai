# GAP_ANALYSIS.md — Known Gaps

Concrete list of what is NOT implemented yet, or is a known partial/simplified implementation. One line per gap, terse. Remove a line the moment it's closed — don't mark it done, delete it; `GAP_CONTEXT.md` keeps the historical reasoning if that's ever needed.

- hermes: `--permission read-only` and `--continue` refused (use `--resume SESSION_ID`); no token usage, cost or reported model.
- pi: prompts starting with `@` refused.
- grok: prompts starting with `/` (after whitespace) refused; `auto` writes aren't confined to the working directory unless the user adds `-- --sandbox workspace`.
- claude-code `bypass` fails as root unless the user sets `IS_SANDBOX=1`.
- opencode: `--permission read-only|auto` and `--system-prompt` refused.
- Windows: `callai -p X` still blocks on a stdin pipe that never closes (`select` can't watch pipes there).
- No live-model recordings except claude: network policy blocks api.openai.com, api.x.ai, router.huggingface.co, and there is no HF_TOKEN. Other tools' parse fixtures use the local stub model.
- `-o stream-json`: codex tool items other than `command_execution`, and every harness's tool-error shapes except grok's refusal, are mapped from their event schema but not yet recorded.
- Live smoke tests verified only for claude-code (the other harnesses need model access this container lacks).
- Fan-out: parallel runs share one working directory (no per-harness worktree), and `-v` stderr from parallel harnesses is interleaved without prefixes.
- `superagent-ai/grok-cli` not supported (only xAI's official `grok`).

See `GAP_CONTEXT.md` for the reasoning behind each entry.
