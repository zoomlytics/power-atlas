from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import neo4j

from power_atlas.claim_participation_edges import (
    EDGE_TYPE_HAS_PARTICIPANT,
    ROLE_OBJECT,
    ROLE_SUBJECT,
    build_participation_edges_with_metrics,
)
from power_atlas.backend_run_catalog import resolve_run_root
from power_atlas.claim_participation_runtime import run_claim_participation_live
from power_atlas.claim_participation_writes import write_claim_participation_edges
from power_atlas.context import RequestContext
from power_atlas.settings import Neo4jSettings


def neo4j_settings_from_config(config: object) -> Neo4jSettings:
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Live claim participation requires config.settings.neo4j to be configured"
    )



def write_participation_edges(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    edge_rows: list[dict[str, Any]],
) -> None:
    if not edge_rows:
        return

    invalid = [i for i, row in enumerate(edge_rows) if not str(row.get("role") or "").strip()]
    if invalid:
        raise ValueError(
            f"write_participation_edges: {len(invalid)} row(s) have a missing or empty "
            f"'role' field (row indices: {invalid}).  Each row must carry a non-empty "
            f"role (e.g. ROLE_SUBJECT or ROLE_OBJECT) before the MERGE is executed."
        )

    invalid_type = [
        i
        for i, row in enumerate(edge_rows)
        if "edge_type" in row and row["edge_type"] != EDGE_TYPE_HAS_PARTICIPANT
    ]
    if invalid_type:
        raise ValueError(
            f"write_participation_edges: {len(invalid_type)} row(s) have an unexpected "
            f"'edge_type' value; expected {EDGE_TYPE_HAS_PARTICIPANT!r} "
            f"(row indices: {invalid_type})."
        )

    write_claim_participation_edges(
        driver,
        neo4j_database=neo4j_database,
        edge_rows=edge_rows,
    )



def run_claim_participation_request_context(request_context: RequestContext) -> dict[str, Any]:
    config = request_context.config
    run_id = request_context.run_id
    source_uri = request_context.source_uri

    run_root = resolve_run_root(config.output_dir, run_id)

    participation_dir = run_root / "claim_participation"
    participation_dir.mkdir(parents=True, exist_ok=True)
    summary_path = participation_dir / "claim_participation_summary.json"
    metrics_path = participation_dir / "participation_metrics.json"

    if config.dry_run:
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "edges_written": 0,
            "subject_edges": 0,
            "object_edges": 0,
            "match_metrics": None,
            "warnings": ["claim participation skipped in dry_run mode"],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    neo4j_settings = neo4j_settings_from_config(config)

    live_result = run_claim_participation_live(
        neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
        neo4j_database=neo4j_settings.database,
        build_edges_with_metrics=build_participation_edges_with_metrics,
        write_edges=write_participation_edges,
    )
    claim_rows = live_result.claim_rows
    mention_rows = live_result.mention_rows
    edge_rows = live_result.edge_rows
    match_metrics = live_result.match_metrics

    subject_edges = sum(1 for edge in edge_rows if edge["role"] == ROLE_SUBJECT)
    object_edges = sum(1 for edge in edge_rows if edge["role"] == ROLE_OBJECT)
    metrics_dict = match_metrics.to_dict()
    metrics_path.write_text(json.dumps(metrics_dict, indent=2), encoding="utf-8")
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "claims_read": len(claim_rows),
        "mentions_read": len(mention_rows),
        "edges_written": len(edge_rows),
        "subject_edges": subject_edges,
        "object_edges": object_edges,
        "match_metrics": metrics_dict,
        "warnings": [],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


__all__ = [
    "neo4j_settings_from_config",
    "run_claim_participation_request_context",
    "write_participation_edges",
]
