"""CA-10: hermes build_argv()/parse() edge cases beyond the recorded conformance fixtures."""

from callai.adapters import get_adapter
from callai.request import Request
from callai.result import Completed

ADAPTER = get_adapter("hermes")


def _parse(stdout, exit_code=0, stderr="\nsession_id: 20260101_000000_000009\n"):
    req = Request(harness_name="hermes", prompt="p", model="m")
    done = Completed(argv=ADAPTER.build_argv(req), exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=5)
    return ADAPTER.parse(done, req)


def test_metadata():
    assert (ADAPTER.name, ADAPTER.binary) == ("hermes", "hermes")
    assert ADAPTER.install_url.startswith("https://")


def test_display_lines_dropped_answer_kept_multiline():
    r = _parse("\x1b[2m  ⚠ warning\x1b[0m\r\n\r\n  ┊ review diff\r\nline one\n\nline two\n")
    assert (r.text, r.is_error, r.session_id) == ("line one\n\nline two", False, "20260101_000000_000009")


def test_no_session_line_gives_none():
    assert _parse("ok\n", stderr="").session_id is None


def test_empty_answer_is_error_with_reason_from_stderr():
    r = _parse("  ⚠ x\r\n", stderr="Error: boom\n\nsession_id: 20260101_000000_000009\n")
    assert (r.is_error, r.text) == (True, "Error: boom")


def test_empty_answer_and_stderr_falls_back_to_raw_stdout():
    r = _parse("", stderr="")
    assert (r.is_error, r.text) == (True, "")


def test_nonzero_exit_is_error():
    r = _parse("HTTP 500: boom\n", exit_code=1)
    assert (r.is_error, r.text, r.model) == (True, "HTTP 500: boom", "m")


def test_system_prompt_goes_in_env_not_argv():
    # CA-21: hermes reads an extra system prompt only from HERMES_EPHEMERAL_SYSTEM_PROMPT (or its config).
    req = Request(harness_name="hermes", prompt="hi", system_prompt="Be terse.")
    assert ADAPTER.build_env(req) == {"HERMES_EPHEMERAL_SYSTEM_PROMPT": "Be terse."}
    assert not any("Be terse." in a for a in ADAPTER.build_argv(req))


def test_no_system_prompt_sets_no_env():
    # An inherited HERMES_EPHEMERAL_SYSTEM_PROMPT is then left alone.
    assert ADAPTER.build_env(Request(harness_name="hermes", prompt="hi")) == {}
