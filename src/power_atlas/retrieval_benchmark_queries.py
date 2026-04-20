from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

RetrievalBenchmarkQuerySpec = tuple[str, str, str, Mapping[str, Any] | None]


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def fetch_retrieval_benchmark_query_rows(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    *,
    base_params: Mapping[str, Any],
    query_specs: Sequence[RetrievalBenchmarkQuerySpec],
    logger: logging.Logger,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    with create_neo4j_driver(neo4j_settings) as driver:
        for result_key, log_label, cypher, extra_params in query_specs:
            logger.info("retrieval_benchmark: running %s query", log_label)
            records, _, _ = driver.execute_query(
                cypher,
                parameters_={**base_params, **(extra_params or {})},
                database_=neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            rows_by_key[result_key] = _records_to_dicts(records)
    return rows_by_key


__all__ = ["RetrievalBenchmarkQuerySpec", "fetch_retrieval_benchmark_query_rows"]