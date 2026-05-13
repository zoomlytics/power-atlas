from __future__ import annotations

from typing import Any

from power_atlas.contracts import (
    EntityResolutionGraphContract,
    get_default_entity_resolution_graph_contract,
)


def _escape_cypher_identifier(value: str) -> str:
    if not value or "`" in value:
        raise ValueError(f"Invalid Cypher identifier {value!r}")
    return f"`{value}`"


def write_resolved_mentions(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    neo4j_database: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    if not resolved_rows:
        return
    resolved_graph = (
        get_default_entity_resolution_graph_contract()
        if entity_resolution_graph is None
        else entity_resolution_graph
    )
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (mention:{mention_label} {{mention_id: row.mention_id, run_id: $run_id}})
        MATCH (canonical:{canonical_label} {{entity_id: row.canonical_entity_id, run_id: row.canonical_run_id}})
        MERGE (mention)-[r:{resolves_to_relationship}]->(canonical)
        SET r.run_id = $run_id,
            r.source_uri = coalesce(nullif(mention.source_uri, ''), $source_uri),
            r.resolution_method = row.resolution_method,
            r.resolution_confidence = row.resolution_confidence,
            r.candidate_ids = row.candidate_ids
        """.format(
            mention_label=_escape_cypher_identifier(resolved_graph.mention_label),
            canonical_label=_escape_cypher_identifier(resolved_graph.canonical_label),
            resolves_to_relationship=_escape_cypher_identifier(
                resolved_graph.resolves_to_relationship
            ),
        ),
        parameters_={
            "rows": resolved_rows,
            "run_id": run_id,
            "source_uri": source_uri or None,
        },
        database_=neo4j_database,
    )


def write_cluster_memberships(
    driver: Any,
    *,
    run_id: str,
    cluster_rows: list[dict[str, Any]],
    neo4j_database: str,
    resolver_version: str,
    created_at: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    if not cluster_rows:
        return
    resolved_graph = (
        get_default_entity_resolution_graph_contract()
        if entity_resolution_graph is None
        else entity_resolution_graph
    )
    driver.execute_query(
        """
        UNWIND $rows AS row
        MERGE (cluster:{cluster_label} {{cluster_id: row.cluster_id}})
        ON CREATE SET
            cluster.canonical_name  = row.canonical_name,
            cluster.normalized_text = row.normalized_text,
            cluster.entity_type     = row.entity_type,
            cluster.run_id          = $run_id,
            cluster.resolver_version = $resolver_version,
            cluster.created_at = $created_at
        WITH row, cluster
        MATCH (mention:{mention_label} {{mention_id: row.mention_id, run_id: $run_id}})
        MERGE (mention)-[r:{member_of_relationship}]->(cluster)
        SET r.score            = row.score,
            r.method           = row.method,
            r.resolver_version = $resolver_version,
            r.run_id           = $run_id,
            r.status           = row.status,
            r.source_uri       = row.source_uri
        """.format(
            cluster_label=_escape_cypher_identifier(resolved_graph.cluster_label),
            mention_label=_escape_cypher_identifier(resolved_graph.mention_label),
            member_of_relationship=_escape_cypher_identifier(
                resolved_graph.member_of_relationship
            ),
        ),
        parameters_={
            "rows": cluster_rows,
            "run_id": run_id,
            "resolver_version": resolver_version,
            "created_at": created_at,
        },
        database_=neo4j_database,
    )

    candidate_rows = [
        row for row in cluster_rows if row["status"] in ("candidate", "review_required")
    ]
    if not candidate_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (mention:{mention_label} {{mention_id: row.mention_id, run_id: $run_id}})
        MATCH (cluster:{cluster_label} {{cluster_id: row.cluster_id}})
        MERGE (mention)-[r:{candidate_match_relationship}]->(cluster)
        SET r.score            = row.score,
            r.method           = row.method,
            r.resolver_version = $resolver_version,
            r.run_id           = $run_id,
            r.status           = row.status,
            r.source_uri       = row.source_uri
        """.format(
            mention_label=_escape_cypher_identifier(resolved_graph.mention_label),
            cluster_label=_escape_cypher_identifier(resolved_graph.cluster_label),
            candidate_match_relationship=_escape_cypher_identifier(
                resolved_graph.candidate_match_relationship
            ),
        ),
        parameters_={
            "rows": candidate_rows,
            "run_id": run_id,
            "resolver_version": resolver_version,
        },
        database_=neo4j_database,
    )


def write_alignment_results(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    alignment_rows: list[dict[str, Any]],
    neo4j_database: str,
    alignment_version: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    if not alignment_rows:
        return
    resolved_graph = (
        get_default_entity_resolution_graph_contract()
        if entity_resolution_graph is None
        else entity_resolution_graph
    )
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (cluster:{cluster_label} {{cluster_id: row.cluster_id}})
        MATCH (canonical:{canonical_label} {{entity_id: row.canonical_entity_id, run_id: row.canonical_run_id}})
        MERGE (cluster)-[r:{aligned_with_relationship} {{
            run_id:            $run_id,
            alignment_version: $alignment_version
        }}]->(canonical)
        SET r.alignment_method = row.alignment_method,
            r.alignment_score  = row.alignment_score,
            r.alignment_status = row.alignment_status,
            r.source_uri       = coalesce(row.source_uri, $source_uri)
        """.format(
            cluster_label=_escape_cypher_identifier(resolved_graph.cluster_label),
            canonical_label=_escape_cypher_identifier(resolved_graph.canonical_label),
            aligned_with_relationship=_escape_cypher_identifier(
                resolved_graph.aligned_with_relationship
            ),
        ),
        parameters_={
            "rows": alignment_rows,
            "run_id": run_id,
            "source_uri": source_uri or None,
            "alignment_version": alignment_version,
        },
        database_=neo4j_database,
    )


__all__ = [
    "write_alignment_results",
    "write_cluster_memberships",
    "write_resolved_mentions",
]