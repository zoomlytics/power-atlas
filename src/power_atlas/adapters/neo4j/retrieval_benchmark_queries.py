from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

RetrievalBenchmarkQuerySpec = tuple[str, str, str, Mapping[str, Any] | None]


# Canonical single-entity traversal (hybrid mode)
# Returns all claims reachable via CanonicalEntity <- ALIGNED_WITH <- cluster <- MEMBER_OF <- mention
# dataset_id filter scopes CanonicalEntity nodes to the active dataset, preventing cross-dataset
# double-counting when the same entity name exists in multiple datasets.
Q_CANONICAL_SINGLE = """\
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS toLower($entity_name)
    AND ($dataset_id IS NULL OR canonical.dataset_id = $dataset_id)
    AND ($run_id IS NULL OR a.run_id = $run_id)
    AND ($run_id IS NULL OR cluster.run_id = $run_id)
    AND ($run_id IS NULL OR m.run_id = $run_id)
    AND ($alignment_version IS NULL OR a.alignment_version = $alignment_version)
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
RETURN canonical.name        AS canonical_entity,
             cluster.cluster_id     AS cluster_id,
             cluster.canonical_name AS cluster,
             m.name                 AS mention,
             r.role                 AS role,
             c.claim_text           AS claim_text,
             c.predicate            AS predicate,
             r.match_method         AS match_method,
             c.claim_id             AS claim_id
ORDER BY role, c.claim_id
"""

# Cluster-name single-entity traversal (no canonical deduplication - fragmentation risk)
# Returns all claims reachable via ResolvedEntityCluster <- MEMBER_OF <- mention
Q_CLUSTER_NAME_SINGLE = """\
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS toLower($entity_name)
    AND ($run_id IS NULL OR (cluster.run_id = $run_id AND m.run_id = $run_id))
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
RETURN cluster.cluster_id    AS cluster_id,
             cluster.canonical_name AS cluster,
             cluster.entity_type    AS cluster_type,
             m.name                 AS mention,
             r.role                 AS role,
             c.claim_text           AS claim_text,
             c.predicate            AS predicate,
             r.match_method         AS match_method,
             c.claim_id             AS claim_id
ORDER BY cluster, role, c.claim_id
"""

# Full lower-layer inspection: canonical -> cluster -> mention -> claim chain
# Uses OPTIONAL MATCH for claims so that dark mentions (no claims) are visible too.
# dataset_id filter scopes CanonicalEntity nodes to the active dataset.
Q_LOWER_LAYER_CHAIN = """\
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS toLower($entity_name)
    AND ($dataset_id IS NULL OR canonical.dataset_id = $dataset_id)
    AND ($run_id IS NULL OR (a.run_id = $run_id AND cluster.run_id = $run_id AND m.run_id = $run_id))
    AND ($alignment_version IS NULL OR a.alignment_version = $alignment_version)
OPTIONAL MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
RETURN canonical.name        AS canonical_entity,
             cluster.canonical_name AS cluster,
             cluster.entity_type    AS cluster_type,
             m.name                 AS mention,
             m.entity_type          AS mention_type,
             r.role                 AS role,
             c.claim_id             AS claim_id,
             c.claim_text           AS claim_text
ORDER BY canonical_entity, cluster, mention, role
"""

# Fragmentation check: how many distinct clusters match a given name text?
Q_FRAGMENTATION_CHECK = """\
MATCH (cluster:ResolvedEntityCluster)
WHERE toLower(cluster.canonical_name) CONTAINS toLower($entity_name)
    AND ($run_id IS NULL OR cluster.run_id = $run_id)
RETURN cluster.cluster_id     AS cluster_id,
             cluster.canonical_name AS canonical_name,
             cluster.entity_type    AS entity_type
ORDER BY entity_type, canonical_name
"""

# Catalog existence check: does a CanonicalEntity node exist for this entity name?
# Read-only, no joins to clusters or mentions. Used to distinguish catalog absence from
# canonical-empty results when cluster traversal still returns rows.
Q_CATALOG_EXISTENCE_CHECK = """\
MATCH (ce:CanonicalEntity)
WHERE toLower(ce.name) CONTAINS toLower($entity_name)
    AND ($dataset_id IS NULL OR ce.dataset_id = $dataset_id)
RETURN ce.name AS canonical_entity_name
ORDER BY ce.name
LIMIT 100
"""

# Pairwise canonical claim lookup - bidirectional.
# Anchored on CanonicalEntity for selectivity.
Q_PAIRWISE_CANONICAL = """\
MATCH (canonSub:CanonicalEntity)
WHERE (toLower(canonSub.name) CONTAINS toLower($entity_a)
     OR toLower(canonSub.name) CONTAINS toLower($entity_b))
    AND ($dataset_id IS NULL OR canonSub.dataset_id = $dataset_id)
MATCH (canonObj:CanonicalEntity)
WHERE (toLower(canonObj.name) CONTAINS toLower($entity_a)
             OR toLower(canonObj.name) CONTAINS toLower($entity_b))
    AND ($dataset_id IS NULL OR canonObj.dataset_id = $dataset_id)
    AND canonObj <> canonSub
WITH canonSub, canonObj
WHERE
    (toLower(canonSub.name) CONTAINS toLower($entity_a) AND toLower(canonObj.name) CONTAINS toLower($entity_b)) OR
    (toLower(canonSub.name) CONTAINS toLower($entity_b) AND toLower(canonObj.name) CONTAINS toLower($entity_a))
MATCH (canonSub)<-[aSub:ALIGNED_WITH]-(clSub:ResolvedEntityCluster)
WHERE ($run_id IS NULL OR clSub.run_id = $run_id)
    AND ($run_id IS NULL OR aSub.run_id = $run_id)
    AND ($alignment_version IS NULL OR aSub.alignment_version = $alignment_version)
MATCH (canonObj)<-[aObj:ALIGNED_WITH]-(clObj:ResolvedEntityCluster)
WHERE ($run_id IS NULL OR clObj.run_id = $run_id)
    AND ($run_id IS NULL OR aObj.run_id = $run_id)
    AND ($alignment_version IS NULL OR aObj.alignment_version = $alignment_version)
MATCH (mSub:EntityMention)-[:MEMBER_OF]->(clSub)
WHERE ($run_id IS NULL OR mSub.run_id = $run_id)
MATCH (mObj:EntityMention)-[:MEMBER_OF]->(clObj)
WHERE ($run_id IS NULL OR mObj.run_id = $run_id)
MATCH (mSub)<-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)
WHERE ($run_id IS NULL OR c.run_id = $run_id)
MATCH (c)-[:HAS_PARTICIPANT {role: 'object'}]->(mObj)
WITH DISTINCT c, mSub, mObj, canonSub, canonObj,
         CASE WHEN toLower(canonSub.name) CONTAINS toLower($entity_a) THEN 'A→B' ELSE 'B→A' END AS direction
RETURN c.claim_id             AS claim_id,
             c.claim_text           AS claim_text,
             c.predicate            AS predicate,
             mSub.name              AS subject_mention,
             mObj.name              AS object_mention,
             canonSub.name          AS subject_canonical,
             canonObj.name          AS object_canonical,
             direction
ORDER BY direction, c.claim_id
"""


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def build_single_entity_query_specs(entity_name: str) -> list[RetrievalBenchmarkQuerySpec]:
    return [
        ("canonical_rows", "canonical single", Q_CANONICAL_SINGLE, {"entity_name": entity_name}),
        ("cluster_rows", "cluster-name single", Q_CLUSTER_NAME_SINGLE, {"entity_name": entity_name}),
        ("lower_layer_rows", "lower-layer chain", Q_LOWER_LAYER_CHAIN, {"entity_name": entity_name}),
        (
            "fragmentation_check_rows",
            "fragmentation check",
            Q_FRAGMENTATION_CHECK,
            {"entity_name": entity_name},
        ),
        (
            "catalog_check_rows",
            "catalog existence check",
            Q_CATALOG_EXISTENCE_CHECK,
            {"entity_name": entity_name},
        ),
    ]


def build_pairwise_query_specs(entity_a: str, entity_b: str) -> list[RetrievalBenchmarkQuerySpec]:
    return [
        (
            "pairwise_rows",
            "pairwise case",
            Q_PAIRWISE_CANONICAL,
            {"entity_a": entity_a, "entity_b": entity_b},
        )
    ]


def fetch_retrieval_benchmark_query_rows(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    *,
    base_params: Mapping[str, Any],
    query_specs: Sequence[RetrievalBenchmarkQuerySpec],
    logger: logging.Logger,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    with create_neo4j_driver(neo4j_settings) as driver:
        for result_key, log_label, cypher, extra_params in query_specs:
            logger.info("retrieval_benchmark: running %s query", log_label)
            records, _, _ = driver.execute_query(
                cypher,
                parameters_={**base_params, **(extra_params or {})},
                database_=neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            rows_by_key[result_key] = _records_to_dicts(records)
    return rows_by_key


__all__ = [
    "Q_CANONICAL_SINGLE",
    "Q_CATALOG_EXISTENCE_CHECK",
    "Q_CLUSTER_NAME_SINGLE",
    "Q_FRAGMENTATION_CHECK",
    "Q_LOWER_LAYER_CHAIN",
    "Q_PAIRWISE_CANONICAL",
    "RetrievalBenchmarkQuerySpec",
    "build_pairwise_query_specs",
    "build_single_entity_query_specs",
    "fetch_retrieval_benchmark_query_rows",
]