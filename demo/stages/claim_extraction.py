from __future__ import annotations

import asyncio
import json
from typing import Any

from power_atlas.bootstrap import require_openai_api_key
from power_atlas.bootstrap.clients import build_llm as build_openai_llm, create_neo4j_driver
from power_atlas.context import RequestContext
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.contracts.prompts import PROMPT_IDS
from power_atlas.settings import Neo4jSettings


def _resolve_pipeline_contract(
    config: Any,
    pipeline_contract: PipelineContractSnapshot | None,
) -> PipelineContractSnapshot:
    if pipeline_contract is not None:
        return pipeline_contract
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if isinstance(config_pipeline_contract, PipelineContractSnapshot):
        return config_pipeline_contract
    raise ValueError(
        "claim extraction requires a pipeline contract from RequestContext/AppContext-derived config or an explicit pipeline_contract argument"
    )


async def _async_read_chunks_and_extract(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str,
    model_name: str,
    pipeline_contract: PipelineContractSnapshot,
) -> tuple[Any, list[Any], Any]:
    from neo4j_graphrag.experimental.components.entity_relation_extractor import LLMEntityRelationExtractor
    from power_atlas.contracts import (
        claim_extraction_lexical_config,
        claim_extraction_schema,
    )
    from demo.io import RunScopedNeo4jChunkReader
    lexical_config = claim_extraction_lexical_config(pipeline_contract)
    chunk_reader = RunScopedNeo4jChunkReader(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        fetch_embeddings=False,
        neo4j_database=neo4j_database,
    )
    text_chunks = await chunk_reader.run(lexical_graph_config=lexical_config)
    llm = build_openai_llm(model_name)
    # create_lexical_graph=False: the lexical graph (Document/Chunk nodes) was already
    # created by the ingest stage. This extraction stage must not recreate or mutate
    # those nodes; it only adds derived outputs (ExtractedClaim, EntityMention,
    # evidence-link relationships) linked to existing chunk nodes via run_id/chunk_id.
    # This keeps extraction non-destructive and consistent with the layered, vendor-plus
    # architecture: ingest writes the lexical graph; extraction extends it additively.
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


def run_claim_and_mention_extraction(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
) -> dict[str, Any]:
    resolved_pipeline_contract = _resolve_pipeline_contract(config, None)
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
            "subject_edges": 0,
            "object_edges": 0,
            "warnings": ["claim extraction skipped in dry_run mode"],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    require_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live claim extraction."
    )

    from demo.extraction_utils import prepare_extracted_rows, write_all_extraction_data
    from demo.stages.claim_participation import (
        ROLE_OBJECT,
        ROLE_SUBJECT,
        build_participation_edges,
    )

    driver = create_neo4j_driver(
        Neo4jSettings(
            uri=config.neo4j_uri,
            username=config.neo4j_username,
            password=config.neo4j_password,
            database=config.neo4j_database,
        )
    )
    edge_rows: list[dict] = []
    with driver:
        graph, text_chunks, lexical_config = asyncio.run(
            _async_read_chunks_and_extract(
                driver,
                run_id=run_id,
                source_uri=source_uri,
                neo4j_database=config.neo4j_database,
                model_name=config.openai_model,
                pipeline_contract=resolved_pipeline_contract,
            )
        )
        claim_rows, mention_rows, warnings = prepare_extracted_rows(
            graph=graph,
            text_chunks=text_chunks,
            run_id=run_id,
            source_uri=source_uri,
            lexical_graph_config=lexical_config,
        )
        edge_rows = build_participation_edges(claim_rows, mention_rows)
        write_all_extraction_data(
            driver,
            neo4j_database=config.neo4j_database,
            lexical_graph_config=lexical_config,
            claim_rows=claim_rows,
            mention_rows=mention_rows,
            edge_rows=edge_rows,
        )

    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {chunk_id for row in all_extracted_rows for chunk_id in row["chunk_ids"]}
    subject_edges = sum(1 for e in edge_rows if e["role"] == ROLE_SUBJECT)
    object_edges = sum(1 for e in edge_rows if e["role"] == ROLE_OBJECT)
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
        "subject_edges": subject_edges,
        "object_edges": object_edges,
        "warnings": warnings,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_claim_and_mention_extraction_request_context(request_context: RequestContext) -> dict[str, Any]:
    """Run claim extraction using request-scoped context as the primary input."""
    return run_claim_and_mention_extraction(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
    )


__all__ = ["run_claim_and_mention_extraction", "run_claim_and_mention_extraction_request_context"]
