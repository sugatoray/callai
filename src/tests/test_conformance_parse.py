"""Runs every conformance/parse case against the registered adapter's parse()."""

import pytest

from callai.adapters import get_adapter
from callai.request import Request
from callai.result import Completed
from tests import conformance as cf

CASES = cf.load_parse_cases()


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_parse_case(case):
    adapter = get_adapter(case.harness_name)
    req = Request(harness_name=case.harness_name, **case.request)
    done = Completed(argv=adapter.build_argv(req), exit_code=case.exit_code, stdout=case.stdout, stderr=case.stderr)
    result = adapter.parse(done, req).to_dict()
    assert {k: result[k] for k in case.expected} == case.expected


STREAM_CASES = [c for c in CASES if c.expected_events is not None]


@pytest.mark.parametrize("case", STREAM_CASES, ids=[c.id for c in STREAM_CASES])
def test_stream_events_case(case):
    # Every stdout line goes through stream_events() in order, sharing one state dict per run.
    adapter = get_adapter(case.harness_name)
    state = {}
    events = [e for line in case.stdout.splitlines(keepends=True) for e in adapter.stream_events(line, state)]
    assert events == case.expected_events
