"""CA-13: live smoke tests: each real harness, through callai, answers a real model.

Opt-in, because they need installed harnesses, credentials and network, and they cost money:

    CALLAI_LIVE=all uv run pytest -m live                  # every installed harness
    CALLAI_LIVE=claude-code,codex uv run pytest -m live    # just these

The model is whatever callai would use anyway: ``CALLAI_MODEL``, the config file (per harness or an
alias) or the harness's own default. ``CALLAI_LIVE_TIMEOUT`` (seconds, default 300) bounds each run.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

from callai.adapters import HARNESS_NAMES, get_adapter
from callai.cli import harness_binary
from callai.config import load_config
from tests.conftest import SRC_DIR

_LIVE = os.environ.get("CALLAI_LIVE", "").strip()
SELECTED = set(HARNESS_NAMES) if _LIVE in ("1", "all") else {s.strip() for s in _LIVE.split(",") if s.strip()}


def _run_live(harness_name, output_format):
    """Run callai against the real harness and model; skip unless selected and installed."""
    if harness_name not in SELECTED:
        pytest.skip("live test: set CALLAI_LIVE=all or CALLAI_LIVE=<harness>[,<harness>...]")
    binary = harness_binary(get_adapter(harness_name), load_config(os.environ))
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} is not installed")
    proc = subprocess.run(
        [sys.executable, "-m", "callai", "-n", harness_name, "-p", "Reply with exactly: pong", "-o", output_format],
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=float(os.environ.get("CALLAI_LIVE_TIMEOUT", "300")),
        check=False,
    )
    detail = f"\nexit={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr[-2000:]!r}"
    assert proc.returncode == 0, detail
    return proc, detail


@pytest.mark.live
@pytest.mark.parametrize("harness_name", HARNESS_NAMES)
def test_live_pong(harness_name):
    proc, detail = _run_live(harness_name, "json")
    result = json.loads(proc.stdout)
    assert result["harness_name"] == harness_name, detail
    assert not result["is_error"], detail
    assert "pong" in result["text"].lower(), detail


@pytest.mark.live
@pytest.mark.parametrize("harness_name", HARNESS_NAMES)
def test_live_stream_json(harness_name):
    # CA-14: start first, result last, and the answer's text events in between (none for hermes).
    proc, detail = _run_live(harness_name, "stream-json")
    events = [json.loads(line) for line in proc.stdout.splitlines()]
    assert events[0]["type"] == "start" and events[-1]["type"] == "result", detail
    assert not events[-1]["is_error"] and "pong" in events[-1]["text"].lower(), detail
    if harness_name != "hermes":
        assert "pong" in "".join(e["text"] for e in events if e["type"] == "text").lower(), detail
