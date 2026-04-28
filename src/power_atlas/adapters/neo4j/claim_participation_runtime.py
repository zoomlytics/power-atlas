from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import neo4j

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.settings import Neo4jSettings


@dataclass(frozen=True)
class ClaimParticipationLiveResult:
    claim_rows: list[dict[str, Any]]
    mention_rows: list[dict[str, Any]]
    edge_rows: list[dict[str, Any]]
    match_metrics: Any


def run_claim_participation_live(
    neo4j_settings: Neo4jSettings,
    *,
    run_id: str,
    source_uri: str | None,
    neo4j_database: str | None,
    build_edges_with_metrics: Callable[..., tuple[list[dict[str, Any]], Any]],
    write_edges: Callable[..., None],
) -> ClaimParticipationLiveResult:
    with create_neo4j_driver(neo4j_settings) as driver:
        claim_result, _, _ = driver.execute_query(
            """
            MATCH (claim:ExtractedClaim {run_id: $run_id})
            OPTIONAL MATCH (claim)-[supported_by:SUPPORTED_BY]->()
            RETURN claim.claim_id AS claim_id,
                   claim.subject   AS subject,
                   claim.object    AS object,
                   claim.source_uri AS source_uri,
                   collect(DISTINCT supported_by.chunk_id) AS chunk_ids
            ORDER BY claim.claim_id
            """,
            parameters_={"run_id": run_id},
            database_=neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        claim_rows = [
            {
                "claim_id": row["claim_id"],
                "chunk_ids": [chunk_id for chunk_id in (row["chunk_ids"] or []) if chunk_id is not None],
                "run_id": run_id,
                "source_uri": row["source_uri"] if row["source_uri"] not in (None, "") else source_uri,
                "properties": {
                    key: value
                    for key, value in (("subject", row["subject"]), ("object", row["object"]))
                    if value is not None
                },
            }
            for row in claim_result
        ]

        mention_result, _, _ = driver.execute_query(
            """
            MATCH (mention:EntityMention {run_id: $run_id})
            OPTIONAL MATCH (mention)-[mentioned_in:MENTIONED_IN]->()
            RETURN mention.mention_id AS mention_id,
                   mention.name       AS name,
                   mention.source_uri AS source_uri,
                   collect(DISTINCT mentioned_in.chunk_id) AS chunk_ids
            ORDER BY mention.mention_id
            """,
            parameters_={"run_id": run_id},
            database_=neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        mention_rows = [
            {
                "mention_id": row["mention_id"],
                "chunk_ids": [chunk_id for chunk_id in (row["chunk_ids"] or []) if chunk_id is not None],
                "run_id": run_id,
                "source_uri": row["source_uri"] if row["source_uri"] not in (None, "") else source_uri,
                "properties": {"name": row["name"] or ""},
            }
            for row in mention_result
        ]

        edge_rows, match_metrics = build_edges_with_metrics(claim_rows, mention_rows)
    write_edges(driver, neo4j_database=neo4j_database, edge_rows=edge_rows)

    return ClaimParticipationLiveResult(
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        edge_rows=edge_rows,
        match_metrics=match_metrics,
    )


__all__ = ["ClaimParticipationLiveResult", "run_claim_participation_live"]