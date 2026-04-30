from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def run_graph_health_diagnostics_main(
    *,
    parse_args: Callable[[list[str] | None], Any],
    build_cli_request_context: Callable[[Any], Any],
    run_graph_health_diagnostics_request_context: Callable[..., dict[str, Any]],
    warn: Callable[[str], None],
    emit: Callable[[str], None] = print,
    argv: list[str] | None = None,
) -> None:
    args = parse_args(argv)

    if not args.neo4j_password:
        emit(
            "ERROR: Neo4j password is required.  Set NEO4J_PASSWORD or pass --neo4j-password.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    request_context = build_cli_request_context(args)

    result = run_graph_health_diagnostics_request_context(
        request_context,
        alignment_version=args.alignment_version,
        output_dir=args.output_dir,
    )

    artifact_path = result["artifact_path"]
    status = result["status"]
    emit(f"Status        : {status}")
    emit(f"Run ID        : {result['run_id'] or '(all runs)'}")
    emit(f"Align version : {result['alignment_version'] or '(all versions)'}")
    emit(f"Artifact path : {artifact_path}")

    if result.get("artifact"):
        artifact = result["artifact"]
        ps = artifact["participation_summary"]
        ms = artifact["mention_summary"]
        als = artifact["alignment_summary"]
        emit("")
        emit("--- Participation ---")
        emit(f"  Total HAS_PARTICIPANT edges : {ps['total_edges']}")
        emit(f"  Edges by role               : {ps['edges_by_role']}")
        emit(f"  Total claims                : {ps['total_claims']}")
        emit(f"  Claims with zero edges      : {ps['claims_with_zero_edges']}")
        claim_cov = f"{ps['claim_coverage_pct']}%" if ps["claim_coverage_pct"] is not None else "n/a"
        emit(f"  Claim coverage              : {claim_cov}")
        emit("")
        emit("--- Mention clustering ---")
        emit(f"  Total mentions              : {ms['total_mentions']}")
        emit(f"  Clustered                   : {ms['clustered_mentions']}")
        emit(f"  Unclustered                 : {ms['unclustered_mentions']}")
        unresolved = f"{ms['unresolved_rate_pct']}%" if ms["unresolved_rate_pct"] is not None else "n/a"
        emit(f"  Unresolved rate             : {unresolved}")
        emit("")
        emit("--- Alignment ---")
        emit(f"  Total clusters              : {als['total_clusters']}")
        emit(f"  Aligned clusters            : {als['aligned_clusters']}")
        emit(f"  Unaligned clusters          : {als['unaligned_clusters']}")
        align_cov = f"{als['alignment_coverage_pct']}%" if als["alignment_coverage_pct"] is not None else "n/a"
        emit(f"  Alignment coverage          : {align_cov}")

    for warning in result.get("warnings", []):
        warn(warning)

    summary = {
        "run_id": result["run_id"],
        "alignment_version": result["alignment_version"],
        "artifact_path": artifact_path,
        "status": status,
    }
    emit("")
    emit(json.dumps(summary))


__all__ = ["run_graph_health_diagnostics_main"]