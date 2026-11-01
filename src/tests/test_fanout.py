"""CA-15c: fan-out (``-n a/b/c`` in parallel, ``-n a,b,c`` one after another, ``-n all``)."""

import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from callai import fanout
from callai.adapters import HARNESS_NAMES
from callai.errors import UsageError
from tests.conftest import isolated_env, run_callai

PARSE = Path(__file__).resolve().parents[2] / "conformance" / "parse"
PONG = {
    "claude": (PARSE / "claude-code/success_pong.stdout").read_text(encoding="utf-8"),
    "codex": (PARSE / "codex/success_pong.stdout").read_text(encoding="utf-8"),
}


# --- -n syntax ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("codex", (["codex"], fanout.SINGLE)),
        ("codex/pi", (["codex", "pi"], fanout.PARALLEL)),
        ("codex,pi,grok", (["codex", "pi", "grok"], fanout.SEQUENTIAL)),
        (" codex / pi ", (["codex", "pi"], fanout.PARALLEL)),
        ("all", (list(HARNESS_NAMES), fanout.ALL)),
    ],
)
def test_split_harness_names(value, expected):
    assert fanout.split_harness_names(value) == expected


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("codex/pi,grok", "not both"),
        ("codex,codex", "codex is listed twice"),
        ("codex//pi", "empty harness name"),
        ("/codex", "empty harness name"),
        ("all,codex", "'all' can't be combined"),
    ],
)
def test_split_harness_names_errors(value, match):
    with pytest.raises(UsageError, match=match):
        fanout.split_harness_names(value)


# --- running ------------------------------------------------------------------


def _run(fake_bin, tmp_path, args, **kw):
    env = isolated_env(tmp_path, fake_bin.dir)
    return run_callai(args, env=env, cwd=tmp_path, timeout=30, **kw)


@pytest.mark.parametrize(("sep", "concurrent"), [("/", True), (",", False)])
def test_parallel_runs_at_once_sequential_one_by_one(fake_bin, tmp_path, sep, concurrent):
    for name in ("claude", "codex"):
        fake_bin.add(name, stdout=PONG[name], sleep=1.5)
    start = time.monotonic()
    proc = _run(fake_bin, tmp_path, ["-n", f"claude-code{sep}codex", "-p", "hi"])
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, proc.stderr
    assert (elapsed < 2.7) is concurrent, elapsed


def test_one_timeout_is_a_failed_result_the_others_finish(fake_bin, tmp_path):
    fake_bin.add("claude", stdout=PONG["claude"], sleep=10)
    fake_bin.add("codex", stdout=PONG["codex"])
    proc = _run(fake_bin, tmp_path, ["-n", "codex/claude-code", "-p", "hi", "--timeout", "1", "-o", "json"])
    assert proc.returncode == 124, proc.stderr
    codex, claude = json.loads(proc.stdout)["results"]
    assert (codex["text"], codex["is_error"]) == ("pong", False)
    assert claude["harness_name"] == "claude-code" and claude["is_error"] and claude["exit_code"] == 124
    assert "timed out" in claude["text"]


def test_sigint_stops_every_parallel_harness(fake_bin, tmp_path):
    for name in ("claude", "codex"):
        fake_bin.add(name, sleep=30)
    env = isolated_env(tmp_path, fake_bin.dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "callai", "-n", "claude-code/codex", "-p", "hi"],
        env=env,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(100):  # wait until both fakes have started
        if fake_bin.record("claude") is not None and fake_bin.record("codex") is not None:
            break
        time.sleep(0.05)
    start = time.monotonic()
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=15)
    assert proc.returncode == 130, err
    assert "interrupted" in err
    assert time.monotonic() - start < 10  # didn't wait for the 30 s fakes


def test_bypass_warns_once_per_harness(fake_bin, tmp_path):
    for name in ("claude", "codex"):
        fake_bin.add(name, stdout=PONG[name])
    proc = _run(fake_bin, tmp_path, ["-n", "claude-code,codex", "-p", "hi", "--permission", "bypass"])
    assert proc.returncode == 0
    assert proc.stderr.count("--permission bypass:") == 2
    assert "claude-code will run" in proc.stderr and "codex will run" in proc.stderr


def test_stdin_is_read_once_and_shared(fake_bin, tmp_path):
    for name in ("claude", "codex"):
        fake_bin.add(name, stdout=PONG[name])
    proc = _run(fake_bin, tmp_path, ["-n", "claude-code/codex", "-p", "review"], stdin="the diff")
    assert proc.returncode == 0, proc.stderr
    assert fake_bin.record("claude")["argv"][-1] == "review\n\nthe diff"
    assert fake_bin.record("codex")["argv"][-1] == "review\n\nthe diff"


def test_sigint_in_sequential_run_skips_the_rest(fake_bin, tmp_path):
    fake_bin.add("claude", sleep=30)
    fake_bin.add("codex", stdout=PONG["codex"])
    env = isolated_env(tmp_path, fake_bin.dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "callai", "-n", "claude-code,codex", "-p", "hi"],
        env=env,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(100):
        if fake_bin.record("claude") is not None:
            break
        time.sleep(0.05)
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=15)
    assert proc.returncode == 130, err
    assert fake_bin.record("codex") is None  # never started


def test_unexpected_error_in_a_parallel_job_is_raised(monkeypatch):
    # A bug in one thread must surface, not vanish into a missing result.
    from callai.adapters import get_adapter
    from callai.request import Request

    adapter = get_adapter("codex")

    def broken(completed, req):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(adapter, "parse", broken)
    job = fanout.Job(adapter, Request(harness_name="codex", prompt="p"), ("true",))
    with pytest.raises(RuntimeError, match="parser bug"):
        fanout.run_jobs([job, job], concurrent=True)
