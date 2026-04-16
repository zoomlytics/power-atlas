from __future__ import annotations

from typing import Protocol, runtime_checkable

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

from power_atlas.llm_utils import build_openai_llm
from power_atlas.settings import AppSettings, Neo4jSettings


@runtime_checkable
class _LegacyNeo4jConfig(Protocol):
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str


def _coerce_neo4j_settings(settings: AppSettings | Neo4jSettings | _LegacyNeo4jConfig) -> Neo4jSettings:
    if isinstance(settings, AppSettings):
        return settings.neo4j
    if isinstance(settings, Neo4jSettings):
        return settings
    return Neo4jSettings(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
        database=getattr(settings, "neo4j_database", Neo4jSettings.database),
    )


def create_neo4j_driver(settings: AppSettings | Neo4jSettings | _LegacyNeo4jConfig) -> neo4j.Driver:
    neo4j_settings = _coerce_neo4j_settings(settings)
    return neo4j.GraphDatabase.driver(
        neo4j_settings.uri,
        auth=(neo4j_settings.username, neo4j_settings.password),
    )


def build_llm_for_settings(
    settings: AppSettings,
    reasoning_effort: str | None = None,
):
    return build_openai_llm(settings.openai_model, reasoning_effort=reasoning_effort)


def build_embedder_for_settings(
    settings: AppSettings,
    *,
    embedder_factory=None,
):
    if embedder_factory is None:
        embedder_factory = OpenAIEmbeddings
    return embedder_factory(model=settings.embedder_model)


__all__ = [
    "build_embedder_for_settings",
    "build_llm_for_settings",
    "create_neo4j_driver",
]
