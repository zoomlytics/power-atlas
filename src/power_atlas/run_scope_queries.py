from __future__ import annotations

import logging

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings

_DATASET_ID_SAMPLE_LIMIT = 10


def fetch_latest_unstructured_run_id(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    dataset_id: str | None = None,
    *,
    logger: logging.Logger,
) -> str | None:
    """Query Neo4j for the latest unstructured ingest run_id from Chunk nodes.

    When *dataset_id* is provided, only Chunk nodes stamped with that
    dataset_id are considered, ensuring dataset-aware run selection in
    multi-dataset repositories. Without *dataset_id*, the query spans all
    datasets (legacy behaviour, single-dataset repos).

    Returns the run_id of the most recently created unstructured ingest run
    (filtered to *dataset_id* when given), or None if no matching Chunk nodes
    exist. Only call this in live mode; it opens a real Neo4j connection.

    Ordering assumption: run_ids are formatted as
    ``unstructured_ingest-<ISO8601_timestamp>-<uuid8>`` (e.g.
    ``unstructured_ingest-20260312T055234558447Z-47b28b7f``). The embedded
    timestamp string is lexicographically sortable so ``ORDER BY run_id DESC``
    reliably returns the most recent run. If the run_id format ever changes
    to a non-sortable scheme, this query must be updated accordingly.

    Dataset-consistency post-resolution safeguard: after the run_id is
    resolved, an additional LIMIT 2 query checks whether the run's Chunk nodes
    carry a consistent dataset stamp. If multiple distinct dataset_ids are
    detected, a WARNING is emitted because the run may have been inconsistently
    ingested. The resolved run_id is always returned so callers can proceed;
    the warning is informational only.
    """
    with create_neo4j_driver(neo4j_settings) as driver:
        with driver.session(database=neo4j_database) as session:
            if dataset_id is not None:
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.run_id STARTS WITH 'unstructured_ingest' "
                    "AND c.dataset_id = $dataset_id "
                    "RETURN c.run_id ORDER BY c.run_id DESC LIMIT 1",
                    dataset_id=dataset_id,
                )
            else:
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.run_id STARTS WITH 'unstructured_ingest' "
                    "RETURN c.run_id ORDER BY c.run_id DESC LIMIT 1"
                )
            record = result.single()
            if record is None:
                return None
            run_id = record[0]

            check_result = session.run(
                "MATCH (c:Chunk) "
                "WHERE c.run_id = $run_id AND c.dataset_id IS NOT NULL "
                "WITH DISTINCT c.dataset_id AS did "
                "ORDER BY did "
                "LIMIT 2 "
                "RETURN collect(did) AS dataset_ids",
                run_id=run_id,
            )
            check_record = check_result.single()
            detected_ids = check_record["dataset_ids"] if check_record else []
            if len(detected_ids) > 1:
                logger.warning(
                    "Latest unstructured run %r has Chunk nodes stamped with "
                    "multiple distinct dataset_ids: %r. "
                    "The run may have been inconsistently ingested. "
                    "Re-ingest to repair, or select a different known-good run_id "
                    "via --run-id.",
                    run_id,
                    detected_ids,
                )
            return run_id


def fetch_dataset_id_for_run(
    neo4j_settings: Neo4jSettings,
    neo4j_database: str,
    run_id: str,
    *,
    logger: logging.Logger,
) -> str | None:
    """Query Neo4j for the dataset_id stamped on Chunk nodes belonging to *run_id*.

    Uses a two-phase query strategy:

    1. **Fast path** — fetches the first two distinct, sorted ``dataset_id``
       values for the run. In the common consistent case (exactly one value),
       this is the only query executed and returns cheaply via ``LIMIT 2``.
    2. **Slow path** — only triggered when the fast path detects two or more
       distinct values. Uses two ``CALL {}`` subqueries in a single additional
       round-trip: one to compute ``count(DISTINCT c.dataset_id)`` for the
       total and one to collect a ``LIMIT``-bounded sorted sample (up to
       ``_DATASET_ID_SAMPLE_LIMIT`` entries). This keeps the returned sample
       bounded, caps the second subquery's ``collect()``, and keeps the emitted
       warning/log line length bounded even on severely corrupted graphs.

    If exactly one distinct value is found on the fast path, it is returned
    as the authoritative dataset_id for the run.

    If multiple distinct values are found (indicating an inconsistently-ingested
    graph), a WARNING is logged with the total distinct count and the first few
    sorted dataset_ids, and the first sorted dataset_id is returned so callers
    can continue deterministic dataset-ownership mismatch checks.

    Returns None if no Chunk nodes with a non-null dataset_id exist for the run.
    Only call this in live mode; it opens a real Neo4j connection.
    """
    with create_neo4j_driver(neo4j_settings) as driver:
        with driver.session(database=neo4j_database) as session:
            result = session.run(
                "MATCH (c:Chunk) "
                "WHERE c.run_id = $run_id AND c.dataset_id IS NOT NULL "
                "WITH DISTINCT c.dataset_id AS dataset_id "
                "ORDER BY dataset_id "
                "LIMIT 2 "
                "RETURN collect(dataset_id) AS dataset_ids",
                run_id=run_id,
            )
            record = result.single()
            detected_ids = record["dataset_ids"]
            if not detected_ids:
                return None

            if len(detected_ids) == 1:
                return detected_ids[0]

            result = session.run(
                "CALL { "
                "  MATCH (c:Chunk) "
                "  WHERE c.run_id = $run_id AND c.dataset_id IS NOT NULL "
                "  RETURN count(DISTINCT c.dataset_id) AS total_count "
                "} "
                "CALL { "
                "  MATCH (c:Chunk) "
                "  WHERE c.run_id = $run_id AND c.dataset_id IS NOT NULL "
                "  WITH DISTINCT c.dataset_id AS dataset_id "
                "  ORDER BY dataset_id "
                "  LIMIT $limit "
                "  RETURN collect(dataset_id) AS sampled_ids "
                "} "
                "RETURN total_count, sampled_ids",
                run_id=run_id,
                limit=_DATASET_ID_SAMPLE_LIMIT,
            )
            record = result.single()
            dataset_id_count = record["total_count"]
            sampled_ids = record["sampled_ids"]
            used_sample_fallback = not sampled_ids
            displayed_ids = sampled_ids if sampled_ids else detected_ids
            first_dataset_id = displayed_ids[0]

            logger.warning(
                "run_id=%r has Chunk nodes stamped with %d distinct dataset_ids. "
                "Showing the first %d sorted dataset_ids: %r. "
                "The graph may have been inconsistently ingested. "
                "Proceeding with dataset-ownership validation using %s, %r.",
                run_id,
                dataset_id_count,
                len(displayed_ids),
                displayed_ids,
                (
                    "the first sorted dataset_id"
                    if not used_sample_fallback
                    else "a fallback dataset_id from the fast-path detection because the slow-path sample was empty"
                ),
                first_dataset_id,
            )
            return first_dataset_id


__all__ = [
    "fetch_dataset_id_for_run",
    "fetch_latest_unstructured_run_id",
]