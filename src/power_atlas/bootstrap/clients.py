from __future__ import annotations

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

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
    return build_openai_llm(model_name, reasoning_effort=reasoning_effort)


def build_llm_for_settings(
    settings: AppSettings,
    reasoning_effort: str | None = None,
):
    return build_llm(settings.openai_model, reasoning_effort=reasoning_effort)


def build_embedder(
    model_name: str,
    *,
    embedder_factory=None,
):
    if embedder_factory is None:
        embedder_factory = OpenAIEmbeddings
    return embedder_factory(model=model_name)


def build_embedder_for_settings(
    settings: AppSettings,
    *,
    embedder_factory=None,
):
    return build_embedder(settings.embedder_model, embedder_factory=embedder_factory)


__all__ = [
    "build_embedder",
    "build_embedder_for_settings",
    "build_llm",
    "build_llm_for_settings",
    "create_neo4j_driver",
]
