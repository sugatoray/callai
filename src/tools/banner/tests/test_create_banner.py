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
