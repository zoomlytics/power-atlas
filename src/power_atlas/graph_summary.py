from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import build_settings, create_neo4j_driver
from power_atlas.graph_status import DEFAULT_UNCONFIGURED_DETAIL
from power_atlas.settings import AppSettings, Neo4jSettings

DEFAULT_GRAPH_SUMMARY_QUERY = """\
OPTIONAL MATCH (document:Document)
WITH count(document) AS document_count
OPTIONAL MATCH (chunk:Chunk)
WITH document_count, count(chunk) AS chunk_count
OPTIONAL MATCH (claim:ExtractedClaim)
WITH document_count, chunk_count, count(claim) AS claim_count
OPTIONAL MATCH (mention:EntityMention)
WITH document_count, chunk_count, claim_count, count(mention) AS mention_count
OPTIONAL MATCH (cluster:ResolvedEntityCluster)
WITH document_count, chunk_count, claim_count, mention_count, count(cluster) AS cluster_count
OPTIONAL MATCH (canonical:CanonicalEntity)
RETURN document_count,
       chunk_count,
       claim_count,
       mention_count,
       cluster_count,
       count(canonical) AS canonical_entity_count
"""


@dataclass(frozen=True, slots=True)
class GraphSummaryCounts:
    document_count: int
    chunk_count: int
    claim_count: int
    mention_count: int
    cluster_count: int
    canonical_entity_count: int


@dataclass(frozen=True, slots=True)
class GraphSummaryResult:
    http_status_code: int
    status: str
    detail: str
    neo4j_uri: str
    database: str
    counts: GraphSummaryCounts | None = None


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
    raise ValueError(f"Graph summary is missing integer field {key!r}")


def _build_counts(records: Sequence[Any]) -> GraphSummaryCounts:
    if not records:
        raise ValueError("Graph summary query returned no records")
    record = records[0]
    return GraphSummaryCounts(
        document_count=_coerce_count(record, "document_count"),
        chunk_count=_coerce_count(record, "chunk_count"),
        claim_count=_coerce_count(record, "claim_count"),
        mention_count=_coerce_count(record, "mention_count"),
        cluster_count=_coerce_count(record, "cluster_count"),
        canonical_entity_count=_coerce_count(record, "canonical_entity_count"),
    )


def resolve_graph_summary(
    settings: AppSettings | None = None,
    *,
    settings_builder: Callable[[], AppSettings] = build_settings,
    driver_factory: Callable[[AppSettings | Neo4jSettings], Any] = create_neo4j_driver,
) -> GraphSummaryResult:
    resolved_settings = settings_builder() if settings is None else settings
    neo4j_settings = resolved_settings.neo4j

    if neo4j_settings.password == Neo4jSettings.password:
        return GraphSummaryResult(
            http_status_code=503,
            status="not_configured",
            detail=DEFAULT_UNCONFIGURED_DETAIL,
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    try:
        with driver_factory(resolved_settings) as driver:
            records, _, _ = driver.execute_query(
                DEFAULT_GRAPH_SUMMARY_QUERY,
                database_=neo4j_settings.database,
            )
            counts = _build_counts(records)
    except Exception as exc:
        return GraphSummaryResult(
            http_status_code=503,
            status="unavailable",
            detail=f"Graph summary query failed: {exc}",
            neo4j_uri=neo4j_settings.uri,
            database=neo4j_settings.database,
        )

    return GraphSummaryResult(
        http_status_code=200,
        status="available",
        detail="Graph summary retrieved successfully",
        neo4j_uri=neo4j_settings.uri,
        database=neo4j_settings.database,
        counts=counts,
    )


__all__ = [
    "DEFAULT_GRAPH_SUMMARY_QUERY",
    "GraphSummaryCounts",
    "GraphSummaryResult",
    "resolve_graph_summary",
]