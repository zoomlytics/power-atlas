from __future__ import annotations

from collections.abc import Callable
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver


def run_structured_ingest_live(
    config: Any,
    *,
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    entities_rows: list[dict[str, str]],
    facts_rows: list[dict[str, str]],
    relationship_rows: list[dict[str, str]],
    claims_rows: list[dict[str, str]],
    write_graph: Callable[..., None],
) -> None:
    with create_neo4j_driver(config) as driver:
        with driver.session(database=config.neo4j_database) as session:
            write_graph(
                session,
                run_id=run_id,
                source_uri=source_uri,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
                entities_rows=entities_rows,
                facts_rows=facts_rows,
                relationship_rows=relationship_rows,
                claims_rows=claims_rows,
            )


__all__ = ["run_structured_ingest_live"]