from __future__ import annotations

from typing import Any

from power_atlas.adapters.graphrag_retrieval import OpenAIEmbeddings

from power_atlas.llm_utils import build_openai_llm
from power_atlas.settings import AppSettings


def build_llm(
    model_name: str,
    reasoning_effort: str | None = None,
    *,
    llm_factory=None,
):
    if llm_factory is None:
        llm_factory = build_openai_llm
    return llm_factory(model_name, reasoning_effort=reasoning_effort)


def build_llm_for_settings(
    settings: AppSettings,
    reasoning_effort: str | None = None,
    *,
    llm_factory=None,
):
    return build_llm(
        settings.openai_model,
        reasoning_effort=reasoning_effort,
        llm_factory=llm_factory,
    )


def build_embedder(
    model_name: str,
    *,
    embedder_factory: type[Any] | None = None,
):
    if embedder_factory is None:
        embedder_factory = OpenAIEmbeddings
    return embedder_factory(model=model_name)


def build_embedder_for_settings(
    settings: AppSettings,
    *,
    embedder_factory: type[Any] | None = None,
):
    return build_embedder(
        settings.embedder_model,
        embedder_factory=embedder_factory,
    )


__all__ = [
    "build_embedder",
    "build_embedder_for_settings",
    "build_llm",
    "build_llm_for_settings",
]