from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver, require_openai_api_key, temporary_environment
from power_atlas.contracts.pipeline import get_pipeline_contract_snapshot
from power_atlas.contracts import (
    DatasetRoot,
    FIXTURES_DIR,
    PDF_PIPELINE_CONFIG_PATH,
    resolve_dataset_root,
)
from demo.cypher_utils import validate_cypher_identifier as _validate_cypher_identifier
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


def _pipeline_contract_value(name: str) -> Any:
    if name in globals():
        return globals()[name]
    snapshot = get_pipeline_contract_snapshot()
    return getattr(snapshot, _PIPELINE_CONTRACT_EXPORTS[name])


def __getattr__(name: str) -> Any:
    if name in _PIPELINE_CONTRACT_EXPORTS:
        return _pipeline_contract_value(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    effective_index_name = index_name or _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME")
    effective_chunk_label = chunk_label or _pipeline_contract_value("CHUNK_EMBEDDING_LABEL")
    effective_embedding_property = embedding_property or _pipeline_contract_value("CHUNK_EMBEDDING_PROPERTY")
    effective_embedding_dimensions = (
        _require_positive_int(embedding_dimensions, "embedding_dimensions")
        if embedding_dimensions is not None
        else _pipeline_contract_value("CHUNK_EMBEDDING_DIMENSIONS")
    )
    effective_embedder_model = embedder_model or _pipeline_contract_value("EMBEDDER_MODEL_NAME")
    effective_chunk_stride = (
        _require_positive_int(chunk_stride, "chunk_stride")
        if chunk_stride is not None
        else _pipeline_contract_value("CHUNK_FALLBACK_STRIDE")
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

    env_updates = {
        "NEO4J_URI": config.neo4j_uri,
        "NEO4J_USERNAME": config.neo4j_username,
        "NEO4J_PASSWORD": config.neo4j_password,
        "NEO4J_DATABASE": config.neo4j_database,
        "OPENAI_MODEL": config.openai_model,
    }

    with temporary_environment(env_updates):
        driver = create_neo4j_driver(config)
        with driver:
            index_creation_strategy = "cypher"
            with driver.session(database=config.neo4j_database) as session:
                session.run(
                    f"""
                    CREATE VECTOR INDEX `{effective_index_name}` IF NOT EXISTS
                    FOR (n:{effective_chunk_label}) ON (n.{effective_embedding_property})
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: $dimensions,
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """,
                    dimensions=effective_embedding_dimensions,
                ).consume()

            # Post-creation contract validation: verify the vector index was created with the
            # contract name. This catches configuration drift where a fallback or override causes
            # a differently-named index to be created, which would break retrieval.
            with driver.session(database=config.neo4j_database) as session:
                index_check_result = session.run(
                    "SHOW INDEXES YIELD name WHERE name = $index_name RETURN count(*) AS contract_index_count",
                    index_name=effective_index_name,
                ).single()
            index_check_mapping = _record_as_mapping(index_check_result)
            contract_index_count = index_check_mapping.get("contract_index_count")
            if contract_index_count == 0:
                raise ValueError(
                    f"Vector index contract violation: index '{effective_index_name}' not found "
                    f"after creation attempt (strategy: {index_creation_strategy}). "
                    f"Retrieval will fail unless the contract index is present."
                )

            pipeline = PipelineRunner.from_config_file(PDF_PIPELINE_CONFIG_PATH)
            pipeline_result = asyncio.run(
                _run_pipeline_with_cleanup(
                    pipeline,
                    {
                        "file_path": pdf_file_path,
                        "document_metadata": {
                            "run_id": stage_run_id,
                            "dataset_id": effective_dataset_id,
                            "source_uri": pdf_source_uri,
                        },
                    },
                )
            )
            if isinstance(pipeline_result, dict):
                for warnings_key in ("warnings", "extraction_warnings"):
                    maybe_warnings = pipeline_result.get(warnings_key)
                    if isinstance(maybe_warnings, list):
                        extraction_warnings = maybe_warnings
                        break

            with driver.session(database=config.neo4j_database) as session:
                session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND (d.run_id IS NULL OR d.run_id = $run_id)
                    SET d.run_id = coalesce(d.run_id, $run_id),
                        d.source_uri = coalesce(d.source_uri, $source_uri),
                        d.dataset_id = coalesce(d.dataset_id, $dataset_id)
                    WITH d
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id IS NULL OR c.run_id = $run_id
                    WITH d,
                         c,
                         toIntegerOrNull(coalesce(c.chunk_order, c.index, c.chunk_index)) AS normalized_chunk_order,
                         coalesce(toIntegerOrNull(coalesce(c.chunk_order, c.index, c.chunk_index)), 0) AS fallback_chunk_order,
                         toIntegerOrNull(coalesce(c.page_number, c.page)) AS normalized_page,
                         toIntegerOrNull(coalesce(c.start_char, c.start_offset, c.start, c.offset)) AS existing_start_char,
                         toIntegerOrNull(coalesce(c.end_char, c.end_offset, c.end)) AS existing_end_char,
                         size(c.text) AS chunk_length
                    WITH d,
                         c,
                         normalized_chunk_order,
                         fallback_chunk_order,
                         normalized_page,
                         chunk_length,
                         CASE
                             WHEN existing_start_char IS NOT NULL THEN existing_start_char
                             ELSE fallback_chunk_order * $default_chunk_stride
                         END AS start_char_value,
                         existing_end_char,
                         toIntegerOrNull(c.chunk_index) AS chunk_index_int,
                         toIntegerOrNull(c.start_char) AS start_char_int,
                         toIntegerOrNull(c.end_char) AS end_char_int,
                         coalesce(
                             toString(c.uid),
                             toString(coalesce(toIntegerOrNull(c.chunk_index), fallback_chunk_order))
                         ) AS missing_chunk_discriminator
                       SET c.run_id = coalesce(c.run_id, $run_id),
                           c.source_uri = coalesce(c.source_uri, d.source_uri, $source_uri),
                           c.dataset_id = coalesce(c.dataset_id, d.dataset_id, $dataset_id),
                           c.chunk_order = normalized_chunk_order,
                           c.chunk_index = coalesce(chunk_index_int, normalized_chunk_order),
                           c.chunk_id = CASE
                               WHEN c.chunk_id IS NOT NULL THEN c.chunk_id
                               WHEN c.uid IS NOT NULL THEN c.uid
                               WHEN normalized_chunk_order IS NULL THEN d.source_uri + ':missing_chunk_order:' + missing_chunk_discriminator
                               ELSE d.source_uri + ':' + toString(normalized_chunk_order)
                           END,
                          c.page_number = normalized_page,
                          c.page = normalized_page,
                          c.start_char = coalesce(start_char_int, start_char_value),
                          c.end_char = CASE
                              WHEN end_char_int IS NOT NULL THEN end_char_int
                              WHEN existing_end_char IS NOT NULL THEN existing_end_char
                              WHEN chunk_length IS NULL OR chunk_length <= 0 THEN start_char_value
                              ELSE start_char_value + chunk_length - 1
                          END,
                          c.embedding = coalesce(c.embedding, c.embedding_vector, c.vector, c.embeddings)
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                    dataset_id=effective_dataset_id,
                    default_chunk_stride=effective_chunk_stride,
                ).consume()
                run_counts = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                    RETURN count(DISTINCT d) AS document_count, count(c) AS chunk_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()
                run_counts = _record_as_mapping(run_counts)
                document_count_value = run_counts.get("document_count")
                chunk_count_value = run_counts.get("chunk_count")
                try:
                    document_count = int(run_counts.get("document_count") or 0)
                    chunk_count = int(run_counts.get("chunk_count") or 0)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Ingest contract violation: unexpected count types "
                        f"(document_count={document_count_value!r}, chunk_count={chunk_count_value!r})"
                    ) from exc
                if document_count <= 0 or chunk_count <= 0:
                    raise ValueError("Ingest contract violation: expected at least one Document and Chunk for this run")
                page_count_result = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                    WITH coalesce(c.page_number, c.page) AS page_value
                    WHERE page_value IS NOT NULL
                    RETURN count(DISTINCT page_value) AS page_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()
                page_count_result = _record_as_mapping(page_count_result)
                page_count_value = page_count_result.get("page_count")
                try:
                    page_count = int(page_count_value) if page_count_value is not None else 0
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Ingest contract violation: unexpected page count type (value={page_count_value!r})") from exc
                summary_counts = {
                    "documents": document_count,
                    "pages": page_count,
                    "chunks": chunk_count,
                }
                missing_chunk_order_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.chunk_order IS NULL
                    RETURN count(c) AS missing_chunk_order_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()["missing_chunk_order_count"]
                if missing_chunk_order_count:
                    raise ValueError("Chunk ordering contract violation: expected stable chunk index on all ingested chunks")
                missing_embedding_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.embedding IS NULL
                    RETURN count(c) AS missing_embedding_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()["missing_embedding_count"]
                if missing_embedding_count:
                    raise ValueError("Chunk embedding contract violation: expected :Chunk.embedding for all ingested chunks")
                missing_page_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND coalesce(c.page_number, c.page) IS NULL
                    RETURN count(c) AS missing_page_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()["missing_page_count"]
                if missing_page_count:
                    extraction_warnings.append(
                        f"{missing_page_count} chunk(s) missing page/page_number; proceeding with degraded citation metadata"
                    )
                missing_char_offset_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $file_path OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND (c.start_char IS NULL OR c.end_char IS NULL)
                    RETURN count(c) AS missing_char_offset_count
                    """,
                    run_id=stage_run_id,
                    file_path=pdf_file_path,
                    source_uri=pdf_source_uri,
                ).single()["missing_char_offset_count"]
                if missing_char_offset_count:
                    raise ValueError("Chunk offset contract violation: expected start_char/end_char on all chunks")

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


__all__ = ["run_pdf_ingest", "sha256_file"]
