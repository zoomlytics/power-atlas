"""Shared text normalization utilities for mention matching and entity resolution.

These helpers are used by both the entity resolution stage and the claim
participation stage.  Keeping them in a single module avoids tight coupling
between stages and ensures consistency.
"""
from __future__ import annotations

import re
import unicodedata

# Typographic/curly apostrophe variants that should normalise to ASCII ' (U+0027).
# Includes: LEFT/RIGHT SINGLE QUOTATION MARK, MODIFIER LETTER APOSTROPHE,
# MODIFIER LETTER PRIME, GRAVE ACCENT, ACUTE ACCENT.
_RE_APOSTROPHE_VARIANTS = re.compile(r"[\u2018\u2019\u02BC\u02B9\u0060\u00B4]")

# Hyphen/dash variants that should normalise to ASCII hyphen-minus (U+002D).
# Includes: HYPHEN, NON-BREAKING HYPHEN, FIGURE DASH, EN DASH, EM DASH,
# HORIZONTAL BAR, MINUS SIGN, SMALL EM DASH, SMALL HYPHEN-MINUS, FULLWIDTH
# HYPHEN-MINUS.
_RE_HYPHEN_VARIANTS = re.compile(
    r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]"
)

# Matches any run of whitespace (including Unicode whitespace such as
# non-breaking space U+00A0, ideographic space U+3000, etc.).
_RE_WHITESPACE = re.compile(r"\s+")


def normalize_mention_text(text: str) -> str:
    """Normalise *text* for mention clustering and entity resolution.

    Steps applied in order:

    1. Strip leading/trailing whitespace.
    2. NFKD Unicode normalisation — decomposes compatibility variants
       (e.g. full-width characters, ligatures) *and* separates base characters
       from their combining marks ready for step 3.
    3. Diacritic removal — drops Unicode combining marks (category ``Mn``) so
       accented forms cluster with their unaccented equivalents
       (e.g. ``"naïve"`` → ``"naive"``, and with later case-folding
       ``"Müller"`` → ``"muller"``).
    4. Apostrophe normalisation — collapses typographic/curly apostrophe
       variants (U+2018 LEFT SINGLE QUOTATION MARK ``'``, U+2019 RIGHT SINGLE
       QUOTATION MARK ``'``, U+02BC MODIFIER LETTER APOSTROPHE ``ʼ``, etc.) to
       the plain ASCII apostrophe (``'``).
    5. Hyphen/dash normalisation — collapses en-dash, em-dash, and other Unicode
       dash code points to the plain ASCII hyphen-minus (``-``).
    6. Whitespace collapse — runs of whitespace (including non-breaking spaces,
       ideographic spaces, etc.) are folded to a single ASCII space.
    7. Case-folding — applies Python's ``str.casefold()`` for aggressive
       lowercase normalisation (handles ``ß`` → ``ss``, etc.).
    """
    # 1. Strip
    text = text.strip()
    # 2+3. NFKD decomposition followed by diacritic removal
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if unicodedata.category(ch) != "Mn"
    )
    # 4. Apostrophe variants → ASCII apostrophe
    text = _RE_APOSTROPHE_VARIANTS.sub("'", text)
    # 5. Hyphen/dash variants → ASCII hyphen-minus
    text = _RE_HYPHEN_VARIANTS.sub("-", text)
    # 6. Collapse whitespace
    text = _RE_WHITESPACE.sub(" ", text).strip()
    # 7. Case-fold
    return text.casefold()


__all__ = [
    "normalize_mention_text",
]
