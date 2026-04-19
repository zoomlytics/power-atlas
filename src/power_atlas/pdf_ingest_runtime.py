from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver, temporary_environment


@dataclass(frozen=True)
class PdfIngestLiveResult:
    index_creation_strategy: str
    pipeline_result: Any
    summary_counts: dict[str, int]
    extraction_warnings: list[Any]


def run_pdf_ingest_live(
    config: Any,
    *,
    stage_run_id: str,
    pdf_file_path: str,
    pdf_source_uri: str,
    effective_dataset_id: str,
    effective_index_name: str,
    effective_chunk_label: str,
    effective_embedding_property: str,
    effective_embedding_dimensions: int,
    effective_chunk_stride: int,
    pipeline_config_path: Any,
    pipeline_runner_cls: Any,
    run_pipeline_with_cleanup: Callable[[Any, dict[str, Any]], Any],
    record_as_mapping: Callable[[Any], dict[str, Any]],
) -> PdfIngestLiveResult:
    summary_counts = {"documents": 0, "pages": 0, "chunks": 0}
    extraction_warnings: list[Any] = []
    env_updates = {
        "NEO4J_URI": config.neo4j_uri,
        "NEO4J_USERNAME": config.neo4j_username,
        "NEO4J_PASSWORD": config.neo4j_password,
        "NEO4J_DATABASE": config.neo4j_database,
        "OPENAI_MODEL": config.openai_model,
    }

    with temporary_environment(env_updates):
        with create_neo4j_driver(config) as driver:
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

            with driver.session(database=config.neo4j_database) as session:
                index_check_result = session.run(
                    "SHOW INDEXES YIELD name WHERE name = $index_name RETURN count(*) AS contract_index_count",
                    index_name=effective_index_name,
                ).single()
            index_check_mapping = record_as_mapping(index_check_result)
            contract_index_count = index_check_mapping.get("contract_index_count")
            if contract_index_count == 0:
                raise ValueError(
                    f"Vector index contract violation: index '{effective_index_name}' not found "
                    f"after creation attempt (strategy: {index_creation_strategy}). "
                    f"Retrieval will fail unless the contract index is present."
                )

            pipeline = pipeline_runner_cls.from_config_file(pipeline_config_path)
            pipeline_result = asyncio.run(
                run_pipeline_with_cleanup(
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
                run_counts = record_as_mapping(run_counts)
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
                page_count_result = record_as_mapping(page_count_result)
                page_count_value = page_count_result.get("page_count")
                try:
                    page_count = int(page_count_value) if page_count_value is not None else 0
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Ingest contract violation: unexpected page count type (value={page_count_value!r})"
                    ) from exc
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

    return PdfIngestLiveResult(
        index_creation_strategy=index_creation_strategy,
        pipeline_result=pipeline_result,
        summary_counts=summary_counts,
        extraction_warnings=list(extraction_warnings),
    )


__all__ = ["PdfIngestLiveResult", "run_pdf_ingest_live"]