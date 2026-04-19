from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, Neo4jGraph, TextChunk

from power_atlas.bootstrap import create_neo4j_driver


@dataclass(frozen=True)
class NarrativeExtractionLiveResult:
    text_chunks: list[TextChunk]
    claim_rows: list[dict[str, Any]]
    mention_rows: list[dict[str, Any]]
    warnings: list[str]


async def _run_read_chunks_and_extract(
    driver: Any,
    *,
    config: Any,
    lexical_graph_config: LexicalGraphConfig,
    read_chunks_and_extract: Callable[..., Any],
) -> tuple[Neo4jGraph, list[TextChunk]]:
    return await read_chunks_and_extract(
        driver,
        config=config,
        lexical_graph_config=lexical_graph_config,
    )


def run_narrative_extraction_live(
    config: Any,
    *,
    lexical_graph_config: LexicalGraphConfig,
    read_chunks_and_extract: Callable[..., Any],
    prepare_rows: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]],
    write_rows: Callable[..., None],
) -> NarrativeExtractionLiveResult:
    with create_neo4j_driver(config) as driver:
        graph, text_chunks = asyncio.run(
            _run_read_chunks_and_extract(
                driver,
                config=config,
                lexical_graph_config=lexical_graph_config,
                read_chunks_and_extract=read_chunks_and_extract,
            )
        )
        claim_rows, mention_rows, warnings = prepare_rows(
            graph=graph,
            text_chunks=text_chunks,
            run_id=config.run_id,
            source_uri=config.source_uri,
            lexical_graph_config=lexical_graph_config,
        )
        write_rows(
            driver,
            neo4j_database=config.neo4j_database,
            lexical_graph_config=lexical_graph_config,
            claim_rows=claim_rows,
            mention_rows=mention_rows,
        )
    return NarrativeExtractionLiveResult(
        text_chunks=text_chunks,
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        warnings=list(warnings),
    )


__all__ = ["NarrativeExtractionLiveResult", "run_narrative_extraction_live"]