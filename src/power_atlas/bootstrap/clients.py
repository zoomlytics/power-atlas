from __future__ import annotations

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings

from power_atlas.llm_utils import build_openai_llm
from power_atlas.settings import AppSettings, Neo4jSettings


def create_neo4j_driver(settings: AppSettings | Neo4jSettings) -> neo4j.Driver:
    neo4j_settings = settings.neo4j if isinstance(settings, AppSettings) else settings
    return neo4j.GraphDatabase.driver(
        neo4j_settings.uri,
        auth=(neo4j_settings.username, neo4j_settings.password),
    )


def build_llm_for_settings(
    settings: AppSettings,
    reasoning_effort: str | None = None,
):
    return build_openai_llm(settings.openai_model, reasoning_effort=reasoning_effort)


def build_embedder_for_settings(settings: AppSettings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=settings.openai_model)


__all__ = [
    "build_embedder_for_settings",
    "build_llm_for_settings",
    "create_neo4j_driver",
]
