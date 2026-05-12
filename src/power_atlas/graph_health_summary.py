from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from power_atlas.context import AppContext
from power_atlas.graph_health_queries import (
    build_graph_health_summary_query_specs,
    fetch_graph_health_query_rows,
)
from power_atlas.graph_status import DEFAULT_UNCONFIGURED_DETAIL
from power_atlas.settings import Neo4jSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GraphHealthSummaryRequest:
    run_id: str
    alignment_version: str | None = None


@dataclass(frozen=True, slots=True)
class GraphHealthParticipationSummary:
    total_edges: int
    edges_by_role: dict[str, int]
    total_claims: int
    claims_with_zero_edges: int
    claim_coverage_pct: float | None


@dataclass(frozen=True, slots=True)
class GraphHealthMentionSummary:
    total_mentions: int
    clustered_mentions: int
    unclustered_mentions: int
    unresolved_rate_pct: float | None


@dataclass(frozen=True, slots=True)
class GraphHealthAlignmentSummary:
    total_clusters: int
    aligned_clusters: int
    unaligned_clusters: int
    alignment_coverage_pct: float | None


@dataclass(frozen=True, slots=True)
class GraphHealthSummaryResult:
    http_status_code: int
    status: str
    detail: str
    run_id: str
    alignment_version: str | None
    neo4j_uri: str
    database: str
    participation_summary: GraphHealthParticipationSummary | None = None
    mention_summary: GraphHealthMentionSummary | None = None
    alignment_summary: GraphHealthAlignmentSummary | None = None


def compute_participation_summary(
    role_dist: list[dict[str, object]],
    edge_coverage: list[dict[str, object]],
) -> GraphHealthParticipationSummary:
    total_edges = sum(int(row["total"]) for row in role_dist)
    edges_by_role = {str(row["role"]): int(row["total"]) for row in role_dist}
    total_claims = sum(int(row["claim_count"]) for row in edge_coverage)
    claims_zero = next(
        (int(row["claim_count"]) for row in edge_coverage if int(row["participant_edges"]) == 0),
        0,
    )
    claims_nonzero = total_claims - claims_zero
    coverage_pct = round(claims_nonzero / total_claims * 100, 2) if total_claims > 0 else None
    return GraphHealthParticipationSummary(
        total_edges=total_edges,
        edges_by_role=edges_by_role,
        total_claims=total_claims,
        claims_with_zero_edges=claims_zero,
        claim_coverage_pct=coverage_pct,
    )


def compute_mention_summary(
    clustering_rows: list[dict[str, object]],
) -> GraphHealthMentionSummary:
    by_status = {bool(row["is_clustered"]): int(row["mention_count"]) for row in clustering_rows}
    clustered = by_status.get(True, 0)
    unclustered = by_status.get(False, 0)
    total = clustered + unclustered
    unresolved_rate_pct = round(unclustered / total * 100, 2) if total > 0 else None
    return GraphHealthMentionSummary(
        total_mentions=total,
        clustered_mentions=clustered,
        unclustered_mentions=unclustered,
        unresolved_rate_pct=unresolved_rate_pct,
    )


def compute_alignment_summary(
    alignment_rows: list[dict[str, object]],
) -> GraphHealthAlignmentSummary:
    by_status = {bool(row["is_aligned"]): int(row["cluster_count"]) for row in alignment_rows}
    aligned = by_status.get(True, 0)
    unaligned = by_status.get(False, 0)
    total = aligned + unaligned
    alignment_coverage_pct = round(aligned / total * 100, 2) if total > 0 else None
    return GraphHealthAlignmentSummary(
        total_clusters=total,
        aligned_clusters=aligned,
        unaligned_clusters=unaligned,
        alignment_coverage_pct=alignment_coverage_pct,
    )


def resolve_graph_health_summary(
    app_context: AppContext,
    request: GraphHealthSummaryRequest,
    *,
    query_rows_fetcher: Callable[..., dict[str, list[dict[str, object]]]] = fetch_graph_health_query_rows,
) -> GraphHealthSummaryResult:
    neo4j_settings = app_context.settings.neo4j

    if neo4j_settings.password == Neo4jSettings.password:
        return GraphHealthSummaryResult(
            http_status_code=503,
            status="not_configured",
            detail=DEFAULT_UNCONFIGURED_DETAIL,
            run_id=request.run_id,
            alignment_version=request.alignment_version,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    try:
        rows = query_rows_fetcher(
            neo4j_settings,
            neo4j_settings.database,
            run_id=request.run_id,
            alignment_version=request.alignment_version,
            query_specs=build_graph_health_summary_query_specs(),
            logger=logger,
        )
    except Exception as exc:
        return GraphHealthSummaryResult(
            http_status_code=503,
            status="unavailable",
            detail=f"Graph health summary query failed: {exc}",
            run_id=request.run_id,
            alignment_version=request.alignment_version,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    participation_summary = compute_participation_summary(
        rows["role_dist"],
        rows["edge_coverage"],
    )
    mention_summary = compute_mention_summary(rows["mention_clustering"])
    alignment_summary = compute_alignment_summary(rows["alignment_coverage"])

    if (
        participation_summary.total_claims == 0
        and mention_summary.total_mentions == 0
        and alignment_summary.total_clusters == 0
    ):
        return GraphHealthSummaryResult(
            http_status_code=404,
            status="not_found",
            detail=f"No graph-health data was found for run_id={request.run_id!r}",
            run_id=request.run_id,
            alignment_version=request.alignment_version,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    detail = "Graph health summary retrieved successfully"
    if request.alignment_version is None:
        detail = (
            "Graph health summary retrieved successfully; alignment coverage aggregates across all alignment versions"
        )

    return GraphHealthSummaryResult(
        http_status_code=200,
        status="available",
        detail=detail,
        run_id=request.run_id,
        alignment_version=request.alignment_version,
        neo4j_uri=neo4j_settings.uri,
        database=neo4j_settings.database,
        participation_summary=participation_summary,
        mention_summary=mention_summary,
        alignment_summary=alignment_summary,
    )


__all__ = [
    "GraphHealthAlignmentSummary",
    "GraphHealthMentionSummary",
    "GraphHealthParticipationSummary",
    "GraphHealthSummaryRequest",
    "GraphHealthSummaryResult",
    "compute_alignment_summary",
    "compute_mention_summary",
    "compute_participation_summary",
    "resolve_graph_health_summary",
]