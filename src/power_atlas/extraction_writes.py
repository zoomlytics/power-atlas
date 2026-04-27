from __future__ import annotations

from typing import Any

import neo4j
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig

from power_atlas.neo4j_io import validate_cypher_identifier


EDGE_TYPE_HAS_PARTICIPANT = "HAS_PARTICIPANT"
def _claim_write_query(chunk_label: str, chunk_id_property: str) -> str:
    return f"""
            UNWIND $rows AS row
            MERGE (claim:ExtractedClaim {{claim_id: row.claim_id, run_id: row.run_id}})
            SET claim += row.properties
            WITH row, claim
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (claim)-[supported_by:SUPPORTED_BY]->(chunk)
            SET supported_by.run_id = row.run_id,
                supported_by.source_uri = row.source_uri,
                supported_by.chunk_id = chunk_id
            """


def _mention_write_query(chunk_label: str, chunk_id_property: str) -> str:
    return f"""
            UNWIND $rows AS row
            MERGE (mention:EntityMention {{mention_id: row.mention_id, run_id: row.run_id}})
            SET mention += row.properties
            WITH row, mention
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (mention)-[mentioned_in:MENTIONED_IN]->(chunk)
            SET mentioned_in.run_id = row.run_id,
                mentioned_in.source_uri = row.source_uri,
                mentioned_in.chunk_id = chunk_id
            """


def _edge_write_query() -> str:
    return """
            UNWIND $rows AS row
            MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})
            MERGE (claim)-[r:HAS_PARTICIPANT {role: row.role}]->(mention)
            SET r.run_id = row.run_id,
                r.source_uri = coalesce(row.source_uri, r.source_uri),
                r.match_method = row.match_method
            """


def _validated_chunk_identifiers(
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[str, str]:
    chunk_label = validate_cypher_identifier(
        lexical_graph_config.chunk_node_label,
        "chunk label",
    )
    chunk_id_property = validate_cypher_identifier(
        lexical_graph_config.chunk_id_property,
        "chunk_id property",
    )
    return chunk_label, chunk_id_property


def write_extracted_rows(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> None:
    chunk_label, chunk_id_property = _validated_chunk_identifiers(lexical_graph_config)
    if claim_rows:
        driver.execute_query(
            _claim_write_query(chunk_label, chunk_id_property),
            parameters_={"rows": claim_rows},
            database_=neo4j_database,
        )
    if mention_rows:
        driver.execute_query(
            _mention_write_query(chunk_label, chunk_id_property),
            parameters_={"rows": mention_rows},
            database_=neo4j_database,
        )


def write_all_extraction_data(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
) -> None:
    chunk_label, chunk_id_property = _validated_chunk_identifiers(lexical_graph_config)

    claim_query = _claim_write_query(chunk_label, chunk_id_property)
    mention_query = _mention_write_query(chunk_label, chunk_id_property)
    participant_query = _edge_write_query()

    if edge_rows:
        invalid = [i for i, row in enumerate(edge_rows) if not str(row.get("role") or "").strip()]
        if invalid:
            raise ValueError(
                f"write_all_extraction_data: {len(invalid)} edge row(s) have a missing or "
                f"empty 'role' field (row indices: {invalid}).  Each row must carry a "
                f"non-empty role (e.g. ROLE_SUBJECT or ROLE_OBJECT) before the transaction "
                f"is executed."
            )

        invalid_type = [
            i
            for i, row in enumerate(edge_rows)
            if "edge_type" in row and row["edge_type"] != EDGE_TYPE_HAS_PARTICIPANT
        ]
        if invalid_type:
            raise ValueError(
                f"write_all_extraction_data: {len(invalid_type)} edge row(s) have an "
                f"unexpected 'edge_type' value; expected {EDGE_TYPE_HAS_PARTICIPANT!r} "
                f"(row indices: {invalid_type})."
            )

    def _write_all(tx: neo4j.ManagedTransaction) -> None:
        if claim_rows:
            tx.run(claim_query, rows=claim_rows).consume()
        if mention_rows:
            tx.run(mention_query, rows=mention_rows).consume()
        if edge_rows:
            tx.run(participant_query, rows=edge_rows).consume()

    with driver.session(database=neo4j_database) as session:
        session.execute_write(_write_all)


__all__ = [
    "EDGE_TYPE_HAS_PARTICIPANT",
    "validate_cypher_identifier",
    "write_all_extraction_data",
    "write_extracted_rows",
]