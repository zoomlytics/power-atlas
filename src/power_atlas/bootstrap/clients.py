from __future__ import annotations

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

from power_atlas.adapters.llm import build_embedder as _build_embedder
from power_atlas.adapters.llm import build_embedder_for_settings as _build_embedder_for_settings
from power_atlas.adapters.llm import build_llm as _build_llm
from power_atlas.adapters.llm import build_llm_for_settings as _build_llm_for_settings
from power_atlas.llm_utils import build_openai_llm
from power_atlas.settings import AppSettings, Neo4jSettings


def _coerce_neo4j_settings(settings: AppSettings | Neo4jSettings) -> Neo4jSettings:
    if isinstance(settings, AppSettings):
        return settings.neo4j
    return settings


def create_neo4j_driver(settings: AppSettings | Neo4jSettings) -> neo4j.Driver:
    neo4j_settings = _coerce_neo4j_settings(settings)
    return neo4j.GraphDatabase.driver(
        neo4j_settings.uri,
        auth=(neo4j_settings.username, neo4j_settings.password),
    )


def build_llm(
    model_name: str,
    reasoning_effort: str | None = None,
):
    return _build_llm(
        model_name,
        reasoning_effort=reasoning_effort,
        llm_factory=build_openai_llm,
    )


def build_llm_for_settings(
    settings: AppSettings,
    reasoning_effort: str | None = None,
):
    return _build_llm_for_settings(
        settings,
        reasoning_effort=reasoning_effort,
        llm_factory=build_openai_llm,
    )


def build_embedder(
    model_name: str,
    *,
    embedder_factory=None,
):
    return _build_embedder(
        model_name,
        embedder_factory=embedder_factory or OpenAIEmbeddings,
    )


def build_embedder_for_settings(
    settings: AppSettings,
    *,
    embedder_factory=None,
):
    return _build_embedder_for_settings(
        settings,
        embedder_factory=embedder_factory or OpenAIEmbeddings,
    )


__all__ = [
    "build_embedder",
    "build_embedder_for_settings",
    "build_llm",
    "build_llm_for_settings",
    "create_neo4j_driver",
]
