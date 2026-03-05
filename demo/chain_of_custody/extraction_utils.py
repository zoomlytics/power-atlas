from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import neo4j

from demo.chain_of_custody.run_scoped_chunk_reader import RunScopedNeo4jChunkReader
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, Neo4jGraph, TextChunk


def coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > 1:
        return None
    return numeric


def fallback_identifier(chunk_ids: list[str]) -> str:
    if not chunk_ids:
        raise ValueError("Cannot build fallback identifier without chunk ids")
    if len(chunk_ids) == 1:
        return chunk_ids[0]
    if len(chunk_ids) == 2:
        return f"{chunk_ids[0]}_and_{chunk_ids[1]}"
    return f"{chunk_ids[0]}_and_{len(chunk_ids) - 1}_more"


def chunk_id_from_node_id(
    node_id: str, node_chunk_map: dict[str, list[str]], *, relationship_type: str
) -> list[str]:
    if node_id in node_chunk_map:
        return node_chunk_map[node_id]
    raise ValueError(
        f"Unable to resolve chunk id(s) for node id {node_id!r}; no {relationship_type!r} "
        "relationships connect it to known chunks."
    )


def prepare_extracted_rows(
    *,
    graph: Neo4jGraph,
    text_chunks: list[TextChunk],
    run_id: str,
    source_uri: str | None,
    extractor_model: str,
    extracted_at: str | None,
    prompt_version: str,
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """
    Map extracted graph nodes to claim/mention rows with provenance.

    Args:
        extracted_at: Optional timestamp; when None, the current UTC time is used.

    Returns:
        claim_rows, mention_rows, warnings
    """
    effective_extracted_at = extracted_at or datetime.now(UTC).isoformat()

    chunk_meta: dict[str, dict[str, Any]] = {}
    for chunk in text_chunks:
        metadata = dict(chunk.metadata or {})
        metadata.setdefault("run_id", run_id)
        if getattr(chunk, "index", None) is not None:
            metadata.setdefault(lexical_graph_config.chunk_index_property, chunk.index)
        chunk_meta[chunk.uid] = metadata

    node_chunk_map: dict[str, list[str]] = {}
    node_chunk_relationship = lexical_graph_config.node_to_chunk_relationship_type
    for relationship in graph.relationships:
        if relationship.type != node_chunk_relationship:
            continue
        source_is_chunk = relationship.start_node_id in chunk_meta
        target_is_chunk = relationship.end_node_id in chunk_meta
        if not source_is_chunk and not target_is_chunk:
            continue
        if source_is_chunk and target_is_chunk:
            continue
        chunk_id = relationship.start_node_id if source_is_chunk else relationship.end_node_id
        node_id = relationship.end_node_id if source_is_chunk else relationship.start_node_id
        node_chunk_map.setdefault(node_id, []).append(chunk_id)

    claim_rows: list[dict[str, Any]] = []
    mention_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for node in graph.nodes:
        if node.label == lexical_graph_config.chunk_node_label:
            continue

        if node.label not in {"ExtractedClaim", "EntityMention"}:
            warnings.append(f"Skipping unsupported node label {node.label!r} for node {node.id!r}")
            continue

        node_chunk_ids = chunk_id_from_node_id(node.id, node_chunk_map, relationship_type=node_chunk_relationship)
        metadata_by_chunk = []
        for chunk_id in node_chunk_ids:
            metadata = chunk_meta.get(chunk_id)
            if metadata is None:
                raise ValueError(f"Extracted node {node.id!r} is missing chunk metadata for run {run_id}")
            metadata_by_chunk.append(metadata)
        if not metadata_by_chunk:
            raise ValueError(f"Extracted node {node.id!r} is missing chunk metadata for run {run_id}")

        chunk_run_ids = {metadata.get("run_id") or run_id for metadata in metadata_by_chunk}
        if len(chunk_run_ids) != 1 or run_id not in chunk_run_ids:
            raise ValueError(
                f"Chunk run_id mismatch for extracted node {node.id!r}: expected {run_id}, "
                f"got {sorted(chunk_run_ids)}"
            )
        provenance_sources = {meta.get("source_uri") or source_uri for meta in metadata_by_chunk}
        if len(provenance_sources) > 1:
            raise ValueError(
                f"Extracted node {node.id!r} spans multiple source_uris; "
                f"expected a single source for run {run_id}, got {sorted(provenance_sources)}"
            )
        provenance_source = next(iter(provenance_sources)) if provenance_sources else source_uri

        base_props = {
            "run_id": run_id,
            "source_uri": provenance_source,
            "extractor_model": extractor_model,
            "extracted_at": effective_extracted_at,
            "prompt_version": prompt_version,
            "chunk_ids": node_chunk_ids,
        }
        node_confidence = coerce_confidence(node.properties.get("confidence"))
        if node_confidence is not None:
            base_props["confidence"] = node_confidence

        chunk_indexes = [
            meta.get(lexical_graph_config.chunk_index_property)
            for meta in metadata_by_chunk
            if meta.get(lexical_graph_config.chunk_index_property) is not None
        ]
        if chunk_indexes:
            unique_indexes = sorted(set(chunk_indexes))
            base_props["chunk_index"] = unique_indexes[0]
            if len(unique_indexes) > 1:
                base_props["chunk_indexes"] = unique_indexes

        page_numbers = [
            meta.get("page_number") if meta.get("page_number") is not None else meta.get("page")
            for meta in metadata_by_chunk
        ]
        page_numbers = [p for p in page_numbers if p is not None]
        if page_numbers:
            unique_pages = sorted(set(page_numbers))
            base_props["page"] = unique_pages[0]
            if len(unique_pages) > 1:
                base_props["pages"] = unique_pages

        fallback_id = fallback_identifier(node_chunk_ids)
        if node.label == "ExtractedClaim":
            claim_text = (
                str(
                    node.properties.get("claim_text")
                    or node.properties.get("text")
                    or node.properties.get("name")
                    or ""
                ).strip()
            )
            properties = dict(base_props)
            properties["claim_text"] = claim_text or f"claim_for_{fallback_id}"
            for key in ("subject", "predicate", "object", "value", "claim_type"):
                if key in node.properties:
                    properties[key] = node.properties[key]
            claim_rows.append(
                {
                    "claim_id": node.id,
                    "chunk_id": node_chunk_ids[0],
                    "chunk_ids": node_chunk_ids,
                    "run_id": run_id,
                    "source_uri": provenance_source,
                    "properties": properties,
                }
            )
            continue

        if node.label == "EntityMention":
            name = str(
                node.properties.get("name")
                or node.properties.get("mention")
                or node.properties.get("text")
                or ""
            ).strip()
            properties = dict(base_props)
            properties["name"] = name or f"mention_for_{fallback_id}"
            if "entity_type" in node.properties:
                properties["entity_type"] = node.properties["entity_type"]
            mention_rows.append(
                {
                    "mention_id": node.id,
                    "chunk_id": node_chunk_ids[0],
                    "chunk_ids": node_chunk_ids,
                    "run_id": run_id,
                    "source_uri": provenance_source,
                    "properties": properties,
                }
            )

    return claim_rows, mention_rows, warnings


def write_extracted_rows(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> None:
    chunk_label = RunScopedNeo4jChunkReader.validate_identifier(
        lexical_graph_config.chunk_node_label, "chunk label"
    )
    chunk_id_property = RunScopedNeo4jChunkReader.validate_identifier(
        lexical_graph_config.chunk_id_property, "chunk_id property"
    )
    if claim_rows:
        driver.execute_query(
            f"""
            UNWIND $rows AS row
            MERGE (claim:ExtractedClaim {{claim_id: row.claim_id, run_id: row.run_id}})
            SET claim += row.properties
            WITH row, claim
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (claim)-[supported_by:SUPPORTED_BY]->(chunk)
            SET supported_by.run_id = row.run_id,
                supported_by.source_uri = row.source_uri,
                supported_by.extracted_at = row.properties.extracted_at,
                supported_by.prompt_version = row.properties.prompt_version,
                supported_by.chunk_id = chunk_id
            """,
            parameters_={"rows": claim_rows},
            database_=neo4j_database,
        )
    if mention_rows:
        driver.execute_query(
            f"""
            UNWIND $rows AS row
            MERGE (mention:EntityMention {{mention_id: row.mention_id, run_id: row.run_id}})
            SET mention += row.properties
            WITH row, mention
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (mention)-[mentioned_in:MENTIONED_IN]->(chunk)
            SET mentioned_in.run_id = row.run_id,
                mentioned_in.source_uri = row.source_uri,
                mentioned_in.extracted_at = row.properties.extracted_at,
                mentioned_in.prompt_version = row.properties.prompt_version,
                mentioned_in.chunk_id = chunk_id
            """,
            parameters_={"rows": mention_rows},
            database_=neo4j_database,
        )
