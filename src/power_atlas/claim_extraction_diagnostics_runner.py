from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from power_atlas.backend_run_catalog import resolve_run_root
from power_atlas.claim_extraction_query_specs import (
    build_claim_extraction_diagnostic_query_specs,
    fetch_claim_extraction_diagnostic_rows,
)
from power_atlas.settings import Neo4jSettings

_logger = logging.getLogger(__name__)


def compute_claim_extraction_participation_summary(
    role_dist: list[dict[str, object]],
    edge_coverage: list[dict[str, object]],
) -> dict[str, object]:
    total_edges = sum(int(row["total"]) for row in role_dist)
    edges_by_role = {str(row["role"]): int(row["total"]) for row in role_dist}
    total_claims = sum(int(row["claim_count"]) for row in edge_coverage)
    claims_with_zero_edges = next(
        (
            int(row["claim_count"])
            for row in edge_coverage
            if int(row["participant_edges"]) == 0
        ),
        0,
    )
    claims_with_edges = total_claims - claims_with_zero_edges
    claim_coverage_pct = (
        round(claims_with_edges / total_claims * 100, 2) if total_claims > 0 else None
    )
    return {
        "total_edges": total_edges,
        "edges_by_role": edges_by_role,
        "total_claims": total_claims,
        "claims_with_zero_edges": claims_with_zero_edges,
        "claim_coverage_pct": claim_coverage_pct,
    }


def compute_claim_extraction_match_summary(
    match_method_dist: list[dict[str, object]],
) -> dict[str, object]:
    edges_by_match_method = {
        str(row["match_method"]): int(row["total"]) for row in match_method_dist
    }
    return {
        "total_edges_with_match_method": sum(edges_by_match_method.values()),
        "edges_by_match_method": edges_by_match_method,
    }


def run_claim_extraction_diagnostics_runtime_default(
    *,
    dry_run: bool,
    output_dir: Path,
    neo4j_settings: Neo4jSettings | None,
    run_id: str,
    source_uri: str | None,
    query_specs_builder: Callable[[], list[tuple[str, str, str]]] = (
        build_claim_extraction_diagnostic_query_specs
    ),
    query_rows_fetcher: Callable[..., dict[str, list[dict[str, object]]]] = (
        fetch_claim_extraction_diagnostic_rows
    ),
) -> dict[str, object]:
    run_root = resolve_run_root(output_dir, run_id)
    diagnostics_dir = run_root / "claim_extraction_diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = diagnostics_dir / "claim_extraction_diagnostics.json"
    generated_at = datetime.now(UTC).isoformat()

    empty_participation_summary = {
        "total_edges": 0,
        "edges_by_role": {},
        "total_claims": 0,
        "claims_with_zero_edges": 0,
        "claim_coverage_pct": None,
    }
    empty_match_summary = {
        "total_edges_with_match_method": 0,
        "edges_by_match_method": {},
    }

    if dry_run:
        result: dict[str, object] = {
            "status": "dry_run",
            "generated_at": generated_at,
            "run_id": run_id,
            "source_uri": source_uri,
            "artifact_path": str(artifact_path),
            "participation_summary": empty_participation_summary,
            "match_summary": empty_match_summary,
            "warnings": ["claim extraction diagnostics skipped in dry_run mode"],
        }
        artifact_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    if neo4j_settings is None:
        raise ValueError("Live claim extraction diagnostics requires neo4j_settings")

    rows = query_rows_fetcher(
        neo4j_settings,
        neo4j_settings.database,
        run_id=run_id,
        query_specs=query_specs_builder(),
        logger=_logger,
    )
    result = {
        "status": "live",
        "generated_at": generated_at,
        "run_id": run_id,
        "source_uri": source_uri,
        "artifact_path": str(artifact_path),
        "participation_summary": compute_claim_extraction_participation_summary(
            rows["role_dist"],
            rows["edge_coverage"],
        ),
        "match_summary": compute_claim_extraction_match_summary(
            rows["match_method_dist"]
        ),
        "warnings": [],
    }
    artifact_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


__all__ = [
    "compute_claim_extraction_match_summary",
    "compute_claim_extraction_participation_summary",
    "run_claim_extraction_diagnostics_runtime_default",
]