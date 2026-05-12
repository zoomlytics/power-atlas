from __future__ import annotations

from power_atlas.backend_graph_response_adapters import (
    build_graph_health_summary_response_payload,
    build_graph_summary_response_payload,
    build_run_scoped_graph_counts_response_payload,
)
from power_atlas.graph_health_summary import (
    GraphHealthAlignmentSummary,
    GraphHealthMentionSummary,
    GraphHealthParticipationSummary,
    GraphHealthSummaryResult,
)
from power_atlas.graph_summary import GraphSummaryCounts, GraphSummaryResult
from power_atlas.run_scoped_graph_counts import (
    RunScopedGraphCounts,
    RunScopedGraphCountsResult,
)


def test_build_graph_summary_response_payload_includes_nested_counts() -> None:
    payload = build_graph_summary_response_payload(
        GraphSummaryResult(
            http_status_code=200,
            status="available",
            detail="Graph summary retrieved successfully",
            neo4j_uri="neo4j://graph.example:7687",
            database="atlas",
            counts=GraphSummaryCounts(
                document_count=4,
                chunk_count=12,
                claim_count=9,
                mention_count=27,
                cluster_count=8,
                canonical_entity_count=5,
            ),
        )
    )

    assert payload == {
        "status": "available",
        "detail": "Graph summary retrieved successfully",
        "neo4j_uri": "neo4j://graph.example:7687",
        "database": "atlas",
        "counts": {
            "document_count": 4,
            "chunk_count": 12,
            "claim_count": 9,
            "mention_count": 27,
            "cluster_count": 8,
            "canonical_entity_count": 5,
        },
    }


def test_build_run_scoped_graph_counts_response_payload_handles_missing_counts() -> None:
    payload = build_run_scoped_graph_counts_response_payload(
        RunScopedGraphCountsResult(
            http_status_code=503,
            status="not_configured",
            detail="Graph integration is not configured",
            run_id="unstructured_ingest-test-run",
            neo4j_uri="neo4j://localhost:7687",
            database="neo4j",
            counts=None,
        )
    )

    assert payload == {
        "status": "not_configured",
        "detail": "Graph integration is not configured",
        "run_id": "unstructured_ingest-test-run",
        "neo4j_uri": "neo4j://localhost:7687",
        "database": "neo4j",
        "counts": None,
    }


def test_build_graph_health_summary_response_payload_includes_nested_sections() -> None:
    payload = build_graph_health_summary_response_payload(
        GraphHealthSummaryResult(
            http_status_code=200,
            status="available",
            detail="Graph health summary retrieved successfully",
            run_id="unstructured_ingest-20260511T000000Z-test",
            alignment_version="v1",
            neo4j_uri="neo4j://graph.example:7687",
            database="atlas",
            participation_summary=GraphHealthParticipationSummary(
                total_edges=14,
                edges_by_role={"subject": 9, "object": 5},
                total_claims=6,
                claims_with_zero_edges=1,
                claim_coverage_pct=83.33,
            ),
            mention_summary=GraphHealthMentionSummary(
                total_mentions=10,
                clustered_mentions=8,
                unclustered_mentions=2,
                unresolved_rate_pct=20.0,
            ),
            alignment_summary=GraphHealthAlignmentSummary(
                total_clusters=5,
                aligned_clusters=4,
                unaligned_clusters=1,
                alignment_coverage_pct=80.0,
            ),
        )
    )

    assert payload == {
        "status": "available",
        "detail": "Graph health summary retrieved successfully",
        "run_id": "unstructured_ingest-20260511T000000Z-test",
        "alignment_version": "v1",
        "neo4j_uri": "neo4j://graph.example:7687",
        "database": "atlas",
        "participation_summary": {
            "total_edges": 14,
            "edges_by_role": {"subject": 9, "object": 5},
            "total_claims": 6,
            "claims_with_zero_edges": 1,
            "claim_coverage_pct": 83.33,
        },
        "mention_summary": {
            "total_mentions": 10,
            "clustered_mentions": 8,
            "unclustered_mentions": 2,
            "unresolved_rate_pct": 20.0,
        },
        "alignment_summary": {
            "total_clusters": 5,
            "aligned_clusters": 4,
            "unaligned_clusters": 1,
            "alignment_coverage_pct": 80.0,
        },
    }