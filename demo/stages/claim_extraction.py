from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from demo.contracts import PROMPT_IDS


async def _async_read_chunks_and_extract(
    driver: "neo4j.Driver",
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str,
    model_name: str,
) -> tuple[Any, list[Any], Any]:
    from neo4j_graphrag.experimental.components.entity_relation_extractor import LLMEntityRelationExtractor
    from neo4j_graphrag.llm import OpenAILLM
    from demo.contracts import (
        claim_extraction_lexical_config,
        claim_extraction_schema,
    )
    from demo.io import RunScopedNeo4jChunkReader

    lexical_config = claim_extraction_lexical_config()
    chunk_reader = RunScopedNeo4jChunkReader(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        fetch_embeddings=False,
        neo4j_database=neo4j_database,
    )
    text_chunks = await chunk_reader.run(lexical_graph_config=lexical_config)
    llm = OpenAILLM(
        model_name=model_name,
        model_params={"temperature": 0},
    )
    # create_lexical_graph=False: the lexical graph (Document/Chunk nodes) was already
    # created by Pipeline 1 (pdf ingest). This pipeline must not recreate or mutate
    # those nodes; it should only produce derived outputs (ExtractedClaim, EntityMention,
    # evidence-link relationships) linked to existing chunk nodes via provenance fields
    # (run_id, chunk_id). This mirrors the narrative extraction pipeline and enforces the
    # strict two-pipeline provenance contract described in the demo README.
    extractor = LLMEntityRelationExtractor(
        llm=llm,
        create_lexical_graph=False,
        use_structured_output=True,
    )
    try:
        graph = await extractor.run(
            chunks=text_chunks,
            schema=claim_extraction_schema(),
            lexical_graph_config=lexical_config,
        )
    finally:
        await llm.async_client.close()
    return graph, text_chunks.chunks, lexical_config


def run_claim_and_mention_extraction(config: Any, *, run_id: str, source_uri: str | None) -> dict[str, Any]:
    run_root = config.output_dir / "runs" / run_id
    extraction_dir = run_root / "claim_extraction"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    summary_path = extraction_dir / "claim_extraction_summary.json"

    prompt_version = PROMPT_IDS["claim_extraction"]
    if config.dry_run:
        summary = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "extractor_model": config.openai_model,
            "prompt_version": prompt_version,
            "chunks_processed": 0,
            "chunks_with_extractions": 0,
            "extracted_claim_count": 0,
            "entity_mention_count": 0,
            "claims": 0,
            "mentions": 0,
            "chunk_ids": [],
            "warnings": ["claim extraction skipped in dry_run mode"],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required for live claim extraction.")

    import neo4j
    from demo.extraction_utils import prepare_extracted_rows, write_extracted_rows

    driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
    with driver:
        graph, text_chunks, lexical_config = asyncio.run(
            _async_read_chunks_and_extract(
                driver,
                run_id=run_id,
                source_uri=source_uri,
                neo4j_database=config.neo4j_database,
                model_name=config.openai_model,
            )
        )
        claim_rows, mention_rows, warnings = prepare_extracted_rows(
            graph=graph,
            text_chunks=text_chunks,
            run_id=run_id,
            source_uri=source_uri,
            lexical_graph_config=lexical_config,
        )
        write_extracted_rows(
            driver,
            neo4j_database=config.neo4j_database,
            lexical_graph_config=lexical_config,
            claim_rows=claim_rows,
            mention_rows=mention_rows,
        )

    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {chunk_id for row in all_extracted_rows for chunk_id in row["chunk_ids"]}
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "extractor_model": config.openai_model,
        "prompt_version": prompt_version,
        # Total number of chunks read and processed as input
        "chunks_processed": len(text_chunks),
        # Number of chunks that produced at least one extraction
        "chunks_with_extractions": len(unique_chunk_ids),
        "extracted_claim_count": len(claim_rows),
        "entity_mention_count": len(mention_rows),
        "claims": len(claim_rows),
        "mentions": len(mention_rows),
        "chunk_ids": sorted(unique_chunk_ids),
        "warnings": warnings,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


__all__ = ["run_claim_and_mention_extraction"]
