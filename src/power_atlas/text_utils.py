"""Shared text normalization utilities for mention matching and entity resolution.

These helpers are used by both the entity resolution stage and the claim
participation stage. Keeping them in the installed package starts the
mechanical promotion work while preserving legacy demo compatibility.
"""
from __future__ import annotations

import re
import unicodedata

_RE_APOSTROPHE_VARIANTS = re.compile(r"[\u2018\u2019\u02BC\u02B9\u0060\u00B4]")
_RE_HYPHEN_VARIANTS = re.compile(
    r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]"
)
_RE_WHITESPACE = re.compile(r"\s+")


def normalize_mention_text(text: str) -> str:
    """Normalise *text* for mention clustering and entity resolution."""
    text = text.strip()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = _RE_APOSTROPHE_VARIANTS.sub("'", text)
    text = _RE_HYPHEN_VARIANTS.sub("-", text)
    text = _RE_WHITESPACE.sub(" ", text).strip()
    return text.casefold()


__all__ = ["normalize_mention_text"]
