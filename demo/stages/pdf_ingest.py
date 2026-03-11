from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from demo.contracts import (
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
    CHUNK_FALLBACK_STRIDE,
    DATASET_ID,
    EMBEDDER_MODEL_NAME,
    FIXTURES_DIR,
    PDF_PIPELINE_CONFIG_PATH,
)
from demo.contracts.runtime import make_run_id


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


def _validate_cypher_identifier(value: str, kind: str) -> None:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {kind} for Cypher fallback: expected a string, got {value!r} (type {type(value).__name__})"
        )
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind} for Cypher fallback: {value!r}")


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


def run_pdf_ingest(
    config: Any,
    run_id: str | None = None,
    *,
    fixtures_dir: Path | None = None,
    index_name: str | None = None,
    chunk_label: str | None = None,
    embedding_property: str | None = None,
    embedding_dimensions: int | None = None,
    embedder_model: str | None = None,
    chunk_stride: int | None = None,
) -> dict[str, Any]:
    pdf_path = ((fixtures_dir or FIXTURES_DIR) / "unstructured" / "chain_of_custody.pdf").resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")
    pdf_file_path = str(pdf_path)
    pdf_source_uri = pdf_path.as_uri()
    dataset_id = DATASET_ID
    effective_index_name = index_name or CHUNK_EMBEDDING_INDEX_NAME
    effective_chunk_label = chunk_label or CHUNK_EMBEDDING_LABEL
    effective_embedding_property = embedding_property or CHUNK_EMBEDDING_PROPERTY
    effective_embedding_dimensions = (
        _require_positive_int(embedding_dimensions, "embedding_dimensions")
        if embedding_dimensions is not None
        else CHUNK_EMBEDDING_DIMENSIONS
    )
    effective_embedder_model = embedder_model or EMBEDDER_MODEL_NAME
    effective_chunk_stride = (
        _require_positive_int(chunk_stride, "chunk_stride")
        if chunk_stride is not None
        else CHUNK_FALLBACK_STRIDE
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
            "dataset_id": dataset_id,
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
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + FixedSizeSplitter",
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

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY when using --live ingest-pdf")

    import neo4j
    from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner
    from neo4j_graphrag.indexes import create_vector_index

    env_updates = {
        "NEO4J_URI": config.neo4j_uri,
        "NEO4J_USERNAME": config.neo4j_username,
        "NEO4J_PASSWORD": config.neo4j_password,
        "NEO4J_DATABASE": config.neo4j_database,
        "OPENAI_MODEL": config.openai_model,
    }
    previous_env = {key: (key in os.environ, os.environ.get(key)) for key in env_updates}
    os.environ.update(env_updates)

    try:
        driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver:
            index_creation_strategy = "neo4j_graphrag.indexes.create_vector_index"
            index_fallback_reason: str | None = None
            try:
                create_vector_index(
                    driver,
                    effective_index_name,
                    label=effective_chunk_label,
                    embedding_property=effective_embedding_property,
                    dimensions=effective_embedding_dimensions,
                    similarity_fn="cosine",
                    database_=config.neo4j_database,
                )
            except Exception as exc:
                index_creation_strategy = "cypher_fallback"
                exc_message = str(exc).splitlines()[0].strip()
                index_fallback_reason = f"{type(exc).__name__}: {exc_message}" if exc_message else type(exc).__name__
                _validate_cypher_identifier(effective_index_name, "index name")
                _validate_cypher_identifier(effective_chunk_label, "label")
                _validate_cypher_identifier(effective_embedding_property, "property")
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
            contract_index_count = (index_check_result or {}).get("contract_index_count")
            if contract_index_count == 0:
                raise ValueError(
                    f"Vector index contract violation: index '{effective_index_name}' not found "
                    f"after creation attempt (strategy: {index_creation_strategy}). "
                    f"Retrieval will fail unless the contract index is present."
                )

            pipeline = PipelineRunner.from_config_file(PDF_PIPELINE_CONFIG_PATH)
            pipeline_result = asyncio.run(
                pipeline.run(
                    {
                        "file_path": pdf_file_path,
                        "document_metadata": {
                            "run_id": stage_run_id,
                            "dataset_id": dataset_id,
                            "source_uri": pdf_source_uri,
                        },
                    }
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
                         coalesce(size(c.text), size(c.body), size(c.content)) AS chunk_length
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
                    dataset_id=dataset_id,
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
    finally:
        for key, (had_key, previous_value) in previous_env.items():
            if not had_key:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value

    ingest_summary = {
        "run_id": stage_run_id,
        "dataset_id": dataset_id,
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
            "dataset_id": dataset_id,
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
        **({"vector_index_fallback_reason": index_fallback_reason} if index_fallback_reason else {}),
    }


__all__ = ["run_pdf_ingest", "sha256_file"]
