from __future__ import annotations

from typing import Any

from power_atlas.claim_extraction_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    openai_model_from_config as _openai_model_from_config,
    resolve_claim_extraction_policy as _resolve_claim_extraction_policy,
    resolve_pipeline_contract as _resolve_pipeline_contract,
    run_claim_extraction as _run_claim_extraction_impl_entrypoint,
    run_claim_extraction_request_context as _run_claim_extraction_request_context_impl,
)
from power_atlas.claim_extraction_runner import (
    run_claim_extraction_runtime_default as _run_claim_extraction_runtime_default,
)
from power_atlas.context import RequestContext
from power_atlas.contracts import ClaimExtractionPolicy
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.settings import Neo4jSettings


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
    from demo.io import RunScopedNeo4jChunkReader

    return _run_claim_extraction_runtime_default(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=claim_extraction_policy,
        neo4j_settings=neo4j_settings,
        model_name=model_name,
        chunk_reader_cls=RunScopedNeo4jChunkReader,
    )


def run_claim_and_mention_extraction_request_context(request_context: RequestContext) -> dict[str, Any]:
    """Run claim extraction using request-scoped context as the primary input."""
    return _run_claim_extraction_request_context_impl(
        request_context,
        config_runner=_run_claim_and_mention_extraction_impl,
    )


__all__ = ["run_claim_and_mention_extraction_request_context"]
