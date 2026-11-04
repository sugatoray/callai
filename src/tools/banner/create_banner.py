"""Build the callai-cli banner page from ``config.yaml`` and ``assets/callai-banner-template.html``.

Usage (from the repository root; ``make maint.banner`` runs this)::

    python src/tools/banner/create_banner.py [--package-version X.Y.Z] [--set KEY=VALUE ...] [--check]
    python src/tools/banner/create_banner.py --png [PATH] [--scale 2] [--background as-is]

Values set to ``"auto"`` in the config are read from the repository: the package name, version,
Python requirement, license and source URL from ``pyproject.toml``, and the harness names from
``HARNESS_NAMES`` in ``src/callai/adapters/__init__.py``. Command-line flags override the config.
``--png`` also screenshots the page with headless Chrome/Chromium (default: 2x, as
``docs/assets/images/banner_2x.png``; the file name follows ``--scale``).

Maintainer tool only: it lives outside the ``callai`` package and is excluded from the sdist and
wheel. Standard library only, like callai itself, so the config is read with a small parser for a
strict YAML subset (see :func:`parse_config`).
"""

from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

BANNER_DIR = Path(__file__).resolve().parent
REPO_ROOT = BANNER_DIR.parents[2]
DEFAULT_CONFIG = BANNER_DIR / "config.yaml"
DEFAULT_TEMPLATE = BANNER_DIR / "assets" / "callai-banner-template.html"
DEFAULT_OUTPUT = BANNER_DIR / "callai-banner.html"
DEFAULT_PNG_DIR = REPO_ROOT / "docs" / "assets" / "images"
DEFAULT_EXAMPLES_DIR = BANNER_DIR / "assets"

#: The banner's size in CSS pixels; a PNG at scale N is N times this.
BANNER_SIZE = (1280, 640)
SCALES = (1, 2, 4)
DEFAULT_SCALE = 2
_PNG_DEFAULT = object()  # --png given without a PATH (not a str: argparse would run type=Path on it)


def default_png(scale: int) -> Path:
    """The default PNG path for a scale: ``docs/assets/images/banner_<scale>x.png``.

    Args:
        scale: The PNG scale (1, 2 or 4).

    Returns:
        The path, with the scale in the file name.
    """
    return DEFAULT_PNG_DIR / f"banner_{scale}x.png"


DEFAULT_PNG = default_png(DEFAULT_SCALE)
BACKGROUNDS = ("as-is", "white", "black", "transparent")
INKS = ("auto", "light", "dark")
#: Where to look for a browser when --chrome and $CHROME are unset, in order. Plain names are looked up on
#: PATH; entries with a path separator are glob patterns (newest match first). chrome-headless-shell comes
#: first: full Chrome's ``--screenshot`` can hang in containers (seen with Chrome for Testing 153).
CHROME_SEARCH = (
    "chrome-headless-shell",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/opt/pw-browsers/chromium",
)
CHROME_TIMEOUT = 90  # seconds

AUTO = "auto"
#: Values that ``"auto"`` reads from the repository.
FACT_KEYS = ("package_name", "package_version", "python_requires", "license", "repo_url", "harnesses")
#: Keys whose value is a list of strings ("auto" is also allowed for ``harnesses``).
LIST_KEYS = ("harnesses", "fanout_harnesses", "fanout_durations", "install_commands")
#: How the install commands are laid out, with the most commands each layout has room for.
INSTALL_STYLES = {"box": 3, "chips": 2}
#: The example PNG written for each install style by ``--examples`` (shown in README.md).
EXAMPLES = {"box": "option_a_box.png", "chips": "option_b_chip.png"}
#: Keys that were renamed, mapped to their replacement.
RENAMED_KEYS = {"install_command": "install_commands"}
#: Every key ``config.yaml`` must define, and the only keys it may define.
CONFIG_KEYS = (
    *FACT_KEYS,
    "page_title",
    "version_label",
    "python_label",
    "license_label",
    "mark_glyph",
    "wordmark_plain",
    "wordmark_accent",
    "tagline",
    "subtitle",
    "install_commands",
    "install_style",
    "terminal_title",
    "fanout_harnesses",
    "fanout_durations",
    "fanout_prompt",
    "pipe_harness",
    "pipe_prompt",
    "harness_label",
    "repo_label",
)
#: Template fields filled straight from a config value (HTML-escaped).
TEXT_FIELDS = (
    "page_title",
    "version_label",
    "python_label",
    "license_label",
    "mark_glyph",
    "wordmark_plain",
    "wordmark_accent",
    "tagline",
    "subtitle",
    "terminal_title",
    "harness_label",
    "repo_label",
)

Value = str | list[str]


class BannerError(Exception):
    """A problem with the config, the template, the repository or the arguments."""


# ── Config: a strict YAML subset ────────────────────────────────────────────────

_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
_ITEM_LINE = re.compile(r"^\s+-\s(.*)$")
_DECODER = json.JSONDecoder()


def _quoted(text: str, lineno: int) -> str:
    """Decode one double-quoted scalar, allowing only a ``# comment`` after it.

    Args:
        text: The text after ``key:`` or ``-``.
        lineno: Line number for error messages.

    Returns:
        The decoded string.

    Raises:
        BannerError: If the value is not a double-quoted string or has trailing text.
    """
    text = text.strip()
    if not text.startswith('"'):
        raise BannerError(f"line {lineno}: values must be double-quoted strings, got {text!r}")
    try:
        value, end = _DECODER.raw_decode(text)
    except json.JSONDecodeError as exc:
        raise BannerError(f"line {lineno}: bad double-quoted string: {exc.msg}") from None
    rest = text[end:].strip()
    if rest and not rest.startswith("#"):
        raise BannerError(f"line {lineno}: unexpected text after the value: {rest!r}")
    return value


def parse_config(text: str) -> dict[str, Value]:
    """Parse the banner config, a strict subset of YAML.

    Allowed: ``# comments``, blank lines, ``key: "value"``, ``key: []`` and ``key:`` followed by
    indented ``- "item"`` lines. Every value must be double-quoted (JSON string escapes). The
    result equals what a full YAML parser returns for the same text.

    Args:
        text: The config file's contents.

    Returns:
        The keys mapped to strings or lists of strings, in file order.

    Raises:
        BannerError: On any line outside the subset, a duplicate key, or an empty list header.
    """
    data: dict[str, Value] = {}
    open_list: str | None = None  # key whose `- item` lines we're reading
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _ITEM_LINE.match(line)
        if item and open_list is not None:
            data[open_list].append(_quoted(item.group(1), lineno))  # type: ignore[union-attr]
            continue
        match = _KEY_LINE.match(line)
        if not match:
            raise BannerError(f'line {lineno}: expected `key: "value"` or `  - "item"`, got {line!r}')
        if open_list is not None and not data[open_list]:
            raise BannerError(f'{open_list}: a list needs at least one `- "item"` line (or write `[]`)')
        key, rest = match.group(1), match.group(2).strip()
        if key in data:
            raise BannerError(f"line {lineno}: duplicate key {key!r}")
        open_list = None
        if not rest or rest.startswith("#"):
            data[key] = []
            open_list = key
        elif rest.split("#", 1)[0].strip() == "[]":
            data[key] = []
        else:
            data[key] = _quoted(rest, lineno)
    if open_list is not None and not data[open_list]:
        raise BannerError(f'{open_list}: a list needs at least one `- "item"` line (or write `[]`)')
    return data


def load_config(path: Path) -> dict[str, Value]:
    """Read and parse a config file.

    Args:
        path: The config file.

    Returns:
        The parsed config.

    Raises:
        BannerError: If the file can't be read or parsed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BannerError(f"cannot read config {path}: {exc.strerror}") from None
    try:
        return parse_config(text)
    except BannerError as exc:
        raise BannerError(f"{path}: {exc}") from None


# ── Facts from the repository ───────────────────────────────────────────────────


def display_python_requires(spec: str) -> str:
    """Turn a ``requires-python`` specifier into banner text, e.g. ``>=3.11`` -> ``≥ 3.11``.

    Args:
        spec: A PEP 440 specifier set such as ``>=3.11,<4``.

    Returns:
        The specifier with ``>=``/``<=`` shown as ``≥``/``≤`` and ``==`` dropped.
    """
    ops = {">=": "≥ ", "<=": "≤ ", "==": "", "!=": "≠ ", "~=": "~", ">": "> ", "<": "< "}
    parts = []
    for clause in filter(None, (c.strip() for c in spec.split(","))):
        op = next((o for o in ops if clause.startswith(o)), "")
        parts.append(ops.get(op, "") + clause[len(op) :].strip())
    return ", ".join(parts)


def _harness_names(root: Path) -> list[str]:
    """Read ``HARNESS_NAMES`` from the adapters package without importing it.

    Args:
        root: The repository root.

    Returns:
        The harness names, in registry order.

    Raises:
        BannerError: If the file or the ``HARNESS_NAMES`` literal is missing.
    """
    path = root / "src" / "callai" / "adapters" / "__init__.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError:
        raise BannerError(f'cannot read {path} (needed for harnesses: "auto")') from None
    for node in tree.body:
        target = (
            node.target
            if isinstance(node, ast.AnnAssign)
            else (node.targets[0] if isinstance(node, ast.Assign) else None)
        )
        if isinstance(target, ast.Name) and target.id == "HARNESS_NAMES" and node.value is not None:
            return [str(name) for name in ast.literal_eval(node.value)]
    raise BannerError(f"{path}: no HARNESS_NAMES literal found")


def repo_facts(root: Path) -> dict[str, Value]:
    """Read the values ``"auto"`` stands for from the repository.

    Args:
        root: The repository root (holds ``pyproject.toml`` and ``src/callai``).

    Returns:
        ``package_name``, ``package_version``, ``python_requires`` (display form), ``license``,
        ``repo_url`` (without the scheme) and ``harnesses``.

    Raises:
        BannerError: If ``pyproject.toml`` or the harness registry can't be read.
    """
    path = root / "pyproject.toml"
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    except OSError:
        raise BannerError(f"cannot read {path}") from None
    license_ = project.get("license", "")
    if isinstance(license_, dict):  # legacy table form: {text = "..."} or {file = "..."}
        license_ = license_.get("text", "")
    urls = project.get("urls", {})
    url = urls.get("Source") or urls.get("Homepage") or ""
    return {
        "package_name": project.get("name", ""),
        "package_version": project.get("version", ""),
        "python_requires": display_python_requires(project.get("requires-python", "")),
        "license": license_,
        "repo_url": re.sub(r"^[a-z]+://", "", url).rstrip("/"),
        "harnesses": _harness_names(root),
    }


# ── Resolving values ────────────────────────────────────────────────────────────


def resolve(config: dict[str, Value], overrides: dict[str, Value], root: Path) -> dict[str, Value]:
    """Merge config and overrides, fill ``"auto"`` from the repository and interpolate ``{fact}``.

    Args:
        config: The parsed config file.
        overrides: Values from the command line; they win over the config.
        root: The repository root, for ``"auto"`` values.

    Returns:
        Every config key with its final value.

    Raises:
        BannerError: On unknown or missing keys, wrong value types, or demo harnesses that
            aren't in ``harnesses``.
    """
    for source in (config, overrides):
        for key in source:
            if key in RENAMED_KEYS:
                raise BannerError(f"{key} was replaced by {RENAMED_KEYS[key]} (a list); rename it in the config")
            if key not in CONFIG_KEYS:
                raise BannerError(f"unknown config key {key!r}; known keys: {', '.join(CONFIG_KEYS)}")
    for key in CONFIG_KEYS:
        if key not in config:
            raise BannerError(f"missing config key {key!r}")
    values = {**config, **overrides}

    facts: dict[str, Value] | None = None
    for key in FACT_KEYS:
        if values[key] == AUTO:
            facts = facts if facts is not None else repo_facts(root)
            values[key] = facts[key]

    for key in CONFIG_KEYS:
        is_list = isinstance(values[key], list)
        if key in LIST_KEYS and not is_list:
            raise BannerError(f"{key} must be a list of strings")
        if key not in LIST_KEYS and is_list:
            raise BannerError(f"{key} must be a string")

    fact_values = {k: v for k, v in values.items() if k in FACT_KEYS and isinstance(v, str)}

    def interpolate(text: str) -> str:
        """Replace ``{fact}`` names (e.g. ``{package_name}``) in a text value; leave others as-is.

        Args:
            text: A text config value.

        Returns:
            The text with known ``{fact}`` names filled in.
        """
        return re.sub(r"\{(\w+)\}", lambda m: fact_values.get(m.group(1), m.group(0)), text)

    for key in TEXT_FIELDS:
        values[key] = interpolate(values[key])  # type: ignore[arg-type]
    values["install_commands"] = [interpolate(c) for c in values["install_commands"]]  # type: ignore[union-attr]

    style, commands = values["install_style"], values["install_commands"]
    if style not in INSTALL_STYLES:
        raise BannerError(f"install_style must be one of {', '.join(INSTALL_STYLES)}, got {style!r}")
    if not commands:
        raise BannerError("install_commands needs at least one command")
    if len(commands) > INSTALL_STYLES[style]:
        room = INSTALL_STYLES[style]
        raise BannerError(f"install_style {style!r} has room for at most {room} install_commands, got {len(commands)}")

    harnesses = values["harnesses"]
    if not values["fanout_harnesses"]:
        raise BannerError("fanout_harnesses needs at least one harness")
    unknown = [h for h in values["fanout_harnesses"] if h not in harnesses]
    if unknown:
        raise BannerError(f"fanout_harnesses: {', '.join(unknown)} not in harnesses ({', '.join(harnesses)})")
    if values["pipe_harness"] not in harnesses:
        raise BannerError(f"pipe_harness {values['pipe_harness']!r} is not in harnesses ({', '.join(harnesses)})")
    if len(values["fanout_durations"]) != len(values["fanout_harnesses"]):
        raise BannerError("fanout_durations needs one entry per fanout_harnesses entry")
    return values


# ── Rendering ───────────────────────────────────────────────────────────────────

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def render(template: str, context: dict[str, str]) -> str:
    """Replace every ``{{ name }}`` in the template with ``context[name]`` (inserted as-is).

    Args:
        template: The template text.
        context: Placeholder names mapped to ready-to-insert HTML.

    Returns:
        The filled template.

    Raises:
        BannerError: If the template uses a placeholder the context doesn't define.
    """
    missing = sorted({m.group(1) for m in _PLACEHOLDER.finditer(template)} - set(context))
    if missing:
        raise BannerError(f"template placeholder(s) with no value: {', '.join(missing)}")
    return _PLACEHOLDER.sub(lambda m: context[m.group(1)], template)


def _terminal_body(values: dict[str, Value]) -> str:
    """The terminal demo's HTML: a fan-out run, a piped JSON run and a prompt with a cursor.

    Args:
        values: The resolved config values.

    Returns:
        HTML for the ``.term-body`` element (whitespace is preserved by its CSS).
    """
    e = html.escape
    fanout = values["fanout_harnesses"]
    quoted = {k: e(json.dumps(values[k], ensure_ascii=False)) for k in ("fanout_prompt", "pipe_prompt")}
    width = max(len(f"== {h} ==") for h in fanout) + 2
    lines = [
        f'<span class="p">$</span> callai <span class="f">-n</span> {e("/".join(fanout))} \\',
        f'    <span class="f">-p</span> <span class="s">{quoted["fanout_prompt"]}</span>',
    ]
    for name, took in zip(fanout, values["fanout_durations"], strict=True):
        header = f"== {name} =="
        lines.append(
            f'<span class="h">{e(header)}</span>{" " * (width - len(header))}'
            f'<span class="ok">✓</span> <span class="c">{e(took)}</span>'
        )
    pipe = values["pipe_harness"]
    sample = e(json.dumps({"harness_name": pipe, "is_error": False})[:-1] + ", …}")
    lines += [
        "",
        f'<span class="p">$</span> git diff | callai <span class="f">-n</span> {e(pipe)} \\',
        f'    <span class="f">-p</span> <span class="s">{quoted["pipe_prompt"]}</span> <span class="f">-o</span> json',
        f'<span class="c">{sample}</span>',
        "",
        '<span class="p">$</span> <span class="cursor"></span>',
    ]
    return "\n".join(lines)


def _install_block(values: dict[str, Value]) -> str:
    """The install commands' HTML: option A (one box) or option B (a chip per command).

    Args:
        values: The resolved config values.

    Returns:
        HTML for the install area; each command is its own editable span.
    """
    pad = "          "
    dollar = '<span class="dollar">$</span>'
    commands = [f"<span data-edit>{html.escape(c, quote=False)}</span>" for c in values["install_commands"]]
    if values["install_style"] == "box":
        lines = "".join(f'\n{pad}  <div class="line">{dollar}{c}</div>' for c in commands)
        return f'<div class="install install-box">{lines}\n{pad}</div>'
    chips = "".join(f'\n{pad}  <div class="install">{dollar}{c}</div>' for c in commands)
    return f'<div class="install-chips">{chips}\n{pad}</div>'


def build_context(values: dict[str, Value]) -> dict[str, str]:
    """Turn resolved values into the template's placeholder HTML.

    Args:
        values: The resolved config values.

    Returns:
        Placeholder names mapped to HTML. ``store_key`` changes whenever the content does, so
        edits saved in a browser for an older build don't hide a newer one.
    """
    context = {key: html.escape(values[key], quote=False) for key in TEXT_FIELDS}  # type: ignore[arg-type]
    context["terminal_body"] = _terminal_body(values)
    context["install_block"] = _install_block(values)
    context["harness_pills"] = "\n".join(
        f'            <span class="pill">{html.escape(name)}</span>' for name in values["harnesses"]
    )
    digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:12]
    context["store_key"] = f"callai-banner:{digest}"
    return context


def build_banner(config_path: Path, template_path: Path, root: Path, overrides: dict[str, Value]) -> str:
    """Build the banner HTML.

    Args:
        config_path: The ``config.yaml`` to read.
        template_path: The HTML template with ``{{ name }}`` placeholders.
        root: The repository root, for ``"auto"`` values.
        overrides: Config values that win over the file (e.g. from ``--package-version``).

    Returns:
        The finished HTML page.

    Raises:
        BannerError: If the template can't be read, or on any config/repository problem.
    """
    values = resolve(load_config(config_path), overrides, root)
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BannerError(f"cannot read template {template_path}: {exc.strerror}") from None
    return render(template, build_context(values))


# ── PNG export ──────────────────────────────────────────────────────────────────


def find_chrome(explicit: str | None) -> str:
    """Locate a Chrome or Chromium executable.

    Args:
        explicit: A path or command name from ``--chrome``; if unset, ``$CHROME``,
            then the first hit in :data:`CHROME_SEARCH`.

    Returns:
        The executable's path.

    Raises:
        BannerError: If the given executable doesn't exist, or none is found.
    """
    given = explicit or os.environ.get("CHROME")
    if given:
        if Path(given).is_file():
            return given
        found = shutil.which(given)
        if found:
            return found
        raise BannerError(f"Chrome executable not found: {given}")
    for entry in CHROME_SEARCH:
        if "/" in entry or "\\" in entry:
            hits = sorted(glob.glob(os.path.expanduser(entry)), reverse=True)
            found = next((h for h in hits if Path(h).is_file()), None)
        else:
            found = shutil.which(entry)
        if found:
            return found
    raise BannerError("no Chrome or Chromium found: install one, or pass --chrome PATH (or set $CHROME)")


def chrome_command(
    chrome: str,
    html_path: Path,
    png_path: Path,
    scale: int = DEFAULT_SCALE,
    background: str = "as-is",
    ink: str = "auto",
    user_data_dir: Path | None = None,
) -> list[str]:
    """The headless Chrome command that screenshots the banner in the page's export mode.

    Args:
        chrome: The Chrome/Chromium executable.
        html_path: The banner page.
        png_path: Where Chrome writes the screenshot.
        scale: Device pixel ratio; the PNG is ``scale`` times 1280 × 640.
        background: One of :data:`BACKGROUNDS`.
        ink: One of :data:`INKS`.
        user_data_dir: A throwaway profile directory, so saved browser edits never leak in.

    Returns:
        The argv list.

    Raises:
        BannerError: On an unknown scale, background or ink.
    """
    if scale not in SCALES:
        raise BannerError(f"scale must be one of {', '.join(map(str, SCALES))}, got {scale}")
    if background not in BACKGROUNDS:
        raise BannerError(f"background must be one of {', '.join(BACKGROUNDS)}, got {background!r}")
    if ink not in INKS:
        raise BannerError(f"ink must be one of {', '.join(INKS)}, got {ink!r}")
    width, height = BANNER_SIZE
    argv = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run"]
    argv += ["--no-default-browser-check", "--default-background-color=00000000"]
    if user_data_dir is not None:
        argv.append(f"--user-data-dir={user_data_dir}")
    if getattr(os, "geteuid", lambda: 1)() == 0:
        argv.append("--no-sandbox")  # Chrome refuses to run as root with its sandbox (containers, CI)
    argv += [
        f"--window-size={width},{height}",
        f"--force-device-scale-factor={scale}",
        "--virtual-time-budget=15000",  # let web fonts load before the screenshot
        f"--screenshot={png_path}",
        html_path.resolve().as_uri() + f"?export&bg={background}&ink={ink}",
    ]
    return argv


def png_size(path: Path) -> tuple[int, int]:
    """Read a PNG's pixel size from its header.

    Args:
        path: The PNG file.

    Returns:
        ``(width, height)``.

    Raises:
        BannerError: If the file isn't a PNG.
    """
    head = path.read_bytes()[:24]
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise BannerError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def export_png(
    chrome: str,
    html_path: Path,
    png_path: Path,
    scale: int = DEFAULT_SCALE,
    background: str = "as-is",
    ink: str = "auto",
) -> None:
    """Screenshot the banner page to a PNG with headless Chrome, and check its size.

    Args:
        chrome: The Chrome/Chromium executable.
        html_path: The banner page.
        png_path: The PNG to write (parent folders are created).
        scale: 1, 2 or 4.
        background: One of :data:`BACKGROUNDS`.
        ink: One of :data:`INKS`.

    Raises:
        BannerError: If Chrome fails, times out, writes nothing, or writes the wrong size.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="callai-banner-chrome-") as profile:
        argv = chrome_command(chrome, html_path, png_path, scale, background, ink, Path(profile))
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=CHROME_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            raise BannerError(
                f"{chrome} timed out after {CHROME_TIMEOUT} s; try chrome-headless-shell "
                "(npx playwright install chromium-headless-shell) via --chrome"
            ) from None
    if proc.returncode != 0 or not png_path.exists():
        detail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise BannerError(f"Chrome failed (exit {proc.returncode}): {' | '.join(detail)}")
    want = (BANNER_SIZE[0] * scale, BANNER_SIZE[1] * scale)
    got = png_size(png_path)
    if got != want:
        raise BannerError(f"{png_path}: expected {want[0]}×{want[1]} pixels, got {got[0]}×{got[1]}")


def write_examples(
    chrome: str, config_path: Path, template_path: Path, root: Path, overrides: dict[str, Value], out_dir: Path
) -> list[Path]:
    """Render the banner once per install style to the example PNGs in :data:`EXAMPLES` (1x).

    Args:
        chrome: The Chrome/Chromium executable.
        config_path: The config file.
        template_path: The HTML template.
        root: The repository root, for ``"auto"`` values.
        overrides: Command-line overrides; ``install_style`` is replaced per example.
        out_dir: Where the PNGs go.

    Returns:
        The PNGs written. A failed build or export raises ``BannerError`` (e.g. more commands than
        option B has room for).
    """
    written = []
    with tempfile.TemporaryDirectory(prefix="callai-banner-examples-") as tmp:
        for style, name in EXAMPLES.items():
            page = Path(tmp) / f"callai-banner-option-{style}.html"
            page.write_text(build_banner(config_path, template_path, root, {**overrides, "install_style": style}))
            export_png(chrome, page, out_dir / name, scale=1)
            written.append(out_dir / name)
    return written


# ── Command line ────────────────────────────────────────────────────────────────


def _parse_set(item: str) -> tuple[str, Value]:
    """Parse one ``--set KEY=VALUE``; list keys take comma-separated values.

    Args:
        item: The ``KEY=VALUE`` text.

    Returns:
        The key and its value.

    Raises:
        BannerError: If there is no ``=``.
    """
    key, sep, value = item.partition("=")
    if not sep:
        raise BannerError(f"--set expects KEY=VALUE, got {item!r}")
    key = key.strip()
    if key in LIST_KEYS and (value != AUTO or key == "install_commands"):
        return key, [v.strip() for v in value.split(",") if v.strip()]
    return key, value


def main(argv: list[str] | None = None) -> int:
    """Run the banner builder.

    Args:
        argv: Arguments (default: ``sys.argv[1:]``).

    Returns:
        0 on success (or an up-to-date ``--check``), 1 if ``--check`` finds the output stale,
        2 on an error.
    """
    parser = argparse.ArgumentParser(description="Build the callai-cli banner HTML from config.yaml and the template.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="config file (default: %(default)s)")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="HTML template (default: %(default)s)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="page to write (default: %(default)s)")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help='repository for "auto" values')
    for fact in FACT_KEYS:
        if fact != "harnesses":
            parser.add_argument("--" + fact.replace("_", "-"), dest=fact, metavar="TEXT", help=f"override {fact}")
    parser.add_argument("--harnesses", metavar="A,B,...", help="override harnesses (comma-separated)")
    parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="override any config key (repeatable)"
    )
    parser.add_argument(
        "--install-style",
        choices=tuple(INSTALL_STYLES),
        help="box (option A) or chips (option B); overrides the config",
    )
    parser.add_argument("--check", action="store_true", help="don't write; exit 1 if the output is out of date")
    png = parser.add_argument_group("PNG export (headless Chrome/Chromium)")
    png.add_argument(
        "--png",
        type=Path,
        nargs="?",
        const=_PNG_DEFAULT,
        metavar="PATH",
        help="also write a PNG of the banner (PATH defaults to docs/assets/images/banner_<scale>x.png)",
    )
    png.add_argument(
        "--scale", type=int, choices=SCALES, default=DEFAULT_SCALE, help="PNG scale (default: %(default)s)"
    )
    png.add_argument("--background", choices=BACKGROUNDS, default="as-is", help="PNG background (default: %(default)s)")
    png.add_argument("--ink", choices=INKS, default="auto", help="text colour (default: %(default)s)")
    png.add_argument("--chrome", metavar="PATH", help="Chrome/Chromium executable (default: $CHROME, then PATH)")
    png.add_argument(
        "--examples",
        type=Path,
        nargs="?",
        const=DEFAULT_EXAMPLES_DIR,
        metavar="DIR",
        help="also write 1x example PNGs of both install styles: option_a_box.png, option_b_chip.png "
        "(DIR defaults to src/tools/banner/assets)",
    )
    ns = parser.parse_args(argv)
    if ns.check and (ns.png or ns.examples):
        print("create_banner: error: --check can't be combined with --png or --examples", file=sys.stderr)
        return 2
    if ns.png is _PNG_DEFAULT:
        ns.png = default_png(ns.scale)

    try:
        overrides = dict(_parse_set(item) for item in ns.set)
        for fact in FACT_KEYS:
            value = getattr(ns, fact)
            if value is not None:
                overrides[fact] = _parse_set(f"{fact}={value}")[1]
        if ns.install_style:
            overrides["install_style"] = ns.install_style
        page = build_banner(ns.config, ns.template, ns.repo_root, overrides)
    except BannerError as exc:
        print(f"create_banner: error: {exc}", file=sys.stderr)
        return 2

    current = ns.output.read_text(encoding="utf-8") if ns.output.exists() else None
    if ns.check:
        if current != page:
            print(f"create_banner: {ns.output} is out of date: run `make maint.banner`", file=sys.stderr)
            return 1
        print(f"{ns.output} is up to date")
        return 0
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_text(page, encoding="utf-8")
    print(f"wrote {ns.output}")
    if ns.png:
        try:
            export_png(find_chrome(ns.chrome), ns.output, ns.png, ns.scale, ns.background, ns.ink)
        except BannerError as exc:
            print(f"create_banner: error: {exc}", file=sys.stderr)
            return 2
        width, height = png_size(ns.png)
        print(f"wrote {ns.png} ({width}×{height}, {ns.scale}x, background {ns.background})")
    if ns.examples:
        try:
            for path in write_examples(
                find_chrome(ns.chrome), ns.config, ns.template, ns.repo_root, overrides, ns.examples
            ):
                print(f"wrote {path} (example, 1x)")
        except BannerError as exc:
            print(f"create_banner: error: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
