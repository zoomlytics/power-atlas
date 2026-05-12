from __future__ import annotations

from power_atlas.backend_graph_query_service import build_backend_graph_query_service
from power_atlas.bootstrap import build_app_context
from power_atlas.graph_health_summary import GraphHealthSummaryRequest, resolve_graph_health_summary
from power_atlas.graph_summary import DEFAULT_GRAPH_SUMMARY_QUERY, resolve_graph_summary
from power_atlas.graph_status import DEFAULT_GRAPH_STATUS_QUERY, resolve_graph_status
from power_atlas.run_scoped_graph_counts import (
    DEFAULT_RUN_SCOPED_GRAPH_COUNTS_QUERY,
    RunScopedGraphCountsRequest,
    resolve_run_scoped_graph_counts,
)


class _FakeDriver:
    def __init__(self, records):
        self.records = records
        self.seen_query = None
        self.seen_database = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_query(self, query, *, database_=None, **kwargs):
        self.seen_query = query
        self.seen_database = database_
        return self.records, None, None


def test_backend_graph_query_service_graph_status_uses_fake_driver_seam() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    fake_driver = _FakeDriver(records=[{"ok": 1}])

    graph_queries = build_backend_graph_query_service(
        app_context,
        graph_status_resolver=lambda runtime_app_context: resolve_graph_status(
            settings=runtime_app_context.settings,
            driver_factory=lambda settings: fake_driver,
        ),
    )

    result = graph_queries.graph_status()

    assert result.http_status_code == 200
    assert result.status == "available"
    assert result.neo4j_uri == "neo4j://graph.example:7687"
    assert result.database == "atlas"
    assert fake_driver.seen_query == DEFAULT_GRAPH_STATUS_QUERY
    assert fake_driver.seen_database == "atlas"


def test_backend_graph_query_service_graph_summary_uses_fake_driver_seam() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    fake_driver = _FakeDriver(
        records=[
            {
                "document_count": 3,
                "chunk_count": 11,
                "claim_count": 7,
                "mention_count": 21,
                "cluster_count": 6,
                "canonical_entity_count": 4,
            }
        ]
    )

    graph_queries = build_backend_graph_query_service(
        app_context,
        graph_summary_resolver=lambda runtime_app_context: resolve_graph_summary(
            settings=runtime_app_context.settings,
            driver_factory=lambda settings: fake_driver,
        ),
    )

    result = graph_queries.graph_summary()

    assert result.http_status_code == 200
    assert result.status == "available"
    assert result.counts is not None
    assert result.counts.document_count == 3
    assert result.counts.chunk_count == 11
    assert result.counts.claim_count == 7
    assert result.counts.mention_count == 21
    assert result.counts.cluster_count == 6
    assert result.counts.canonical_entity_count == 4
    assert fake_driver.seen_query == DEFAULT_GRAPH_SUMMARY_QUERY
    assert fake_driver.seen_database == "atlas"


def test_backend_graph_query_service_run_scoped_counts_uses_fake_driver_seam() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    fake_driver = _FakeDriver(
        records=[
            {
                "chunk_count": 11,
                "claim_count": 7,
                "mention_count": 21,
                "cluster_count": 6,
            }
        ]
    )

    graph_queries = build_backend_graph_query_service(
        app_context,
        run_scoped_graph_counts_resolver=lambda runtime_app_context, request: resolve_run_scoped_graph_counts(
            runtime_app_context,
            request,
            driver_factory=lambda settings: fake_driver,
        ),
    )

    result = graph_queries.run_scoped_graph_counts(
        RunScopedGraphCountsRequest(run_id="unstructured_ingest-20260511T000000Z-test")
    )

    assert result.http_status_code == 200
    assert result.status == "available"
    assert result.counts is not None
    assert result.counts.chunk_count == 11
    assert result.counts.claim_count == 7
    assert result.counts.mention_count == 21
    assert result.counts.cluster_count == 6
    assert fake_driver.seen_query == DEFAULT_RUN_SCOPED_GRAPH_COUNTS_QUERY
    assert fake_driver.seen_database == "atlas"


def test_backend_graph_query_service_graph_health_summary_uses_fake_query_rows() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )

    def _fake_query_rows_fetcher(*args, **kwargs):
        return {
            "role_dist": [{"role": "subject", "total": 9}, {"role": "object", "total": 5}],
            "edge_coverage": [
                {"participant_edges": 0, "claim_count": 1},
                {"participant_edges": 2, "claim_count": 5},
            ],
            "mention_clustering": [
                {"is_clustered": True, "mention_count": 8},
                {"is_clustered": False, "mention_count": 2},
            ],
            "alignment_coverage": [
                {"is_aligned": True, "cluster_count": 4},
                {"is_aligned": False, "cluster_count": 1},
            ],
        }

    graph_queries = build_backend_graph_query_service(
        app_context,
        graph_health_summary_resolver=lambda runtime_app_context, request: resolve_graph_health_summary(
            runtime_app_context,
            request,
            query_rows_fetcher=_fake_query_rows_fetcher,
        ),
    )

    result = graph_queries.graph_health_summary(
        GraphHealthSummaryRequest(
            run_id="unstructured_ingest-20260511T000000Z-test",
            alignment_version="v1",
        )
    )

    assert result.http_status_code == 200
    assert result.status == "available"
    assert result.participation_summary is not None
    assert result.mention_summary is not None
    assert result.alignment_summary is not None
    assert result.participation_summary.total_edges == 14
    assert result.participation_summary.claims_with_zero_edges == 1
    assert result.mention_summary.total_mentions == 10
    assert result.alignment_summary.alignment_coverage_pct == 80.0