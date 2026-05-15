"""Utilities for constructing OpenAI LLM instances in a capability-aware way."""
from __future__ import annotations

import re

from power_atlas.adapters.graphrag_retrieval import OpenAILLM

_TEMP_NEVER_PATTERNS = [
    re.compile(r"^o\d", re.IGNORECASE),
    re.compile(r"^gpt-5(?!\.)(-mini|-nano|-pro)?(?:-[\w-]+)*$", re.IGNORECASE),
    re.compile(r"^gpt-5\.\d.*-pro(?:-[\w-]+)*$", re.IGNORECASE),
]
_TEMP_GPT5_VERSIONED_RE = re.compile(r"^gpt-5\.\d", re.IGNORECASE)


def model_supports_temperature(
    model_name: str, reasoning_effort: str | None = None
) -> bool:
    for pattern in _TEMP_NEVER_PATTERNS:
        if pattern.match(model_name):
            return False
    if _TEMP_GPT5_VERSIONED_RE.match(model_name):
        return reasoning_effort == "none"
    return True


def build_openai_llm(model_name: str, reasoning_effort: str | None = None):
    model_params: dict = {}
    if model_supports_temperature(model_name, reasoning_effort=reasoning_effort):
        model_params["temperature"] = 0
    if reasoning_effort is not None:
        model_params["reasoning_effort"] = reasoning_effort
    return OpenAILLM(model_name=model_name, model_params=model_params)


_model_supports_temperature = model_supports_temperature


__all__ = ["OpenAILLM", "build_openai_llm", "model_supports_temperature"]
