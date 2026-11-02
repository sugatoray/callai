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

try:
    from importlib import metadata
except ImportError:  # for Python<3.8
    import importlib_metadata as metadata

__libname__ = "callai"
__title__ = __name__ if __name__ == __libname__ else __libname__.replace("-", "_")  # type: ignore
__version__ = metadata.version(__title__)  # type: ignore

#__version__ = "0.8.0"
