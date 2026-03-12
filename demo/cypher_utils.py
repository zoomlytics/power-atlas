"""Shared Cypher identifier validation utilities."""
from __future__ import annotations

import re


def validate_cypher_identifier(value: str, kind: str) -> None:
    """Raise ValueError if *value* is not a safe bare Cypher identifier.

    A safe bare identifier matches ``[A-Za-z_][A-Za-z0-9_]*``: it can be
    interpolated directly into a Cypher statement without quoting or escaping.

    Args:
        value: The string to validate.
        kind: Human-readable label used in the error message (e.g. ``"index name"``).

    Raises:
        ValueError: If *value* is not a string, or contains characters outside
            the allowed set, or starts with a digit.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {kind} for Cypher fallback: expected a string, got {value!r} (type {type(value).__name__})"
        )
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind} for Cypher fallback: {value!r}")
