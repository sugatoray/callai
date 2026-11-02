"""callai: run a prompt non-interactively through any coding-agent harness.

Usage mirrors ``claude -p``::

    callai -n {claude-code,codex,opencode,pi,hermes,grok} -p PROMPT [-m MODEL]

From Python::

    from callai import run
    result = run("codex", "Fix the failing test", permission="auto")
    print(result.text, result.session_id)

See ``docs/DESIGN.md`` for the CLI surface and ``conformance/`` for the executable spec.
"""

from .api import run
from .cli import main
from .errors import CallaiError, HarnessNotFound, HarnessTimeout, Interrupted, UsageError
from .result import Result

__all__ = [
    "CallaiError",
    "HarnessNotFound",
    "HarnessTimeout",
    "Interrupted",
    "Result",
    "UsageError",
    "main",
    "run",
]

from importlib import metadata

try:
    __version__ = metadata.version("callai-cli")  # the distribution name, not the import name
except metadata.PackageNotFoundError:  # pragma: no cover - running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
