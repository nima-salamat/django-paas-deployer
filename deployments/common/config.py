"""
deployments/common/config.py
----------------------------
Single source of truth for parsing ``Deploy.config``.

Previously the codebase had THREE copies of the same JSON-decoding logic
in ``deploy_service.py``, ``tasks.py`` and ``validators.py``.  They
frequently drifted.  This module also adds typed accessors and boolean
coercion so call sites stop hand-rolling ``_as_bool``.
"""

from __future__ import annotations

import json
from typing import Any


def parse_config(raw: Any) -> dict[str, Any]:
    """
    Normalize ``Deploy.config`` to a dict.

    Handles:
      * dict  -> shallow copy
      * JSON-encoded string -> dict
      * double-encoded JSON string (``"\\\"{...}\\\""``) -> dict
      * None / empty / invalid -> empty dict
    """
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except (ValueError, TypeError):
            pass
    return {}


def as_bool(value: Any) -> bool:
    """Coerce common truthy representations to a real bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def as_int(value: Any, *, default: int, minimum: int | None = None,
           maximum: int | None = None) -> int:
    """Coerce to int with bounds; falls back to ``default`` on error."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        result = max(result, minimum)
    if maximum is not None:
        result = min(result, maximum)
    return result


def first_present(*values: Any, skip: tuple = (None, "")) -> Any:
    """Return the first value not in ``skip`` (None / empty string by default)."""
    for v in values:
        if v not in skip:
            return v
    return None


__all__ = ["parse_config", "as_bool", "as_int", "first_present"]
