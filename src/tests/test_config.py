"""CA-12: config file (``config.toml``), ``CALLAI_*`` env defaults and model aliases (DESIGN §6)."""

import pytest

from callai import config as cfg
from callai.errors import UsageError

FULL = """
default_harness = "codex"
model = "fast"
timeout = 600

[harnesses.codex]
binary = "~/bin/codex"
model = "gpt-5-codex"
extra_args = ["--skip-git-repo-check"]

[aliases]
fast = { claude-code = "haiku", codex = "gpt-5-codex-mini" }
"""


def _write(tmp_path, text, name="config.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- where the file lives ------------------------------------------------------


def test_config_path_precedence(tmp_path):
    home = str(tmp_path / "home")
    assert cfg.config_path({"CALLAI_CONFIG": "/x/c.toml", "XDG_CONFIG_HOME": "/xdg"}, home) == ("/x/c.toml", True)
    assert cfg.config_path({"XDG_CONFIG_HOME": "/xdg"}, home) == ("/xdg/callai/config.toml", False)
    assert cfg.config_path({}, home) == (f"{home}/.config/callai/config.toml", False)


def test_missing_default_file_is_an_empty_config(tmp_path):
    assert cfg.load_config({"XDG_CONFIG_HOME": str(tmp_path)}) == cfg.Config()


def test_missing_explicit_file_is_an_error(tmp_path):
    with pytest.raises(UsageError, match="CALLAI_CONFIG.*nope.toml"):
        cfg.load_config({"CALLAI_CONFIG": str(tmp_path / "nope.toml")})


# --- parsing and validation ----------------------------------------------------


def test_full_config_parses(tmp_path):
    c = cfg.load_config({"CALLAI_CONFIG": str(_write(tmp_path, FULL))})
    assert (c.default_harness, c.model, c.timeout) == ("codex", "fast", 600)
    codex = c.harnesses["codex"]
    assert (codex.binary, codex.model, codex.extra_args) == ("~/bin/codex", "gpt-5-codex", ("--skip-git-repo-check",))
    assert c.aliases == {"fast": {"claude-code": "haiku", "codex": "gpt-5-codex-mini"}}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("default_harness = ", "invalid TOML"),
        ("default_tool = 'codex'", "unknown key 'default_tool'"),
        ("default_harness = 'nope'", "default_harness: unknown harness 'nope'"),
        ("timeout = 0", "timeout must be a positive number"),
        ("timeout = true", "timeout must be a positive number"),
        ("model = 3", "model must be a string"),
        ("[harnesses.nope]\nmodel = 'x'", r"\[harnesses\.nope\]: unknown harness"),
        ("[harnesses.codex]\nbinaryy = 'x'", r"\[harnesses\.codex\]: unknown key 'binaryy'"),
        ("[harnesses.codex]\nextra_args = '--x'", r"extra_args must be a list of strings"),
        ("[harnesses.codex]\nbinary = ''", r"binary must be a non-empty string"),
        ("[aliases]\nfast = 'haiku'", r"\[aliases\] fast must map harness names to models"),
        ("[aliases]\nfast = { nope = 'x' }", r"\[aliases\] fast: unknown harness 'nope'"),
        ("harnesses = 3", "harnesses must be a table"),
        ("[harnesses]\ncodex = 3", r"\[harnesses\.codex\] must be a table"),
    ],
)
def test_invalid_config_is_a_usage_error_naming_the_file(tmp_path, text, match):
    path = _write(tmp_path, text)
    with pytest.raises(UsageError, match=match) as exc:
        cfg.load_config({"CALLAI_CONFIG": str(path)})
    assert str(path) in str(exc.value)


def test_unreadable_config_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError, match="cannot read"):
        cfg.load_config({"CALLAI_CONFIG": str(tmp_path)})  # a directory


# --- model aliases -------------------------------------------------------------


ALIASES = {"fast": {"claude-code": "haiku", "codex": "gpt-5-codex-mini"}}


def test_alias_resolves_per_harness():
    c = cfg.Config(aliases=ALIASES)
    assert cfg.resolve_model(c, "claude-code", "fast") == "haiku"
    assert cfg.resolve_model(c, "codex", "fast") == "gpt-5-codex-mini"


def test_non_alias_model_passes_through_verbatim():
    assert cfg.resolve_model(cfg.Config(aliases=ALIASES), "codex", "o3") == "o3"
    assert cfg.resolve_model(cfg.Config(), "codex", None) is None


def test_alias_without_entry_for_this_harness_is_an_error():
    # Passing the alias name itself on to pi would be a silent wrong model; refuse instead.
    with pytest.raises(UsageError, match="model alias 'fast' has no entry for pi"):
        cfg.resolve_model(cfg.Config(aliases=ALIASES), "pi", "fast")
