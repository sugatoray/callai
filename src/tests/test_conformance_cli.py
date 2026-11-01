"""Runs every conformance/cli case end-to-end against ``python -m callai`` (subprocess, fake harnesses)."""

import json
from pathlib import Path

import pytest

from tests import conformance as cf
from tests.conftest import isolated_env, run_callai

CASES = cf.load_cli_cases()


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_cli_case(case, fake_bin, tmp_path):
    for name, spec in case.fake_harnesses.items():
        fake_bin.add(name, **spec)
    env = isolated_env(tmp_path, fake_bin.dir, case.env)
    if case.config is not None:
        conf = Path(env["XDG_CONFIG_HOME"]) / "callai" / "config.toml"
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(case.config, encoding="utf-8")
    proc = run_callai(case.args, env=env, cwd=tmp_path, stdin=case.stdin, stdin_open=case.stdin_open, timeout=15)
    exp = case.expected
    detail = f"\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"

    assert proc.returncode == exp["exit_code"], detail
    if exp["stdout"] is not None:
        assert proc.stdout == exp["stdout"], detail
    if exp["stdout_json"] is not None:
        assert json.loads(proc.stdout) == exp["stdout_json"], detail
    if exp["stdout_json_subset"] is not None:
        got = json.loads(proc.stdout)
        assert {k: got.get(k) for k in exp["stdout_json_subset"]} == exp["stdout_json_subset"], detail
    if exp["stdout_events"] is not None:
        lines = [json.loads(line) for line in proc.stdout.splitlines()]
        assert len(lines) == len(exp["stdout_events"]), detail
        for got, want in zip(lines, exp["stdout_events"], strict=True):
            assert {k: got.get(k) for k in want} == want, detail
    for needle in exp["stdout_contains"]:
        assert needle in proc.stdout, detail
    for needle in exp["stderr_contains"]:
        assert needle in proc.stderr, detail
    if exp["harness_argv"] is not None or exp["harness_env"] is not None:
        (name,) = case.fake_harnesses  # the loader requires exactly one fake
        record = fake_bin.record(name)
        assert record is not None, f"fake {name!r} was never run{detail}"
        if exp["harness_argv"] is not None:
            assert record["argv"] == exp["harness_argv"]
        if exp["harness_env"] is not None:
            assert {k: record["env"].get(k) for k in exp["harness_env"]} == exp["harness_env"]
