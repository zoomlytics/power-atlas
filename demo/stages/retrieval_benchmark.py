"""Post-hybrid retrieval benchmark stage.

Runs a fixed set of canonical-traversal and cluster-name-traversal queries
against a live Neo4j database and captures the results as a structured JSON
artifact for regression tracking.

The benchmark covers five canonical case types:

1. **single_entity** — single-entity canonical traversal for each benchmark
   entity (MercadoLibre, Xapo, Endeavor, Linda Rottenberg).
2. **pairwise_entity** — pairwise canonical claim lookup for each benchmark
   entity pair (Amazon ↔ eBay).
3. **fragmented_entity** — entities known to fragment under raw cluster-name
   traversal (e.g. an org that appears as both Organization and Person clusters).
4. **composite_claim** — entities whose claims have list-valued subject/object
   slots, exercising the list-split match path.
5. **canonical_vs_cluster** — side-by-side comparison of canonical-traversal
   claim counts vs. cluster-name-traversal claim counts; fragmentation is
   flagged when the cluster path returns more distinct clusters than the
   canonical path.

For each case the artifact records:

- ``canonical_rows`` — rows returned by the canonical traversal query.
- ``cluster_rows`` — rows returned by the parallel cluster-name traversal query.
- ``lower_layer_rows`` — rows from the full
  ``canonical → cluster → mention → claim`` inspection chain.
- ``fragmentation_check_rows`` — cluster-level fragmentation check rows.
- ``catalog_check_rows`` — rows from a direct ``CanonicalEntity`` existence
  check (used to distinguish *catalog absent* from *catalog present but
  canonical empty*).
- Derived counts: ``canonical_claim_count``, ``cluster_claim_count``,
  ``canonical_cluster_count``, ``cluster_name_cluster_count``,
  ``fragmentation_detected``.
- ``canonical_catalog_present`` — ``True`` when a ``CanonicalEntity`` node
  exists for the entity name (derived from ``catalog_check_rows``).
- ``fragmentation_type_hints`` — machine-readable cause tokens including the
  precise ``"catalog_absent"`` / ``"catalog_present_canonical_empty"`` sub-tokens
  that replace the ambiguous ``"catalog_absent_or_alignment_gap"`` token.

All queries use ``routing_=neo4j.RoutingControl.READ`` and never mutate graph
state.

Dataset scoping
---------------
In a multi-dataset graph, ``CanonicalEntity`` nodes from different datasets
share the same namespace.  Passing ``dataset_id`` to
:func:`run_retrieval_benchmark` constrains all ``CanonicalEntity`` lookups to
nodes whose ``dataset_id`` property matches, preventing cross-dataset leakage
(e.g. shared entities that exist in both ``demo_dataset_v1`` and
``demo_dataset_v2`` will not be double-counted).  The ``dataset_id`` is also
stamped as a top-level field in the benchmark artifact for auditability.

Omit ``dataset_id`` (or pass ``None``) to aggregate across *all* datasets —
useful for quick explorations but not suitable as a regression baseline in a
multi-dataset graph.

Usage (standalone script)
-------------------------
See ``pipelines/query/retrieval_benchmark.py`` for a CLI wrapper.

Usage (programmatic)
--------------------
>>> from demo.stages.retrieval_benchmark import run_retrieval_benchmark
>>> result = run_retrieval_benchmark(
...     config,
...     run_id="unstructured_ingest-...",
...     alignment_version="v1.0",
...     dataset_id="demo_dataset_v1",
... )
>>> print(result["artifact"]["benchmark_summary"])
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import neo4j

_logger = logging.getLogger(__name__)

__all__ = [
    "BENCHMARK_CASES",
    "BenchmarkCaseDefinition",
    "BenchmarkCaseResult",
    "RetrievalBenchmarkArtifact",
    "build_benchmark_case_result",
    "build_benchmark_artifact",
    "run_retrieval_benchmark",
    "_Q_CATALOG_EXISTENCE_CHECK",
]

# ---------------------------------------------------------------------------
# Static benchmark case definitions
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class BenchmarkCaseDefinition:
    """Static definition of a single benchmark case.

    Attributes
    ----------
    case_id:
        Unique short identifier for this case (e.g. ``"mercadolibre_single"``).
    case_type:
        One of ``"single_entity"``, ``"pairwise_entity"``,
        ``"fragmented_entity"``, ``"composite_claim"``,
        ``"canonical_vs_cluster"``.
    entity_names:
        Entity name fragments used to drive the ``toLower(...) CONTAINS``
        filter.  For single-entity cases this is a one-element list; for
        pairwise cases it contains exactly two names.
    description:
        Human-readable description of the case.
    expected_shape:
        Short description of what a *good* result looks like for this case.
    failure_modes:
        List of known failure patterns to watch for.
    lower_layer_checks:
        Which lower-layer checks provide explainability for this case.
    """

    case_id: str
    case_type: str
    entity_names: tuple[str, ...]
    description: str
    expected_shape: str
    failure_modes: tuple[str, ...]
    lower_layer_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        # Coerce mutable lists to immutable tuples so callers can pass either.
        object.__setattr__(self, "entity_names", tuple(self.entity_names))
        object.__setattr__(self, "failure_modes", tuple(self.failure_modes))
        object.__setattr__(self, "lower_layer_checks", tuple(self.lower_layer_checks))


#: Default benchmark cases derived from the benchmark specification.
#: Covers the five case types specified in the issue:
#:   single-entity, pairwise-entity, fragmented-entity, composite-claim,
#:   and canonical-vs-cluster comparison.
#: 9 entries: 4 single-entity, 1 pairwise-entity, 1 fragmented-entity,
#:            1 composite-claim, 2 canonical-vs-cluster.
BENCHMARK_CASES: list[BenchmarkCaseDefinition] = [
    # ------------------------------------------------------------------
    # 1. Single-entity retrieval
    # ------------------------------------------------------------------
    BenchmarkCaseDefinition(
        case_id="mercadolibre_single",
        case_type="single_entity",
        entity_names=["mercadolibre"],
        description=(
            "Single-entity canonical traversal for MercadoLibre. "
            "Exercises the canonical → cluster → mention → claim path for a "
            "well-known organization that may appear under multiple surface forms."
        ),
        expected_shape=(
            "At least one row with canonical_entity='MercadoLibre', one or more "
            "distinct cluster values, and claims with role='subject' or role='object'. "
            "The canonical path should return a single canonical_entity value with "
            "claims deduplicated across surface-form variants."
        ),
        failure_modes=[
            "canonical_rows empty — CanonicalEntity not present or ALIGNED_WITH edges missing",
            "lower_layer_rows shows cluster with zero claims — participation stage gap",
            "fragmentation_detected — cluster-name path returns more clusters than canonical",
        ],
        lower_layer_checks=[
            "canonical → cluster: verify ALIGNED_WITH edges present",
            "cluster → mention: verify MEMBER_OF edges present",
            "mention → claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="xapo_single",
        case_type="single_entity",
        entity_names=["xapo"],
        description=(
            "Single-entity canonical traversal for Xapo. "
            "Tests retrieval for a fintech entity that may appear under "
            "abbreviated and full-name surface forms."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Xapo', claims grouped under "
            "a single canonical entry point regardless of surface-form variation."
        ),
        failure_modes=[
            "canonical_rows empty — Xapo not in structured catalog or alignment failed",
            "cluster_rows returns zero results — entity not mentioned in unstructured source",
            "multiple canonical_entity values — duplicate CanonicalEntity nodes",
        ],
        lower_layer_checks=[
            "canonical → cluster: verify ALIGNED_WITH edges present",
            "cluster → mention: verify MEMBER_OF edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="endeavor_single",
        case_type="single_entity",
        entity_names=["endeavor"],
        description=(
            "Single-entity canonical traversal for Endeavor. "
            "Tests retrieval for a known entity present in the structured "
            "catalog and likely mentioned in unstructured sources."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Endeavor', at least one "
            "participating mention, and at least one associated claim."
        ),
        failure_modes=[
            "canonical_rows empty — Endeavor not in structured catalog",
            "lower_layer_rows shows zero claims — participation coverage gap",
        ],
        lower_layer_checks=[
            "canonical → cluster: verify ALIGNED_WITH edges present",
            "mention → claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="linda_rottenberg_single",
        case_type="single_entity",
        entity_names=["linda rottenberg"],
        description=(
            "Single-entity canonical traversal for Linda Rottenberg (Person). "
            "Tests retrieval for a named individual, verifying the person-entity "
            "path works symmetrically with org-entity cases."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Linda Rottenberg', entity_type='Person', "
            "claims where she appears as subject or object."
        ),
        failure_modes=[
            "canonical_rows empty — Linda Rottenberg not in structured catalog",
            "entity_type mismatch — mention clustered as Organization instead of Person",
            "lower_layer_rows shows cluster with zero claims",
        ],
        lower_layer_checks=[
            "canonical → cluster: verify ALIGNED_WITH edges present with entity_type='Person'",
            "cluster → mention: verify MEMBER_OF edges present",
            "mention → claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    # ------------------------------------------------------------------
    # 2. Pairwise entity claim lookup
    # ------------------------------------------------------------------
    BenchmarkCaseDefinition(
        case_id="amazon_ebay_pairwise",
        case_type="pairwise_entity",
        entity_names=["amazon", "ebay"],
        description=(
            "Pairwise canonical claim lookup for Amazon and eBay. "
            "Finds claims where both entities appear as participants (subject "
            "and/or object), verifying that pairwise canonical resolution works "
            "for two distinct organization entities."
        ),
        expected_shape=(
            "Zero or more rows each carrying both subject_canonical and object_canonical "
            "resolved to the correct canonical entities. Zero rows is acceptable if "
            "no cross-entity claims were extracted; what matters is the query returns "
            "without error and the canonical chain is traversable for both entities."
        ),
        failure_modes=[
            "query returns error — ALIGNED_WITH or MEMBER_OF edges missing for one entity",
            "result mixes unrelated entities — toLower CONTAINS filter too broad",
        ],
        lower_layer_checks=[
            "single-entity lower_layer check for each entity separately before pairwise",
        ],
    ),
    # ------------------------------------------------------------------
    # 3. Fragmented-entity cases
    # ------------------------------------------------------------------
    BenchmarkCaseDefinition(
        case_id="mercadolibre_fragmentation",
        case_type="fragmented_entity",
        entity_names=["mercadolibre"],
        description=(
            "Fragmentation check for MercadoLibre. "
            "Compares the number of distinct clusters returned by cluster-name "
            "traversal vs. canonical traversal. MercadoLibre is a known candidate "
            "for entity-type splits (e.g., appearing as both Organization and Person "
            "clusters under the same name text)."
        ),
        expected_shape=(
            "Canonical traversal returns a single canonical_entity value. "
            "Cluster-name traversal may return multiple rows if fragmentation "
            "exists; fragmentation_detected=True is the expected failure signal."
        ),
        failure_modes=[
            "fragmentation_detected=True — cluster-name returns more clusters than canonical",
            "canonical_rows empty — CanonicalEntity not present",
        ],
        lower_layer_checks=[
            "fragmentation_check_rows: inspect cluster_entity_type distribution",
            "canonical → cluster: confirm single aligned canonical entity",
        ],
    ),
    # ------------------------------------------------------------------
    # 4. Composite/list-valued claim cases
    # ------------------------------------------------------------------
    BenchmarkCaseDefinition(
        case_id="endeavor_composite",
        case_type="composite_claim",
        entity_names=["endeavor"],
        description=(
            "Composite/list-valued claim case for Endeavor. "
            "Looks for claims where the subject or object slot contains a "
            "list-valued expression (joined by 'and', 'or', '/', etc.) that "
            "was resolved via the list-split match path. This exercises the "
            "claim_participation list-split fallback."
        ),
        expected_shape=(
            "Rows where match_method='list_split' appear in canonical_rows or "
            "cluster_rows, or match_method='normalized_exact' for sub-tokens. "
            "If no list-split edges exist for this entity, the case is informative "
            "rather than a failure."
        ),
        failure_modes=[
            "match_method only shows raw_exact — list-split path was not exercised",
            "canonical_rows empty — Endeavor not reachable via canonical path",
        ],
        lower_layer_checks=[
            "canonical → cluster → mention → claim: inspect match_method per row",
            "check participation_metrics.json for list_split_suppressed count",
        ],
    ),
    # ------------------------------------------------------------------
    # 5. Canonical vs cluster-name comparison (summary cases)
    # ------------------------------------------------------------------
    BenchmarkCaseDefinition(
        case_id="xapo_canonical_vs_cluster",
        case_type="canonical_vs_cluster",
        entity_names=["xapo"],
        description=(
            "Canonical-traversal vs. cluster-name-traversal comparison for Xapo. "
            "Records the claim counts and cluster counts from both paths so that "
            "the delta can be tracked as a regression metric."
        ),
        expected_shape=(
            "canonical_claim_count >= cluster_claim_count (canonical deduplicates) or "
            "both counts equal (no fragmentation). "
            "cluster_name_cluster_count >= canonical_cluster_count (fragmentation is additive). "
            "fragmentation_detected=False is the healthy state."
        ),
        failure_modes=[
            "canonical_claim_count < cluster_claim_count — canonical path misses claims "
            "(investigate ALIGNED_WITH coverage; if canonical rows are entirely absent see catalog_present_canonical_empty hint)",
            "fragmentation_detected=True — cluster-name path returns spurious extra clusters",
        ],
        lower_layer_checks=[
            "canonical → cluster: inspect ALIGNED_WITH edges for alignment_method",
            "fragmentation_check_rows: entity_type distribution across clusters",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="linda_rottenberg_canonical_vs_cluster",
        case_type="canonical_vs_cluster",
        entity_names=["linda rottenberg"],
        description=(
            "Canonical-traversal vs. cluster-name-traversal comparison for Linda Rottenberg. "
            "Validates that Person-type entities also benefit from canonical deduplication."
        ),
        expected_shape=(
            "canonical_claim_count >= cluster_claim_count. "
            "fragmentation_detected=False is the healthy state for a named individual."
        ),
        failure_modes=[
            "fragmentation_detected=True — entity_type split produced both Person and Org clusters",
            "canonical_rows empty — Linda Rottenberg not in structured catalog",
        ],
        lower_layer_checks=[
            "canonical → cluster: verify entity_type='Person' on aligned cluster",
            "fragmentation_check_rows: confirm single entity_type across clusters",
        ],
    ),
]

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# Canonical single-entity traversal (hybrid mode)
# Returns all claims reachable via CanonicalEntity ← ALIGNED_WITH ← cluster ← MEMBER_OF ← mention
# dataset_id filter scopes CanonicalEntity nodes to the active dataset, preventing cross-dataset
# double-counting when the same entity name exists in multiple datasets.
_Q_CANONICAL_SINGLE = """\
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

# Cluster-name single-entity traversal (no canonical deduplication — fragmentation risk)
# Returns all claims reachable via ResolvedEntityCluster ← MEMBER_OF ← mention
_Q_CLUSTER_NAME_SINGLE = """\
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

# Full lower-layer inspection: canonical → cluster → mention → claim chain
# Uses OPTIONAL MATCH for claims so that dark mentions (no claims) are visible too.
# dataset_id filter scopes CanonicalEntity nodes to the active dataset.
_Q_LOWER_LAYER_CHAIN = """\
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
_Q_FRAGMENTATION_CHECK = """\
MATCH (cluster:ResolvedEntityCluster)
WHERE toLower(cluster.canonical_name) CONTAINS toLower($entity_name)
  AND ($run_id IS NULL OR cluster.run_id = $run_id)
RETURN cluster.cluster_id     AS cluster_id,
       cluster.canonical_name AS canonical_name,
       cluster.entity_type    AS entity_type
ORDER BY entity_type, canonical_name
"""

# Catalog existence check: does a CanonicalEntity node exist for this entity name?
# Read-only, no joins to clusters or mentions.  Used to distinguish "catalog absent"
# from "catalog present but canonical empty" in the canonical-empty / cluster-populated result class.
# Keep enough rows for diagnostics, but bound the result set so broad CONTAINS
# matches do not cause excessive query time or oversized benchmark artifacts.
# dataset_id filter prevents catalog hits from other datasets inflating the existence check.
_Q_CATALOG_EXISTENCE_CHECK = """\
MATCH (ce:CanonicalEntity)
WHERE toLower(ce.name) CONTAINS toLower($entity_name)
  AND ($dataset_id IS NULL OR ce.dataset_id = $dataset_id)
RETURN ce.name AS canonical_entity_name
ORDER BY ce.name
LIMIT 100
"""

# Pairwise canonical claim lookup — bidirectional
# Anchored on CanonicalEntity for selectivity — filters on names before joining clusters/mentions.
# dataset_id filter scopes both subject and object CanonicalEntity nodes to the active dataset.
_Q_PAIRWISE_CANONICAL = """\
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


# ---------------------------------------------------------------------------
# Result-shaping helpers
# ---------------------------------------------------------------------------


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    """Convert Neo4j ``Record`` objects to plain dicts."""
    return [dict(r) for r in records]


def _count_distinct(rows: list[dict[str, Any]], key: str) -> int:
    """Count distinct values of *key* across *rows*."""
    return len({r[key] for r in rows if r.get(key) is not None})


def _count_distinct_claims(rows: list[dict[str, Any]]) -> int:
    """Count distinct claim_id values across *rows*."""
    return _count_distinct(rows, "claim_id")


def _count_distinct_clusters(rows: list[dict[str, Any]]) -> int:
    """Count distinct clusters across *rows*, preferring cluster_id when available."""
    # Prefer the true cluster identity key when present to avoid canonical-name collisions.
    if any("cluster_id" in r for r in rows):
        return _count_distinct(rows, "cluster_id")
    # Fallback for legacy row shapes that only expose 'cluster' (e.g., canonical_name).
    return _count_distinct(rows, "cluster")


def _detect_fragmentation(
    canonical_cluster_count: int,
    cluster_name_cluster_count: int,
) -> bool:
    """Return True when the cluster-name path exposes more clusters than the canonical path.

    Fragmentation is defined as ``cluster_name_cluster_count > canonical_cluster_count``,
    meaning the raw text-match returns more distinct clusters than the canonical
    deduplication collapses — a signal that entity-type or spelling splits exist.
    """
    return cluster_name_cluster_count > canonical_cluster_count


def _classify_fragmentation_type(
    fragmentation_check_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    catalog_check_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return a list of hint strings classifying the cause of a canonical-empty or fragmented result.

    The hints are machine-readable tokens intended for reviewers and downstream
    tooling.  More than one hint may be returned when multiple causes apply.
    An empty list means neither condition was detected.

    Parameters
    ----------
    fragmentation_check_rows:
        Rows from the fragmentation check query (``ResolvedEntityCluster`` nodes
        matching the entity name).  Used to detect entity_type case-sensitivity
        splits.
    canonical_rows:
        Rows from the canonical traversal query.
    cluster_rows:
        Rows from the cluster-name traversal query.
    catalog_check_rows:
        Rows from the catalog existence check query (``CanonicalEntity`` nodes
        matching the entity name).  When provided, this enables the specific
        ``"catalog_absent"`` / ``"catalog_present_canonical_empty"`` distinction.  When ``None``
        (the default), the ambiguous ``"catalog_absent_or_alignment_gap"`` token
        is emitted instead.

    Returns
    -------
    List of zero or more of the following tokens:

    ``"entity_type_case_split"``
        At least two ``entity_type`` values appear in ``fragmentation_check_rows``
        whose lower-cased forms are identical (e.g., ``"Organization"`` and
        ``"organization"``).  This is the raw entity_type normalisation signal:
        the same conceptual type was persisted under two different case variants,
        producing distinct clusters that are not collapsed by the canonical path.

    ``"catalog_absent"``
        ``canonical_rows`` is empty while ``cluster_rows`` is non-empty, **and**
        ``catalog_check_rows`` is empty — confirming no ``CanonicalEntity`` node
        exists for this entity name.  The entity is absent from the structured
        catalog; adding it (and the corresponding ``ALIGNED_WITH`` edges) would
        enable canonical retrieval.

    ``"catalog_present_canonical_empty"``
        ``canonical_rows`` is empty while ``cluster_rows`` is non-empty, **and**
        ``catalog_check_rows`` is non-empty — confirming a ``CanonicalEntity``
        node exists but the canonical traversal still returns no rows.  The
        specific root cause (e.g., missing ``ALIGNED_WITH`` edges, canonical-name
        filter mismatch, or ambiguous catalog entries) is not determined by this
        token; it reflects only that the catalog is present and canonical
        retrieval returned no results.

    ``"catalog_absent_or_alignment_gap"``
        ``canonical_rows`` is empty while ``cluster_rows`` is non-empty, but
        ``catalog_check_rows`` was not provided (``None``), so the specific
        sub-cause cannot be determined.  This token is the backwards-compatible
        fallback when no catalog existence check was performed.
    """
    hints: list[str] = []

    # Detect entity_type case-sensitivity split:
    # Collect non-null entity_type values and check whether any pair of values
    # differs only by case normalization.
    entity_types = [
        r.get("entity_type")
        for r in fragmentation_check_rows
        if r.get("entity_type") is not None
    ]
    unique_types = set(entity_types)
    unique_lower = {et.lower() for et in unique_types}
    if len(unique_lower) < len(unique_types):
        hints.append("entity_type_case_split")

    # Detect canonical-empty / cluster-populated condition and classify as
    # catalog-absent vs catalog-present-but-canonical-empty when
    # catalog_check_rows is available.
    if not canonical_rows and cluster_rows:
        if catalog_check_rows is None:
            # No catalog existence check available; fall back to the ambiguous
            # combined token for backwards compatibility.
            hints.append("catalog_absent_or_alignment_gap")
        elif catalog_check_rows:
            # CanonicalEntity exists but canonical traversal returned no rows.
            # The specific root cause is not determined here; use graph health
            # diagnostics to investigate ALIGNED_WITH coverage.
            hints.append("catalog_present_canonical_empty")
        else:
            # No CanonicalEntity node found in the structured catalog.
            hints.append("catalog_absent")

    return hints


# ---------------------------------------------------------------------------
# Artifact dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class BenchmarkCaseResult:
    """Result for a single benchmark case.

    Attributes
    ----------
    case_id:
        Unique short identifier, mirrors :attr:`BenchmarkCaseDefinition.case_id`.
    case_type:
        One of the five benchmark case types.
    entity_names:
        Entity name fragments used as query parameters.
    description:
        Human-readable description of the case.
    expected_shape:
        Documentation string describing a good result.
    failure_modes:
        List of known failure patterns.
    canonical_rows:
        Rows returned by the canonical traversal query.
    cluster_rows:
        Rows returned by the cluster-name traversal query.
    lower_layer_rows:
        Rows from the full ``canonical → cluster → mention → claim`` chain.
    fragmentation_check_rows:
        Rows from the cluster fragmentation check.
    canonical_claim_count:
        Number of distinct claims reachable via canonical traversal.
    cluster_claim_count:
        Number of distinct claims reachable via cluster-name traversal.
    canonical_cluster_count:
        Number of distinct clusters visible through the canonical path.
    cluster_name_cluster_count:
        Number of distinct clusters matched by cluster-name text search.
    fragmentation_detected:
        ``True`` when ``cluster_name_cluster_count > canonical_cluster_count``.
    canonical_empty_cluster_populated:
        ``True`` when ``canonical_claim_count == 0`` and ``cluster_claim_count > 0``.
        Signals the "canonical-empty / cluster-populated" result class: the entity is
        reachable via cluster-name traversal but absent from the canonical path.
        Reviewers should consult ``fragmentation_type_hints`` to understand why.
    fragmentation_type_hints:
        List of machine-readable cause tokens derived by
        :func:`_classify_fragmentation_type`.  Possible values:

        - ``"entity_type_case_split"`` — entity_type values differ only by case
          (e.g., ``"Organization"`` vs ``"organization"``), producing distinct clusters.
        - ``"catalog_absent_or_alignment_gap"`` — canonical path returns no rows
          while the cluster-name path does; the entity is either absent from the
          structured catalog or its ``ALIGNED_WITH`` edges are missing.
          This token is emitted only when no ``catalog_check_rows`` are available
          to distinguish the sub-causes.  When ``catalog_check_rows`` are
          provided, the more specific ``"catalog_absent"`` or
          ``"catalog_present_canonical_empty"`` token is emitted instead.
        - ``"catalog_absent"`` — canonical path returns no rows, cluster-name
          path does, and the catalog existence check confirms no ``CanonicalEntity``
          node matches this entity name.  The entity is genuinely absent from the
          structured catalog.
        - ``"catalog_present_canonical_empty"`` — canonical path returns no rows,
          cluster-name path does, and the catalog existence check confirms a
          ``CanonicalEntity`` node exists for this entity name.  The specific root
          cause (e.g., missing ``ALIGNED_WITH`` edges, canonical-name filter
          mismatch, or ambiguous catalog entries) requires further investigation
          using graph health diagnostics.
    catalog_check_rows:
        Rows returned by the catalog existence check query
        (``CanonicalEntity`` nodes matching the entity name).  An empty list
        means no ``CanonicalEntity`` was found.  Non-empty means at least one
        node exists.  Used to compute ``canonical_catalog_present``.
    canonical_catalog_present:
        ``True`` when at least one ``CanonicalEntity`` node matched the entity
        name in the catalog existence check.  ``False`` when the entity is
        absent from the structured catalog.
    """

    case_id: str
    case_type: str
    entity_names: list[str]
    description: str
    expected_shape: str
    failure_modes: list[str]
    canonical_rows: list[dict[str, Any]]
    cluster_rows: list[dict[str, Any]]
    lower_layer_rows: list[dict[str, Any]]
    fragmentation_check_rows: list[dict[str, Any]]
    canonical_claim_count: int
    cluster_claim_count: int
    canonical_cluster_count: int
    cluster_name_cluster_count: int
    fragmentation_detected: bool
    canonical_empty_cluster_populated: bool
    fragmentation_type_hints: list[str]
    catalog_check_rows: list[dict[str, Any]]
    canonical_catalog_present: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PairwiseCaseResult:
    """Result for a pairwise benchmark case.

    Attributes
    ----------
    case_id:
        Unique identifier for this pairwise case.
    entity_names:
        Exactly two entity name fragments.
    description:
        Human-readable description.
    expected_shape:
        Documentation string describing a good result.
    failure_modes:
        List of known failure patterns.
    pairwise_rows:
        Rows returned by the pairwise canonical query.
    pairwise_claim_count:
        Number of distinct claims in ``pairwise_rows``.
    """

    case_id: str
    entity_names: list[str]
    description: str
    expected_shape: str
    failure_modes: list[str]
    pairwise_rows: list[dict[str, Any]]
    pairwise_claim_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class RetrievalBenchmarkArtifact:
    """Structured container for a single retrieval benchmark run.

    All fields are JSON-serialisable.

    Attributes
    ----------
    generated_at:
        ISO-8601 UTC timestamp of when the artifact was produced.
    run_id:
        The pipeline run_id this artifact is scoped to, or ``None`` when
        collected across all runs.
    dataset_id:
        The dataset this benchmark is scoped to, or ``None`` when collected
        across all datasets.  In a multi-dataset graph, always pass a
        ``dataset_id`` so that benchmark results are auditable and comparable
        across pipeline runs for the same dataset.
    alignment_version:
        The alignment version used to scope ``ALIGNED_WITH`` queries, or
        ``None`` when not specified.
    case_results:
        List of :class:`BenchmarkCaseResult` dicts (single-entity,
        fragmented-entity, composite-claim, and canonical-vs-cluster cases).
    pairwise_results:
        List of :class:`PairwiseCaseResult` dicts (pairwise-entity cases).
    benchmark_summary:
        Derived aggregate summary across all cases.
    """

    generated_at: str
    run_id: str | None
    dataset_id: str | None
    alignment_version: str | None
    case_results: list[dict[str, Any]]
    pairwise_results: list[dict[str, Any]]
    benchmark_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialise the artifact to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def _compute_benchmark_summary(
    case_results: list[BenchmarkCaseResult],
    pairwise_results: list[PairwiseCaseResult],
) -> dict[str, Any]:
    """Derive an aggregate summary from benchmark case results.

    Parameters
    ----------
    case_results:
        Single-entity, fragmented-entity, composite-claim, and
        canonical-vs-cluster results.
    pairwise_results:
        Pairwise-entity results.

    Returns
    -------
    dict with summary metrics.
    """
    total_cases = len(case_results) + len(pairwise_results)
    fragmentation_detected_count = sum(1 for r in case_results if r.fragmentation_detected)
    entities_with_claims_canonical = sum(1 for r in case_results if r.canonical_claim_count > 0)
    entities_with_claims_cluster = sum(1 for r in case_results if r.cluster_claim_count > 0)
    total_canonical_claims = sum(r.canonical_claim_count for r in case_results)
    total_cluster_claims = sum(r.cluster_claim_count for r in case_results)
    total_pairwise_claims = sum(r.pairwise_claim_count for r in pairwise_results)
    canonical_empty_cluster_populated_count = sum(
        1 for r in case_results if r.canonical_empty_cluster_populated
    )

    return {
        "total_cases": total_cases,
        "single_and_comparison_cases": len(case_results),
        "pairwise_cases": len(pairwise_results),
        "fragmentation_detected_count": fragmentation_detected_count,
        "canonical_empty_cluster_populated_count": canonical_empty_cluster_populated_count,
        "entities_with_claims_canonical": entities_with_claims_canonical,
        "entities_with_claims_cluster": entities_with_claims_cluster,
        "total_canonical_claims": total_canonical_claims,
        "total_cluster_claims": total_cluster_claims,
        "total_pairwise_claims": total_pairwise_claims,
    }


# ---------------------------------------------------------------------------
# Core builder (pure, no I/O)
# ---------------------------------------------------------------------------


def build_benchmark_case_result(
    *,
    case_def: BenchmarkCaseDefinition,
    canonical_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    lower_layer_rows: list[dict[str, Any]],
    fragmentation_check_rows: list[dict[str, Any]],
    catalog_check_rows: list[dict[str, Any]],
) -> BenchmarkCaseResult:
    """Build a :class:`BenchmarkCaseResult` from pre-fetched query rows.

    This function is intentionally free of I/O so it can be unit-tested
    without a running Neo4j instance.  All rows must be plain Python
    dicts (not Neo4j ``Record`` objects).

    Parameters
    ----------
    case_def:
        The static definition for this benchmark case.
    canonical_rows:
        Rows from the canonical traversal query.
    cluster_rows:
        Rows from the cluster-name traversal query.
    lower_layer_rows:
        Rows from the lower-layer chain inspection query.
    fragmentation_check_rows:
        Rows from the fragmentation check query.
    catalog_check_rows:
        Rows from the catalog existence check query (``CanonicalEntity`` nodes
        matching the entity name).  An empty list means no ``CanonicalEntity``
        was found; a non-empty list means at least one node exists.  Always
        provide this argument — pass ``[]`` when the catalog check returned no
        results.  When this list is empty, the ``"catalog_absent"`` hint is
        emitted (provided the canonical-empty / cluster-populated condition also
        holds); when non-empty, the ``"catalog_present_canonical_empty"`` hint is emitted instead.
    """
    canonical_claim_count = _count_distinct_claims(canonical_rows)
    cluster_claim_count = _count_distinct_claims(cluster_rows)
    canonical_cluster_count = _count_distinct_clusters(canonical_rows)
    cluster_name_cluster_count = _count_distinct(fragmentation_check_rows, "cluster_id")
    fragmentation = _detect_fragmentation(canonical_cluster_count, cluster_name_cluster_count)
    canonical_empty_cluster_populated = canonical_claim_count == 0 and cluster_claim_count > 0
    fragmentation_type_hints = _classify_fragmentation_type(
        fragmentation_check_rows, canonical_rows, cluster_rows, catalog_check_rows
    )
    canonical_catalog_present = bool(catalog_check_rows)

    return BenchmarkCaseResult(
        case_id=case_def.case_id,
        case_type=case_def.case_type,
        entity_names=list(case_def.entity_names),
        description=case_def.description,
        expected_shape=case_def.expected_shape,
        failure_modes=list(case_def.failure_modes),
        canonical_rows=canonical_rows,
        cluster_rows=cluster_rows,
        lower_layer_rows=lower_layer_rows,
        fragmentation_check_rows=fragmentation_check_rows,
        canonical_claim_count=canonical_claim_count,
        cluster_claim_count=cluster_claim_count,
        canonical_cluster_count=canonical_cluster_count,
        cluster_name_cluster_count=cluster_name_cluster_count,
        fragmentation_detected=fragmentation,
        canonical_empty_cluster_populated=canonical_empty_cluster_populated,
        fragmentation_type_hints=fragmentation_type_hints,
        catalog_check_rows=catalog_check_rows,
        canonical_catalog_present=canonical_catalog_present,
    )


def build_benchmark_artifact(
    *,
    run_id: str | None,
    dataset_id: str | None = None,
    alignment_version: str | None,
    case_results: list[BenchmarkCaseResult],
    pairwise_results: list[PairwiseCaseResult],
    generated_at: str | None = None,
) -> RetrievalBenchmarkArtifact:
    """Build a :class:`RetrievalBenchmarkArtifact` from pre-computed results.

    This function is intentionally free of I/O so it can be unit-tested
    without a running Neo4j instance.

    Parameters
    ----------
    run_id:
        Pipeline run_id to embed in the artifact, or ``None`` for an
        unscoped (all-runs) artifact.
    dataset_id:
        Dataset identifier to stamp in the artifact, or ``None`` for an
        unscoped (all-datasets) artifact.  Pass this whenever the benchmark
        was run against a specific dataset so the artifact is auditable.
    alignment_version:
        Alignment version to embed, or ``None`` when not applicable.
    case_results:
        Results for single-entity, fragmented-entity, composite-claim, and
        canonical-vs-cluster cases.
    pairwise_results:
        Results for pairwise-entity cases.
    generated_at:
        ISO-8601 timestamp string.  If ``None``, the current UTC time is used.
    """
    ts = generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = _compute_benchmark_summary(case_results, pairwise_results)
    return RetrievalBenchmarkArtifact(
        generated_at=ts,
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        case_results=[r.to_dict() for r in case_results],
        pairwise_results=[r.to_dict() for r in pairwise_results],
        benchmark_summary=summary,
    )


# ---------------------------------------------------------------------------
# Pipeline stage entry point
# ---------------------------------------------------------------------------


def run_retrieval_benchmark(
    config: Any,
    *,
    run_id: str | None = None,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    benchmark_cases: list[BenchmarkCaseDefinition] | None = None,
    _suppress_alignment_version_warning: bool = False,
) -> dict[str, Any]:
    """Run the retrieval benchmark and write a JSON artifact.

    Connects to Neo4j using credentials from *config*, runs the full set of
    benchmark queries for each case defined in *benchmark_cases* (defaulting to
    :data:`BENCHMARK_CASES`), and persists the result as a JSON artifact under
    ``<output_dir>/runs/<run_id>/retrieval_benchmark/retrieval_benchmark.json``
    (or ``<output_dir>/runs/retrieval_benchmark/retrieval_benchmark.json`` when
    no ``run_id`` is given).

    Parameters
    ----------
    config:
        :class:`~demo.contracts.runtime.Config` instance providing
        ``neo4j_uri``, ``neo4j_username``, ``neo4j_password``,
        ``neo4j_database``, ``output_dir``, and ``dry_run``.
    run_id:
        Scopes all queries to a specific pipeline run.  Pass ``None`` to
        collect aggregate metrics across all runs.
    dataset_id:
        Scopes all ``CanonicalEntity`` queries to a specific dataset, preventing
        cross-dataset double-counting of shared entity names.  Pass ``None`` to
        aggregate across all datasets (suitable for exploration only — not for
        regression baselines in a multi-dataset graph).  The value is stamped
        as a top-level field in the artifact for auditability.
    alignment_version:
        Scopes alignment queries to a specific alignment version (e.g.
        ``"v1.0"``).  Pass ``None`` to aggregate across all versions.
    output_dir:
        Base output directory.  Artifacts are written under
        ``<output_dir>/runs/<run_id>/retrieval_benchmark/`` (scoped) or
        ``<output_dir>/runs/retrieval_benchmark/`` (unscoped).  Defaults to
        ``config.output_dir``.
    benchmark_cases:
        List of :class:`BenchmarkCaseDefinition` objects to run.  Defaults
        to :data:`BENCHMARK_CASES`.
    _suppress_alignment_version_warning:
        When ``True``, suppresses the ``alignment_version is None`` warning
        emitted by this function.  Pass ``True`` from an orchestrator that has
        already logged its own warning for the same event to avoid duplicate
        log entries.  Standalone callers should leave this at the default
        ``False`` so the warning is visible.

    Returns
    -------
    A dict with ``status``, ``run_id``, ``dataset_id``, ``alignment_version``,
    ``artifact_path``, and the full ``artifact`` payload.
    """
    cases = benchmark_cases if benchmark_cases is not None else BENCHMARK_CASES
    effective_output_dir = output_dir if output_dir is not None else config.output_dir
    effective_output_dir = Path(effective_output_dir)

    runs_root = (effective_output_dir / "runs").resolve()

    if run_id == "":
        raise ValueError("run_id must be None or a non-empty string.")

    if dataset_id == "":
        raise ValueError("dataset_id must be None or a non-empty string.")

    if run_id is not None:
        run_id_path = Path(run_id)
        if run_id_path.is_absolute() or ".." in run_id_path.parts or run_id_path.name != run_id:
            raise ValueError(
                f"Invalid run_id {run_id!r}: must be a simple relative name without path separators or '..'."
            )
        run_root = (runs_root / run_id_path).resolve()
        if run_root == runs_root or runs_root not in run_root.parents:
            raise ValueError(
                f"Invalid run_id {run_id!r}: must resolve to a subdirectory of the runs directory."
            )
        artifact_dir = run_root / "retrieval_benchmark"
    else:
        artifact_dir = runs_root / "retrieval_benchmark"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "retrieval_benchmark.json"

    # Warn when alignment_version is None so callers are aware that the
    # benchmark will aggregate across all versions.  The warning is suppressed
    # when _suppress_alignment_version_warning=True to avoid a duplicate log
    # entry in orchestrated runs where the orchestrator has already emitted its
    # own warning for the same event.
    if alignment_version is None and not _suppress_alignment_version_warning:
        _logger.warning(
            "run_retrieval_benchmark: alignment_version is None — benchmark will aggregate "
            "across ALL alignment versions in the database, not just the current cohort. "
            "Pass alignment_version (e.g. from the hybrid entity resolution stage output) "
            "to scope queries to the intended ALIGNED_WITH edge version."
        )

    if getattr(config, "dry_run", False):
        dry_artifact_obj = build_benchmark_artifact(
            run_id=run_id,
            dataset_id=dataset_id,
            alignment_version=alignment_version,
            case_results=[],
            pairwise_results=[],
        )
        artifact_path.write_text(dry_artifact_obj.to_json(), encoding="utf-8")
        return {
            "status": "dry_run",
            "run_id": run_id,
            "dataset_id": dataset_id,
            "alignment_version": alignment_version,
            "artifact_path": str(artifact_path),
            "artifact": None,
            "warnings": ["retrieval benchmark skipped in dry_run mode"],
        }

    params: dict[str, Any] = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "alignment_version": alignment_version,
    }

    with neo4j.GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_username, config.neo4j_password),
    ) as driver:

        def _query(cypher: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            p = {**params, **(extra or {})}
            records, _, _ = driver.execute_query(
                cypher,
                parameters_=p,
                database_=config.neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            return _records_to_dicts(records)

        case_results: list[BenchmarkCaseResult] = []
        pairwise_results: list[PairwiseCaseResult] = []

        for case_def in cases:
            if not case_def.entity_names:
                raise ValueError(
                    f"retrieval_benchmark: case {case_def.case_id!r} has empty entity_names"
                )
            entity_name = case_def.entity_names[0]

            if case_def.case_type == "pairwise_entity":
                if len(case_def.entity_names) < 2:
                    _logger.warning(
                        "retrieval_benchmark: pairwise case %r has fewer than 2 entity names; skipping",
                        case_def.case_id,
                    )
                    continue
                entity_a = case_def.entity_names[0]
                entity_b = case_def.entity_names[1]
                _logger.info(
                    "retrieval_benchmark: running pairwise case %r (%r ↔ %r)",
                    case_def.case_id,
                    entity_a,
                    entity_b,
                )
                pairwise_rows = _query(
                    _Q_PAIRWISE_CANONICAL,
                    {"entity_a": entity_a, "entity_b": entity_b},
                )
                pairwise_results.append(
                    PairwiseCaseResult(
                        case_id=case_def.case_id,
                        entity_names=list(case_def.entity_names),
                        description=case_def.description,
                        expected_shape=case_def.expected_shape,
                        failure_modes=list(case_def.failure_modes),
                        pairwise_rows=pairwise_rows,
                        pairwise_claim_count=_count_distinct_claims(pairwise_rows),
                    )
                )
            else:
                _logger.info(
                    "retrieval_benchmark: running case %r (entity=%r)",
                    case_def.case_id,
                    entity_name,
                )
                canonical_rows = _query(
                    _Q_CANONICAL_SINGLE, {"entity_name": entity_name}
                )
                cluster_rows = _query(
                    _Q_CLUSTER_NAME_SINGLE, {"entity_name": entity_name}
                )
                lower_layer_rows = _query(
                    _Q_LOWER_LAYER_CHAIN, {"entity_name": entity_name}
                )
                fragmentation_check_rows = _query(
                    _Q_FRAGMENTATION_CHECK, {"entity_name": entity_name}
                )
                catalog_check_rows = _query(
                    _Q_CATALOG_EXISTENCE_CHECK, {"entity_name": entity_name}
                )
                case_results.append(
                    build_benchmark_case_result(
                        case_def=case_def,
                        canonical_rows=canonical_rows,
                        cluster_rows=cluster_rows,
                        lower_layer_rows=lower_layer_rows,
                        fragmentation_check_rows=fragmentation_check_rows,
                        catalog_check_rows=catalog_check_rows,
                    )
                )

    artifact = build_benchmark_artifact(
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        case_results=case_results,
        pairwise_results=pairwise_results,
    )

    artifact_path.write_text(artifact.to_json(), encoding="utf-8")
    _logger.info("retrieval_benchmark: artifact written to %s", artifact_path)

    return {
        "status": "live",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "alignment_version": alignment_version,
        "artifact_path": str(artifact_path),
        "artifact": artifact.to_dict(),
        "warnings": [],
    }
