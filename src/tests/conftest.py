"""Shared pytest configuration for callai tests: fake harness executables and an isolated CLI runner."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]

_FAKE_SCRIPT = """#!{python}
import json, os, sys, time
spec = json.load(open({spec!r}, encoding="utf-8"))
# Write then rename, so a test polling for the record never reads it half-written.
with open({record!r} + ".tmp", "w", encoding="utf-8") as fh:
    json.dump({{"argv": [os.path.basename(sys.argv[0])] + sys.argv[1:], "cwd": os.getcwd(),
               "stdin": sys.stdin.read(), "env": dict(os.environ)}}, fh)
os.replace({record!r} + ".tmp", {record!r})
time.sleep(spec["sleep"])
sys.stdout.write(spec["stdout"]); sys.stdout.flush()
sys.stderr.write(spec["stderr"]); sys.stderr.flush()
sys.exit(spec["exit_code"])
"""


class FakeBin:
    """A directory of fake harness executables that replay canned output and record how they were called."""

    def __init__(self, root: Path):
        self.dir = root / "fakebin"
        self.dir.mkdir()

    def add(self, name, stdout="", stderr="", exit_code=0, sleep=0):
        spec = self.dir / f".{name}.spec.json"
        spec.write_text(
            json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "sleep": sleep}), encoding="utf-8"
        )
        exe = self.dir / name
        exe.write_text(
            _FAKE_SCRIPT.format(python=sys.executable, spec=str(spec), record=str(self.record_path(name))),
            encoding="utf-8",
        )
        exe.chmod(0o755)
        return exe

    def record_path(self, name):
        return self.dir / f".{name}.record.json"

    def record(self, name):
        """How the fake was called ({"argv", "cwd", "stdin", "env"}), or None if it never ran."""
        path = self.record_path(name)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@pytest.fixture
def fake_bin(tmp_path):
    return FakeBin(tmp_path)


def isolated_env(tmp_path, fake_dir, overrides=None):
    """Environment for running callai: PATH holds only fakes, config dirs are empty, no inherited CALLAI_*."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CALLAI_")}
    env.update(
        {
            "PATH": str(fake_dir),
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "PYTHONPATH": str(SRC_DIR),
        }
    )
    env.update(overrides or {})
    return env


def run_callai(args, *, env, cwd, stdin=None, stdin_open=False, timeout=30, **popen_kw):
    """Run ``python -m callai`` end-to-end; stdin=None means an empty pipe (never inherit the test's stdin).

    ``stdin_open=True`` gives callai a pipe whose writer stays open and silent until callai exits.
    """
    if stdin_open:
        r, w = os.pipe()
        try:
            return subprocess.run(
                [sys.executable, "-m", "callai", *args],
                stdin=r,
                capture_output=True,
                text=True,
                env=env,
                cwd=cwd,
                timeout=timeout,
                check=False,
                **popen_kw,
            )
        finally:
            os.close(r)
            os.close(w)
    return subprocess.run(
        [sys.executable, "-m", "callai", *args],
        input=stdin or "",
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
        check=False,
        **popen_kw,
    )
