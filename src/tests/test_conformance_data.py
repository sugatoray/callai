"""Checks that the shipped conformance suite is well-formed.

Adapter/CLI behaviour against these cases is tested in later tickets (CA-3..CA-5);
this file only guarantees the data itself loads and is internally consistent.
"""

from tests import conformance as cf

HARNESS_NAMES = {"claude-code", "codex", "opencode", "pi", "hermes", "grok"}


def test_all_cases_load():
    assert cf.load_argv_cases()
    assert cf.load_parse_cases()
    assert cf.load_cli_cases()


def test_argv_cases_use_known_tools():
    for case in cf.load_argv_cases():
        assert case.harness_name in HARNESS_NAMES, case.id


def test_argv_cases_end_with_prompt_after_double_dash():
    # The prompt always comes last, where no part of it can be parsed as a harness flag (see
    # WISDOM.md): after a "--" (opencode splits it on spaces, so the elements after some "--"
    # rejoin to exactly the prompt), or, for a harness with no "--" for its prompt option (grok),
    # as the value of a final "--option=PROMPT" element.
    for case in cf.load_argv_cases():
        argv = case.expected_argv
        if argv is not None:
            tails = [" ".join(argv[i + 1 :]) for i, a in enumerate(argv) if a == "--"]
            if argv[-1].startswith("--") and "=" in argv[-1]:
                tails.append(argv[-1].partition("=")[2])
            assert case.request["prompt"] in tails, case.id


def test_parse_cases_use_known_tools():
    for case in cf.load_parse_cases():
        assert case.harness_name in HARNESS_NAMES, case.id


def test_case_ids_unique():
    for loader in (cf.load_argv_cases, cf.load_parse_cases, cf.load_cli_cases):
        ids = [c.id for c in loader()]
        assert len(ids) == len(set(ids))
