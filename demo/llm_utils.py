"""Compatibility shim for LLM utilities.

The implementation now lives in ``power_atlas.llm_utils``. This legacy module
remains so existing demo imports continue to work during the staged migration.
"""
from power_atlas.llm_utils import OpenAILLM, _model_supports_temperature, build_openai_llm

__all__ = ["OpenAILLM", "_model_supports_temperature", "build_openai_llm"]
