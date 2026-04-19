from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver


@dataclass(frozen=True)
class ClaimExtractionLiveResult:
    text_chunks: list[Any]
    claim_rows: list[dict[str, Any]]
    mention_rows: list[dict[str, Any]]
    edge_rows: list[dict[str, Any]]
    warnings: list[str]


def run_claim_extraction_live(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    model_name: str,
    pipeline_contract: Any,
    read_chunks_and_extract: Callable[..., Any],
    prepare_rows: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]],
    build_edges: Callable[..., list[dict[str, Any]]],
    write_rows: Callable[..., None],
) -> ClaimExtractionLiveResult:
    with create_neo4j_driver(config) as driver:
        graph, text_chunks, lexical_config = asyncio.run(
            read_chunks_and_extract(
                driver,
                run_id=run_id,
                source_uri=source_uri,
                neo4j_database=config.neo4j_database,
                model_name=model_name,
                pipeline_contract=pipeline_contract,
            )
        )
        claim_rows, mention_rows, warnings = prepare_rows(
            graph=graph,
            text_chunks=text_chunks,
            run_id=run_id,
            source_uri=source_uri,
            lexical_graph_config=lexical_config,
        )
        edge_rows = build_edges(claim_rows, mention_rows)
        write_rows(
            driver,
            neo4j_database=config.neo4j_database,
            lexical_graph_config=lexical_config,
            claim_rows=claim_rows,
            mention_rows=mention_rows,
            edge_rows=edge_rows,
        )
    return ClaimExtractionLiveResult(
        text_chunks=text_chunks,
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        edge_rows=edge_rows,
        warnings=list(warnings),
    )


__all__ = ["ClaimExtractionLiveResult", "run_claim_extraction_live"]