from __future__ import annotations

import json
from typing import Any

from power_atlas.adapters.llm import build_llm as build_openai_llm
from power_atlas.bootstrap import require_openai_api_key
from power_atlas.claim_extraction_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    openai_model_from_config as _openai_model_from_config,
    resolve_claim_extraction_policy as _resolve_claim_extraction_policy,
    resolve_pipeline_contract as _resolve_pipeline_contract,
    run_claim_extraction as _run_claim_extraction_impl_entrypoint,
    run_claim_extraction_request_context as _run_claim_extraction_request_context_impl,
)
from power_atlas.context import RequestContext
from power_atlas.contracts import ClaimExtractionPolicy, get_default_claim_extraction_policy
from power_atlas.contracts.pipeline import PipelineContractSnapshot, is_pipeline_contract_snapshot
from power_atlas.contracts.prompts import PROMPT_IDS
from power_atlas.claim_extraction_runtime import run_claim_extraction_live
from power_atlas.settings import Neo4jSettings

async def _async_read_chunks_and_extract(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str,
    model_name: str,
    pipeline_contract: PipelineContractSnapshot,
    claim_extraction_policy: ClaimExtractionPolicy | None = None,
) -> tuple[Any, list[Any], Any]:
    from neo4j_graphrag.experimental.components.entity_relation_extractor import LLMEntityRelationExtractor
    from power_atlas.contracts import (
        claim_extraction_lexical_config,
        claim_extraction_schema,
    )
    from demo.io import RunScopedNeo4jChunkReader
    resolved_claim_extraction_policy = _resolve_claim_extraction_policy(claim_extraction_policy)
    lexical_config = claim_extraction_lexical_config(
        pipeline_contract,
        resolved_claim_extraction_policy.ontology,
    )
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
            schema=claim_extraction_schema(resolved_claim_extraction_policy.ontology),
            lexical_graph_config=lexical_config,
        )
    finally:
        await llm.async_client.close()
    return graph, text_chunks.chunks, lexical_config


def _run_claim_and_mention_extraction_impl(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot | None = None,
    claim_extraction_policy: ClaimExtractionPolicy | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_claim_extraction_impl_entrypoint(
        config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=claim_extraction_policy,
        neo4j_settings=neo4j_settings,
        model_name=model_name,
        runtime_runner=_run_claim_and_mention_extraction_runtime,
    )


def _run_claim_and_mention_extraction_runtime(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot,
    claim_extraction_policy: ClaimExtractionPolicy,
    neo4j_settings: Neo4jSettings,
    model_name: str,
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

    require_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live claim extraction."
    )

    from power_atlas.claim_participation_edges import (
        ROLE_OBJECT,
        ROLE_SUBJECT,
        build_participation_edges,
    )
    from power_atlas.extraction_rows import prepare_extracted_rows
    from power_atlas.extraction_writes import write_all_extraction_data

    live_result = run_claim_extraction_live(
        neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
        model_name=model_name,
        neo4j_database=neo4j_settings.database,
        pipeline_contract=pipeline_contract,
        read_chunks_and_extract=lambda *args, **kwargs: _async_read_chunks_and_extract(
            *args,
            **kwargs,
            claim_extraction_policy=claim_extraction_policy,
        ),
        prepare_rows=prepare_extracted_rows,
        build_edges=build_participation_edges,
        write_rows=write_all_extraction_data,
    )
    text_chunks = live_result.text_chunks
    claim_rows = live_result.claim_rows
    mention_rows = live_result.mention_rows
    edge_rows = live_result.edge_rows
    warnings = live_result.warnings

    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {chunk_id for row in all_extracted_rows for chunk_id in row["chunk_ids"]}
    subject_edges = sum(1 for e in edge_rows if e["role"] == ROLE_SUBJECT)
    object_edges = sum(1 for e in edge_rows if e["role"] == ROLE_OBJECT)
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "extractor_model": model_name,
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
    return _run_claim_extraction_request_context_impl(
        request_context,
        config_runner=_run_claim_and_mention_extraction_impl,
    )


__all__ = ["run_claim_and_mention_extraction_request_context"]
