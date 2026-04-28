from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Callable

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

GraphHealthQuerySpec = tuple[str, str, str]
PER_CANONICAL_ALIGNMENT_LIMIT = 30
CANONICAL_CHAIN_HEALTH_LIMIT = 30


_Q_PARTICIPATION_ROLE_DIST = """\
MATCH ()-[r:HAS_PARTICIPANT]->()
WHERE ($run_id IS NULL OR r.run_id = $run_id)
RETURN r.role AS role, count(*) AS total
ORDER BY total DESC
"""

_Q_CLAIM_EDGE_COVERAGE = """\
MATCH (c:ExtractedClaim)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
OPTIONAL MATCH (c)-[r:HAS_PARTICIPANT]->(:EntityMention)
WITH c, count(r) AS participant_edges
RETURN participant_edges, count(*) AS claim_count
ORDER BY participant_edges
"""

_Q_MATCH_METHOD_DIST = """\
MATCH ()-[r:HAS_PARTICIPANT]->()
WHERE ($run_id IS NULL OR r.run_id = $run_id)
    AND r.match_method IS NOT NULL
RETURN r.match_method AS match_method, count(*) AS total
ORDER BY total DESC
"""

_Q_MENTION_CLUSTERING = """\
MATCH (m:EntityMention)
WHERE ($run_id IS NULL OR m.run_id = $run_id)
OPTIONAL MATCH (m)-[:MEMBER_OF]->(cluster:ResolvedEntityCluster)
WITH m, count(cluster) > 0 AS is_clustered
RETURN is_clustered, count(DISTINCT m) AS mention_count
ORDER BY is_clustered DESC
"""

_Q_CLUSTER_SIZE_DIST = """\
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE ($run_id IS NULL OR cluster.run_id = $run_id)
WITH cluster, count(m) AS member_count
RETURN member_count, count(cluster) AS cluster_count
ORDER BY member_count
"""

_Q_ALIGNMENT_COVERAGE = """\
MATCH (cluster:ResolvedEntityCluster)
WHERE ($run_id IS NULL OR cluster.run_id = $run_id)
OPTIONAL MATCH (cluster)-[a:ALIGNED_WITH]->(:CanonicalEntity)
    WHERE ($run_id IS NULL OR a.run_id = $run_id)
        AND ($alignment_version IS NULL OR a.alignment_version = $alignment_version)
WITH cluster, count(a) > 0 AS is_aligned
RETURN is_aligned, count(*) AS cluster_count
ORDER BY is_aligned DESC
"""


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def build_cluster_type_fragmentation_query(
    *,
    build_entity_type_cypher_case: Callable[[str], str],
) -> str:
    _indent = "     "
    case_expr = build_entity_type_cypher_case("m.entity_type")
    indented_case = case_expr.replace("\n", "\n" + _indent)
    return "".join(
        [
            "MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)\n",
            "WHERE ($run_id IS NULL OR cluster.run_id = $run_id)\n",
            "WITH cluster,\n",
            f"{_indent}{indented_case} AS normalized_type\n",
            "WITH cluster,\n",
            "     count(DISTINCT normalized_type) AS type_count\n",
            "RETURN type_count AS distinct_types_in_cluster, count(cluster) AS cluster_count\n",
            "ORDER BY type_count\n",
        ]
    )


def build_graph_health_query_specs(
    *,
    cluster_type_fragmentation_query: str,
    per_canonical_alignment_limit: int = PER_CANONICAL_ALIGNMENT_LIMIT,
    canonical_chain_health_limit: int = CANONICAL_CHAIN_HEALTH_LIMIT,
) -> list[GraphHealthQuerySpec]:
    per_canonical_alignment = f"""\
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE ($run_id IS NULL OR a.run_id = $run_id)
  AND ($alignment_version IS NULL OR a.alignment_version = $alignment_version)
  AND ($run_id IS NULL OR cluster.run_id = $run_id)
  AND ($run_id IS NULL OR m.run_id = $run_id)
RETURN canonical.name              AS canonical_entity,
       canonical.entity_id         AS entity_id,
       canonical.entity_type       AS entity_type,
       count(DISTINCT cluster)     AS aligned_cluster_count,
       count(DISTINCT m)           AS bridged_mention_count,
       collect(DISTINCT a.alignment_method)[0..5] AS sample_methods
ORDER BY aligned_cluster_count DESC
LIMIT {per_canonical_alignment_limit}
"""
    canonical_chain_health = f"""\
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE ($run_id IS NULL OR a.run_id = $run_id)
  AND ($alignment_version IS NULL OR a.alignment_version = $alignment_version)
  AND ($run_id IS NULL OR cluster.run_id = $run_id)
  AND ($run_id IS NULL OR m.run_id = $run_id)
OPTIONAL MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT]->(m)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
WITH canonical, count(DISTINCT m) AS mention_count, count(DISTINCT c) AS claim_count
RETURN canonical.name        AS canonical_entity,
       canonical.entity_type AS entity_type,
       mention_count,
       claim_count,
       CASE WHEN claim_count = 0 THEN 'dark' ELSE 'active' END AS status
ORDER BY claim_count DESC
LIMIT {canonical_chain_health_limit}
"""
    return [
        ("role_dist", "participation role distribution", _Q_PARTICIPATION_ROLE_DIST),
        ("edge_coverage", "claim edge coverage", _Q_CLAIM_EDGE_COVERAGE),
        ("match_method_dist", "match method distribution", _Q_MATCH_METHOD_DIST),
        ("mention_clustering", "mention clustering", _Q_MENTION_CLUSTERING),
        ("cluster_size_dist", "cluster size distribution", _Q_CLUSTER_SIZE_DIST),
        (
            "cluster_type_frag",
            "cluster type fragmentation",
            cluster_type_fragmentation_query,
        ),
        ("alignment_coverage", "alignment coverage", _Q_ALIGNMENT_COVERAGE),
        ("per_canonical", "per-canonical alignment", per_canonical_alignment),
        ("chain_health", "canonical chain health", canonical_chain_health),
    ]


def fetch_graph_health_query_rows(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    *,
    run_id: str | None,
    alignment_version: str | None,
    query_specs: Sequence[GraphHealthQuerySpec],
    logger: logging.Logger,
) -> dict[str, list[dict[str, Any]]]:
    params: dict[str, Any] = {
        "run_id": run_id,
        "alignment_version": alignment_version,
    }
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    with create_neo4j_driver(neo4j_settings) as driver:
        for result_key, log_label, cypher in query_specs:
            logger.info("graph_health: running %s query", log_label)
            records, _, _ = driver.execute_query(
                cypher,
                parameters_=params,
                database_=neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            rows_by_key[result_key] = _records_to_dicts(records)
    return rows_by_key


__all__ = [
    "CANONICAL_CHAIN_HEALTH_LIMIT",
    "GraphHealthQuerySpec",
    "PER_CANONICAL_ALIGNMENT_LIMIT",
    "build_cluster_type_fragmentation_query",
    "build_graph_health_query_specs",
    "fetch_graph_health_query_rows",
]