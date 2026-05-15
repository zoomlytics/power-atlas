from __future__ import annotations

from typing import Any

from neo4j_graphrag.experimental.components.entity_relation_extractor import (
    LLMEntityRelationExtractor,
)
from power_atlas.adapters.graphrag_types import (
    LexicalGraphConfig,
    Neo4jGraph,
    TextChunk,
    TextChunks,
)

from power_atlas.adapters.llm import build_llm as build_openai_llm
from power_atlas.contracts import claim_extraction_schema
from power_atlas.neo4j_io import RunScopedNeo4jChunkReader


async def read_chunks_and_extract_narrative_graph(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str | None,
    model_name: str,
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[Neo4jGraph, list[TextChunk]]:
    chunk_reader = RunScopedNeo4jChunkReader(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        fetch_embeddings=False,
        neo4j_database=neo4j_database,
    )
    text_chunks: TextChunks = await chunk_reader.run(
        lexical_graph_config=lexical_graph_config
    )
    llm = build_openai_llm(model_name)
    extractor = LLMEntityRelationExtractor(
        llm=llm,
        create_lexical_graph=False,
        use_structured_output=True,
    )
    try:
        graph = await extractor.run(
            chunks=text_chunks,
            schema=claim_extraction_schema(),
            lexical_graph_config=lexical_graph_config,
        )
    finally:
        await llm.async_client.close()
    return graph, text_chunks.chunks


__all__ = ["read_chunks_and_extract_narrative_graph"]