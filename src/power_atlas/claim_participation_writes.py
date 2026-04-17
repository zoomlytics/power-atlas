from __future__ import annotations

from typing import Any

import neo4j


def write_claim_participation_edges(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    edge_rows: list[dict[str, Any]],
) -> None:
    """Persist claim participation edges with idempotent MERGE semantics."""
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
        MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})
        MERGE (claim)-[r:HAS_PARTICIPANT {role: row.role}]->(mention)
        SET r.run_id = row.run_id,
            r.source_uri = coalesce(row.source_uri, r.source_uri),
            r.match_method = row.match_method
        """,
        parameters_={"rows": edge_rows},
        database_=neo4j_database,
    )


__all__ = ["write_claim_participation_edges"]