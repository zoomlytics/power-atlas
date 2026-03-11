"""Utilities for constructing OpenAI LLM instances in a capability-aware way.

Some OpenAI models (the o1/o3 reasoning series) only support the default
temperature value and raise an error if an explicit temperature is supplied.
This module centralises LLM construction so that callers do not need to
duplicate the capability-detection logic.
"""
from __future__ import annotations

import re

from neo4j_graphrag.llm import OpenAILLM

# Reasoning models (o1, o3 family) do not accept an explicit temperature parameter.
# Match model names like o1, o1-mini, o1-preview, o3, o3-mini, o3-small, etc.
_REASONING_MODEL_RE = re.compile(r"^o\d", re.IGNORECASE)


def _model_supports_temperature(model_name: str) -> bool:
    """Return True if the model accepts an explicit ``temperature`` parameter.

    OpenAI reasoning models (o1-*, o3-*, etc.) only support the default
    temperature and raise an error when a different value is supplied.
    Standard chat completion models (gpt-3.5-*, gpt-4*, etc.) accept
    ``temperature=0`` for deterministic, grounded output.
    """
    return not _REASONING_MODEL_RE.match(model_name)


def build_openai_llm(model_name: str):
    """Create an :class:`~neo4j_graphrag.llm.OpenAILLM` with capability-aware model params.

    Uses ``temperature=0`` for standard chat models to encourage deterministic,
    grounded output.  Omits the ``temperature`` parameter for reasoning models
    (o1, o3 series) that only support the default temperature value (1).

    Args:
        model_name: The OpenAI model identifier (e.g. ``"gpt-4o-mini"`` or
            ``"o1-mini"``).

    Returns:
        A configured :class:`~neo4j_graphrag.llm.OpenAILLM` instance.
    """
    model_params: dict = {"temperature": 0} if _model_supports_temperature(model_name) else {}
    return OpenAILLM(model_name=model_name, model_params=model_params)


__all__ = ["build_openai_llm", "_model_supports_temperature"]
