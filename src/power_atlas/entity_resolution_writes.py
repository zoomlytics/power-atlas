from __future__ import annotations

from typing import Any


def write_resolved_mentions(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    neo4j_database: str,
) -> None:
    if not resolved_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
        MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
        MERGE (mention)-[r:RESOLVES_TO]->(canonical)
        SET r.run_id = $run_id,
            r.source_uri = coalesce(nullif(mention.source_uri, ''), $source_uri),
            r.resolution_method = row.resolution_method,
            r.resolution_confidence = row.resolution_confidence,
            r.candidate_ids = row.candidate_ids
        """,
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
) -> None:
    if not cluster_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MERGE (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
        ON CREATE SET
            cluster.canonical_name  = row.canonical_name,
            cluster.normalized_text = row.normalized_text,
            cluster.entity_type     = row.entity_type,
            cluster.run_id          = $run_id,
            cluster.resolver_version = $resolver_version,
            cluster.created_at = $created_at
        WITH row, cluster
        MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
        MERGE (mention)-[r:MEMBER_OF]->(cluster)
        SET r.score            = row.score,
            r.method           = row.method,
            r.resolver_version = $resolver_version,
            r.run_id           = $run_id,
            r.status           = row.status,
            r.source_uri       = row.source_uri
        """,
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
        MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
        MATCH (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
        MERGE (mention)-[r:CANDIDATE_MATCH]->(cluster)
        SET r.score            = row.score,
            r.method           = row.method,
            r.resolver_version = $resolver_version,
            r.run_id           = $run_id,
            r.status           = row.status,
            r.source_uri       = row.source_uri
        """,
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
) -> None:
    if not alignment_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
        MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
        MERGE (cluster)-[r:ALIGNED_WITH {
            run_id:            $run_id,
            alignment_version: $alignment_version
        }]->(canonical)
        SET r.alignment_method = row.alignment_method,
            r.alignment_score  = row.alignment_score,
            r.alignment_status = row.alignment_status,
            r.source_uri       = coalesce(row.source_uri, $source_uri)
        """,
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