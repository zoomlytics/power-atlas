from __future__ import annotations

from typing import Any, Callable

from power_atlas.context import RequestContext, RequestRuntime
from power_atlas.contracts import ClaimExtractionPolicy, get_default_claim_extraction_policy
from power_atlas.contracts.pipeline import (
    PipelineContractSnapshot,
    is_pipeline_contract_snapshot,
)
from power_atlas.settings import Neo4jSettings


def resolve_claim_extraction_policy(
    claim_extraction_policy: ClaimExtractionPolicy | None,
) -> ClaimExtractionPolicy:
    return (
        get_default_claim_extraction_policy()
        if claim_extraction_policy is None
        else claim_extraction_policy
    )


def resolve_pipeline_contract(
    config: Any,
    pipeline_contract: PipelineContractSnapshot | None,
) -> PipelineContractSnapshot:
    if pipeline_contract is not None:
        return pipeline_contract
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if is_pipeline_contract_snapshot(config_pipeline_contract):
        return config_pipeline_contract
    raise ValueError(
        "claim extraction requires a pipeline contract from RequestContext/AppContext-backed config or an explicit pipeline_contract argument"
    )


def neo4j_settings_from_config(
    config: object,
    neo4j_settings: Neo4jSettings | None = None,
) -> Neo4jSettings:
    if neo4j_settings is not None:
        return neo4j_settings
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Live claim extraction requires config.settings.neo4j or an explicit "
        "neo4j_settings argument from RequestContext/AppContext-backed config"
    )


def openai_model_from_config(
    config: object,
    model_name: str | None = None,
) -> str:
    if isinstance(model_name, str) and model_name:
        return model_name
    config_settings = getattr(config, "settings", None)
    settings_openai_model = getattr(config_settings, "openai_model", None)
    if isinstance(settings_openai_model, str) and settings_openai_model:
        return settings_openai_model
    raise ValueError(
        "Claim extraction requires config.settings.openai_model or an explicit "
        "model_name argument from RequestContext/AppContext-backed config"
    )


def _default_runtime_runner() -> Callable[..., dict[str, Any]]:
    from power_atlas.claim_extraction_runner import run_claim_extraction_runtime_default

    return run_claim_extraction_runtime_default


def _default_config_runner(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot | None = None,
    claim_extraction_policy: ClaimExtractionPolicy | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return run_claim_extraction(
        config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=pipeline_contract,
        claim_extraction_policy=claim_extraction_policy,
        neo4j_settings=neo4j_settings,
        model_name=model_name,
    )


def run_claim_extraction(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    pipeline_contract: PipelineContractSnapshot | None = None,
    claim_extraction_policy: ClaimExtractionPolicy | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    model_name: str | None = None,
    runtime_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_pipeline_contract = resolve_pipeline_contract(config, pipeline_contract)
    resolved_model_name = openai_model_from_config(config, model_name)
    resolved_neo4j_settings = neo4j_settings_from_config(config, neo4j_settings)
    resolved_runtime_runner = runtime_runner or _default_runtime_runner()
    return resolved_runtime_runner(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        pipeline_contract=resolved_pipeline_contract,
        claim_extraction_policy=resolve_claim_extraction_policy(claim_extraction_policy),
        neo4j_settings=resolved_neo4j_settings,
        model_name=resolved_model_name,
    )


def run_claim_extraction_request_context(
    request_context: RequestContext,
    *,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return run_claim_extraction_runtime(
        request_context.runtime,
        config_runner=config_runner,
    )


def run_claim_extraction_runtime(
    request_runtime: RequestRuntime,
    *,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_config_runner = config_runner or _default_config_runner
    return resolved_config_runner(
        request_runtime.config,
        run_id=request_runtime.run_id,
        source_uri=request_runtime.source_uri,
        pipeline_contract=request_runtime.pipeline_contract,
        claim_extraction_policy=request_runtime.policies.claim_extraction,
        neo4j_settings=request_runtime.settings.neo4j,
        model_name=request_runtime.settings.openai_model,
    )


__all__ = [
    "neo4j_settings_from_config",
    "openai_model_from_config",
    "resolve_claim_extraction_policy",
    "resolve_pipeline_contract",
    "run_claim_extraction",
    "run_claim_extraction_runtime",
    "run_claim_extraction_request_context",
]