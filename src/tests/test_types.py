"""CA-2: Request / Result / Completed data types and their agreement with the conformance spec."""

import dataclasses

import pytest

from callai.errors import CallaiError, UsageError
from callai.request import OUTPUT_FORMATS, PERMISSIONS, Request
from callai.result import Completed, Result
from tests import conformance as cf

# --- errors -----------------------------------------------------------------


def test_usage_error_maps_to_exit_2():
    err = UsageError("bad flag")
    assert isinstance(err, CallaiError)
    assert err.exit_code == 2
    assert str(err) == "bad flag"


# --- Request ----------------------------------------------------------------


def test_request_defaults_match_conformance_spec():
    req = Request(harness_name="claude-code", prompt="hi")
    fields = {f.name: getattr(req, f.name) for f in dataclasses.fields(req) if f.name != "harness_name"}
    expected = {**cf.REQUEST_DEFAULTS, "prompt": "hi", "extra_args": ()}
    assert fields == expected


def test_request_enums_match_conformance_spec():
    assert set(OUTPUT_FORMATS) == cf.OUTPUT_FORMATS
    assert set(PERMISSIONS) == cf.PERMISSIONS


def test_request_is_frozen_and_extra_args_normalised_to_tuple():
    req = Request(harness_name="claude-code", prompt="hi", extra_args=["--a", "b"])
    assert req.extra_args == ("--a", "b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.prompt = "other"


def test_request_accepts_every_conformance_request():
    for case in cf.load_argv_cases():
        req = Request(harness_name=case.harness_name, **case.request)
        assert req.prompt == case.request["prompt"]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"output_format": "xml"}, "output format"),
        ({"permission": "root"}, "permission"),
        ({"prompt": 3}, "prompt"),
        ({"timeout": 0}, "timeout"),
        ({"timeout": -1.5}, "timeout"),
        ({"extra_args": ["ok", 1]}, "extra_args"),
        ({"extra_args": "--flag"}, "extra_args"),
        ({"resume": ""}, "resume: empty session id"),
        ({"resume": "-x"}, "resume: a session id can't start with '-'"),
        ({"resume": 3}, "resume"),
        ({"resume": "s1", "continue_session": True}, "--resume or --continue, not both"),
    ],
)
def test_request_validation(kwargs, match):
    with pytest.raises(UsageError, match=match):
        Request(**{"harness_name": "claude-code", "prompt": "hi", **kwargs})


def test_request_timeout_positive_ok():
    assert Request(harness_name="claude-code", prompt="hi", timeout=0.5).timeout == 0.5


# --- Completed --------------------------------------------------------------


def test_completed_fields():
    c = Completed(argv=["claude", "-p"], exit_code=0, stdout="out", stderr="err", duration_ms=12)
    assert (c.argv, c.exit_code, c.stdout, c.stderr, c.duration_ms) == (["claude", "-p"], 0, "out", "err", 12)


# --- Result -----------------------------------------------------------------

RESULT_JSON_KEYS = [
    "harness_name",
    "model",
    "text",
    "exit_code",
    "is_error",
    "duration_ms",
    "session_id",
    "usage",
    "cost_usd",
    "argv",
]


def test_result_to_dict_is_design_section_5_schema():
    r = Result(harness_name="claude-code", text="pong", exit_code=0, is_error=False)
    d = r.to_dict()
    assert list(d) == RESULT_JSON_KEYS  # stable key order for -o json
    assert d == {
        "harness_name": "claude-code",
        "model": None,
        "text": "pong",
        "exit_code": 0,
        "is_error": False,
        "duration_ms": None,
        "session_id": None,
        "usage": None,
        "cost_usd": None,
        "argv": [],
    }


def test_result_to_dict_excludes_raw_streams_but_keeps_them_on_the_object():
    r = Result(harness_name="t", text="x", exit_code=1, is_error=True, raw_stdout="RAW", raw_stderr="ERR")
    assert "raw_stdout" not in r.to_dict() and "raw_stderr" not in r.to_dict()
    assert (r.raw_stdout, r.raw_stderr) == ("RAW", "ERR")


def test_result_full_round_trip():
    r = Result(
        harness_name="claude-code",
        model="claude-haiku-5-5",
        text="pong",
        exit_code=0,
        is_error=False,
        duration_ms=3186,
        session_id="00000000-0000-4000-8000-000000000001",
        usage={"input_tokens": 10, "output_tokens": 2},
        cost_usd=0.0035,
        argv=("claude", "-p", "--", "x"),
    )
    d = r.to_dict()
    assert d["usage"] == {"input_tokens": 10, "output_tokens": 2}
    assert d["argv"] == ["claude", "-p", "--", "x"]
    d["usage"]["input_tokens"] = 0  # to_dict returns copies, not shared state
    assert r.usage["input_tokens"] == 10


def test_conformance_parse_keys_are_result_keys():
    assert cf.RESULT_KEYS.issubset(RESULT_JSON_KEYS)


def test_result_with_updates():
    r = Result(harness_name="t", text="x", exit_code=0, is_error=False)
    r2 = r.with_updates(duration_ms=5, argv=["a"])
    assert (r2.duration_ms, r2.argv) == (5, ("a",))
    assert r.duration_ms is None
