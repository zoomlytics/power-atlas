from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import neo4j


def fetch_entity_mentions(
    driver: Any,
    *,
    run_id: str,
    source_uri_fallback: str | None,
    neo4j_database: str,
) -> list[dict[str, Any]]:
    mention_result, _, _ = driver.execute_query(
        """
        MATCH (mention:EntityMention {run_id: $run_id})
        RETURN mention.mention_id AS mention_id,
               mention.name AS name,
               mention.entity_type AS entity_type,
               mention.source_uri AS source_uri
        ORDER BY mention.mention_id
        """,
        parameters_={"run_id": run_id},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.READ,
    )
    return [
        {
            "mention_id": record["mention_id"],
            "name": record["name"] or "",
            "entity_type": record["entity_type"],
            "source_uri": record["source_uri"] if record["source_uri"] not in (None, "") else source_uri_fallback,
        }
        for record in mention_result
    ]


def fetch_canonical_entities(
    driver: Any,
    *,
    dataset_id: str,
    neo4j_database: str,
) -> list[dict[str, Any]]:
    canonical_result, _, _ = driver.execute_query(
        """
        MATCH (canonical:CanonicalEntity)
        WHERE canonical.dataset_id = $dataset_id
        RETURN canonical.entity_id AS entity_id,
               canonical.run_id AS run_id,
               canonical.name AS name,
               canonical.aliases AS aliases
        ORDER BY canonical.entity_id
        """,
        parameters_={"dataset_id": dataset_id},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.READ,
    )
    return [
        {
            "entity_id": record["entity_id"],
            "run_id": record["run_id"],
            "name": record["name"] or "",
            "aliases": record["aliases"],
        }
        for record in canonical_result
        if record["entity_id"] and record["run_id"]
    ]


@dataclass(frozen=True)
class EntityResolutionGraphCoverage:
    mentions_clustered: int
    mentions_unclustered: int


def fetch_member_of_coverage(
    driver: Any,
    *,
    run_id: str,
    neo4j_database: str,
) -> EntityResolutionGraphCoverage:
    count_result, _, _ = driver.execute_query(
        """
        MATCH (m:EntityMention {run_id: $run_id})
        OPTIONAL MATCH (m)-[:MEMBER_OF]->(c:ResolvedEntityCluster {run_id: $run_id})
        RETURN count(DISTINCT CASE WHEN c IS NOT NULL THEN m END) AS mentions_clustered,
               count(DISTINCT CASE WHEN c IS NULL THEN m END)     AS mentions_unclustered
        """,
        parameters_={"run_id": run_id},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.WRITE,
    )
    if not count_result:
        return EntityResolutionGraphCoverage(mentions_clustered=0, mentions_unclustered=0)
    return EntityResolutionGraphCoverage(
        mentions_clustered=int(count_result[0]["mentions_clustered"]),
        mentions_unclustered=int(count_result[0]["mentions_unclustered"]),
    )


@dataclass(frozen=True)
class EntityResolutionAlignmentCoverage:
    total_clusters: int
    aligned_clusters: int
    distinct_canonical_entities_aligned: int
    mentions_in_aligned: int
    alignment_breakdown: dict[str, int]


def fetch_alignment_coverage(
    driver: Any,
    *,
    run_id: str,
    alignment_version: str,
    neo4j_database: str,
) -> EntityResolutionAlignmentCoverage:
    total_clusters_q, _, _ = driver.execute_query(
        """
        MATCH (c:ResolvedEntityCluster {run_id: $run_id})
        RETURN count(c) AS total_clusters
        """,
        parameters_={"run_id": run_id},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.WRITE,
    )
    total_clusters = int(total_clusters_q[0]["total_clusters"] or 0) if total_clusters_q else 0

    aligned_q, _, _ = driver.execute_query(
        """
        MATCH (c:ResolvedEntityCluster {run_id: $run_id})
              -[:ALIGNED_WITH {run_id: $run_id, alignment_version: $alignment_version}]->
              (ce:CanonicalEntity)
        RETURN count(DISTINCT c)  AS aligned_clusters,
               count(DISTINCT ce) AS distinct_canonical_entities_aligned
        """,
        parameters_={"run_id": run_id, "alignment_version": alignment_version},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.WRITE,
    )
    aligned_clusters = int(aligned_q[0]["aligned_clusters"] or 0) if aligned_q else 0
    distinct_canonical_entities_aligned = int(
        aligned_q[0]["distinct_canonical_entities_aligned"] or 0
    ) if aligned_q else 0

    breakdown_q, _, _ = driver.execute_query(
        """
        MATCH (:ResolvedEntityCluster {run_id: $run_id})
              -[r:ALIGNED_WITH {run_id: $run_id, alignment_version: $alignment_version}]->
              (:CanonicalEntity)
        RETURN r.alignment_method AS alignment_method,
               count(r)           AS method_count
        """,
        parameters_={"run_id": run_id, "alignment_version": alignment_version},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.WRITE,
    )
    alignment_breakdown: dict[str, int] = {}
    for record in breakdown_q:
        method = record.get("alignment_method") or "unknown"
        alignment_breakdown[method] = alignment_breakdown.get(method, 0) + int(record.get("method_count") or 0)

    mentions_in_q, _, _ = driver.execute_query(
        """
        MATCH (m:EntityMention {run_id: $run_id})
              -[:MEMBER_OF]->
              (c:ResolvedEntityCluster {run_id: $run_id})
              -[:ALIGNED_WITH {run_id: $run_id, alignment_version: $alignment_version}]->
              (:CanonicalEntity)
        RETURN count(DISTINCT m) AS mentions_in_aligned
        """,
        parameters_={"run_id": run_id, "alignment_version": alignment_version},
        database_=neo4j_database,
        routing_=neo4j.RoutingControl.WRITE,
    )
    mentions_in_aligned = int(mentions_in_q[0]["mentions_in_aligned"] or 0) if mentions_in_q else 0

    return EntityResolutionAlignmentCoverage(
        total_clusters=total_clusters,
        aligned_clusters=aligned_clusters,
        distinct_canonical_entities_aligned=distinct_canonical_entities_aligned,
        mentions_in_aligned=mentions_in_aligned,
        alignment_breakdown=alignment_breakdown,
    )


__all__ = [
    "EntityResolutionAlignmentCoverage",
    "EntityResolutionGraphCoverage",
    "fetch_alignment_coverage",
    "fetch_canonical_entities",
    "fetch_entity_mentions",
    "fetch_member_of_coverage",
]