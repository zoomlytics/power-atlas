from __future__ import annotations

import json
from typing import Any

from power_atlas.adapters.llm import build_llm as build_openai_llm
from power_atlas.claim_extraction_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    openai_model_from_config as _openai_model_from_config,
    resolve_claim_extraction_policy as _resolve_claim_extraction_policy,
    resolve_pipeline_contract as _resolve_pipeline_contract,
    run_claim_extraction as _run_claim_extraction_impl_entrypoint,
    run_claim_extraction_request_context as _run_claim_extraction_request_context_impl,
)
from power_atlas.claim_extraction_runner import read_chunks_and_extract as _read_chunks_and_extract_impl
from power_atlas.claim_extraction_runner import (
    run_claim_extraction_runtime as _run_claim_and_mention_extraction_runtime_impl,
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
    from demo.io import RunScopedNeo4jChunkReader

    resolved_claim_extraction_policy = _resolve_claim_extraction_policy(claim_extraction_policy)
    return await _read_chunks_and_extract_impl(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        neo4j_database=neo4j_database,
        model_name=model_name,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=resolved_claim_extraction_policy,
        chunk_reader_cls=RunScopedNeo4jChunkReader,
        llm_builder=build_openai_llm,
    )


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
    from power_atlas.claim_participation_edges import (
        ROLE_OBJECT,
        ROLE_SUBJECT,
        build_participation_edges,
    )
    from power_atlas.extraction_rows import prepare_extracted_rows
    from power_atlas.extraction_writes import write_all_extraction_data

    return _run_claim_and_mention_extraction_runtime_impl(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=claim_extraction_policy,
        neo4j_settings=neo4j_settings,
        model_name=model_name,
        read_chunks_and_extract=lambda *args, **kwargs: _async_read_chunks_and_extract(
            *args,
            **kwargs,
            claim_extraction_policy=claim_extraction_policy,
        ),
        prepare_rows=prepare_extracted_rows,
        build_edges=build_participation_edges,
        write_rows=write_all_extraction_data,
        role_subject=ROLE_SUBJECT,
        role_object=ROLE_OBJECT,
        live_runner=run_claim_extraction_live,
    )


def run_claim_and_mention_extraction_request_context(request_context: RequestContext) -> dict[str, Any]:
    """Run claim extraction using request-scoped context as the primary input."""
    return _run_claim_extraction_request_context_impl(
        request_context,
        config_runner=_run_claim_and_mention_extraction_impl,
    )


__all__ = ["run_claim_and_mention_extraction_request_context"]
