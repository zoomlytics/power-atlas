from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def _emit_claim_extraction_diagnostics_report(
    result: dict[str, Any],
    *,
    emit: Callable[..., None],
    warn: Callable[[str], None],
) -> None:
    emit(f"Status        : {result['status']}")
    emit(f"Run ID        : {result['run_id']}")
    emit(f"Source URI    : {result['source_uri'] or '(none)'}")
    emit(f"Artifact path : {result['artifact_path']}")

    participation_summary = result.get("participation_summary")
    if participation_summary is not None:
        emit("")
        emit("--- Participation ---")
        emit(f"  Total HAS_PARTICIPANT edges : {participation_summary['total_edges']}")
        emit(f"  Edges by role               : {participation_summary['edges_by_role']}")
        emit(f"  Total claims                : {participation_summary['total_claims']}")
        emit(
            f"  Claims with zero edges      : {participation_summary['claims_with_zero_edges']}"
        )
        claim_coverage = participation_summary["claim_coverage_pct"]
        emit(
            "  Claim coverage              : "
            f"{'n/a' if claim_coverage is None else str(claim_coverage) + '%'}"
        )

    match_summary = result.get("match_summary")
    if match_summary is not None:
        emit("")
        emit("--- Match methods ---")
        emit(
            "  Total edges with method     : "
            f"{match_summary['total_edges_with_match_method']}"
        )
        emit(
            f"  Edges by match method       : {match_summary['edges_by_match_method']}"
        )

    for warning in result.get("warnings", []):
        warn(warning)

    summary = {
        "run_id": result["run_id"],
        "artifact_path": result["artifact_path"],
        "status": result["status"],
    }
    if "inferred_dataset_id" in result:
        summary["inferred_dataset_id"] = result["inferred_dataset_id"]
    emit("")
    emit(json.dumps(summary))


def run_claim_extraction_diagnostics_report_main(
    *,
    parse_args: Callable[[list[str] | None], Any],
    build_settings: Callable[[Any], Any],
    resolve_artifact: Callable[[Any, str], Any],
    resolve_current_artifact: Callable[..., Any],
    warn: Callable[[str], None],
    emit: Callable[..., None] = print,
    argv: list[str] | None = None,
) -> None:
    args = parse_args(argv)
    settings = build_settings(args)

    if bool(getattr(args, "current", False)):
        stage_prefix = getattr(args, "stage_prefix", None)
        if not isinstance(stage_prefix, str) or not stage_prefix:
            emit(
                "ERROR: stage_prefix is required when --current is used.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        result_obj = resolve_current_artifact(
            settings,
            stage_prefix,
            dataset_id=getattr(args, "dataset_id", None),
        )
    else:
        run_id = getattr(args, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            emit(
                "ERROR: run_id is required unless --current is used.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        result_obj = resolve_artifact(settings, run_id)

    result = {
        "status": result_obj.status,
        "run_id": result_obj.run_id,
        "source_uri": result_obj.source_uri,
        "artifact_path": result_obj.artifact_path,
        "participation_summary": (
            None
            if result_obj.participation_summary is None
            else {
                "total_edges": result_obj.participation_summary.total_edges,
                "edges_by_role": result_obj.participation_summary.edges_by_role,
                "total_claims": result_obj.participation_summary.total_claims,
                "claims_with_zero_edges": result_obj.participation_summary.claims_with_zero_edges,
                "claim_coverage_pct": result_obj.participation_summary.claim_coverage_pct,
            }
        ),
        "match_summary": (
            None
            if result_obj.match_summary is None
            else {
                "total_edges_with_match_method": result_obj.match_summary.total_edges_with_match_method,
                "edges_by_match_method": result_obj.match_summary.edges_by_match_method,
            }
        ),
        "warnings": [] if result_obj.warnings is None else result_obj.warnings,
    }
    inferred_dataset_id = getattr(result_obj, "inferred_dataset_id", None)
    if inferred_dataset_id is not None:
        result["inferred_dataset_id"] = inferred_dataset_id

    _emit_claim_extraction_diagnostics_report(result, emit=emit, warn=warn)


__all__ = ["run_claim_extraction_diagnostics_report_main"]