# Changelog: callai-cli banner tool

All notable changes to the banner tool in `src/tools/banner/` are documented in this file. The tool is not
part of the `callai` package; changes to callai itself are in the [root changelog](../../../CHANGELOG.md).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- PNG export from the command line: `--png [PATH]` (default `docs/assets/images/banner_<scale>x.png`, so `banner_2x.png`), `--scale`
  (default **2**), `--background`, `--ink` and `--chrome`, and `make maint.banner.png` (`BANNER_PNG`,
  `BANNER_SCALE`, `BANNER_BACKGROUND`, `BANNER_INK`, `BANNER_CHROME`).
  - Headless Chrome screenshots the page's new export mode (`?export&bg=…&ink=…`: only the banner, unscaled).
  - The builder prefers `chrome-headless-shell`, uses a throwaway profile, stops after 90 s, and checks the
    PNG's size.
  - The 2x banner is committed at `docs/assets/images/banner_2x.png`.
- `README.md` covers the files, the `make` commands and their variables, `config.yaml`, the command-line
  options, using the page, and running the tests.
- `create_banner.py` builds `callai-banner.html` from `assets/callai-banner-template.html` and `config.yaml`.
  It uses only the standard library.
  - Every value in `config.yaml` is double-quoted. A strict YAML-subset parser rejects anything else, and a
    test checks that it reads the shipped config the same way as PyYAML.
  - `"auto"` values are read from the repository. The package name, version, Python requirement, license
    and source URL come from `pyproject.toml`. The harness list comes from `HARNESS_NAMES` in
    `src/callai/adapters/__init__.py`, which is read without being imported.
  - Text values can use `{package_name}`, `{package_version}`, `{python_requires}`, `{license}` and
    `{repo_url}`.
  - Flags override the config: `--package-version`, `--package-name`, `--python-requires`, `--license`,
    `--repo-url`, `--harnesses` and `--set KEY=VALUE`. `--check` writes nothing and exits with 1 if the page
    is stale.
  - The build stops with exit code 2 on an unknown or missing key, a value of the wrong type, an unfilled
    placeholder, or a terminal-demo harness that isn't in `harnesses`.
- `make maint.banner` and `make maint.banner.check`, with `BANNER_PACKAGE_VERSION`, `BANNER_ARGS` and
  `BANNER_PYTHON`.
- Tests in `tests/`, run by `make test`. `test_committed_banner_is_up_to_date` fails while the committed
  page is stale.
- The banner page (1280 × 640):
  - The wordmark, version and license badges, tagline, install command, a terminal demo and the harness row.
  - An Edit/Save toggle that keeps edits in the browser. Save HTML downloads a copy with the edits built in,
    and Reset discards them.
  - PNG export on the banner's own, a white, a black or a transparent background, at 1x, 2x or 4x.
    "Export all 12" downloads every combination, and an Ink setting keeps the text readable on white.

### Changed

- The page moved from `docs/callai/images/callai-banner.html` to `src/tools/banner/`. Its design is now the
  template `assets/callai-banner-template.html`, and its content comes from `config.yaml`.
- The harness row follows the registry order (`… pi, hermes, grok`).
- Each build has its own browser-storage key, so edits saved for an older build never cover up a newer
  one.

### Fixed

- The terminal demo turns off font ligatures, so `==` in the `== name ==` headers shows as two characters.
