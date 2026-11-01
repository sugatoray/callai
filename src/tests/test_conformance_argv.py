"""Runs every conformance/argv case against the registered adapter's build_argv()."""

import pytest

from callai.adapters import get_adapter
from callai.errors import UsageError
from callai.request import Request
from tests import conformance as cf

CASES = cf.load_argv_cases()


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_argv_case(case):
    adapter = get_adapter(case.harness_name)
    req = Request(harness_name=case.harness_name, **case.request)
    if case.expected_error is not None:
        with pytest.raises(UsageError, match=case.expected_error["message_contains"]):
            adapter.build_argv(req)
    else:
        assert adapter.build_argv(req) == case.expected_argv
        assert adapter.build_env(req) == case.expected_env


def test_claude_code_adapter_metadata():
    adapter = get_adapter("claude-code")
    assert adapter.name == "claude-code"
    assert adapter.binary == "claude"
    assert adapter.install_url.startswith("https://")
