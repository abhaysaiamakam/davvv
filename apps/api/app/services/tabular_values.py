"""Shared CSV missing-value semantics used by analysis and transformations."""
from __future__ import annotations

from typing import Any


EXPLICIT_NULL_TOKENS = {"null", "none", "nan", "n/a"}


def is_missing_value(value: Any) -> bool:
    """Empty, whitespace-only, short-row null, and explicit null tokens are missing."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return not stripped or stripped.casefold() in EXPLICIT_NULL_TOKENS


def missing_representation(value: Any) -> str:
    """Describe how a missing value appeared in the source CSV."""
    if value is None:
        # csv.DictReader represents cells beyond a short row as None.
        return "null"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return "whitespace" if value else "empty_string"
        if stripped.casefold() in EXPLICIT_NULL_TOKENS:
            return "explicit_null"
    return "unknown"
