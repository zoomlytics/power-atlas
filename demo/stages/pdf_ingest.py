from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from power_atlas.context import RequestContext
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.pdf_ingest_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    openai_model_from_config as _openai_model_from_config,
    resolve_pipeline_contract as _resolve_pipeline_contract,
    run_pdf_ingest as _run_pdf_ingest,
    run_pdf_ingest_request_context as _run_pdf_ingest_request_context,
)
from power_atlas.pdf_ingest_runner import (
    DEFAULT_PDF_FILENAME as _DEFAULT_PDF_FILENAME,
    dataset_metadata_from_fixtures_root as _dataset_metadata_from_fixtures_root,
    normalize_pipeline_result as _normalize_pipeline_result,
    record_as_mapping as _record_as_mapping,
    require_positive_int as _require_positive_int,
    resolve_pdf_dataset as _resolve_pdf_dataset,
    run_pdf_ingest_runtime as _run_pdf_ingest_runtime_impl,
    run_pipeline_with_cleanup as _run_pipeline_with_cleanup_impl,
    sha256_file,
)
from power_atlas.pdf_ingest_runtime import run_pdf_ingest_live
from power_atlas.settings import Neo4jSettings
from demo.cypher_utils import validate_cypher_identifier as _validate_cypher_identifier

_logger = logging.getLogger(__name__)
async def _run_pipeline_with_cleanup(pipeline: Any, run_params: dict[str, Any]) -> Any:
    return await _run_pipeline_with_cleanup_impl(
        pipeline,
        run_params,
        logger=_logger,
    )


def _run_pdf_ingest_impl(
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
    return _run_pdf_ingest(
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
        runtime_runner=_run_pdf_ingest_runtime,
    )


def _run_pdf_ingest_runtime(
    *,
    config: Any,
    run_id: str | None,
    fixtures_dir: Path | None,
    pdf_filename: str | None,
    dataset_id: str | None,
    index_name: str | None,
    chunk_label: str | None,
    embedding_property: str | None,
    embedding_dimensions: int | None,
    embedder_model: str | None,
    chunk_stride: int | None,
    pipeline_contract: PipelineContractSnapshot,
    neo4j_settings: Neo4jSettings,
    openai_model: str,
    dataset_name: str | None,
) -> dict[str, Any]:
    return _run_pdf_ingest_runtime_impl(
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
        pipeline_contract=pipeline_contract,
        neo4j_settings=neo4j_settings,
        openai_model=openai_model,
        dataset_name=dataset_name,
        validate_cypher_identifier_fn=_validate_cypher_identifier,
        live_runner=run_pdf_ingest_live,
        run_pipeline_with_cleanup_fn=_run_pipeline_with_cleanup,
        record_as_mapping_fn=_record_as_mapping,
        normalize_pipeline_result_fn=_normalize_pipeline_result,
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
) -> dict[str, Any]:
    """Run PDF ingest using request-scoped context as the primary input."""
    return _run_pdf_ingest_request_context(
        request_context,
        fixtures_dir=fixtures_dir,
        pdf_filename=pdf_filename,
        dataset_id=dataset_id,
        index_name=index_name,
        chunk_label=chunk_label,
        embedding_property=embedding_property,
        embedding_dimensions=embedding_dimensions,
        embedder_model=embedder_model,
        chunk_stride=chunk_stride,
        config_runner=_run_pdf_ingest_impl,
    )


__all__ = ["run_pdf_ingest_request_context", "sha256_file"]
