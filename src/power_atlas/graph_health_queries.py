from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

GraphHealthQuerySpec = tuple[str, str, str]


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def fetch_graph_health_query_rows(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    *,
    run_id: str | None,
    alignment_version: str | None,
    query_specs: Sequence[GraphHealthQuerySpec],
    logger: logging.Logger,
) -> dict[str, list[dict[str, Any]]]:
    params: dict[str, Any] = {
        "run_id": run_id,
        "alignment_version": alignment_version,
    }
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    with create_neo4j_driver(neo4j_settings) as driver:
        for result_key, log_label, cypher in query_specs:
            logger.info("graph_health: running %s query", log_label)
            records, _, _ = driver.execute_query(
                cypher,
                parameters_=params,
                database_=neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            rows_by_key[result_key] = _records_to_dicts(records)
    return rows_by_key


__all__ = ["GraphHealthQuerySpec", "fetch_graph_health_query_rows"]