"""Check what each ``callai --permission`` level really lets a harness do, using scripted tool calls.

For every level (default, read-only, auto, bypass) and every probe (file write and shell write, each
inside the working directory and outside it), this starts ``stub_llm_server.py`` with
``--tool-call`` set to that harness's own write or shell tool, runs ``callai -n HARNESS_NAME`` against it,
and reports whether the file appeared and what the harness sent back as the tool's result.

The harness must already be configured to use the stub at ``http://127.0.0.1:8765/v1`` through its
environment (``ANTHROPIC_BASE_URL``, ``CODEX_HOME``, ``XDG_CONFIG_HOME``, ``PI_CODING_AGENT_DIR``,
``GROK_XAI_API_BASE_URL`` ...; see ``conformance/README.md``, "Recording without network").
Pick an ``--outside`` directory the harness's sandbox wouldn't allow anyway, i.e. not under ``/tmp``
(codex allows ``/tmp``). Working directories are made under ``$TMPDIR``; to probe a sandbox, set it
outside ``/tmp`` too, or the sandbox's ``/tmp`` exception hides what it does to the workspace.

Usage:
    python permission_probe.py --name grok --model stub-model --outside ~/callai-probe-outside
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUB = HERE / "stub_llm_server.py"
SRC = HERE.parents[1] / "src"
LEVELS = ("default", "read-only", "auto", "bypass")

# Each harness's own tool names and argument names (from the ``tools`` array in the stub's request log).
WRITE_TOOLS = {
    "claude-code": ("Write", "file_path"),
    "opencode": ("write", "filePath"),
    "pi": ("write", "path"),
    "grok": ("write", "file_path"),
    "hermes": ("write_file", "path"),
}
SHELL_TOOLS = {
    "claude-code": ("Bash", "command"),
    "codex": ("exec_command", "cmd"),
    "opencode": ("bash", "command"),
    "pi": ("bash", "command"),
    "grok": ("run_terminal_command", "command"),
    "hermes": ("terminal", "command"),
}


def probes(tool: str, workdir: Path, outside: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    """Build the scripted tool calls for one run, each with the file it would create.

    Args:
        tool: callai tool name.
        workdir: The run's working directory.
        outside: A directory outside the working directory.

    Returns:
        Probe name → (tool call for the stub, file that appears if the call ran).
    """
    calls: dict[str, tuple[dict[str, Any], Path]] = {}
    for where, target in (("", workdir / "probe.txt"), ("-outside", outside / f"{workdir.name}.txt")):
        if tool in WRITE_TOOLS:
            name, arg = WRITE_TOOLS[tool]
            calls[f"write{where}"] = ({"name": name, "arguments": {arg: str(target), "content": "hi"}}, target)
        name, arg = SHELL_TOOLS[tool]
        shell_target = target.with_suffix(".sh.txt")
        args: dict[str, Any] = {arg: f"echo hi > {shell_target}"}
        if tool == "grok":
            args["description"] = "permission probe"
        calls[f"shell{where}"] = ({"name": name, "arguments": args}, shell_target)
    return calls


def tool_result(log: Path, start: int) -> str:
    """The first tool result the harness sent back to the stub after line ``start`` of its log.

    Args:
        log: The stub's request log.
        start: Number of log lines that belong to earlier runs.

    Returns:
        The result text (shortened), or a note that none was sent.
    """
    for line in log.read_text(encoding="utf-8").splitlines()[start:] if log.exists() else []:
        body = json.loads(line)["body"]
        for m in body.get("messages") or body.get("input") or []:
            if not isinstance(m, dict):
                continue
            # Anthropic Messages (claude-code): the result is a tool_result block in a user message.
            blocks = [b for b in m.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_result"]
            if blocks or m.get("role") == "tool" or str(m.get("type", "")).endswith("_output"):
                c = blocks[0].get("content") if blocks else m.get("content", m.get("output"))
                return (c if isinstance(c, str) else json.dumps(c)).replace("\n", " ")[:120]
    return "(no tool result sent back)"


def main() -> None:
    """Run every probe at every level and print one line per run."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", dest="harness_name", required=True, choices=sorted(SHELL_TOOLS))
    ap.add_argument("--model", required=True)
    ap.add_argument("--outside", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    args.outside.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    root = Path(tempfile.mkdtemp(prefix=f"callai-probe-{args.harness_name}-"))
    log = root / "stub.log"
    print(f"{'probe':14} {'level':9} {'exit':4} {'effect':6} tool result")
    for probe in ("write", "write-outside", "shell", "shell-outside"):
        for level in LEVELS:
            workdir = root / f"{args.harness_name}-{probe}-{level}"
            workdir.mkdir()
            spec = probes(args.harness_name, workdir, args.outside.resolve()).get(probe)
            if spec is None:
                continue
            call, target = spec
            target.unlink(missing_ok=True)
            start = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
            stub = subprocess.Popen(
                [
                    sys.executable,
                    str(STUB),
                    "--port",
                    str(args.port),
                    "--log",
                    str(log),
                    "--tool-call",
                    json.dumps(call),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                time.sleep(0.8)
                run = subprocess.run(
                    [sys.executable, "-m", "callai", "-n", args.harness_name, "-m", args.model, "--timeout", "60"]
                    + ["--permission", level, "-p", "Do the task."],
                    env=env,
                    cwd=workdir,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            finally:
                stub.terminate()
                stub.wait()
            note = run.stderr.strip().splitlines()[-1] if run.returncode == 2 else tool_result(log, start)
            effect = "YES" if target.exists() else "no"
            print(f"{probe:14} {level:9} {run.returncode:<4} {effect:6} {note}", flush=True)
            target.unlink(missing_ok=True)
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
