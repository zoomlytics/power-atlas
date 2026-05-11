from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.contracts.pipeline import (
    PipelineContractSnapshot,
    is_pipeline_contract_snapshot,
)
from power_atlas.settings import Neo4jSettings


def _default_runtime_runner() -> Callable[..., dict[str, Any]]:
    from power_atlas.pdf_ingest_runner import run_pdf_ingest_runtime_default

    return run_pdf_ingest_runtime_default


def _default_config_runner(
    config: Any,
    run_id: str | None = None,
    *,
    fixtures_dir: Path | None = None,
    pdf_filename: str | None = None,
    dataset_id: str | None = None,
    index_name: str | None = None,
    chunk_label: str | None = None,
    embedding_property: str | None = None,
    embedding_dimensions: int | None = None,
    embedder_model: str | None = None,
    chunk_stride: int | None = None,
    pipeline_contract: PipelineContractSnapshot | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    openai_model: str | None = None,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    return run_pdf_ingest(
        config,
        run_id,
        fixtures_dir=fixtures_dir,
        pdf_filename=pdf_filename,
        dataset_id=dataset_id,
        index_name=index_name,
        chunk_label=chunk_label,
        embedding_property=embedding_property,
        embedding_dimensions=embedding_dimensions,
        embedder_model=embedder_model,
        chunk_stride=chunk_stride,
        pipeline_contract=pipeline_contract,
        neo4j_settings=neo4j_settings,
        openai_model=openai_model,
        dataset_name=dataset_name,
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
        "run_pdf_ingest requires a pipeline contract from RequestContext/AppContext-backed config or an explicit pipeline_contract argument"
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
        "Live PDF ingest requires config.settings.neo4j or an explicit "
        "neo4j_settings argument from RequestContext/AppContext-backed config"
    )


def openai_model_from_config(
    config: object,
    openai_model: str | None = None,
) -> str:
    if isinstance(openai_model, str) and openai_model:
        return openai_model
    config_settings = getattr(config, "settings", None)
    settings_openai_model = getattr(config_settings, "openai_model", None)
    if isinstance(settings_openai_model, str) and settings_openai_model:
        return settings_openai_model
    raise ValueError(
        "PDF ingest requires config.settings.openai_model or an explicit "
        "openai_model argument from RequestContext/AppContext-backed config"
    )


def run_pdf_ingest(
    config: Any,
    run_id: str | None = None,
    *,
    fixtures_dir: Path | None = None,
    pdf_filename: str | None = None,
    dataset_id: str | None = None,
    index_name: str | None = None,
    chunk_label: str | None = None,
    embedding_property: str | None = None,
    embedding_dimensions: int | None = None,
    embedder_model: str | None = None,
    chunk_stride: int | None = None,
    pipeline_contract: PipelineContractSnapshot | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    openai_model: str | None = None,
    dataset_name: str | None = None,
    runtime_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_pipeline_contract = resolve_pipeline_contract(config, pipeline_contract)
    resolved_openai_model = openai_model_from_config(config, openai_model)
    resolved_neo4j_settings = neo4j_settings_from_config(config, neo4j_settings)
    if dataset_name is None:
        config_settings = getattr(config, "settings", None)
        settings_dataset_name = getattr(config_settings, "dataset_name", None)
        if isinstance(settings_dataset_name, str) and settings_dataset_name:
            dataset_name = settings_dataset_name
        else:
            dataset_name = getattr(config, "dataset_name", None)
    resolved_runtime_runner = runtime_runner or _default_runtime_runner()
    return resolved_runtime_runner(
        config=config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        pdf_filename=pdf_filename,
        dataset_id=dataset_id,
        index_name=index_name,
        chunk_label=chunk_label,
        embedding_property=embedding_property,
        embedding_dimensions=embedding_dimensions,
        embedder_model=embedder_model,
        chunk_stride=chunk_stride,
        pipeline_contract=resolved_pipeline_contract,
        neo4j_settings=resolved_neo4j_settings,
        openai_model=resolved_openai_model,
        dataset_name=dataset_name,
    )


def run_pdf_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    pdf_filename: str | None = None,
    dataset_id: str | None = None,
    index_name: str | None = None,
    chunk_label: str | None = None,
    embedding_property: str | None = None,
    embedding_dimensions: int | None = None,
    embedder_model: str | None = None,
    chunk_stride: int | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pipeline_contract = request_context.pipeline_contract
    resolved_config_runner = config_runner or _default_config_runner
    return resolved_config_runner(
        request_context.config,
        request_context.run_id,
        fixtures_dir=fixtures_dir,
        pdf_filename=pdf_filename,
        dataset_id=dataset_id,
        index_name=index_name or pipeline_contract.chunk_embedding_index_name,
        chunk_label=chunk_label or pipeline_contract.chunk_embedding_label,
        embedding_property=embedding_property or pipeline_contract.chunk_embedding_property,
        embedding_dimensions=(
            embedding_dimensions
            if embedding_dimensions is not None
            else pipeline_contract.chunk_embedding_dimensions
        ),
        embedder_model=embedder_model or pipeline_contract.embedder_model_name,
        chunk_stride=(
            chunk_stride if chunk_stride is not None else pipeline_contract.chunk_fallback_stride
        ),
        pipeline_contract=pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
        openai_model=request_context.settings.openai_model,
        dataset_name=request_context.settings.dataset_name,
    )


__all__ = [
    "neo4j_settings_from_config",
    "openai_model_from_config",
    "resolve_pipeline_contract",
    "run_pdf_ingest",
    "run_pdf_ingest_request_context",
]