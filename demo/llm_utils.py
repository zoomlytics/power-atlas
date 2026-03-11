"""Utilities for constructing OpenAI LLM instances in a capability-aware way.

Temperature support varies by model family and request configuration:

- Standard chat models (``gpt-3.5-*``, ``gpt-4o*``, ``gpt-4.1*``, etc.)
  accept ``temperature=0``.
- Reasoning models (``o1*``, ``o3*``, ``o4-mini*``) only support the default
  temperature and raise an error if an explicit value is supplied.
- GPT-5 base/mini/nano/pro variants (``gpt-5``, ``gpt-5-mini``,
  ``gpt-5-nano``, ``gpt-5-pro``, ``gpt-5.4-pro``) never accept explicit
  temperature.
- GPT-5 versioned models (``gpt-5.1``, ``gpt-5.2``, ``gpt-5.4``) accept
  ``temperature`` only when ``reasoning_effort`` is ``"none"``; any other
  (or absent) effort value makes temperature unsupported.

This module centralises LLM construction so that callers do not need to
duplicate the capability-detection logic.
"""
from __future__ import annotations

import re

from neo4j_graphrag.llm import OpenAILLM

# Models that never accept an explicit temperature parameter.
_TEMP_NEVER_PATTERNS = [
    # Reasoning series: o1, o3, o4-mini, etc.
    re.compile(r"^o\d", re.IGNORECASE),
    # GPT-5 base and named variants (not versioned like gpt-5.1)
    re.compile(r"^gpt-5(-mini|-nano|-pro)?$", re.IGNORECASE),
    # GPT-5.x-pro variants (e.g. gpt-5.4-pro)
    re.compile(r"^gpt-5\.\d.*-pro$", re.IGNORECASE),
]

# GPT-5 versioned models (e.g. gpt-5.1, gpt-5.2, gpt-5.4): temperature is
# supported only when reasoning_effort is "none".
_TEMP_GPT5_VERSIONED_RE = re.compile(r"^gpt-5\.\d", re.IGNORECASE)


def _model_supports_temperature(
    model_name: str, reasoning_effort: str | None = None
) -> bool:
    """Return True if the model accepts an explicit ``temperature`` parameter.

    Temperature support depends on both the model family and, for GPT-5.x
    versioned models, the ``reasoning_effort`` setting:

    - ``o1*``, ``o3*``, ``o4-mini*``: never accept temperature.
    - ``gpt-5``, ``gpt-5-mini``, ``gpt-5-nano``, ``gpt-5-pro``: never accept
      temperature.
    - ``gpt-5.x-pro`` variants (e.g. ``gpt-5.4-pro``): never accept
      temperature.
    - ``gpt-5.1``, ``gpt-5.2``, ``gpt-5.4`` (versioned, non-pro): accept
      temperature only when ``reasoning_effort == "none"``.
    - All other models (``gpt-4.1*``, ``gpt-4o*``, etc.): accept temperature.

    Args:
        model_name: The OpenAI model identifier.
        reasoning_effort: Optional reasoning effort setting (e.g. ``"none"``,
            ``"low"``, ``"high"``). Relevant for GPT-5.x versioned models.

    Returns:
        True if the model accepts an explicit ``temperature`` parameter.
    """
    for pattern in _TEMP_NEVER_PATTERNS:
        if pattern.match(model_name):
            return False
    if _TEMP_GPT5_VERSIONED_RE.match(model_name):
        return reasoning_effort == "none"
    return True


def build_openai_llm(model_name: str, reasoning_effort: str | None = None):
    """Create an :class:`~neo4j_graphrag.llm.OpenAILLM` with capability-aware model params.

    Uses ``temperature=0`` for models that support it to encourage
    deterministic, grounded output.  Omits ``temperature`` for models that do
    not accept it (reasoning models and GPT-5 base/mini/nano/pro variants).

    For GPT-5.x versioned models (e.g. ``gpt-5.1``), ``temperature=0`` is
    only included when ``reasoning_effort`` is ``"none"``.

    Args:
        model_name: The OpenAI model identifier (e.g. ``"gpt-4.1"`` or
            ``"gpt-5-mini"``).
        reasoning_effort: Optional reasoning effort setting (e.g. ``"none"``,
            ``"low"``, ``"high"``). When provided, it is forwarded to the
            model as a request parameter and used to determine temperature
            compatibility for GPT-5.x versioned models.

    Returns:
        A configured :class:`~neo4j_graphrag.llm.OpenAILLM` instance.
    """
    model_params: dict = {}
    if _model_supports_temperature(model_name, reasoning_effort=reasoning_effort):
        model_params["temperature"] = 0
    if reasoning_effort is not None:
        model_params["reasoning_effort"] = reasoning_effort
    return OpenAILLM(model_name=model_name, model_params=model_params)


__all__ = ["build_openai_llm"]
