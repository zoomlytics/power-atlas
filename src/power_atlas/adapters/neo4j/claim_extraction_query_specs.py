from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

ClaimExtractionDiagnosticQuerySpec = tuple[str, str, str]


_Q_PARTICIPATION_ROLE_DIST = """\
MATCH ()-[r:HAS_PARTICIPANT]->()
WHERE r.run_id = $run_id
RETURN r.role AS role, count(*) AS total
ORDER BY total DESC
"""

_Q_CLAIM_EDGE_COVERAGE = """\
MATCH (c:ExtractedClaim)
WHERE c.run_id = $run_id
OPTIONAL MATCH (c)-[r:HAS_PARTICIPANT]->(:EntityMention)
WITH c, count(r) AS participant_edges
RETURN participant_edges, count(*) AS claim_count
ORDER BY participant_edges
"""

_Q_MATCH_METHOD_DIST = """\
MATCH ()-[r:HAS_PARTICIPANT]->()
WHERE r.run_id = $run_id
  AND r.match_method IS NOT NULL
RETURN r.match_method AS match_method, count(*) AS total
ORDER BY total DESC
"""


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def build_claim_extraction_diagnostic_query_specs() -> list[ClaimExtractionDiagnosticQuerySpec]:
    return [
        ("role_dist", "participation role distribution", _Q_PARTICIPATION_ROLE_DIST),
        ("edge_coverage", "claim edge coverage", _Q_CLAIM_EDGE_COVERAGE),
        ("match_method_dist", "match method distribution", _Q_MATCH_METHOD_DIST),
    ]


def fetch_claim_extraction_diagnostic_rows(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    *,
    run_id: str,
    query_specs: Sequence[ClaimExtractionDiagnosticQuerySpec],
    logger: logging.Logger,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    with create_neo4j_driver(neo4j_settings) as driver:
        for result_key, log_label, cypher in query_specs:
            logger.info("claim_extraction_diagnostics: running %s query", log_label)
            records, _, _ = driver.execute_query(
                cypher,
                parameters_={"run_id": run_id},
                database_=neo4j_database,
                routing_=neo4j.RoutingControl.READ,
            )
            rows_by_key[result_key] = _records_to_dicts(records)
    return rows_by_key


__all__ = [
    "ClaimExtractionDiagnosticQuerySpec",
    "build_claim_extraction_diagnostic_query_specs",
    "fetch_claim_extraction_diagnostic_rows",
]