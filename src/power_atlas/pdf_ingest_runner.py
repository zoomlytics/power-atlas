from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable

from power_atlas.bootstrap import require_openai_api_key
from power_atlas.contracts import DatasetRoot, PDF_PIPELINE_CONFIG_PATH, make_run_id, resolve_dataset_root
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.neo4j_io import validate_cypher_identifier
from power_atlas.pdf_ingest_runtime import run_pdf_ingest_live
from power_atlas.settings import Neo4jSettings


DEFAULT_PDF_FILENAME = "chain_of_custody.pdf"
_logger = logging.getLogger(__name__)


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


def dataset_metadata_from_fixtures_root(fixtures_root: Path) -> tuple[str, str]:
    manifest_path = fixtures_root / "manifest.json"
    dataset_id = fixtures_root.name
    pdf_filename = DEFAULT_PDF_FILENAME
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


def resolve_pdf_dataset(
    *,
    dataset_name: str | None,
    fixtures_dir: Path | None,
    dataset_id: str | None,
    pdf_filename: str | None,
) -> tuple[Path, str, str]:
    if fixtures_dir is None:
        dataset_root: DatasetRoot = resolve_dataset_root(dataset_name)
        effective_dataset_id = (
            dataset_id if isinstance(dataset_id, str) and dataset_id else dataset_root.dataset_id
        )
        effective_pdf_filename = pdf_filename or dataset_root.pdf_filename
        return dataset_root.root, effective_dataset_id, effective_pdf_filename

    derived_dataset_id, derived_pdf_filename = dataset_metadata_from_fixtures_root(fixtures_dir)
    effective_dataset_id = dataset_id if isinstance(dataset_id, str) and dataset_id else derived_dataset_id
    effective_pdf_filename = pdf_filename or derived_pdf_filename
    return fixtures_dir, effective_dataset_id, effective_pdf_filename


def record_as_mapping(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    if isinstance(record, dict):
        return record
    try:
        return record.data()  # type: ignore[union-attr]
    except AttributeError:
        return {}


def normalize_pipeline_result(value: Any) -> Any:
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


def require_positive_int(value: int, param_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{param_name} must be a positive integer (int type), got {value!r}")
    if value <= 0:
        raise ValueError(f"{param_name} must be a positive integer (int type), got {value!r}")
    return value


async def run_pipeline_with_cleanup(
    pipeline: Any,
    run_params: dict[str, Any],
    *,
    logger: Any | None = None,
) -> Any:
    active_logger = _logger if logger is None else logger
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
                        active_logger.warning(
                            "Failed to close async_client for LLM %r during pipeline cleanup",
                            llm,
                            exc_info=True,
                        )


def run_pdf_ingest_runtime(
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
    require_openai_api_key_fn: Callable[..., None] = require_openai_api_key,
    validate_cypher_identifier_fn: Callable[[str, str], Any] = validate_cypher_identifier,
    live_runner: Callable[..., Any] = run_pdf_ingest_live,
    run_pipeline_with_cleanup_fn: Callable[..., Any] = run_pipeline_with_cleanup,
    record_as_mapping_fn: Callable[[Any], dict[str, Any]] = record_as_mapping,
    normalize_pipeline_result_fn: Callable[[Any], Any] = normalize_pipeline_result,
) -> dict[str, Any]:
    resolved_pdf_filename = pdf_filename or DEFAULT_PDF_FILENAME
    if (
        resolved_pdf_filename in (".", "..")
        or Path(resolved_pdf_filename).name != resolved_pdf_filename
        or not resolved_pdf_filename.lower().endswith(".pdf")
    ):
        raise ValueError(
            f"pdf_filename must be a plain .pdf basename without path separators, got {resolved_pdf_filename!r}"
        )

    fixtures_root, effective_dataset_id, resolved_pdf_filename = resolve_pdf_dataset(
        dataset_name=dataset_name,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        pdf_filename=resolved_pdf_filename,
    )
    pdf_base_dir = (fixtures_root / "unstructured").resolve()
    pdf_path = (pdf_base_dir / resolved_pdf_filename).resolve()
    try:
        pdf_path.relative_to(pdf_base_dir)
    except ValueError as exc:
        raise ValueError(
            f"pdf_filename {resolved_pdf_filename!r} resolves outside the unstructured fixtures directory"
        ) from exc
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")

    pdf_file_path = str(pdf_path)
    pdf_source_uri = pdf_path.as_uri()
    effective_index_name = index_name or pipeline_contract.chunk_embedding_index_name
    effective_chunk_label = chunk_label or pipeline_contract.chunk_embedding_label
    effective_embedding_property = embedding_property or pipeline_contract.chunk_embedding_property
    effective_embedding_dimensions = (
        require_positive_int(embedding_dimensions, "embedding_dimensions")
        if embedding_dimensions is not None
        else pipeline_contract.chunk_embedding_dimensions
    )
    effective_embedder_model = embedder_model or pipeline_contract.embedder_model_name
    effective_chunk_stride = (
        require_positive_int(chunk_stride, "chunk_stride")
        if chunk_stride is not None
        else pipeline_contract.chunk_fallback_stride
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

    require_openai_api_key_fn("Set OPENAI_API_KEY when using --live ingest-pdf")

    from power_atlas.adapters.graphrag_components import PipelineRunner

    validate_cypher_identifier_fn(effective_index_name, "index name")
    validate_cypher_identifier_fn(effective_chunk_label, "label")
    validate_cypher_identifier_fn(effective_embedding_property, "property")

    live_result = live_runner(
        neo4j_settings,
        stage_run_id=stage_run_id,
        pdf_file_path=pdf_file_path,
        pdf_source_uri=pdf_source_uri,
        openai_model=openai_model,
        effective_dataset_id=effective_dataset_id,
        effective_index_name=effective_index_name,
        effective_chunk_label=effective_chunk_label,
        effective_embedding_property=effective_embedding_property,
        effective_embedding_dimensions=effective_embedding_dimensions,
        effective_chunk_stride=effective_chunk_stride,
        pipeline_config_path=PDF_PIPELINE_CONFIG_PATH,
        pipeline_runner_cls=PipelineRunner,
        run_pipeline_with_cleanup=run_pipeline_with_cleanup_fn,
        record_as_mapping=record_as_mapping_fn,
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
        "pipeline_result": normalize_pipeline_result_fn(pipeline_result),
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


def run_pdf_ingest_runtime_default(
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
    return run_pdf_ingest_runtime(
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
    )


__all__ = [
    "DEFAULT_PDF_FILENAME",
    "dataset_metadata_from_fixtures_root",
    "normalize_pipeline_result",
    "record_as_mapping",
    "require_positive_int",
    "resolve_pdf_dataset",
    "run_pdf_ingest_runtime",
    "run_pdf_ingest_runtime_default",
    "run_pipeline_with_cleanup",
    "sha256_file",
]