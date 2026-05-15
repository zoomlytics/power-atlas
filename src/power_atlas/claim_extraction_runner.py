from __future__ import annotations

import json
from typing import Any, Callable

from power_atlas.adapters.llm import build_llm as build_openai_llm
from power_atlas.bootstrap import require_openai_api_key
from power_atlas.claim_extraction_runtime import run_claim_extraction_live
from power_atlas.contracts import ClaimExtractionPolicy
from power_atlas.contracts import claim_extraction_lexical_config, claim_extraction_schema
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.neo4j_io import RunScopedNeo4jChunkReader
from power_atlas.settings import Neo4jSettings


async def read_chunks_and_extract(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str,
    model_name: str,
    pipeline_contract: PipelineContractSnapshot,
    claim_extraction_policy: ClaimExtractionPolicy,
    chunk_reader_cls: type[Any] = RunScopedNeo4jChunkReader,
    llm_builder: Callable[[str], Any] = build_openai_llm,
) -> tuple[Any, list[Any], Any]:
    from neo4j_graphrag.experimental.components.entity_relation_extractor import (
        LLMEntityRelationExtractor,
    )

    lexical_config = claim_extraction_lexical_config(
        pipeline_contract,
        claim_extraction_policy.ontology,
    )
    chunk_reader = chunk_reader_cls(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        fetch_embeddings=False,
        neo4j_database=neo4j_database,
    )
    text_chunks = await chunk_reader.run(lexical_graph_config=lexical_config)
    llm = llm_builder(model_name)
    extractor = LLMEntityRelationExtractor(
        llm=llm,
        create_lexical_graph=False,
        use_structured_output=True,
    )
    try:
        graph = await extractor.run(
            chunks=text_chunks,
            schema=claim_extraction_schema(claim_extraction_policy.ontology),
            lexical_graph_config=lexical_config,
        )
    finally:
        await llm.async_client.close()
    return graph, text_chunks.chunks, lexical_config


def run_claim_extraction_runtime(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot,
    claim_extraction_policy: ClaimExtractionPolicy,
    neo4j_settings: Neo4jSettings,
    model_name: str,
    read_chunks_and_extract: Callable[..., Any],
    prepare_rows: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]],
    build_edges: Callable[..., list[dict[str, Any]]],
    write_rows: Callable[..., None],
    role_subject: str,
    role_object: str,
    live_runner: Callable[..., Any] = run_claim_extraction_live,
    require_openai_api_key_fn: Callable[..., None] = require_openai_api_key,
) -> dict[str, Any]:
    run_root = config.output_dir / "runs" / run_id
    extraction_dir = run_root / "claim_extraction"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    summary_path = extraction_dir / "claim_extraction_summary.json"

    prompt_version = claim_extraction_policy.prompt_id
    if config.dry_run:
        summary = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "extractor_model": model_name,
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

    require_openai_api_key_fn(
        "OPENAI_API_KEY environment variable is required for live claim extraction."
    )

    live_result = live_runner(
        neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
        model_name=model_name,
        neo4j_database=neo4j_settings.database,
        pipeline_contract=pipeline_contract,
        read_chunks_and_extract=read_chunks_and_extract,
        prepare_rows=prepare_rows,
        build_edges=build_edges,
        write_rows=write_rows,
    )
    text_chunks = live_result.text_chunks
    claim_rows = live_result.claim_rows
    mention_rows = live_result.mention_rows
    edge_rows = live_result.edge_rows
    warnings = live_result.warnings

    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {
        chunk_id for row in all_extracted_rows for chunk_id in row["chunk_ids"]
    }
    subject_edges = sum(1 for edge in edge_rows if edge["role"] == role_subject)
    object_edges = sum(1 for edge in edge_rows if edge["role"] == role_object)
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "extractor_model": model_name,
        "prompt_version": prompt_version,
        "chunks_processed": len(text_chunks),
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


def run_claim_extraction_runtime_default(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot,
    claim_extraction_policy: ClaimExtractionPolicy,
    neo4j_settings: Neo4jSettings,
    model_name: str,
    chunk_reader_cls: type[Any] = RunScopedNeo4jChunkReader,
    llm_builder: Callable[[str], Any] = build_openai_llm,
) -> dict[str, Any]:
    from power_atlas.claim_participation_edges import (
        ROLE_OBJECT,
        ROLE_SUBJECT,
        build_participation_edges,
    )
    from power_atlas.extraction_rows import prepare_extracted_rows
    from power_atlas.extraction_writes import write_all_extraction_data

    return run_claim_extraction_runtime(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=claim_extraction_policy,
        neo4j_settings=neo4j_settings,
        model_name=model_name,
        read_chunks_and_extract=lambda *args, **kwargs: read_chunks_and_extract(
            *args,
            **kwargs,
            claim_extraction_policy=claim_extraction_policy,
            chunk_reader_cls=chunk_reader_cls,
            llm_builder=llm_builder,
        ),
        prepare_rows=prepare_extracted_rows,
        build_edges=build_participation_edges,
        write_rows=write_all_extraction_data,
        role_subject=ROLE_SUBJECT,
        role_object=ROLE_OBJECT,
    )


__all__ = [
    "read_chunks_and_extract",
    "run_claim_extraction_runtime",
    "run_claim_extraction_runtime_default",
]