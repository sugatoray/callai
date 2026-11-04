"""Tests for src/tools/banner/create_banner.py (the callai-cli banner builder)."""

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

BANNER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BANNER_DIR.parents[2]
sys.path.insert(0, str(BANNER_DIR))

import create_banner as cb  # noqa: E402

CONFIG = BANNER_DIR / "config.yaml"
TEMPLATE = BANNER_DIR / "assets" / "callai-banner-template.html"
OUTPUT = BANNER_DIR / "callai-banner.html"


def real_harness_names():
    tree = ast.parse((REPO_ROOT / "src/callai/adapters/__init__.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "HARNESS_NAMES":
            return list(ast.literal_eval(node.value))
    raise AssertionError("HARNESS_NAMES not found")


def make_repo(tmp_path, version="9.9.9", harnesses=("alpha", "beta", "gamma")):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo-cli"\n'
        f'version = "{version}"\n'
        'requires-python = ">=3.12"\n'
        'license = "MIT"\n'
        "[project.urls]\n"
        'Source = "https://example.com/acme/demo"\n'
    )
    adapters = tmp_path / "src" / "callai" / "adapters"
    adapters.mkdir(parents=True, exist_ok=True)
    names = ", ".join(f'"{h}"' for h in harnesses)
    (adapters / "__init__.py").write_text(f"HARNESS_NAMES: tuple[str, ...] = ({names})\n")
    return tmp_path


def config_text(**changes):
    """The shipped config with some top-level scalar values replaced."""
    text = CONFIG.read_text()
    for key, value in changes.items():
        text, n = re.subn(rf'^{key}: ".*"$', f'{key}: "{value}"', text, flags=re.M)
        assert n == 1, key
    return text


# ── YAML subset parser ──────────────────────────────────────────────────────────


def test_parse_config_scalars_lists_and_comments():
    text = (
        "# a comment\n"
        "\n"
        'name: "callai"  # trailing comment\n'
        'quote: "say \\"hi\\" # not a comment"\n'
        "items:\n"
        '  - "a"\n'
        '  - "b, c"\n'
        "empty: []\n"
        'unicode: "≥ 3.11 — ok"\n'
    )
    assert cb.parse_config(text) == {
        "name": "callai",
        "quote": 'say "hi" # not a comment',
        "items": ["a", "b, c"],
        "empty": [],
        "unicode": "≥ 3.11 — ok",
    }


@pytest.mark.parametrize(
    "text, message",
    [
        ("name: callai\n", "double-quoted"),
        ("name: 'callai'\n", "double-quoted"),
        ("items:\n  - a\n", "double-quoted"),
        ('name: "a"\nname: "b"\n', "duplicate"),
        ('  name: "a"\n', "line 1"),
        ('name: "a" extra\n', "after the value"),
        ('items:\n  - "a"\nother:\n', "other"),
        ('- "orphan"\n', "line 1"),
    ],
)
def test_parse_config_rejects_non_conforming_yaml(text, message):
    with pytest.raises(cb.BannerError, match=message):
        cb.parse_config(text)


def test_shipped_config_is_all_double_quoted_and_valid_yaml():
    data = cb.parse_config(CONFIG.read_text())
    assert set(data) == set(cb.CONFIG_KEYS)
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(CONFIG.read_text()) == data  # the subset parser agrees with a real YAML parser


# ── Facts read from the repository ──────────────────────────────────────────────


def test_repo_facts_from_a_repository(tmp_path):
    facts = cb.repo_facts(make_repo(tmp_path))
    assert facts == {
        "package_name": "demo-cli",
        "package_version": "9.9.9",
        "python_requires": "≥ 3.12",
        "license": "MIT",
        "repo_url": "example.com/acme/demo",
        "harnesses": ["alpha", "beta", "gamma"],
    }


def test_repo_facts_match_this_repository():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    facts = cb.repo_facts(REPO_ROOT)
    assert facts["package_name"] == project["name"]
    assert facts["package_version"] == project["version"]
    assert facts["harnesses"] == real_harness_names()


def test_repo_facts_missing_pyproject_is_an_error(tmp_path):
    with pytest.raises(cb.BannerError, match="pyproject.toml"):
        cb.repo_facts(tmp_path)


@pytest.mark.parametrize(
    "spec, shown",
    [(">=3.11", "≥ 3.11"), ("<=3.14", "≤ 3.14"), (">=3.11,<4", "≥ 3.11, < 4"), ("==3.12", "3.12")],
)
def test_python_requires_display(spec, shown):
    assert cb.display_python_requires(spec) == shown


# ── Building ────────────────────────────────────────────────────────────────────


def build(tmp_path, text=None, **kwargs):
    repo = make_repo(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(text if text is not None else CONFIG.read_text())
    kwargs.setdefault("fanout_harnesses", None)
    overrides = {k: v for k, v in kwargs.items() if v is not None}
    # The shipped config names real harnesses in the terminal demo; point them at the fake repo's.
    overrides.setdefault("fanout_harnesses", ["alpha", "beta"])
    overrides.setdefault("fanout_durations", ["1.0s", "2.0s"])
    overrides.setdefault("pipe_harness", "gamma")
    return cb.build_banner(cfg, TEMPLATE, repo, overrides)


def test_build_uses_repository_facts(tmp_path):
    html = build(tmp_path)
    assert "v9.9.9" in html
    assert "Python ≥ 3.12" in html
    assert ">MIT<" in html
    assert "example.com/acme/demo" in html
    assert "pip install demo-cli" in html  # {package_name} interpolation
    for name in ("alpha", "beta", "gamma"):
        assert f'<span class="pill">{name}</span>' in html
    assert "{{" not in html


def test_package_version_override_wins_and_changes_store_key(tmp_path):
    a = build(tmp_path)
    b = build(tmp_path, package_version="1.2.3")
    assert "v1.2.3" in b and "v9.9.9" not in b
    key = re.compile(r"const STORE_KEY = '(callai-banner:[0-9a-f]{12})'")
    assert key.search(a).group(1) != key.search(b).group(1)


def test_explicit_config_value_beats_auto(tmp_path):
    html = build(tmp_path, config_text(license="BSD-3-Clause"))
    assert ">BSD-3-Clause<" in html and ">MIT<" not in html


def test_text_values_are_html_escaped(tmp_path):
    html = build(tmp_path, tagline="<script>alert(1)</script> & co")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in html


def test_terminal_fanout_lines_are_aligned(tmp_path):
    html = build(
        tmp_path,
        fanout_harnesses=["a", "longer-name"],
        fanout_durations=["1s", "2s"],
        harnesses=["a", "longer-name", "gamma"],
    )
    rows = [re.sub(r"<[^>]+>", "", line) for line in html.splitlines() if 'class="h"' in line]
    assert len(rows) == 2
    assert rows[0].index("✓") == rows[1].index("✓")


def test_unknown_and_missing_config_keys_are_errors(tmp_path):
    with pytest.raises(cb.BannerError, match="unknown config key 'colour'"):
        build(tmp_path, CONFIG.read_text() + 'colour: "red"\n')
    without_tagline = re.sub(r'^tagline: ".*"\n', "", CONFIG.read_text(), flags=re.M)
    with pytest.raises(cb.BannerError, match="missing config key 'tagline'"):
        build(tmp_path, without_tagline)


def test_unknown_override_key_is_an_error(tmp_path):
    with pytest.raises(cb.BannerError, match="unknown config key 'nope'"):
        build(tmp_path, nope="x")


def test_demo_harnesses_must_exist(tmp_path):
    with pytest.raises(cb.BannerError, match="pipe_harness 'zzz'"):
        build(tmp_path, pipe_harness="zzz")
    with pytest.raises(cb.BannerError, match="fanout_harnesses"):
        build(tmp_path, fanout_harnesses=["alpha", "zzz"])


def test_fanout_harnesses_must_not_be_empty(tmp_path):
    with pytest.raises(cb.BannerError, match="at least one"):
        build(tmp_path, fanout_harnesses=[], fanout_durations=[])


def test_fanout_durations_must_match_harnesses(tmp_path):
    with pytest.raises(cb.BannerError, match="fanout_durations"):
        build(tmp_path, fanout_durations=["1s"])


def test_list_and_scalar_types_are_checked(tmp_path):
    with pytest.raises(cb.BannerError, match="tagline must be a string"):
        build(tmp_path, tagline=["a"])
    with pytest.raises(cb.BannerError, match="fanout_harnesses must be a list"):
        build(tmp_path, fanout_harnesses="alpha")


def test_render_rejects_unknown_placeholder():
    with pytest.raises(cb.BannerError, match="nope"):
        cb.render("<p>{{ nope }}</p>", {})
    assert cb.render("<p>{{ a }}|{{a}}</p>", {"a": "x"}) == "<p>x|x</p>"


# ── CLI ─────────────────────────────────────────────────────────────────────────


def run_main(tmp_path, *args):
    repo = make_repo(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(config_text(pipe_harness="gamma"))
    out = tmp_path / "out.html"
    base = ["--config", str(cfg), "--template", str(TEMPLATE), "--output", str(out), "--repo-root", str(repo)]
    base += ["--set", "fanout_harnesses=alpha,beta", "--set", "fanout_durations=1s,2s"]
    return cb.main([*base, *args]), out


def test_main_writes_output_with_cli_overrides(tmp_path, capsys):
    code, out = run_main(tmp_path, "--package-version", "4.5.6", "--set", "tagline=Hello there")
    assert code == 0
    html = out.read_text()
    assert "v4.5.6" in html and "Hello there" in html
    assert str(out) in capsys.readouterr().out


def test_main_check_reports_stale_and_fresh(tmp_path, capsys):
    code, out = run_main(tmp_path, "--check")
    assert code == 1 and not out.exists()
    assert "out of date" in capsys.readouterr().err
    run_main(tmp_path)
    code, _ = run_main(tmp_path, "--check")
    assert code == 0


def test_main_reports_errors_with_exit_2(tmp_path, capsys):
    code, _ = run_main(tmp_path, "--set", "pipe_harness=zzz")
    assert code == 2
    assert "error:" in capsys.readouterr().err
    code, _ = run_main(tmp_path, "--set", "no-equals-sign")
    assert code == 2


def test_committed_banner_is_up_to_date():
    """`make maint.banner` must be re-run after changing the version, harnesses, config or template."""
    expected = cb.build_banner(CONFIG, TEMPLATE, REPO_ROOT, {})
    assert OUTPUT.read_text() == expected, "src/tools/banner/callai-banner.html is stale: run `make maint.banner`"


# ── PNG export (headless Chrome) ────────────────────────────────────────────────

FAKE_CHROME = """#!{python}
import struct, sys, zlib
args = sys.argv[1:]
out = next(a.split("=", 1)[1] for a in args if a.startswith("--screenshot="))
scale = float(next(a.split("=", 1)[1] for a in args if a.startswith("--force-device-scale-factor=")))
w, h = (int(v) for v in next(a.split("=", 1)[1] for a in args if a.startswith("--window-size=")).split(","))
w, h = int(w * scale) + {extra}, int(h * scale)
ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
open(out, "wb").write(b"\\x89PNG\\r\\n\\x1a\\n" + chunk)
with open(out + ".argv", "w") as f:
    f.write("\\n".join(args))
# keep a copy of the page that was screenshotted (it may be a temporary file)
from urllib.parse import unquote, urlparse
if args[-1].startswith("file:"):
    page = unquote(urlparse(args[-1]).path)
    open(out + ".html", "w").write(open(page).read())
"""


def fake_chrome(tmp_path, extra=0):
    path = tmp_path / "fake-chrome"
    path.write_text(FAKE_CHROME.format(python=sys.executable, extra=extra))
    path.chmod(0o755)
    return path


def test_chrome_command_defaults_to_2x_as_is(tmp_path):
    html_path = tmp_path / "b.html"
    argv = cb.chrome_command("chrome", html_path, tmp_path / "b.png")
    assert argv[0] == "chrome"
    assert "--force-device-scale-factor=2" in argv
    assert "--window-size=1280,640" in argv
    assert f"--screenshot={tmp_path / 'b.png'}" in argv
    assert argv[-1] == html_path.resolve().as_uri() + "?export&bg=as-is&ink=auto"


def test_chrome_command_background_ink_and_scale(tmp_path):
    argv = cb.chrome_command(
        "chrome", tmp_path / "b.html", tmp_path / "b.png", scale=4, background="transparent", ink="dark"
    )
    assert "--force-device-scale-factor=4" in argv
    assert "--default-background-color=00000000" in argv
    assert argv[-1].endswith("?export&bg=transparent&ink=dark")
    with pytest.raises(cb.BannerError, match="background"):
        cb.chrome_command("chrome", tmp_path / "b.html", tmp_path / "b.png", background="pink")


def test_find_chrome(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROME_BIN", "/elsewhere/chrome")  # other tools' variable: ignored
    exe = fake_chrome(tmp_path)
    assert cb.find_chrome(str(exe)) == str(exe)
    with pytest.raises(cb.BannerError, match="not found"):
        cb.find_chrome(str(tmp_path / "missing"))
    monkeypatch.setenv("CHROME", str(exe))
    assert cb.find_chrome(None) == str(exe)
    monkeypatch.delenv("CHROME")
    monkeypatch.setattr(cb.shutil, "which", lambda name: None)
    monkeypatch.setattr(cb, "CHROME_SEARCH", ())
    with pytest.raises(cb.BannerError, match="--chrome"):
        cb.find_chrome(None)


def test_png_size(tmp_path):
    exe = fake_chrome(tmp_path)
    out = tmp_path / "x.png"
    import subprocess

    subprocess.run([str(exe), f"--screenshot={out}", "--force-device-scale-factor=2", "--window-size=10,5"], check=True)
    assert cb.png_size(out) == (20, 10)
    (tmp_path / "bad.png").write_bytes(b"nope")
    with pytest.raises(cb.BannerError, match="not a PNG"):
        cb.png_size(tmp_path / "bad.png")


def test_main_png_writes_html_and_2x_png_by_default(tmp_path):
    exe = fake_chrome(tmp_path)
    png = tmp_path / "img" / "banner.png"
    code, out = run_main(tmp_path, "--png", str(png), "--chrome", str(exe))
    assert code == 0 and out.exists()
    assert cb.png_size(png) == (2560, 1280)
    argv = (png.parent / "banner.png.argv").read_text().splitlines()
    assert argv[-1] == out.resolve().as_uri() + "?export&bg=as-is&ink=auto"


def test_main_png_scale_option(tmp_path):
    exe = fake_chrome(tmp_path)
    png = tmp_path / "banner.png"
    code, _ = run_main(tmp_path, "--png", str(png), "--chrome", str(exe), "--scale", "4", "--background", "white")
    assert code == 0
    assert cb.png_size(png) == (5120, 2560)


def test_main_png_wrong_size_is_an_error(tmp_path, capsys):
    exe = fake_chrome(tmp_path, extra=3)
    code, _ = run_main(tmp_path, "--png", str(tmp_path / "banner.png"), "--chrome", str(exe))
    assert code == 2
    assert "2563×1280" in capsys.readouterr().err


def test_main_png_and_check_conflict(tmp_path):
    code, _ = run_main(tmp_path, "--png", str(tmp_path / "b.png"), "--check")
    assert code == 2


def test_default_png_path_names_the_scale():
    images = REPO_ROOT / "docs" / "assets" / "images"
    assert images / "banner_2x.png" == cb.DEFAULT_PNG
    assert cb.default_png(4) == images / "banner_4x.png"


def test_main_png_without_path_uses_scale_in_default_name(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "DEFAULT_PNG_DIR", tmp_path / "images")
    exe = fake_chrome(tmp_path)
    code, _ = run_main(tmp_path, "--chrome", str(exe), "--scale", "4", "--png")
    assert code == 0
    assert cb.png_size(tmp_path / "images" / "banner_4x.png") == (5120, 2560)
    code, _ = run_main(tmp_path, "--chrome", str(exe), "--png")
    assert code == 0
    assert cb.png_size(tmp_path / "images" / "banner_2x.png") == (2560, 1280)


def test_find_chrome_searches_names_then_globs(tmp_path, monkeypatch):
    shell = tmp_path / "pw" / "chromium_headless_shell-1" / "chrome-headless-shell"
    shell.parent.mkdir(parents=True)
    shell.write_text("")
    monkeypatch.delenv("CHROME", raising=False)
    monkeypatch.setattr(cb.shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)
    monkeypatch.setattr(cb, "CHROME_SEARCH", ("nope", str(tmp_path / "pw" / "*" / "chrome-headless-shell"), "chromium"))
    assert cb.find_chrome(None) == str(shell)
    monkeypatch.setattr(cb, "CHROME_SEARCH", ("nope", str(tmp_path / "none" / "*"), "chromium"))
    assert cb.find_chrome(None) == "/usr/bin/chromium"


def test_real_chrome_renders_banner_at_2x(tmp_path):
    """Only with chrome-headless-shell: full Chrome's --screenshot can hang in containers and CI."""
    try:
        chrome = cb.find_chrome(None)
    except cb.BannerError:
        pytest.skip("no Chrome/Chromium installed")
    if "headless-shell" not in Path(chrome).name:
        pytest.skip(f"{chrome} is not chrome-headless-shell")
    png = tmp_path / "banner.png"
    cb.export_png(chrome, OUTPUT, png)
    assert cb.png_size(png) == (2560, 1280)


# ── Install commands: option A (box) and option B (chips) ───────────────────────

EXAMPLES_DIR = BANNER_DIR / "assets"


def markup(html):
    """The banner's own markup (between its banner:html markers), without the editor's toolbar and script."""
    return html[html.index("banner:html:start") : html.index("banner:html:end")]


def test_install_default_is_one_box_with_both_commands(tmp_path):
    html = build(tmp_path)
    block = html[html.index('<div class="install install-box">') :]
    block = block[: block.index("</div>\n", block.index("uv tool install")) + 6]
    assert block.count('<div class="line"><span class="dollar">$</span>') == 2
    assert "<span data-edit>pip install demo-cli</span>" in block  # {package_name} filled in
    assert "<span data-edit>uv tool install demo-cli</span>" in block
    assert "install-chips" not in markup(html)


def test_install_style_chips_stacks_separate_chips(tmp_path):
    html = build(tmp_path, install_style="chips")
    body = markup(html)
    assert '<div class="install-chips">' in body and "install-box" not in body
    assert body.count('<div class="install"><span class="dollar">$</span><span data-edit>') == 2


def test_install_commands_override_and_limits(tmp_path):
    html = build(tmp_path, install_commands=["pipx install {package_name}"])
    assert "pipx install demo-cli" in html and "uv tool install" not in markup(html)
    with pytest.raises(cb.BannerError, match="install_style must be one of box, chips"):
        build(tmp_path, install_style="grid")
    with pytest.raises(cb.BannerError, match="install_commands needs at least one"):
        build(tmp_path, install_commands=[])
    build(tmp_path, install_commands=["a", "b", "c"])  # box fits three
    with pytest.raises(cb.BannerError, match="at most 3 install_commands"):
        build(tmp_path, install_commands=["a", "b", "c", "d"])
    with pytest.raises(cb.BannerError, match="at most 2 install_commands"):
        build(tmp_path, install_style="chips", install_commands=["a", "b", "c"])


def test_old_install_command_key_names_its_replacement(tmp_path):
    text = CONFIG.read_text().replace("install_commands:\n", 'install_command: "pip install x"\ninstall_commands:\n')
    with pytest.raises(cb.BannerError, match="install_command was replaced by install_commands"):
        build(tmp_path, text)


def test_main_install_style_flag(tmp_path):
    code, out = run_main(tmp_path, "--install-style", "chips")
    assert code == 0
    assert '<div class="install-chips">' in markup(out.read_text())


def test_main_examples_render_both_options(tmp_path):
    exe = fake_chrome(tmp_path)
    examples = tmp_path / "examples"
    code, out = run_main(tmp_path, "--examples", str(examples), "--chrome", str(exe))
    assert code == 0
    box, chips = examples / "option_a_box.png", examples / "option_b_chip.png"
    assert cb.png_size(box) == cb.png_size(chips) == (1280, 640)  # 1x
    assert 'class="install install-box"' in (examples / "option_a_box.png.html").read_text()
    assert 'class="install-chips"' in (examples / "option_b_chip.png.html").read_text()
    assert 'class="install install-box"' in out.read_text()  # the main page keeps the configured style
    assert not list(tmp_path.glob("**/callai-banner-option-*.html"))  # temporary pages are cleaned up


def test_examples_and_check_conflict(tmp_path):
    code, _ = run_main(tmp_path, "--examples", str(tmp_path), "--check")
    assert code == 2


def test_default_examples_dir_and_names():
    assert cb.DEFAULT_EXAMPLES_DIR == EXAMPLES_DIR
    assert cb.EXAMPLES == {"box": "option_a_box.png", "chips": "option_b_chip.png"}


def test_committed_examples_exist_and_readme_shows_them():
    readme = (BANNER_DIR / "README.md").read_text()
    for name in cb.EXAMPLES.values():
        assert cb.png_size(EXAMPLES_DIR / name) == (1280, 640)
        assert f"](assets/{name})" in readme


def test_editor_toolbar_has_an_install_switch(tmp_path):
    html = build(tmp_path)
    seg = html[html.index('<div class="seg" id="installSeg">') :]
    seg = seg[: seg.index("</div>")]
    assert 'data-install="box"' in seg and 'data-install="chips"' in seg
    # the page's own limit for option B matches the builder's
    assert f"const MAX_CHIPS = {cb.INSTALL_STYLES['chips']};" in html
