from __future__ import annotations

from power_atlas.backend_graph import (
    GraphHealthSummaryResult,
    GraphStatusResult,
    GraphSummaryResult,
    RunScopedGraphCountsResult,
)


def build_graph_status_response_payload(probe: GraphStatusResult) -> dict[str, object | None]:
    return {
        "status": probe.status,
        "detail": probe.detail,
        "neo4j_uri": probe.neo4j_uri,
        "database": probe.database,
    }


def build_graph_summary_response_payload(probe: GraphSummaryResult) -> dict[str, object | None]:
    counts = None
    if probe.counts is not None:
        counts = {
            "document_count": probe.counts.document_count,
            "chunk_count": probe.counts.chunk_count,
            "claim_count": probe.counts.claim_count,
            "mention_count": probe.counts.mention_count,
            "cluster_count": probe.counts.cluster_count,
            "canonical_entity_count": probe.counts.canonical_entity_count,
        }
    return {
        "status": probe.status,
        "detail": probe.detail,
        "neo4j_uri": probe.neo4j_uri,
        "database": probe.database,
        "counts": counts,
    }


def build_run_scoped_graph_counts_response_payload(
    probe: RunScopedGraphCountsResult,
) -> dict[str, object | None]:
    counts = None
    if probe.counts is not None:
        counts = {
            "chunk_count": probe.counts.chunk_count,
            "claim_count": probe.counts.claim_count,
            "mention_count": probe.counts.mention_count,
            "cluster_count": probe.counts.cluster_count,
        }
    return {
        "status": probe.status,
        "detail": probe.detail,
        "run_id": probe.run_id,
        "neo4j_uri": probe.neo4j_uri,
        "database": probe.database,
        "counts": counts,
    }


def build_graph_health_summary_response_payload(
    probe: GraphHealthSummaryResult,
) -> dict[str, object | None]:
    participation_summary = None
    mention_summary = None
    alignment_summary = None
    if probe.participation_summary is not None:
        participation_summary = {
            "total_edges": probe.participation_summary.total_edges,
            "edges_by_role": probe.participation_summary.edges_by_role,
            "total_claims": probe.participation_summary.total_claims,
            "claims_with_zero_edges": probe.participation_summary.claims_with_zero_edges,
            "claim_coverage_pct": probe.participation_summary.claim_coverage_pct,
        }
    if probe.mention_summary is not None:
        mention_summary = {
            "total_mentions": probe.mention_summary.total_mentions,
            "clustered_mentions": probe.mention_summary.clustered_mentions,
            "unclustered_mentions": probe.mention_summary.unclustered_mentions,
            "unresolved_rate_pct": probe.mention_summary.unresolved_rate_pct,
        }
    if probe.alignment_summary is not None:
        alignment_summary = {
            "total_clusters": probe.alignment_summary.total_clusters,
            "aligned_clusters": probe.alignment_summary.aligned_clusters,
            "unaligned_clusters": probe.alignment_summary.unaligned_clusters,
            "alignment_coverage_pct": probe.alignment_summary.alignment_coverage_pct,
        }
    return {
        "status": probe.status,
        "detail": probe.detail,
        "run_id": probe.run_id,
        "alignment_version": probe.alignment_version,
        "neo4j_uri": probe.neo4j_uri,
        "database": probe.database,
        "participation_summary": participation_summary,
        "mention_summary": mention_summary,
        "alignment_summary": alignment_summary,
    }


__all__ = [
    "build_graph_health_summary_response_payload",
    "build_graph_status_response_payload",
    "build_graph_summary_response_payload",
    "build_run_scoped_graph_counts_response_payload",
]