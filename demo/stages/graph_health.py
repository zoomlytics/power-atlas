"""Graph-health diagnostics stage.

Runs a fixed set of read-only Cypher queries against a live Neo4j database and
returns a structured JSON artifact capturing key graph-health metrics for a given
pipeline run.  The artifact is scoped by ``run_id`` (and optionally
``alignment_version``) so it can be versioned and diffed across runs.

Metrics collected
-----------------
The artifact mirrors the diagnostic section (12) of
``pipelines/query/README.md`` and covers five areas:

1. **Participation coverage** — ``HAS_PARTICIPANT`` edge counts by role and the
   distribution of edges per ``ExtractedClaim`` (revealing claims left
   unlinked).
2. **Mention clustering** — total and unclustered ``EntityMention`` counts
   together with the cluster-size distribution.
3. **Cluster fragmentation** — distribution of how many distinct entity types
   appear inside each ``ResolvedEntityCluster``.  Healthy clusters have exactly
   one distinct type.
4. **Alignment coverage** — aligned vs unaligned ``ResolvedEntityCluster``
   counts for the given ``alignment_version``, plus a per-canonical breakdown
   of aligned clusters and bridged mentions.
5. **End-to-end chain** — for each ``CanonicalEntity``, counts of reachable
   mentions and claims via the full hybrid path
   (``ALIGNED_WITH`` → ``MEMBER_OF`` → ``HAS_PARTICIPANT``).

All queries use ``routing_=neo4j.RoutingControl.READ`` and accept explicit
``run_id`` / ``alignment_version`` parameters; they never mutate graph state.

Usage (standalone script)
-------------------------
See ``pipelines/query/graph_health_diagnostics.py`` for a CLI wrapper.

Usage (programmatic)
--------------------
>>> from demo.stages.graph_health import run_graph_health_diagnostics
>>> result = run_graph_health_diagnostics(config, run_id="unstructured_ingest-...", alignment_version="v1.0")
>>> print(result["artifact"]["participation_summary"])
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from demo.stages.entity_resolution import build_entity_type_cypher_case as _build_entity_type_cypher_case

_logger = logging.getLogger(__name__)

__all__ = [
    "GraphHealthArtifact",
    "build_graph_health_artifact",
    "run_graph_health_diagnostics",
]

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# All queries that are run_id-scoped accept a $run_id parameter.  Queries that
# are scoped by alignment_version also accept $alignment_version.  Global
# (unscoped) variants exist as a fallback when no run_id is provided.

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


def _build_cluster_type_fragmentation_query() -> str:
    """Build the cluster type-fragmentation Cypher query.

    The normalization applied to ``m.entity_type`` inside the query is derived
    directly from :func:`~demo.stages.entity_resolution.build_entity_type_cypher_case`,
    which reflects the same :data:`~demo.stages.entity_resolution._ENTITY_TYPE_SYNONYMS`
    table used by entity resolution at cluster-assignment time.  This ensures that
    graph-health fragmentation diagnostics are semantically consistent with actual
    clustering behaviour.
    """
    _indent = "     "  # aligns continuation lines under the opening CASE keyword
    case_expr = _build_entity_type_cypher_case("m.entity_type")
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


_Q_CLUSTER_TYPE_FRAGMENTATION = _build_cluster_type_fragmentation_query()

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

# Row limits applied by the detailed per-entity queries that follow.  Used to detect
# when results may be truncated and to surface a warning to callers.  The
# query strings are built from these constants so that the limit is defined in
# exactly one place.
_PER_CANONICAL_ALIGNMENT_LIMIT = 30
_CANONICAL_CHAIN_HEALTH_LIMIT = 30

_Q_PER_CANONICAL_ALIGNMENT = f"""\
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
LIMIT {_PER_CANONICAL_ALIGNMENT_LIMIT}
"""

_Q_CANONICAL_CHAIN_HEALTH = f"""\
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
LIMIT {_CANONICAL_CHAIN_HEALTH_LIMIT}
"""


# ---------------------------------------------------------------------------
# Result-shaping helpers
# ---------------------------------------------------------------------------


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    """Convert Neo4j ``Record`` objects to plain dicts."""
    return [dict(r) for r in records]


def _compute_participation_summary(
    role_dist: list[dict[str, Any]],
    edge_coverage: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive high-level participation summary from raw query rows.

    Parameters
    ----------
    role_dist:
        Rows from :data:`_Q_PARTICIPATION_ROLE_DIST`.
    edge_coverage:
        Rows from :data:`_Q_CLAIM_EDGE_COVERAGE`.

    Returns
    -------
    dict with ``total_edges``, ``edges_by_role``, ``total_claims``,
    ``claims_with_zero_edges``, and ``claim_coverage_pct``.
    """
    total_edges: int = sum(r["total"] for r in role_dist)
    edges_by_role: dict[str, int] = {r["role"]: r["total"] for r in role_dist}

    total_claims: int = sum(r["claim_count"] for r in edge_coverage)
    claims_zero: int = next(
        (r["claim_count"] for r in edge_coverage if r["participant_edges"] == 0), 0
    )
    claims_nonzero = total_claims - claims_zero
    coverage_pct: float | None = None
    if total_claims > 0:
        coverage_pct = round(claims_nonzero / total_claims * 100, 2)
    return {
        "total_edges": total_edges,
        "edges_by_role": edges_by_role,
        "total_claims": total_claims,
        "claims_with_zero_edges": claims_zero,
        "claim_coverage_pct": coverage_pct,
    }


def _compute_mention_summary(
    clustering_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive mention summary from raw clustering query rows.

    Parameters
    ----------
    clustering_rows:
        Rows from :data:`_Q_MENTION_CLUSTERING` (``is_clustered``,
        ``mention_count``).

    Returns
    -------
    dict with ``total_mentions``, ``clustered_mentions``,
    ``unclustered_mentions``, and ``unresolved_rate_pct``.
    """
    by_status: dict[bool, int] = {r["is_clustered"]: r["mention_count"] for r in clustering_rows}
    clustered: int = by_status.get(True, 0)
    unclustered: int = by_status.get(False, 0)
    total = clustered + unclustered
    rate: float | None = None
    if total > 0:
        rate = round(unclustered / total * 100, 2)
    return {
        "total_mentions": total,
        "clustered_mentions": clustered,
        "unclustered_mentions": unclustered,
        "unresolved_rate_pct": rate,
    }


def _compute_alignment_summary(
    alignment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive alignment summary from raw coverage query rows.

    Parameters
    ----------
    alignment_rows:
        Rows from :data:`_Q_ALIGNMENT_COVERAGE` (``is_aligned``,
        ``cluster_count``).

    Returns
    -------
    dict with ``total_clusters``, ``aligned_clusters``, ``unaligned_clusters``,
    and ``alignment_coverage_pct``.
    """
    by_status: dict[bool, int] = {r["is_aligned"]: r["cluster_count"] for r in alignment_rows}
    aligned: int = by_status.get(True, 0)
    unaligned: int = by_status.get(False, 0)
    total = aligned + unaligned
    pct: float | None = None
    if total > 0:
        pct = round(aligned / total * 100, 2)
    return {
        "total_clusters": total,
        "aligned_clusters": aligned,
        "unaligned_clusters": unaligned,
        "alignment_coverage_pct": pct,
    }


# ---------------------------------------------------------------------------
# Artifact dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class GraphHealthArtifact:
    """Structured container for a single graph-health diagnostics run.

    All fields are JSON-serialisable.  ``alignment_*`` fields are usually
    populated (often with empty lists and an ``alignment_coverage_pct`` of
    0.0); ``None`` values mainly indicate that no clustering/alignment data
    exists for the given scope.  ``alignment_version`` is ``None`` when no
    alignment version was requested.

    Attributes
    ----------
    generated_at:
        ISO-8601 UTC timestamp of when the artifact was produced.
    run_id:
        The pipeline run_id this artifact is scoped to, or ``None`` when
        collected across all runs.
    alignment_version:
        The alignment version used to scope alignment queries, or ``None``
        when no alignment version was requested.
    participation_role_distribution:
        Raw rows from the role-distribution query
        (``[{"role": ..., "total": ...}, ...]``).
    claim_edge_coverage_distribution:
        Raw rows from the claim-edge coverage query
        (``[{"participant_edges": ..., "claim_count": ...}, ...]``).
    match_method_distribution:
        Raw rows from the match-method distribution query
        (``[{"match_method": ..., "total": ...}, ...]``).
    mention_clustering:
        Raw rows from the mention clustering query
        (``[{"is_clustered": ..., "mention_count": ...}, ...]``).
    cluster_size_distribution:
        Raw rows from the cluster-size distribution query.
    cluster_type_fragmentation:
        Raw rows from the type-fragmentation query (``distinct_types_in_cluster``
        → ``cluster_count``).
    alignment_coverage:
        Raw rows from the alignment-coverage query
        (``[{"is_aligned": ..., "cluster_count": ...}, ...]``).
    per_canonical_alignment:
        Raw rows from the per-canonical alignment query (top 30 canonical
        entities by aligned cluster count).
    canonical_chain_health:
        Raw rows from the end-to-end chain health query (top 30 canonicals).
    participation_summary:
        Derived high-level summary — ``total_edges``, ``edges_by_role``,
        ``total_claims``, ``claims_with_zero_edges``, ``claim_coverage_pct``.
    mention_summary:
        Derived summary — ``total_mentions``, ``clustered_mentions``,
        ``unclustered_mentions``, ``unresolved_rate_pct``.
    alignment_summary:
        Derived summary — ``total_clusters``, ``aligned_clusters``,
        ``unaligned_clusters``, ``alignment_coverage_pct``.
    """

    generated_at: str
    run_id: str | None
    alignment_version: str | None
    participation_role_distribution: list[dict[str, Any]]
    claim_edge_coverage_distribution: list[dict[str, Any]]
    match_method_distribution: list[dict[str, Any]]
    mention_clustering: list[dict[str, Any]]
    cluster_size_distribution: list[dict[str, Any]]
    cluster_type_fragmentation: list[dict[str, Any]]
    alignment_coverage: list[dict[str, Any]]
    per_canonical_alignment: list[dict[str, Any]]
    canonical_chain_health: list[dict[str, Any]]
    participation_summary: dict[str, Any]
    mention_summary: dict[str, Any]
    alignment_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialise the artifact to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Core builder (pure, no I/O — accepts pre-fetched rows)
# ---------------------------------------------------------------------------


def build_graph_health_artifact(
    *,
    run_id: str | None,
    alignment_version: str | None,
    participation_role_distribution: list[dict[str, Any]],
    claim_edge_coverage_distribution: list[dict[str, Any]],
    match_method_distribution: list[dict[str, Any]],
    mention_clustering: list[dict[str, Any]],
    cluster_size_distribution: list[dict[str, Any]],
    cluster_type_fragmentation: list[dict[str, Any]],
    alignment_coverage: list[dict[str, Any]],
    per_canonical_alignment: list[dict[str, Any]],
    canonical_chain_health: list[dict[str, Any]],
    generated_at: str | None = None,
) -> GraphHealthArtifact:
    """Build a :class:`GraphHealthArtifact` from pre-fetched query rows.

    This function is intentionally free of I/O so it can be unit-tested
    without a running Neo4j instance.  All rows must be plain Python
    dicts (not Neo4j ``Record`` objects).

    Parameters
    ----------
    run_id:
        Pipeline run_id to embed in the artifact, or ``None`` for
        an unscoped (all-runs) artifact.
    alignment_version:
        Alignment version to embed, or ``None`` when not applicable.
    participation_role_distribution:
        Rows from :data:`_Q_PARTICIPATION_ROLE_DIST`.
    claim_edge_coverage_distribution:
        Rows from :data:`_Q_CLAIM_EDGE_COVERAGE`.
    match_method_distribution:
        Rows from :data:`_Q_MATCH_METHOD_DIST`.
    mention_clustering:
        Rows from :data:`_Q_MENTION_CLUSTERING`.
    cluster_size_distribution:
        Rows from :data:`_Q_CLUSTER_SIZE_DIST`.
    cluster_type_fragmentation:
        Rows from :data:`_Q_CLUSTER_TYPE_FRAGMENTATION`.
    alignment_coverage:
        Rows from :data:`_Q_ALIGNMENT_COVERAGE`.
    per_canonical_alignment:
        Rows from :data:`_Q_PER_CANONICAL_ALIGNMENT`.
    canonical_chain_health:
        Rows from :data:`_Q_CANONICAL_CHAIN_HEALTH`.
    generated_at:
        ISO-8601 timestamp string.  If ``None``, the current UTC time is used.

    Returns
    -------
    :class:`GraphHealthArtifact`
    """
    ts = generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    participation_summary = _compute_participation_summary(
        participation_role_distribution, claim_edge_coverage_distribution
    )
    mention_summary = _compute_mention_summary(mention_clustering)
    alignment_summary = _compute_alignment_summary(alignment_coverage)
    return GraphHealthArtifact(
        generated_at=ts,
        run_id=run_id,
        alignment_version=alignment_version,
        participation_role_distribution=participation_role_distribution,
        claim_edge_coverage_distribution=claim_edge_coverage_distribution,
        match_method_distribution=match_method_distribution,
        mention_clustering=mention_clustering,
        cluster_size_distribution=cluster_size_distribution,
        cluster_type_fragmentation=cluster_type_fragmentation,
        alignment_coverage=alignment_coverage,
        per_canonical_alignment=per_canonical_alignment,
        canonical_chain_health=canonical_chain_health,
        participation_summary=participation_summary,
        mention_summary=mention_summary,
        alignment_summary=alignment_summary,
    )


# ---------------------------------------------------------------------------
# Pipeline stage entry point
# ---------------------------------------------------------------------------


def run_graph_health_diagnostics(
    config: Any,
    *,
    run_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, Any]:
    """Run graph-health diagnostics and write a JSON artifact.

    Connects to Neo4j using credentials from *config*, runs the full set of
    diagnostic read queries, and persists the result as a JSON artifact under
    ``<output_dir>/runs/<run_id>/graph_health/graph_health_diagnostics.json``
    (or ``<output_dir>/runs/graph_health/graph_health_diagnostics.json`` when no
    ``run_id`` is given).

    Parameters
    ----------
    config:
        :class:`~power_atlas.contracts.runtime.Config` instance providing
        ``neo4j_uri``, ``neo4j_username``, ``neo4j_password``,
        ``neo4j_database``, ``output_dir``, and ``dry_run``.
    run_id:
        Scopes all queries to a specific pipeline run.  Pass ``None`` to
        collect aggregate metrics across all runs (useful for a quick
        whole-database health check).  **Warning:** omitting ``run_id``
        aggregates across all runs in the database; results may mix data
        from different pipeline executions.
    alignment_version:
        Scopes alignment queries to a specific alignment version (e.g.
        ``"v1.0"``).  Pass ``None`` to aggregate across all alignment
        versions — or when no ``ALIGNED_WITH`` edges exist.  **Warning:**
        omitting ``alignment_version`` aggregates across all alignment
        versions; alignment metrics may be inflated or mixed across cohorts.
    output_dir:
        Base output directory.  Artifacts are written under
        ``<output_dir>/runs/<run_id>/graph_health/`` (scoped) or
        ``<output_dir>/runs/graph_health/`` (unscoped).  Defaults to
        ``config.output_dir``.
    suppress_alignment_version_warning:
        When ``True``, suppresses the ``alignment_version is None`` warning
        emitted by this function.  Pass ``True`` from an orchestrator that has
        already logged its own warning for the same event to avoid duplicate
        log entries.  Standalone callers should leave this at the default
        ``False`` so the warning is visible.

    Returns
    -------
    A dict with ``status``, ``run_id``, ``alignment_version``,
    ``artifact_path``, ``artifact`` payload, and a ``warnings`` list.
    The ``warnings`` list contains any scoping or truncation warnings emitted
    during the run so that CLI wrappers and programmatic callers can inspect
    or re-emit them.
    """
    effective_output_dir = output_dir if output_dir is not None else config.output_dir
    effective_output_dir = Path(effective_output_dir)

    # Determine artifact output path.
    # Unscoped diagnostics still live under "runs/" to align with the repository's
    # artifact layout convention (stage outputs are always under <output_dir>/runs/).
    runs_root = (effective_output_dir / "runs").resolve()

    # Treat only None as "unscoped". Reject the empty string to avoid ambiguity
    # between an explicitly empty run_id and a genuinely unscoped artifact.
    if run_id == "":
        raise ValueError("run_id must be None or a non-empty string.")

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
        artifact_dir = run_root / "graph_health"
    else:
        artifact_dir = runs_root / "graph_health"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "graph_health_diagnostics.json"

    # Collect scoping warnings before dry_run/live-mode handling so they are
    # surfaced uniformly in both modes.
    collected_warnings: list[str] = []

    if run_id is None:
        msg = (
            "run_graph_health_diagnostics: run_id is None — diagnostics will aggregate "
            "across ALL pipeline runs in the database, not just the current run. "
            "Pass run_id to scope queries to the intended pipeline execution."
        )
        collected_warnings.append(msg)

    if alignment_version is None and not suppress_alignment_version_warning:
        msg = (
            "run_graph_health_diagnostics: alignment_version is None — alignment "
            "metrics will aggregate across ALL alignment versions in the database, "
            "not just the current cohort. "
            "Pass alignment_version (e.g. from the hybrid entity resolution stage output) "
            "to scope queries to the intended ALIGNED_WITH edge version."
        )
        collected_warnings.append(msg)

    if getattr(config, "dry_run", False):
        # In dry_run mode, write a file with the same schema as the live artifact
        # by building a real GraphHealthArtifact from empty row lists.  This
        # ensures the on-disk format is fully stable — including all summary
        # keys — regardless of dry_run state.
        dry_artifact_obj = build_graph_health_artifact(
            run_id=run_id,
            alignment_version=alignment_version,
            participation_role_distribution=[],
            claim_edge_coverage_distribution=[],
            match_method_distribution=[],
            mention_clustering=[],
            cluster_size_distribution=[],
            cluster_type_fragmentation=[],
            alignment_coverage=[],
            per_canonical_alignment=[],
            canonical_chain_health=[],
        )
        artifact_path.write_text(dry_artifact_obj.to_json(), encoding="utf-8")
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "alignment_version": alignment_version,
            "artifact_path": str(artifact_path),
            "artifact": None,
            "warnings": ["graph health diagnostics skipped in dry_run mode"] + collected_warnings,
        }
        return summary

    params: dict[str, Any] = {
        "run_id": run_id,
        "alignment_version": alignment_version,
    }

    with create_neo4j_driver(config) as driver:
        def _query(cypher: str) -> list[dict[str, Any]]:
            records, _, _ = driver.execute_query(
                cypher,
                parameters_=params,
                database_=config.neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            return _records_to_dicts(records)

        _logger.info("graph_health: running participation role distribution query")
        role_dist = _query(_Q_PARTICIPATION_ROLE_DIST)

        _logger.info("graph_health: running claim edge coverage query")
        edge_coverage = _query(_Q_CLAIM_EDGE_COVERAGE)

        _logger.info("graph_health: running match method distribution query")
        match_method_dist = _query(_Q_MATCH_METHOD_DIST)

        _logger.info("graph_health: running mention clustering query")
        mention_clustering = _query(_Q_MENTION_CLUSTERING)

        _logger.info("graph_health: running cluster size distribution query")
        cluster_size_dist = _query(_Q_CLUSTER_SIZE_DIST)

        _logger.info("graph_health: running cluster type fragmentation query")
        cluster_type_frag = _query(_Q_CLUSTER_TYPE_FRAGMENTATION)

        _logger.info("graph_health: running alignment coverage query")
        alignment_coverage = _query(_Q_ALIGNMENT_COVERAGE)

        _logger.info("graph_health: running per-canonical alignment query")
        per_canonical = _query(_Q_PER_CANONICAL_ALIGNMENT)

        _logger.info("graph_health: running canonical chain health query")
        chain_health = _query(_Q_CANONICAL_CHAIN_HEALTH)

    artifact = build_graph_health_artifact(
        run_id=run_id,
        alignment_version=alignment_version,
        participation_role_distribution=role_dist,
        claim_edge_coverage_distribution=edge_coverage,
        match_method_distribution=match_method_dist,
        mention_clustering=mention_clustering,
        cluster_size_distribution=cluster_size_dist,
        cluster_type_fragmentation=cluster_type_frag,
        alignment_coverage=alignment_coverage,
        per_canonical_alignment=per_canonical,
        canonical_chain_health=chain_health,
    )

    artifact_path.write_text(artifact.to_json(), encoding="utf-8")
    _logger.info("graph_health: artifact written to %s", artifact_path)

    # Detect truncation: if a capped query returned exactly its row limit the
    # result set may be incomplete.  Surface this as a warning so callers and
    # CLI consumers can tell when per-entity detail tables are partial.
    if len(per_canonical) == _PER_CANONICAL_ALIGNMENT_LIMIT:
        msg = (
            f"run_graph_health_diagnostics: per_canonical_alignment result is at the "
            f"query row limit ({_PER_CANONICAL_ALIGNMENT_LIMIT} rows) — the detail table "
            f"may be truncated and not reflect all canonical entities in the current scope."
        )
        collected_warnings.append(msg)

    if len(chain_health) == _CANONICAL_CHAIN_HEALTH_LIMIT:
        msg = (
            f"run_graph_health_diagnostics: canonical_chain_health result is at the "
            f"query row limit ({_CANONICAL_CHAIN_HEALTH_LIMIT} rows) — the detail table "
            f"may be truncated and not reflect all canonical entities in the current scope."
        )
        collected_warnings.append(msg)

    return {
        "status": "live",
        "run_id": run_id,
        "alignment_version": alignment_version,
        "artifact_path": str(artifact_path),
        "artifact": artifact.to_dict(),
        "warnings": collected_warnings,
    }
