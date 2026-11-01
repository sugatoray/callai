# SCOPE.md — Project Scope, Decisions & Roadmap

What `callai` is, what was decided about language and distribution, and in what
order work happens. The *how* (CLI surface, adapters, output schema, exit codes)
lives in [`docs/DESIGN.md`](docs/DESIGN.md); the ticketed backlog lives in
[`docs/.scrolls/PLAN.md`](docs/.scrolls/PLAN.md).

Recorded: 2026-10-30, from the initial design discussion.

## 1. Objective

One command line that replaces running each coding-agent harness CLI by hand:

```bash
callai --name/-n {claude-code,codex,opencode,pi,hermes,grok} \
       -c/--command/-p/--prompt PROMPT [-m/--model MODEL]
```

It runs the prompt non-interactively through the chosen harness and returns the output. It is
modelled on `claude -p`. `callai` is a **thin dispatcher**: it builds the right command line
for the harness, runs it as a subprocess, and turns the result into one predictable text or
JSON shape. It does not reimplement agents, call model APIs, or manage credentials.

## 2. Language decision — Python first

### Python vs TypeScript, pros and cons

The workload is to start a subprocess, wait for it, parse JSON or text, and print the
result. Neither language is noticeably faster at this, so the choice depends on the
surroundings.

| Factor | Python | TypeScript |
|---|---|---|
| Fits this repo's existing setup (`expt_svg2font`: setuptools, pytest + coverage, ruff, interrogate) | ✓ | ✗ (new setup) |
| Can be stdlib-only (argparse, subprocess, tomllib, json) | ✓ | ✗ (needs a TOML dependency, or a JSON config instead) |
| Robust process-group kill / timeout handling | ✓ | ✓ |
| Same ecosystem as the wrapped harnesses (claude, opencode, pi are Node/TS; codex installs via npm) | ✗ | ✓ |
| `npx` / `npm i -g` install for the target users | ✗ | ✓ |
| Easy single-file binary | ✗ (PyInstaller/Nuitka are clunky) | ✓ (`bun build --compile`, about 50 MB) |
| Path to native harness SDKs later (mostly TS-first; Claude also has Python) | weaker | ✓ |
| Library use from eval scripts / notebooks / data pipelines | ✓ | ✗ |
| Owner's comfort / speed of iteration | ✓ | — |
| Start-up time | Tie: both are tiny next to agent runs that take seconds to minutes | Tie |

**Decision:** build in **Python** first. The owner is most comfortable in Python,
it fits the repo setup, and it needs no third-party dependencies.

## 3. Rust core — feasibility (recorded for later)

A Rust core with Python and TS packages on top **is feasible**. Precedents: ruff and uv
(Rust on PyPI), Biome, esbuild and SWC (native binaries on npm), and HF `tokenizers` (one Rust core
with both Python and Node bindings).

There are two ways to connect the Rust core to Python and TypeScript:

- **A. Native bindings** (PyO3 + maturin for Python, napi-rs for Node). The API runs
  in-process, but you maintain two binding layers. Streaming events across the language
  boundary is fiddly, PyO3 async is less mature, and the build matrix is doubled
  (Python version × platform, plus Node × platform).
- **B. One Rust binary + thin wrappers (preferred if we go to Rust).** The `callai` binary
  contains all adapters. The Python and TS packages are each about 100 lines that run the
  binary with `-o json` / `stream-json` and return typed objects. The contract is the JSON
  output schema: generate a JSON Schema from the Rust types (`schemars`), then Python
  dataclasses (`datamodel-code-generator`) and TS types (`json-schema-to-typescript`)
  from that schema. The extra process costs a few ms, which doesn't matter for this workload.
  Exit codes, timeouts and SIGINT behave the same everywhere. Native bindings can still be
  added later.

Suggested Rust crates: `clap` (aliases `-p/-c/--prompt/--command`), `serde`/`serde_json`, `toml`,
`schemars`, `command-group` (process-tree kill, Windows job objects), `assert_cmd` + `insta`
(snapshot tests of each adapter's command line), `cargo-dist` or a GitHub Actions matrix for releases.

Is it worth it? The core is about 1–2k lines and Rust won't make it noticeably faster for users. What
Rust buys is **distribution**: a small static binary, published identically to every
registry from one implementation.

## 4. Distribution — PyPI and npm from one install command each

### Rust binary on PyPI and npm (Option B above)

- **PyPI:** maturin `bindings = "bin"` builds one wheel per platform (manylinux / musllinux /
  macOS / Windows tags). `pip` / `uv tool install` / `pipx` downloads only the matching wheel,
  which puts `callai` on PATH and includes the pure-Python API module.
- **npm** (esbuild/Biome pattern): the main `callai` package holds the TS wrapper and a launcher.
  Each platform gets a package (`@callai/linux-x64`, `@callai/darwin-arm64`,
  `@callai/win32-x64`, …) with `"os"`/`"cpu"` fields, listed in `optionalDependencies`.
  The package manager installs only the matching one. Nothing is downloaded at install time,
  so it works offline, behind proxies and with `--ignore-scripts`.
- **Targets (7):** Linux glibc and musl × x64/arm64, macOS x64/arm64, Windows x64.
- **Caveats:**
  - Unsupported platforms: pip falls back to the source package, which needs Rust. Consider
    publishing no source package and showing a clear error instead.
  - `npm --omit=optional` breaks the install. The launcher must detect this and explain the fix.
  - Some older npm versions had lockfile bugs across different operating systems.
  - Installing from both PyPI and npm puts two `callai` commands on PATH. They're the same
    binary, so it's harmless; `--version` should report where it was installed from.
  - Check the `callai` name on both PyPI and npm early. The package name can differ from the
    command name.

### Python on npm (if we stay Python-only for a while)

| Option | How | npm users need Python? | Notes |
|---|---|---|---|
| 1. Frozen binary per platform | PyInstaller (**onedir**, not onefile) or Nuitka, same `optionalDependencies` layout | No | About 10–30 MB per platform. Needs a CI runner per OS (no cross-compiling), Windows antivirus false positives, macOS signing and notarization, an old-glibc build host. |
| 2. Vendor pure-Python source | npm package ships `callai/*.py` and the launcher runs `python3 -m callai` (falls back to `uv` if present) | Yes (≥ 3.11) | A few KB, one package. Only possible because `callai` is stdlib-only. Many JS developers lack a modern Python. |
| 3. Hand off to `uvx` | Launcher runs `uvx callai@<same version>` | Needs `uv` | Tiny, but needs the network on first run. Fine internally, weak as a public package. |
| ✗ Pyodide / WASM | — | — | Not viable: WASM can't start subprocesses, which is all `callai` does. |

## 5. Roadmap (agreed)

1. **Python implementation (now).** Build with Red/Green TDD, following `docs/DESIGN.md`. Publish to PyPI.
2. **TypeScript port, maintained alongside Python.** Port module by module. The Python test
   suite is the spec, so the port can be checked against it. Later on, both implementations are maintained.
3. **Rust port (only if it makes sense then).** Same conformance suite.
4. **Final distribution (if it makes sense).** Rust becomes the single core, published to
   PyPI and npm as one binary with thin Python and TS wrappers (§3 Option B, §4).

### What makes the ports checkable

Keep tests that don't depend on the implementation language **as data**, not just as Python code, so
every port runs the same cases:

- `conformance/argv/*.json`: `{request} → expected argv` golden cases for each adapter.
- `conformance/parse/<tool>/*`: recorded harness output, plus the expected normalised `Result` JSON.
- `conformance/cli/*.json`: CLI cases (args + stdin + fake-harness behaviour → stdout, exit code).
- Fake harness scripts that echo their argv and replay recorded output.

pytest (and later vitest / `cargo test`) load these same files. A port is done when it
passes the whole shared suite. Implementation-specific unit tests can still live next to each
implementation.

## 6. Decisions (resolved 2026-10-30 — see DESIGN §11)

- `grok`: xAI's official Grok Build CLI.
- Default `--output-format`: `text`.
- Minimum Python: 3.11 (stdlib-only).
- Names: PyPI **`callai-cli`** (`callai` is taken); the command and import name stay `callai`.
  npm `callai` / `callai-cli` were both free on 2026-10-30; pick at the TS port.
