"""Compatibility shim for prompt contracts.

The implementation now lives in ``power_atlas.contracts.prompts``. This legacy
module remains so existing demo imports continue to work during the staged
migration.
"""

from power_atlas.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE, PROMPT_IDS

__all__ = ["PROMPT_IDS", "POWER_ATLAS_RAG_TEMPLATE"]
