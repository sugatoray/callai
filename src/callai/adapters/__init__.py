"""Harness adapters and the registry that maps ``--name`` values to them."""

from __future__ import annotations

from ..errors import UsageError
from .base import Adapter, strip_ansi

# Every harness callai supports, in --help order (DESIGN.md §2). Adapters register as they are built.
HARNESS_NAMES: tuple[str, ...] = ("claude-code", "codex", "opencode", "pi", "hermes", "grok")

REGISTRY: dict[str, Adapter] = {}


def register(adapter: Adapter) -> Adapter:
    """Add an adapter to the registry.

    Args:
        adapter: The adapter instance; its ``name`` must be one of ``HARNESS_NAMES``.

    Returns:
        The same adapter, so this can wrap an instantiation.

    Raises:
        ValueError: If the name is not a supported harness or is already registered.
    """
    if adapter.name not in HARNESS_NAMES:
        raise ValueError(f"{adapter.name!r} is not a supported harness")
    if adapter.name in REGISTRY:
        raise ValueError(f"{adapter.name!r} is already registered")
    REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(harness_name: str) -> Adapter:
    """Look up the adapter for a ``--name`` value.

    Args:
        harness_name: Harness name from the command line, environment or config.

    Returns:
        The registered adapter.

    Raises:
        UsageError: If the harness is unknown or its adapter is not implemented yet.
    """
    if harness_name not in HARNESS_NAMES:
        raise UsageError(f"unknown harness {harness_name!r}; choose from {', '.join(HARNESS_NAMES)}")
    try:
        return REGISTRY[harness_name]
    except KeyError:
        raise UsageError(f"harness {harness_name!r} is not implemented yet") from None


# Built-in adapters (imported last: they use register() above).
from .claude_code import ClaudeCode  # noqa: E402
from .codex import Codex  # noqa: E402
from .grok import Grok  # noqa: E402
from .hermes import Hermes  # noqa: E402
from .opencode import OpenCode  # noqa: E402
from .pi import Pi  # noqa: E402

register(ClaudeCode())
register(Codex())
register(OpenCode())
register(Pi())
register(Grok())
register(Hermes())

__all__ = [
    "HARNESS_NAMES",
    "REGISTRY",
    "Adapter",
    "ClaudeCode",
    "Codex",
    "Grok",
    "Hermes",
    "OpenCode",
    "Pi",
    "get_adapter",
    "register",
    "strip_ansi",
]
