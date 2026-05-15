"""Graph-health diagnostics stage.

Runs a fixed set of read-only Cypher queries against a live Neo4j database and
returns a structured JSON artifact capturing key graph-health metrics for a given
pipeline run. The artifact is scoped by ``run_id`` (and optionally
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
   appear inside each ``ResolvedEntityCluster``. Healthy clusters have exactly
   one distinct type.
4. **Alignment coverage** — aligned vs unaligned ``ResolvedEntityCluster``
   counts for the given ``alignment_version``, plus a per-canonical breakdown
   of aligned clusters and bridged mentions.
5. **End-to-end chain** — for each ``CanonicalEntity``, counts of reachable
   mentions and claims via the full hybrid path
   (``ALIGNED_WITH`` → ``MEMBER_OF`` → ``HAS_PARTICIPANT``).

All queries use ``routing_=neo4j.RoutingControl.READ`` and accept explicit
``run_id`` / ``alignment_version`` parameters; they never mutate graph state.

Standalone surface
------------------
``run_graph_health_diagnostics(...)`` remains an intentional standalone API for
manual diagnostics, notebooks, and query-pipeline scripts that want explicit
``Config`` plus scoping arguments without going through demo orchestration.
Orchestrated and pipeline-owned flows should prefer
``run_graph_health_diagnostics_request_context(...)`` so run scope and runtime
ownership stay with ``RequestContext`` at the call boundary.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import timezone, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from power_atlas.context import RequestContext
from power_atlas.contracts import EntityTypeNormalizationPolicy
from power_atlas.contracts import build_entity_type_cypher_case as _build_entity_type_cypher_case
from power_atlas.graph_health_queries import CANONICAL_CHAIN_HEALTH_LIMIT as _CANONICAL_CHAIN_HEALTH_LIMIT
from power_atlas.graph_health_queries import PER_CANONICAL_ALIGNMENT_LIMIT as _PER_CANONICAL_ALIGNMENT_LIMIT
from power_atlas.graph_health_queries import build_cluster_type_fragmentation_query
from power_atlas.graph_health_queries import build_graph_health_query_specs
from power_atlas.graph_health_queries import fetch_graph_health_query_rows
from power_atlas.settings import Neo4jSettings

_logger = logging.getLogger(__name__)

GraphHealthQueryRowsFetcher = Callable[..., dict[str, list[dict[str, object]]]]


def _neo4j_settings_from_config(config) -> Neo4jSettings:
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Graph health diagnostics require config.settings.neo4j from "
        "RequestContext/AppContext-backed config"
    )


def _neo4j_settings_from_request_context(request_context: RequestContext) -> Neo4jSettings:
    request_settings_neo4j = getattr(request_context.settings, "neo4j", None)
    if isinstance(request_settings_neo4j, Neo4jSettings):
        return request_settings_neo4j
    return _neo4j_settings_from_config(request_context.config)


def _get_cluster_type_fragmentation_query(
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str:
    """Return the current cluster type-fragmentation query.

    This stays live with entity-resolution normalization policy changes rather
    than freezing the derived Cypher text at module import time.
    """
    return build_cluster_type_fragmentation_query(
        build_entity_type_cypher_case=lambda var: _build_entity_type_cypher_case(
            var,
            entity_type_policy=entity_type_policy,
        ),
    )


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    """Convert Neo4j ``Record`` objects to plain dicts."""
    return [dict(r) for r in records]


def _compute_participation_summary(
    role_dist: list[dict[str, Any]],
    edge_coverage: list[dict[str, Any]],
) -> dict[str, Any]:
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


@dataclasses.dataclass
class GraphHealthArtifact:
    """Structured container for a single graph-health diagnostics run.

    All fields are JSON-serialisable. ``alignment_*`` fields are usually
    populated (often with empty lists and an ``alignment_coverage_pct`` of
    0.0); ``None`` values mainly indicate that no clustering/alignment data
    exists for the given scope. ``alignment_version`` is ``None`` when no
    alignment version was requested.
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
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


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
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def _run_graph_health_diagnostics_impl(
    *,
    dry_run: bool,
    output_dir: Path,
    neo4j_settings: Neo4jSettings | None,
    run_id: str | None = None,
    alignment_version: str | None = None,
    suppress_alignment_version_warning: bool = False,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
    query_rows_fetcher: GraphHealthQueryRowsFetcher = fetch_graph_health_query_rows,
) -> dict[str, Any]:
    effective_output_dir = Path(output_dir)
    runs_root = (effective_output_dir / "runs").resolve()

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

    collected_warnings: list[str] = []

    if run_id is None:
        collected_warnings.append(
            "run_graph_health_diagnostics: run_id is None — diagnostics will aggregate "
            "across ALL pipeline runs in the database, not just the current run. "
            "Pass run_id to scope queries to the intended pipeline execution."
        )

    if alignment_version is None and not suppress_alignment_version_warning:
        collected_warnings.append(
            "run_graph_health_diagnostics: alignment_version is None — alignment "
            "metrics will aggregate across ALL alignment versions in the database, "
            "not just the current cohort. "
            "Pass alignment_version (e.g. from the hybrid entity resolution stage output) "
            "to scope queries to the intended ALIGNED_WITH edge version."
        )

    if dry_run:
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
        return {
            "status": "dry_run",
            "run_id": run_id,
            "alignment_version": alignment_version,
            "artifact_path": str(artifact_path),
            "artifact": None,
            "warnings": ["graph health diagnostics skipped in dry_run mode"] + collected_warnings,
        }

    if neo4j_settings is None:
        raise ValueError("Graph health diagnostics require Neo4j settings for live execution.")

    query_rows = query_rows_fetcher(
        neo4j_settings,
        neo4j_settings.database,
        run_id=run_id,
        alignment_version=alignment_version,
        query_specs=build_graph_health_query_specs(
            cluster_type_fragmentation_query=_get_cluster_type_fragmentation_query(
                entity_type_policy,
            ),
            per_canonical_alignment_limit=_PER_CANONICAL_ALIGNMENT_LIMIT,
            canonical_chain_health_limit=_CANONICAL_CHAIN_HEALTH_LIMIT,
        ),
        logger=_logger,
    )

    per_canonical = query_rows["per_canonical"]
    chain_health = query_rows["chain_health"]
    artifact = build_graph_health_artifact(
        run_id=run_id,
        alignment_version=alignment_version,
        participation_role_distribution=query_rows["role_dist"],
        claim_edge_coverage_distribution=query_rows["edge_coverage"],
        match_method_distribution=query_rows["match_method_dist"],
        mention_clustering=query_rows["mention_clustering"],
        cluster_size_distribution=query_rows["cluster_size_dist"],
        cluster_type_fragmentation=query_rows["cluster_type_frag"],
        alignment_coverage=query_rows["alignment_coverage"],
        per_canonical_alignment=per_canonical,
        canonical_chain_health=chain_health,
    )

    artifact_path.write_text(artifact.to_json(), encoding="utf-8")
    _logger.info("graph_health: artifact written to %s", artifact_path)

    if len(per_canonical) == _PER_CANONICAL_ALIGNMENT_LIMIT:
        collected_warnings.append(
            f"run_graph_health_diagnostics: per_canonical_alignment result is at the "
            f"query row limit ({_PER_CANONICAL_ALIGNMENT_LIMIT} rows) — the detail table "
            f"may be truncated and not reflect all canonical entities in the current scope."
        )

    if len(chain_health) == _CANONICAL_CHAIN_HEALTH_LIMIT:
        collected_warnings.append(
            f"run_graph_health_diagnostics: canonical_chain_health result is at the "
            f"query row limit ({_CANONICAL_CHAIN_HEALTH_LIMIT} rows) — the detail table "
            f"may be truncated and not reflect all canonical entities in the current scope."
        )

    return {
        "status": "live",
        "run_id": run_id,
        "alignment_version": alignment_version,
        "artifact_path": str(artifact_path),
        "artifact": artifact.to_dict(),
        "warnings": collected_warnings,
    }


def run_graph_health_diagnostics(
    config: Any,
    *,
    run_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    suppress_alignment_version_warning: bool = False,
    query_rows_fetcher: GraphHealthQueryRowsFetcher = fetch_graph_health_query_rows,
) -> dict[str, Any]:
    resolved_output_dir = Path(output_dir if output_dir is not None else config.output_dir)
    dry_run = bool(getattr(config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else _neo4j_settings_from_config(config)
    return _run_graph_health_diagnostics_impl(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=run_id,
        alignment_version=alignment_version,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        query_rows_fetcher=query_rows_fetcher,
    )


def run_graph_health_diagnostics_request_context(
    request_context: RequestContext,
    *,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    suppress_alignment_version_warning: bool = False,
    query_rows_fetcher: GraphHealthQueryRowsFetcher = fetch_graph_health_query_rows,
) -> dict[str, Any]:
    resolved_output_dir = Path(
        output_dir if output_dir is not None else request_context.config.output_dir
    )
    dry_run = bool(getattr(request_context.config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else _neo4j_settings_from_request_context(
        request_context
    )
    return _run_graph_health_diagnostics_impl(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=request_context.run_id,
        alignment_version=alignment_version,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        entity_type_policy=request_context.policies.entity_type_normalization,
        query_rows_fetcher=query_rows_fetcher,
    )


__all__ = [
    "GraphHealthArtifact",
    "GraphHealthQueryRowsFetcher",
    "build_graph_health_artifact",
    "run_graph_health_diagnostics",
    "run_graph_health_diagnostics_request_context",
]