from __future__ import annotations

from typing import Any


def write_alignment_results(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    alignment_rows: list[dict[str, Any]],
    neo4j_database: str,
    alignment_version: str,
) -> None:
    if not alignment_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
        MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
        MERGE (cluster)-[r:ALIGNED_WITH {
            run_id:            $run_id,
            alignment_version: $alignment_version
        }]->(canonical)
        SET r.alignment_method = row.alignment_method,
            r.alignment_score  = row.alignment_score,
            r.alignment_status = row.alignment_status,
            r.source_uri       = coalesce(row.source_uri, $source_uri)
        """,
        parameters_={
            "rows": alignment_rows,
            "run_id": run_id,
            "source_uri": source_uri or None,
            "alignment_version": alignment_version,
        },
        database_=neo4j_database,
    )


__all__ = ["write_alignment_results"]