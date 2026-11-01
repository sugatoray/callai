"""User configuration: ``config.toml``, and model aliases (DESIGN.md §6).

Precedence, applied by the CLI: command-line flag > ``CALLAI_*`` environment variable > this file >
built-in default. The file is optional; a missing default file is an empty config.
"""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import HARNESS_NAMES
from .errors import UsageError


class _Invalid(ValueError):
    """A problem in the config file; :func:`load_config` adds the file name and raises UsageError."""


_TOP_KEYS = {"default_harness", "model", "timeout", "harnesses", "aliases"}
_HARNESS_KEYS = {"binary", "model", "extra_args"}


@dataclass(frozen=True)
class HarnessConfig:
    """Settings for one harness, from ``[harnesses.<name>]``.

    Attributes:
        binary: Executable to run instead of the adapter's default (``~`` is expanded).
        model: Default model for this harness (may be an alias).
        extra_args: Arguments passed to the harness before any given after ``--``.
    """

    binary: str | None = None
    model: str | None = None
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    """Parsed ``config.toml``; every field is optional.

    Attributes:
        default_harness: Harness used when neither ``-n`` nor ``CALLAI_HARNESS_NAME`` is given.
        model: Default model for every harness (typically an alias).
        timeout: Default ``--timeout`` in seconds.
        harnesses: Per-harness settings, by harness name.
        aliases: Model alias -> {harness name -> model}.
    """

    default_harness: str | None = None
    model: str | None = None
    timeout: float | None = None
    harnesses: dict[str, HarnessConfig] = field(default_factory=dict)
    aliases: dict[str, dict[str, str]] = field(default_factory=dict)


def config_path(environ: Mapping[str, str], home: str | None = None) -> tuple[str, bool]:
    """Where the config file is, and whether the user named it explicitly.

    Args:
        environ: Environment (``CALLAI_CONFIG``, ``XDG_CONFIG_HOME``).
        home: Home directory; defaults to the current user's.

    Returns:
        ``(path, explicit)``: ``explicit`` is true when ``CALLAI_CONFIG`` set it.
    """
    if environ.get("CALLAI_CONFIG"):
        return environ["CALLAI_CONFIG"], True
    base = environ.get("XDG_CONFIG_HOME") or os.path.join(home or str(Path.home()), ".config")
    return os.path.join(base, "callai", "config.toml"), False


def load_config(environ: Mapping[str, str], home: str | None = None) -> Config:
    """Read and validate the config file.

    Args:
        environ: Environment used to find the file.
        home: Home directory; defaults to the current user's.

    Returns:
        The config; empty if the default file doesn't exist.

    Raises:
        UsageError: If an explicit ``CALLAI_CONFIG`` file is missing, or the file is unreadable,
            not TOML, or has unknown keys or invalid values. The message names the file.
    """
    path, explicit = config_path(environ, home)
    if not os.path.exists(path):
        if explicit:
            raise UsageError(f"CALLAI_CONFIG points at {path}, which doesn't exist")
        return Config()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path}: invalid TOML ({exc})") from None
    except OSError as exc:
        raise UsageError(f"{path}: cannot read config ({exc.strerror or exc})") from None
    try:
        return _parse(data)
    except _Invalid as exc:
        raise UsageError(f"{path}: {exc}") from None


def resolve_model(config: Config, harness_name: str, model: str | None) -> str | None:
    """Turn a model alias into the harness's own model name; anything else passes through.

    Args:
        config: The config holding ``[aliases]``.
        harness_name: Harness the model is for.
        model: Model or alias, or ``None``.

    Returns:
        The model to pass to the harness.

    Raises:
        UsageError: If ``model`` is an alias with no entry for this harness.
    """
    if model is None or model not in config.aliases:
        return model
    try:
        return config.aliases[model][harness_name]
    except KeyError:
        raise UsageError(f"model alias {model!r} has no entry for {harness_name}") from None


# --- validation ---------------------------------------------------------------


def _parse(data: dict[str, Any]) -> Config:
    """Validate a decoded config file.

    Args:
        data: Decoded TOML.

    Returns:
        The config.

    Raises:
        _Invalid: On unknown keys or invalid values.
    """
    _check_keys(data, _TOP_KEYS, "")
    default = data.get("default_harness")
    if default is not None and default not in HARNESS_NAMES:
        raise _Invalid(f"default_harness: unknown harness {default!r}; choose from {', '.join(HARNESS_NAMES)}")
    model = _opt_str(data, "model", "")
    timeout = data.get("timeout")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, int | float) or not math.isfinite(timeout) or timeout <= 0
    ):
        raise _Invalid(f"timeout must be a positive number of seconds, got {timeout!r}")
    return Config(
        default_harness=default,
        model=model,
        timeout=timeout,
        harnesses=_parse_harnesses(_table(data, "harnesses")),
        aliases=_parse_aliases(_table(data, "aliases")),
    )


def _parse_harnesses(raw: dict[str, Any]) -> dict[str, HarnessConfig]:
    """Validate ``[harnesses.<name>]`` tables.

    Args:
        raw: The ``harnesses`` table.

    Returns:
        Settings by harness name.

    Raises:
        _Invalid: On an unknown harness, unknown key or invalid value.
    """
    out = {}
    for name, table in raw.items():
        where = f"[harnesses.{name}]"
        if name not in HARNESS_NAMES:
            raise _Invalid(f"{where}: unknown harness; choose from {', '.join(HARNESS_NAMES)}")
        if not isinstance(table, dict):
            raise _Invalid(f"{where} must be a table")
        _check_keys(table, _HARNESS_KEYS, where)
        binary = _opt_str(table, "binary", where)
        if binary == "":
            raise _Invalid(f"{where}: binary must be a non-empty string")
        extra = table.get("extra_args", [])
        if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
            raise _Invalid(f"{where}: extra_args must be a list of strings")
        out[name] = HarnessConfig(binary=binary, model=_opt_str(table, "model", where), extra_args=tuple(extra))
    return out


def _parse_aliases(raw: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Validate ``[aliases]``: each alias maps harness names to model names.

    Args:
        raw: The ``aliases`` table.

    Returns:
        Alias -> {harness name -> model}.

    Raises:
        _Invalid: If an alias isn't a table of strings or names an unknown harness.
    """
    out = {}
    for alias, mapping in raw.items():
        if not isinstance(mapping, dict) or not all(isinstance(m, str) for m in mapping.values()):
            raise _Invalid(f"[aliases] {alias} must map harness names to models, e.g. {{ codex = 'o3' }}")
        for name in mapping:
            if name not in HARNESS_NAMES:
                raise _Invalid(f"[aliases] {alias}: unknown harness {name!r}; choose from {', '.join(HARNESS_NAMES)}")
        out[alias] = dict(mapping)
    return out


def _check_keys(table: dict[str, Any], allowed: set[str], where: str) -> None:
    """Refuse unknown keys, so a typo doesn't silently do nothing.

    Args:
        table: A TOML table.
        allowed: Keys it may have.
        where: Table name for the message (``""`` for the top level).

    Raises:
        _Invalid: On the first unknown key.
    """
    for key in table:
        if key not in allowed:
            prefix = f"{where}: " if where else ""
            raise _Invalid(f"{prefix}unknown key {key!r}; allowed: {', '.join(sorted(allowed))}")


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    """An optional sub-table, ``{}`` if absent.

    Args:
        data: The parent table.
        key: Sub-table name.

    Returns:
        The sub-table.

    Raises:
        _Invalid: If the key holds something other than a table.
    """
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise _Invalid(f"{key} must be a table")
    return value


def _opt_str(table: dict[str, Any], key: str, where: str) -> str | None:
    """An optional string value.

    Args:
        table: The table.
        key: The key.
        where: Table name for the message.

    Returns:
        The string, or ``None`` if absent.

    Raises:
        _Invalid: If the value isn't a string.
    """
    value = table.get(key)
    if value is not None and not isinstance(value, str):
        raise _Invalid(f"{where + ': ' if where else ''}{key} must be a string")
    return value
