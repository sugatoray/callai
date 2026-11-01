"""CA-2: Adapter base class and tool registry."""

import pytest

from callai import adapters
from callai.adapters import HARNESS_NAMES, Adapter, get_adapter, register
from callai.errors import UsageError
from callai.request import Request
from callai.result import Completed, Result


class EchoAdapter(Adapter):
    name = "echo-tool"
    binary = "echo"
    install_url = "https://example.invalid/echo"

    def build_argv(self, req):
        return [self.binary, *req.extra_args, "--", req.prompt]

    def parse(self, completed, req):
        return self.text_result(completed, req)


@pytest.fixture
def registry(monkeypatch):
    """Isolated registry with the echo tool allowed."""
    monkeypatch.setattr(adapters, "REGISTRY", {})
    monkeypatch.setattr(adapters, "HARNESS_NAMES", (*HARNESS_NAMES, "echo-tool"))
    return adapters


def test_supported_tools_match_design():
    assert HARNESS_NAMES == ("claude-code", "codex", "opencode", "pi", "hermes", "grok")


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        Adapter()


def test_register_and_get(registry):
    adapter = EchoAdapter()
    assert register(adapter) is adapter
    assert get_adapter("echo-tool") is adapter


def test_register_rejects_unknown_tool_name(registry):
    class Rogue(EchoAdapter):
        name = "rogue"

    with pytest.raises(ValueError, match="rogue"):
        register(Rogue())


def test_register_rejects_duplicates(registry):
    register(EchoAdapter())
    with pytest.raises(ValueError, match="already registered"):
        register(EchoAdapter())


def test_get_unknown_tool_is_usage_error_listing_choices(registry):
    with pytest.raises(UsageError, match=r"unknown harness 'nope'.*claude-code"):
        get_adapter("nope")


def test_get_known_but_unimplemented_tool_is_usage_error(registry):
    with pytest.raises(UsageError, match=r"'codex' is not implemented yet"):
        get_adapter("codex")


def test_registered_adapters_are_consistent():
    # Real adapters (added from CA-5 on) must use a supported tool name and declare a binary.
    for name, adapter in adapters.REGISTRY.items():
        assert name == adapter.name and name in HARNESS_NAMES
        assert adapter.binary and adapter.install_url.startswith("https://")


def test_build_env_defaults_to_nothing():
    # CA-21: adapters set harness env vars only when they need to.
    assert EchoAdapter().build_env(Request(harness_name="echo-tool", prompt="hi")) == {}


def test_text_result_strips_ansi_and_whitespace():
    adapter = EchoAdapter()
    req = Request(harness_name="echo-tool", prompt="hi", model="m1")
    done = Completed(argv=["echo", "--", "hi"], exit_code=0, stdout="\x1b[1;32mhello\x1b[0m world\n\n", stderr="")
    result = adapter.parse(done, req)
    assert isinstance(result, Result)
    assert result.to_dict() == {
        "harness_name": "echo-tool",
        "model": "m1",
        "text": "hello world",
        "exit_code": 0,
        "is_error": False,
        "duration_ms": None,
        "session_id": None,
        "usage": None,
        "cost_usd": None,
        "argv": ["echo", "--", "hi"],
    }
    assert result.raw_stdout == done.stdout


def test_text_result_nonzero_exit_is_error():
    adapter = EchoAdapter()
    req = Request(harness_name="echo-tool", prompt="hi")
    done = Completed(argv=["echo"], exit_code=3, stdout="", stderr="boom", duration_ms=7)
    result = adapter.parse(done, req)
    assert (result.is_error, result.exit_code, result.duration_ms, result.raw_stderr) == (True, 3, 7, "boom")
