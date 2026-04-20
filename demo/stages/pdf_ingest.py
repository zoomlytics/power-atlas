from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from power_atlas.bootstrap import require_openai_api_key
from power_atlas.context import RequestContext
from power_atlas.contracts import (
    DatasetRoot,
    FIXTURES_DIR,
    PDF_PIPELINE_CONFIG_PATH,
    resolve_dataset_root,
)
from power_atlas.contracts.pipeline import PipelineContractSnapshot, is_pipeline_contract_snapshot
from power_atlas.pdf_ingest_runtime import run_pdf_ingest_live
from power_atlas.settings import Neo4jSettings
from demo.cypher_utils import validate_cypher_identifier as _validate_cypher_identifier
from demo.stages.pipeline_contract_compat import get_stage_pipeline_contract_value
from power_atlas.contracts import make_run_id

# Local fallback to avoid importing a private implementation detail from
# power_atlas.contracts.paths. Resolved datasets should use DatasetRoot.pdf_filename.
_DEFAULT_PDF_FILENAME = "chain_of_custody.pdf"
_logger = logging.getLogger(__name__)
_PIPELINE_CONTRACT_EXPORTS = {
    "CHUNK_EMBEDDING_DIMENSIONS": "chunk_embedding_dimensions",
    "CHUNK_EMBEDDING_INDEX_NAME": "chunk_embedding_index_name",
    "CHUNK_EMBEDDING_LABEL": "chunk_embedding_label",
    "CHUNK_EMBEDDING_PROPERTY": "chunk_embedding_property",
    "CHUNK_FALLBACK_STRIDE": "chunk_fallback_stride",
    "EMBEDDER_MODEL_NAME": "embedder_model_name",
}


def _pipeline_contract_value(
    name: str,
    pipeline_contract: PipelineContractSnapshot,
) -> Any:
    return get_stage_pipeline_contract_value(name, _PIPELINE_CONTRACT_EXPORTS, pipeline_contract)


def _resolve_pipeline_contract(
    config: Any,
    pipeline_contract: PipelineContractSnapshot | None,
) -> PipelineContractSnapshot:
    if pipeline_contract is not None:
        return pipeline_contract
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if is_pipeline_contract_snapshot(config_pipeline_contract):
        return config_pipeline_contract
    raise ValueError(
        "run_pdf_ingest requires a pipeline contract from RequestContext/AppContext-derived config or an explicit pipeline_contract argument"
    )


def _dataset_metadata_from_fixtures_root(fixtures_root: Path) -> tuple[str, str]:
    manifest_path = fixtures_root / "manifest.json"
    dataset_id = fixtures_root.name
    pdf_filename = _DEFAULT_PDF_FILENAME
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        if isinstance(manifest, dict):
            candidate_id = manifest.get("dataset")
            if isinstance(candidate_id, str) and candidate_id:
                dataset_id = candidate_id
            for entry in manifest.get("provenance", []):
                if isinstance(entry, dict) and entry.get("kind") == "pdf":
                    candidate_pdf = Path(str(entry.get("path", ""))).name
                    if candidate_pdf:
                        pdf_filename = candidate_pdf
                        break
    return dataset_id, pdf_filename


def _resolve_pdf_dataset(
    config: Any,
    fixtures_dir: Path | None,
    dataset_id: str | None,
    pdf_filename: str | None,
) -> tuple[Path, str, str]:
    if fixtures_dir is None:
        dataset_root: DatasetRoot = resolve_dataset_root(getattr(config, "dataset_name", None))
        effective_dataset_id = dataset_id if isinstance(dataset_id, str) and dataset_id else dataset_root.dataset_id
        effective_pdf_filename = pdf_filename or dataset_root.pdf_filename
        return dataset_root.root, effective_dataset_id, effective_pdf_filename

    derived_dataset_id, derived_pdf_filename = _dataset_metadata_from_fixtures_root(fixtures_dir)
    effective_dataset_id = dataset_id if isinstance(dataset_id, str) and dataset_id else derived_dataset_id
    effective_pdf_filename = pdf_filename or derived_pdf_filename
    return fixtures_dir, effective_dataset_id, effective_pdf_filename


def _neo4j_settings_from_config(config: object) -> Neo4jSettings:
    neo4j_uri = getattr(config, "neo4j_uri", None)
    neo4j_username = getattr(config, "neo4j_username", None)
    neo4j_password = getattr(config, "neo4j_password", None)
    neo4j_database = getattr(config, "neo4j_database", None)

    missing_cfg = [
        key
        for key, value in (
            ("neo4j_uri", neo4j_uri),
            ("neo4j_username", neo4j_username),
            ("neo4j_password", neo4j_password),
        )
        if not value
    ]
    if missing_cfg:
        raise ValueError(f"Live PDF ingest requires config attributes: {', '.join(missing_cfg)}")

    return Neo4jSettings(
        uri=str(neo4j_uri),
        username=str(neo4j_username),
        password=str(neo4j_password),
        database=str(neo4j_database) if neo4j_database else Neo4jSettings.database,
    )


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                hasher.update(chunk)
    except OSError as exc:
        if hasattr(exc, "add_note"):  # pragma: no cover - Python 3.11+
            exc.add_note(f"While hashing file {path}")
        raise
    return hasher.hexdigest()


def _record_as_mapping(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    if isinstance(record, dict):
        return record
    try:
        return record.data()  # type: ignore[union-attr]
    except AttributeError:
        return {}


def _normalize_pipeline_result(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        try:
            summary = repr(value)
        except Exception:  # pragma: no cover - defensive
            summary = f"<unrepresentable {type(value).__name__} object>"
        max_len = 200
        if len(summary) > max_len:
            summary = summary[: max_len - 3] + "..."
        return {"type": type(value).__name__, "summary": summary}


def _require_positive_int(value: int, param_name: str) -> int:
    """Validate positive integer overrides, explicitly rejecting bool since it subclasses int."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{param_name} must be a positive integer (int type), got {value!r}")
    if value <= 0:
        raise ValueError(f"{param_name} must be a positive integer (int type), got {value!r}")
    return value


async def _run_pipeline_with_cleanup(pipeline: Any, run_params: dict[str, Any]) -> Any:
    """Run the pipeline and close all LLM async clients within the same event loop.

    The vendor PipelineRunner.close() only tears down Neo4j drivers.  Any LLM
    that owns an httpx AsyncClient (e.g. OpenAI) must also be explicitly closed
    before the event loop exits; otherwise its garbage-collection finaliser fires
    after the loop is shut down and prints an 'Event loop is closed' traceback.
    """
    try:
        return await pipeline.run(run_params)
    finally:
        config = getattr(pipeline, "config", None)
        if config is not None:
            global_data = getattr(config, "_global_data", None) or {}
            llm_config: dict[str, Any] = global_data.get("llm_config", {})
            for llm in llm_config.values():
                async_client = getattr(llm, "async_client", None)
                if async_client is not None and callable(getattr(async_client, "close", None)):
                    try:
                        await async_client.close()
                    except Exception:
                        _logger.warning(
                            "Failed to close async_client for LLM %r during pipeline cleanup",
                            llm,
                            exc_info=True,
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
) -> dict[str, Any]:
    resolved_pipeline_contract = _resolve_pipeline_contract(config, None)
    _pdf_filename = pdf_filename or _DEFAULT_PDF_FILENAME
    if (
        _pdf_filename in (".", "..")
        or Path(_pdf_filename).name != _pdf_filename
        or not _pdf_filename.lower().endswith(".pdf")
    ):
        raise ValueError(
            f"pdf_filename must be a plain .pdf basename without path separators, got {_pdf_filename!r}"
        )
    fixtures_root, effective_dataset_id, _pdf_filename = _resolve_pdf_dataset(
        config,
        fixtures_dir,
        dataset_id,
        _pdf_filename,
    )
    pdf_base_dir = (fixtures_root / "unstructured").resolve()
    pdf_path = (pdf_base_dir / _pdf_filename).resolve()
    try:
        pdf_path.relative_to(pdf_base_dir)
    except ValueError as exc:
        raise ValueError(
            f"pdf_filename {_pdf_filename!r} resolves outside the unstructured fixtures directory"
        ) from exc
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")
    pdf_file_path = str(pdf_path)
    pdf_source_uri = pdf_path.as_uri()
    effective_index_name = index_name or _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME", resolved_pipeline_contract)
    effective_chunk_label = chunk_label or _pipeline_contract_value("CHUNK_EMBEDDING_LABEL", resolved_pipeline_contract)
    effective_embedding_property = embedding_property or _pipeline_contract_value(
        "CHUNK_EMBEDDING_PROPERTY", resolved_pipeline_contract
    )
    effective_embedding_dimensions = (
        _require_positive_int(embedding_dimensions, "embedding_dimensions")
        if embedding_dimensions is not None
        else _pipeline_contract_value("CHUNK_EMBEDDING_DIMENSIONS", resolved_pipeline_contract)
    )
    effective_embedder_model = embedder_model or _pipeline_contract_value("EMBEDDER_MODEL_NAME", resolved_pipeline_contract)
    effective_chunk_stride = (
        _require_positive_int(chunk_stride, "chunk_stride")
        if chunk_stride is not None
        else _pipeline_contract_value("CHUNK_FALLBACK_STRIDE", resolved_pipeline_contract)
    )
    stage_run_id = run_id or make_run_id("unstructured_ingest")
    run_root = config.output_dir / "runs" / stage_run_id
    pdf_ingest_dir = run_root / "pdf_ingest"
    pdf_ingest_dir.mkdir(parents=True, exist_ok=True)
    ingest_summary_path = pdf_ingest_dir / "ingest_summary.json"
    pdf_fingerprint_sha256 = sha256_file(pdf_path)
    if PDF_PIPELINE_CONFIG_PATH.is_file():
        pipeline_config_sha256 = sha256_file(PDF_PIPELINE_CONFIG_PATH)
    elif config.dry_run:
        pipeline_config_sha256 = None
    else:
        raise FileNotFoundError(f"Required PDF pipeline config not found: {PDF_PIPELINE_CONFIG_PATH}")
    summary_counts = {"documents": 0, "pages": 0, "chunks": 0}
    extraction_warnings: list[Any] = []

    if config.dry_run:
        ingest_summary = {
            "run_id": stage_run_id,
            "dataset_id": effective_dataset_id,
            "source_uri": pdf_source_uri,
            "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
            "counts": summary_counts,
            "embedding_model": effective_embedder_model,
            "embedding_dimensions": effective_embedding_dimensions,
            "vector_index": {
                "index_name": effective_index_name,
                "label": effective_chunk_label,
                "embedding_property": effective_embedding_property,
                "dimensions": effective_embedding_dimensions,
                "creation_strategy": "dry_run",
            },
            "warnings": extraction_warnings,
            "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
            "pipeline_config_sha256": pipeline_config_sha256,
        }
        ingest_summary_path.write_text(json.dumps(ingest_summary, indent=2), encoding="utf-8")
        return {
            "status": "dry_run",
            "documents": [pdf_source_uri],
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + PageAwareFixedSizeSplitter",
            "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
            "pipeline_config_sha256": pipeline_config_sha256,
            "vector_index": {
                "index_name": effective_index_name,
                "label": effective_chunk_label,
                "embedding_property": effective_embedding_property,
                "dimensions": effective_embedding_dimensions,
                "creation_strategy": "dry_run",
            },
            "pdf_ingest_dir": str(pdf_ingest_dir),
            "ingest_summary_path": str(ingest_summary_path),
            "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
            "counts": summary_counts,
            "embedding_model": effective_embedder_model,
            "warnings": extraction_warnings,
        }

    require_openai_api_key("Set OPENAI_API_KEY when using --live ingest-pdf")

    from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner

    _validate_cypher_identifier(effective_index_name, "index name")
    _validate_cypher_identifier(effective_chunk_label, "label")
    _validate_cypher_identifier(effective_embedding_property, "property")

    neo4j_settings = _neo4j_settings_from_config(config)

    live_result = run_pdf_ingest_live(
        neo4j_settings,
        stage_run_id=stage_run_id,
        pdf_file_path=pdf_file_path,
        pdf_source_uri=pdf_source_uri,
        openai_model=config.openai_model,
        effective_dataset_id=effective_dataset_id,
        effective_index_name=effective_index_name,
        effective_chunk_label=effective_chunk_label,
        effective_embedding_property=effective_embedding_property,
        effective_embedding_dimensions=effective_embedding_dimensions,
        effective_chunk_stride=effective_chunk_stride,
        pipeline_config_path=PDF_PIPELINE_CONFIG_PATH,
        pipeline_runner_cls=PipelineRunner,
        run_pipeline_with_cleanup=_run_pipeline_with_cleanup,
        record_as_mapping=_record_as_mapping,
    )
    index_creation_strategy = live_result.index_creation_strategy
    pipeline_result = live_result.pipeline_result
    summary_counts = live_result.summary_counts
    extraction_warnings = live_result.extraction_warnings

    ingest_summary = {
        "run_id": stage_run_id,
        "dataset_id": effective_dataset_id,
        "source_uri": pdf_source_uri,
        "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
        "counts": summary_counts,
        "embedding_model": effective_embedder_model,
        "embedding_dimensions": effective_embedding_dimensions,
        "vector_index": {
            "index_name": effective_index_name,
            "label": effective_chunk_label,
            "embedding_property": effective_embedding_property,
            "dimensions": effective_embedding_dimensions,
            "creation_strategy": index_creation_strategy or "unknown",
        },
        "warnings": extraction_warnings,
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        "pipeline_config_sha256": pipeline_config_sha256,
    }
    ingest_summary_path.write_text(json.dumps(ingest_summary, indent=2), encoding="utf-8")

    return {
        "status": "live",
        "documents": [pdf_source_uri],
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        "pipeline_config_sha256": pipeline_config_sha256,
        "vector_index": {
            "index_name": effective_index_name,
            "label": effective_chunk_label,
            "embedding_property": effective_embedding_property,
            "dimensions": effective_embedding_dimensions,
            "creation_strategy": index_creation_strategy or "unknown",
        },
        "pipeline_result": _normalize_pipeline_result(pipeline_result),
        "provenance": {
            "run_id": stage_run_id,
            "dataset_id": effective_dataset_id,
            "source_uri": pdf_source_uri,
            "chunk_order_property": "chunk_order",
            "chunk_id_property": "chunk_id",
            "chunk_index_property": "chunk_index",
            "page_property": "page_number",
            "start_char_property": "start_char",
            "end_char_property": "end_char",
        },
        "pdf_ingest_dir": str(pdf_ingest_dir),
        "ingest_summary_path": str(ingest_summary_path),
        "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
        "counts": summary_counts,
        "embedding_model": effective_embedder_model,
        "warnings": extraction_warnings,
    }


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
    pipeline_contract = request_context.pipeline_contract
    return run_pdf_ingest(
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
    )


__all__ = ["run_pdf_ingest", "run_pdf_ingest_request_context", "sha256_file"]
