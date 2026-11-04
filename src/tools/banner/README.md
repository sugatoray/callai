# callai-cli banner

A maintainer tool that builds the callai-cli banner: a single, self-contained HTML page (1280 × 640) that
you can edit in the browser and export as PNG. It is not part of the `callai` package; `MANIFEST.in` prunes
`src/tools/`, so nothing here ships in the sdist or wheel.

## Files

| file | what it is |
|---|---|
| `assets/callai-banner-template.html` | The page design, with `{{ name }}` placeholders. Edit this to change layout, styles or behaviour. |
| `config.yaml` | Every value that goes into the banner. Edit this to change text, badges or the terminal demo. |
| `create_banner.py` | The builder: fills the template from the config and the repository. Standard library only. |
| `callai-banner.html` | The generated page (committed). **Don't edit by hand**: run `make maint.banner` instead. |
| `tests/` | Tests for the builder. They run with `make test`. |
| `CHANGELOG.md` | Changes to this tool (the root `CHANGELOG.md` covers callai itself). |

## Make commands

Run these from the repository root.

| command | what it does |
|---|---|
| `make maint.banner` | Rebuild `callai-banner.html` from the template and `config.yaml`. |
| `make maint.banner.check` | Write nothing; exit 1 if `callai-banner.html` is out of date. |

Both take these variables:

| variable | default | meaning |
|---|---|---|
| `BANNER_PACKAGE_VERSION` | *(empty)* | Show this version instead of the one in `pyproject.toml` (`--package-version`). |
| `BANNER_ARGS` | *(empty)* | Extra arguments for `create_banner.py` (see [Command line](#command-line)). |
| `BANNER_PYTHON` | `uv run --no-project python` | The Python that runs the builder (needs 3.11+ for `tomllib`). |

```bash
make maint.banner
```

```bash
make maint.banner BANNER_PACKAGE_VERSION=0.9.0
```

```bash
make maint.banner BANNER_ARGS='--set tagline="Hello there" --harnesses codex,pi'
```

## How it works

1. `create_banner.py` reads `config.yaml`.
2. Every value set to `"auto"` is read from the repository:

   | key | source |
   |---|---|
   | `package_name` | `[project] name` in `pyproject.toml` |
   | `package_version` | `[project] version` |
   | `python_requires` | `[project] requires-python`, shown as e.g. `≥ 3.11` |
   | `license` | `[project] license` |
   | `repo_url` | `[project.urls] Source` (or `Homepage`), without `https://` |
   | `harnesses` | `HARNESS_NAMES` in `src/callai/adapters/__init__.py` (read, not imported) |

3. Command-line flags override both the config and `"auto"`.
4. Text values can use `{package_name}`, `{package_version}`, `{python_requires}`, `{license}` and
   `{repo_url}`. For example, `install_command: "pip install {package_name}"`.
5. The values are HTML-escaped and put into the template's `{{ name }}` placeholders. The harness pills
   and the terminal demo are generated, with the fan-out lines aligned.
6. The page is written to `callai-banner.html`.

The build stops with an error (exit 2) if:

- the config has an unknown or missing key, or a value of the wrong type;
- the template uses a placeholder that has no value;
- a terminal-demo harness (`fanout_harnesses`, `pipe_harness`) isn't in `harnesses`;
- `fanout_harnesses` is empty or `fanout_durations` has a different length.

## `config.yaml`

The config is a strict subset of YAML that any YAML parser reads the same way:

- every value is a **double-quoted** string (JSON escapes), or a list of double-quoted strings;
- write a list as `key:` followed by indented `  - "item"` lines, or as `key: []`;
- `# comments` and blank lines are allowed; nested mappings, unquoted values and single quotes are not.

| key | used for |
|---|---|
| `package_name`, `package_version`, `python_requires`, `license`, `repo_url` | Repository facts (`"auto"` or your own text). |
| `harnesses` | The harness pills (`"auto"` or a list). |
| `page_title` | The browser tab title and the toolbar label. |
| `version_label`, `python_label`, `license_label` | The two badges above the wordmark. |
| `mark_glyph` | The text in the square mark (`>_`). |
| `wordmark_plain`, `wordmark_accent` | The wordmark: plain part, then the gradient part (`call` + `ai`). |
| `tagline`, `subtitle` | The headline and the line under it. |
| `install_command` | The install chip (without the `$`). |
| `terminal_title` | The terminal window's title bar. |
| `fanout_harnesses`, `fanout_durations`, `fanout_prompt` | The parallel-run demo: one duration per harness. |
| `pipe_harness`, `pipe_prompt` | The `git diff \| callai ... -o json` demo. |
| `harness_label`, `repo_label` | The text before the pills and the URL at the bottom right. |

## Command line

```text
python src/tools/banner/create_banner.py [options]

  --config PATH            config file (default: src/tools/banner/config.yaml)
  --template PATH          HTML template (default: src/tools/banner/assets/callai-banner-template.html)
  --output PATH            page to write (default: src/tools/banner/callai-banner.html)
  --repo-root PATH         repository that "auto" values are read from (default: this repository)
  --package-name TEXT      override package_name
  --package-version TEXT   override package_version
  --python-requires TEXT   override python_requires
  --license TEXT           override license
  --repo-url TEXT          override repo_url
  --harnesses A,B,...      override harnesses
  --set KEY=VALUE          override any config key; list keys take comma-separated values (repeatable)
  --check                  don't write; exit 1 if the output is out of date
```

Exit codes: 0 on success (or an up-to-date `--check`), 1 if `--check` finds the page stale, 2 on an error.

## Using the page

Open `callai-banner.html` in a browser. It needs internet access for its fonts and for the PNG export
library (`html-to-image`, loaded from a CDN).

- **✎ Edit / ✓ Save**: click Edit, then click any outlined text to change it. In the harness row, press
  Enter inside a pill to add one, or empty a pill to remove it. Save keeps your edits in this browser.
  Each build has its own storage key, so edits saved for an older build never cover up a newer one.
- **Save HTML** downloads a copy of the page with your edits built in.
- **Reset** throws away saved edits.
- **Export PNG** uses the chosen **Background** (as is, white, black or transparent) and **Scale**
  (1x = 1280 × 640, 2x, 4x). **Export all 12** downloads every background at every scale, named like
  `callai-banner-transparent@4x.png`.
- **Ink** sets the text colour. **Auto** switches to dark text on white; choose **Dark** for a
  transparent PNG that will sit on a light background.

Edits made in the browser stay in the browser. To change the banner for good, edit `config.yaml` (or the
template) and run `make maint.banner`.

## Tests

```bash
make test
```

```bash
uv run --extra test pytest src/tools/banner/tests --no-cov
```

Pass `--no-cov` when you run only these tests: the project's coverage threshold is measured on the `callai`
package. One test, `test_committed_banner_is_up_to_date`, fails whenever the committed page is stale, for
example after a version bump in `pyproject.toml`. Fix it with `make maint.banner`.
