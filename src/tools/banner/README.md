# callai-cli banner

A maintainer tool that builds the callai-cli banner: a single, self-contained HTML page (1280 × 640) that
you can edit in the browser and export as PNG. `make maint.banner.png` also renders it to
`docs/assets/images/banner_2x.png` at 2x (2560 × 1280). It is not part of the `callai` package; `MANIFEST.in` prunes
`src/tools/`, so nothing here ships in the sdist or wheel.

## Files

| file | what it is |
|---|---|
| `assets/callai-banner-template.html` | The page design, with `{{ name }}` placeholders. Edit this to change layout, styles or behaviour. |
| `config.yaml` | Every value that goes into the banner. Edit this to change text, badges or the terminal demo. |
| `create_banner.py` | The builder: fills the template from the config and the repository. Standard library only. |
| `callai-banner.html` | The generated page (committed). **Don't edit by hand**: run `make maint.banner` instead. |
| `../../../docs/assets/images/banner_2x.png` | The 2x PNG of the page (committed), made by `make maint.banner.png`. |
| `assets/option_a_box.png`, `assets/option_b_chip.png` | Examples of the two install-command layouts (committed, 1x), shown [below](#install-commands-option-a-or-b). Made by `make maint.banner.png` or `make maint.banner.examples`. |
| `tests/` | Tests for the builder. They run with `make test`. |
| `CHANGELOG.md` | Changes to this tool (the root `CHANGELOG.md` covers callai itself). |

## Make commands

Run these from the repository root.

| command | what it does |
|---|---|
| `make maint.banner` | Rebuild `callai-banner.html` from the template and `config.yaml`. |
| `make maint.banner.check` | Write nothing; exit 1 if `callai-banner.html` is out of date. |
| `make maint.banner.png` | Rebuild `callai-banner.html`, render it to `docs/assets/images/banner_2x.png` at **2x** with headless Chrome, and re-render the two [option examples](#install-commands-option-a-or-b). Run this whenever the banner changes. |
| `make maint.banner.examples` | Rebuild `callai-banner.html` and re-render only the option examples. |

All four take these variables:

| variable | default | meaning |
|---|---|---|
| `BANNER_PACKAGE_VERSION` | *(empty)* | Show this version instead of the one in `pyproject.toml` (`--package-version`). |
| `BANNER_ARGS` | *(empty)* | Extra arguments for `create_banner.py` (see [Command line](#command-line)). |
| `BANNER_PYTHON` | `uv run --no-project python` | The Python that runs the builder (needs 3.11+ for `tomllib`). |
| `BANNER_INSTALL_STYLE` | *(empty: `install_style` in `config.yaml`)* | `box` (option A) or `chips` (option B), see [below](#install-commands-option-a-or-b). |

`make maint.banner.png` and `make maint.banner.examples` also take:

| variable | default | meaning |
|---|---|---|
| `BANNER_PNG` | `docs/assets/images/banner_$(BANNER_SCALE)x.png` | Where to write the PNG. The default name carries the scale: `banner_1x.png`, `banner_2x.png`, `banner_4x.png`. |
| `BANNER_SCALE` | `2` | `1`, `2` or `4`: the PNG is 1280 × 640 times this. |
| `BANNER_BACKGROUND` | `as-is` | `as-is`, `white`, `black` or `transparent`. |
| `BANNER_INK` | `auto` | `auto` (dark text on white), `light` or `dark`. |
| `BANNER_CHROME` | *(found automatically)* | The Chrome/Chromium executable (see [PNG export](#png-export)). |
| `BANNER_EXAMPLES_DIR` | `src/tools/banner/assets` | Where the option examples go. |

(`BANNER_PNG`, `BANNER_SCALE`, `BANNER_BACKGROUND` and `BANNER_INK` apply to `maint.banner.png` only; the
examples are always 1x with the banner's own background.)

```bash
make maint.banner
```

```bash
make maint.banner BANNER_PACKAGE_VERSION=0.9.0
```

```bash
make maint.banner BANNER_ARGS='--set tagline="Hello there" --harnesses codex,pi'
```

```bash
make maint.banner.png
```

```bash
make maint.banner.png BANNER_SCALE=4
```

```bash
make maint.banner.png BANNER_BACKGROUND=transparent BANNER_PNG=build/banner_2x_transparent.png
```

```bash
make maint.banner.png BANNER_INSTALL_STYLE=chips
```

## Install commands: option A or B

The banner shows the install commands from `install_commands` in `config.yaml` (by default
`pip install {package_name}` and `uv tool install {package_name}`). `install_style` picks the layout:

| option | `install_style` | layout | room for | example |
|---|---|---|---|---|
| **A** (default) | `"box"` | one box, a line per command | 3 commands | `assets/option_a_box.png` |
| **B** | `"chips"` | a separate chip per command, stacked | 2 commands | `assets/option_b_chip.png` |

**Option A: `box` (default)**

![Option A: the install commands in one box](assets/option_a_box.png)

**Option B: `chips`**

![Option B: a chip per install command](assets/option_b_chip.png)

Ways to choose the layout, from most to least lasting:

1. **In `config.yaml`**: set `install_style: "chips"` and run `make maint.banner.png`. Every build uses it.
2. **For one build**: run `make maint.banner.png BANNER_INSTALL_STYLE=chips`, or
   `create_banner.py --install-style chips`, or `--set install_style=chips`.
3. **In the browser**: the **Install: Box / Chips** switch in the page's toolbar flips the layout live,
   so you can compare and export either one without rebuilding. **Save HTML** keeps the layout you chose;
   a reload goes back to the built one. **Chips** is disabled while there are more than 2 commands.

The build stops with an error if there are more commands than the layout has room for, or none at all.

The two example images are rendered from the current config and template, once per layout. They're
refreshed every time the banner images are (`make maint.banner.png`), or on their own with
`make maint.banner.examples`. Commit them along with `callai-banner.html` and `banner_2x.png`.

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
| `install_commands` | The install commands, one per line or chip, without the `$` (a list; can use `{package_name}`). Replaces the old `install_command`, which is now an error. |
| `install_style` | `"box"` (option A, default) or `"chips"` (option B); see [Install commands](#install-commands-option-a-or-b). |
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
  --install-style {box,chips}
                           install-command layout: box (option A) or chips (option B)
  --check                  don't write; exit 1 if the output is out of date

PNG export (headless Chrome/Chromium):
  --png [PATH]             also write a PNG (PATH defaults to docs/assets/images/banner_<scale>x.png)
  --scale {1,2,4}          PNG scale (default: 2)
  --background {as-is,white,black,transparent}
                           PNG background (default: as-is)
  --ink {auto,light,dark}  text colour (default: auto)
  --chrome PATH            Chrome/Chromium executable (default: $CHROME, then a search)
  --examples [DIR]         also write the 1x option examples option_a_box.png and option_b_chip.png
                           (DIR defaults to src/tools/banner/assets)
```

Exit codes: 0 on success (or an up-to-date `--check`), 1 if `--check` finds the page stale, 2 on an error
(including a failed PNG export). `--check` can't be combined with `--png` or `--examples`.

## PNG export

`--png` (and `make maint.banner.png`) writes the HTML page first, then opens it in headless Chrome in the
page's **export mode** (`callai-banner.html?export&bg=…&ink=…`). That mode shows only the banner at its
native 1280 × 640, with no toolbar and no scaling. Chrome takes a screenshot at `--force-device-scale-factor`
= the scale, so 2x gives 2560 × 1280. The builder then checks the PNG's size and stops with an error if
it's wrong. The browser renders the page itself, so this doesn't use the in-page export library. It still
needs internet access for the web fonts.

The browser used is `--chrome` (or `BANNER_CHROME`), else `$CHROME`, else the first one found in this order:

1. `chrome-headless-shell` on `PATH`, or one that Playwright installed (`~/.cache/ms-playwright`,
   `~/Library/Caches/ms-playwright`, `/opt/pw-browsers`);
2. `google-chrome`, `google-chrome-stable`, `chromium`, `chromium-browser` or `chrome` on `PATH`;
3. the usual Chrome/Chromium install paths on macOS and Windows.

The headless shell comes first because full Chrome's `--screenshot` can hang in containers. If it does,
the export stops after 90 seconds. Install the shell with:

```bash
npx playwright install chromium-headless-shell
```

Each export runs in a throwaway browser profile, so edits saved in your own browser never end up in the PNG.

## Using the page

Open `callai-banner.html` in a browser. It needs internet access for its fonts and for the PNG export
library (`html-to-image`, loaded from a CDN).

- **✎ Edit / ✓ Save**: click Edit, then click any outlined text to change it. In the harness row, press
  Enter inside a pill to add one, or empty a pill to remove it. Save keeps your edits in this browser.
  Each build has its own storage key, so edits saved for an older build never cover up a newer one.
- **Save HTML** downloads a copy of the page with your edits built in.
- **Reset** throws away saved edits.
- **Export PNG** uses the chosen **Background** (as is, white, black or transparent) and **Scale**
  (1x = 1280 × 640, **2x by default**, 4x). The browser saves it to your downloads folder; use
  `make maint.banner.png` to write `docs/assets/images/banner_2x.png`. **Export all 12** downloads every background at every scale, named like
  `callai-banner-transparent@4x.png`.
- **Ink** sets the text colour. **Auto** switches to dark text on white; choose **Dark** for a
  transparent PNG that will sit on a light background.
- **Install** switches the install commands between **Box** (option A) and **Chips** (option B), keeping
  any edits; see [Install commands](#install-commands-option-a-or-b).

Edits made in the browser stay in the browser. To change the banner for good, edit `config.yaml` (or the
template) and run `make maint.banner`.

## Used by the docs page

`make docs.html` (`docs/site/build_docs_html.py`) shows this banner at the top of the docs landing page. It
copies the CSS between the `banner:css:start`/`banner:css:end` comments and the markup between
`banner:html:start`/`banner:html:end` from `callai-banner.html`, without `data-edit` and the editor's ids, and
with the wordmark `<h1>` turned into a `<div>` so it stays out of the page outline. Keep those markers in the
template. Run `make maint.banner` before `make docs.html` so the docs get the current banner.

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
