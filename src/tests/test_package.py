"""CA-1: package skeleton — version, entry points, packaging metadata."""

import subprocess
import sys
import tomllib
from pathlib import Path

import callai
from callai import cli

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_version_matches_pyproject():
    assert callai.__version__ == _pyproject()["project"]["version"]


def test_distribution_name_and_console_script():
    project = _pyproject()["project"]
    assert project["name"] == "callai-cli"
    assert project["scripts"] == {"callai": "callai.cli:main"}
    assert project["requires-python"] == ">=3.11"
    assert project["dependencies"] == []  # stdlib-only (DESIGN §4)


def test_main_version_flag(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out == f"callai {callai.__version__}\n"


def test_python_dash_m_entry_point():
    proc = subprocess.run(
        [sys.executable, "-m", "callai", "--version"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],  # src/, so `callai` is importable without install
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"callai {callai.__version__}\n"


def test_main_without_args_is_usage_error(capsys):
    # No tool/prompt is always a usage error (DESIGN §8: exit 2), from the skeleton onwards.
    assert cli.main([]) == 2
    assert "usage: callai" in capsys.readouterr().err


def test_license_is_apache_2():
    assert _pyproject()["project"]["license"] == "Apache-2.0"
    text = (PYPROJECT.parent / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0" in text
