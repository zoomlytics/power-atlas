from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import build_settings, create_neo4j_driver
from power_atlas.settings import AppSettings, Neo4jSettings

DEFAULT_GRAPH_STATUS_QUERY = "RETURN 1 AS ok"
DEFAULT_UNCONFIGURED_DETAIL = "Neo4j password is not configured"


@dataclass(frozen=True, slots=True)
class GraphStatusResult:
    http_status_code: int
    status: str
    detail: str
    neo4j_uri: str
    database: str


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    try:
        return dict(record).get(key)
    except (TypeError, ValueError):
        return getattr(record, key, None)


def _probe_returned_ok(records: Sequence[Any]) -> bool:
    if not records:
        return False
    return _record_value(records[0], "ok") == 1


def resolve_graph_status(
    settings: AppSettings | None = None,
    *,
    settings_builder: Callable[[], AppSettings] = build_settings,
    driver_factory: Callable[[AppSettings | Neo4jSettings], Any] = create_neo4j_driver,
) -> GraphStatusResult:
    resolved_settings = settings_builder() if settings is None else settings
    neo4j_settings = resolved_settings.neo4j

    if neo4j_settings.password == Neo4jSettings.password:
        return GraphStatusResult(
            http_status_code=503,
            status="not_configured",
            detail=DEFAULT_UNCONFIGURED_DETAIL,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    try:
        with driver_factory(resolved_settings) as driver:
            records, _, _ = driver.execute_query(
                DEFAULT_GRAPH_STATUS_QUERY,
                database_=neo4j_settings.database,
            )
    except Exception as exc:
        return GraphStatusResult(
            http_status_code=503,
            status="unavailable",
            detail=f"Neo4j connectivity check failed: {exc}",
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    if not _probe_returned_ok(records):
        return GraphStatusResult(
            http_status_code=503,
            status="unavailable",
            detail="Neo4j connectivity check returned an unexpected result",
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    return GraphStatusResult(
        http_status_code=200,
        status="available",
        detail="Neo4j graph is reachable",
        neo4j_uri=neo4j_settings.uri,
        database=neo4j_settings.database,
    )


__all__ = [
    "DEFAULT_GRAPH_STATUS_QUERY",
    "DEFAULT_UNCONFIGURED_DETAIL",
    "GraphStatusResult",
    "resolve_graph_status",
]