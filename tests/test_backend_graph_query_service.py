from __future__ import annotations

from power_atlas.backend_graph_query_service import build_backend_graph_query_service
from power_atlas.bootstrap import build_app_context
from power_atlas.graph_status import DEFAULT_GRAPH_STATUS_QUERY, resolve_graph_status


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