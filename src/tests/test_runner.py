"""CA-4: runner — subprocess execution, timeouts, process groups, interrupts, missing binaries."""

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from callai import runner
from callai.errors import CallaiError, HarnessNotFound, HarnessTimeout, Interrupted, UsageError
from tests.conftest import isolated_env

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake harnesses are POSIX shebang scripts")


def test_error_exit_codes():
    assert HarnessNotFound("claude").exit_code == 127
    assert HarnessTimeout("claude", 1).exit_code == 124
    assert Interrupted().exit_code == 130
    assert all(issubclass(e, CallaiError) for e in (HarnessNotFound, HarnessTimeout, Interrupted))


def test_harness_not_found_message():
    msg = str(HarnessNotFound("claude", harness_name="claude-code", install_url="https://x.invalid/install"))
    assert "'claude'" in msg and "claude-code" in msg and "https://x.invalid/install" in msg


def test_resolve_binary(fake_bin, monkeypatch):
    exe = fake_bin.add("claude")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    assert runner.resolve_binary("claude") == str(exe)
    with pytest.raises(HarnessNotFound, match="'codex'"):
        runner.resolve_binary("codex")


def test_run_captures_output_exit_code_and_duration(fake_bin, monkeypatch):
    fake_bin.add("claude", stdout="out\n", stderr="err\n", exit_code=3)
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    done = runner.run(["claude", "-p", "--", "hi"])
    assert (done.exit_code, done.stdout, done.stderr) == (3, "out\n", "err\n")
    assert done.argv == ["claude", "-p", "--", "hi"]  # bare name kept; resolution is internal
    assert isinstance(done.duration_ms, int) and done.duration_ms >= 0
    assert fake_bin.record("claude")["argv"] == ["claude", "-p", "--", "hi"]


def test_run_keeps_line_endings_byte_exact(fake_bin, monkeypatch):
    # hermes marks display lines with \r\n; universal-newline decoding would erase that (and -o raw
    # would not be the harness's real output).
    fake_bin.add("claude", stdout="a\r\nb\n\rc", stderr="e\r\n")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    done = runner.run(["claude"])
    assert (done.stdout, done.stderr) == ("a\r\nb\n\rc", "e\r\n")


def test_run_gives_harness_empty_stdin(fake_bin, monkeypatch):
    # The prompt travels in argv; a harness must never also read callai's stdin (claude -p would append it).
    fake_bin.add("claude")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    runner.run(["claude"])
    assert fake_bin.record("claude")["stdin"] == ""


def test_run_cwd(fake_bin, monkeypatch, tmp_path):
    fake_bin.add("claude")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    work = tmp_path / "work"
    work.mkdir()
    runner.run(["claude"], cwd=str(work))
    assert fake_bin.record("claude")["cwd"] == str(work)


def test_run_env_adds_to_inherited_environment(fake_bin, monkeypatch):
    # CA-21: an adapter's env vars are set for the harness on top of callai's own environment.
    fake_bin.add("claude")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    monkeypatch.setenv("CALLAI_INHERITED", "yes")
    monkeypatch.setenv("HARNESS_VAR", "old")
    runner.run(["claude"], env={"HARNESS_VAR": "new"})
    env = fake_bin.record("claude")["env"]
    assert (env["CALLAI_INHERITED"], env["HARNESS_VAR"]) == ("yes", "new")


def test_run_on_stdout_line_delivers_lines_while_harness_runs(tmp_path, monkeypatch):
    # CA-14: -o stream-json must show events as they happen, not after the harness exits.
    exe = tmp_path / "slow"
    exe.write_text(
        f"#!{sys.executable}\nimport sys, time\nprint('a', flush=True)\ntime.sleep(1.5)\nprint('b', flush=True)\n",
        encoding="utf-8",
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    seen = []
    start = time.monotonic()
    done = runner.run(["slow"], on_stdout_line=lambda line: seen.append((line, time.monotonic() - start)))
    assert [line for line, _ in seen] == ["a\n", "b\n"]
    assert seen[0][1] < 1.2  # well before the harness finished
    assert done.stdout == "a\nb\n"  # still captured in full


def test_stop_all_kills_a_harness_that_ignores_sigint(tmp_path, monkeypatch):
    # CA-15c: Ctrl-C in a parallel fan-out stops harnesses running in other threads.
    exe = tmp_path / "stubborn"
    exe.write_text(
        f"#!{sys.executable}\nimport signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "print('up', flush=True)\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(runner, "_GRACE_SECONDS", 0.5)
    started, done = threading.Event(), []
    worker = threading.Thread(
        target=lambda: done.append(runner.run(["stubborn"], on_stdout_line=lambda line: started.set())), daemon=True
    )
    worker.start()
    assert started.wait(10)
    begin = time.monotonic()
    runner.stop_all()
    worker.join(10)
    assert done and done[0].exit_code != 0
    assert time.monotonic() - begin < 5
    assert set() == runner._LIVE


def test_run_bad_cwd_is_usage_error(fake_bin, monkeypatch, tmp_path):
    fake_bin.add("claude")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    with pytest.raises(UsageError, match="not a directory"):
        runner.run(["claude"], cwd=str(tmp_path / "missing"))


def test_run_timeout_raises(fake_bin, monkeypatch):
    fake_bin.add("claude", sleep=10)
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    start = time.monotonic()
    with pytest.raises(HarnessTimeout, match="timed out after 0.3s"):
        runner.run(["claude"], timeout=0.3)
    assert time.monotonic() - start < 5


def test_run_timeout_kills_whole_process_group(fake_bin, monkeypatch, tmp_path):
    # A harness that spawns a long-lived child: the child must die with it.
    pidfile = tmp_path / "child.pid"
    exe = fake_bin.dir / "claude"
    exe.write_text(
        textwrap.dedent(f"""\
            #!{sys.executable}
            import subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            open({str(pidfile)!r}, "w").write(str(child.pid))
            time.sleep(60)
        """)
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    with pytest.raises(HarnessTimeout):
        runner.run(["claude"], timeout=1)
    child_pid = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("grandchild survived the timeout kill")


def test_run_verbose_tees_stderr(fake_bin, monkeypatch, capsys):
    fake_bin.add("claude", stdout="o", stderr="live progress\n")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    done = runner.run(["claude"], verbose=True)
    assert done.stderr == "live progress\n"  # still captured
    assert "live progress" in capsys.readouterr().err


def test_run_quiet_by_default(fake_bin, monkeypatch, capsys):
    fake_bin.add("claude", stderr="noise\n")
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    runner.run(["claude"])
    assert capsys.readouterr().err == ""


def test_sigint_is_forwarded_and_exits_130(fake_bin, tmp_path):
    fake_bin.add("claude", sleep=30)
    env = isolated_env(tmp_path, fake_bin.dir)
    proc = subprocess.Popen(
        [sys.executable, "-m", "callai", "-n", "claude-code", "-p", "hi"],
        env=env,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(100):  # wait until the fake harness has started
        if fake_bin.record("claude") is not None:
            break
        time.sleep(0.05)
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=15)
    assert proc.returncode == 130, err
    assert "interrupted" in err


def test_signal_group_tolerates_finished_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    proc.wait()
    runner._signal_group(proc, signal.SIGTERM)  # group is gone: must not raise
