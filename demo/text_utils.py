"""Compatibility shim for text normalization utilities.

The implementation now lives in the installed package at
``power_atlas.text_utils``. This legacy module remains so existing demo imports
continue to work during the staged migration.
"""
from power_atlas.text_utils import normalize_mention_text

__all__ = ["normalize_mention_text"]
