from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.context import AppContext
from power_atlas.graph_status import DEFAULT_UNCONFIGURED_DETAIL
from power_atlas.settings import Neo4jSettings

DEFAULT_RUN_SCOPED_GRAPH_COUNTS_QUERY = """\
OPTIONAL MATCH (chunk:Chunk {run_id: $run_id})
WITH count(chunk) AS chunk_count
OPTIONAL MATCH (claim:ExtractedClaim {run_id: $run_id})
WITH chunk_count, count(claim) AS claim_count
OPTIONAL MATCH (mention:EntityMention {run_id: $run_id})
WITH chunk_count, claim_count, count(mention) AS mention_count
OPTIONAL MATCH (cluster:ResolvedEntityCluster {run_id: $run_id})
RETURN chunk_count,
       claim_count,
       mention_count,
       count(cluster) AS cluster_count
"""


@dataclass(frozen=True, slots=True)
class RunScopedGraphCountsRequest:
    run_id: str


@dataclass(frozen=True, slots=True)
class RunScopedGraphCounts:
    chunk_count: int
    claim_count: int
    mention_count: int
    cluster_count: int


@dataclass(frozen=True, slots=True)
class RunScopedGraphCountsResult:
    http_status_code: int
    status: str
    detail: str
    run_id: str
    neo4j_uri: str
    database: str
    counts: RunScopedGraphCounts | None = None


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    try:
        return dict(record).get(key)
    except (TypeError, ValueError):
        return getattr(record, key, None)


def _coerce_count(record: Any, key: str) -> int:
    value = _record_value(record, key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    raise ValueError(f"Run-scoped graph counts are missing integer field {key!r}")


def _build_counts(record: Any) -> RunScopedGraphCounts:
    return RunScopedGraphCounts(
        chunk_count=_coerce_count(record, "chunk_count"),
        claim_count=_coerce_count(record, "claim_count"),
        mention_count=_coerce_count(record, "mention_count"),
        cluster_count=_coerce_count(record, "cluster_count"),
    )


def resolve_run_scoped_graph_counts(
    app_context: AppContext,
    request: RunScopedGraphCountsRequest,
) -> RunScopedGraphCountsResult:
    neo4j_settings = app_context.settings.neo4j

    if neo4j_settings.password == Neo4jSettings.password:
        return RunScopedGraphCountsResult(
            http_status_code=503,
            status="not_configured",
            detail=DEFAULT_UNCONFIGURED_DETAIL,
            run_id=request.run_id,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    try:
        with create_neo4j_driver(app_context.settings) as driver:
            records, _, _ = driver.execute_query(
                DEFAULT_RUN_SCOPED_GRAPH_COUNTS_QUERY,
                parameters_={"run_id": request.run_id},
                database_=neo4j_settings.database,
            )
    except Exception as exc:
        return RunScopedGraphCountsResult(
            http_status_code=503,
            status="unavailable",
            detail=f"Run-scoped graph counts query failed: {exc}",
            run_id=request.run_id,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    if not records:
        return RunScopedGraphCountsResult(
            http_status_code=404,
            status="not_found",
            detail=f"No graph rows were returned for run_id={request.run_id!r}",
            run_id=request.run_id,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    counts = _build_counts(records[0])
    if (
        counts.chunk_count == 0
        and counts.claim_count == 0
        and counts.mention_count == 0
        and counts.cluster_count == 0
    ):
        return RunScopedGraphCountsResult(
            http_status_code=404,
            status="not_found",
            detail=f"No run-scoped graph data was found for run_id={request.run_id!r}",
            run_id=request.run_id,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    return RunScopedGraphCountsResult(
        http_status_code=200,
        status="available",
        detail="Run-scoped graph counts retrieved successfully",
        run_id=request.run_id,
        neo4j_uri=neo4j_settings.uri,
        database=neo4j_settings.database,
        counts=counts,
    )


__all__ = [
    "DEFAULT_RUN_SCOPED_GRAPH_COUNTS_QUERY",
    "RunScopedGraphCounts",
    "RunScopedGraphCountsRequest",
    "RunScopedGraphCountsResult",
    "resolve_run_scoped_graph_counts",
]