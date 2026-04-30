from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def run_retrieval_benchmark_main(
    *,
    parse_args: Callable[[list[str] | None], Any],
    build_cli_request_context: Callable[[Any], Any],
    run_retrieval_benchmark_request_context: Callable[..., dict[str, Any]],
    warn: Callable[[str], None],
    emit: Callable[..., None] = print,
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

    result = run_retrieval_benchmark_request_context(
        request_context,
        dataset_id=args.dataset_id,
        alignment_version=args.alignment_version,
        output_dir=args.output_dir,
    )

    artifact_path = result["artifact_path"]
    status = result["status"]
    emit(f"Status           : {status}")
    emit(
        f"Dataset ID       : "
        f"{'(all datasets)' if result['dataset_id'] is None else result['dataset_id']}"
    )
    emit(
        f"Run ID           : "
        f"{'(all runs)' if result['run_id'] is None else result['run_id']}"
    )
    emit(
        f"Align version    : "
        f"{'(all versions)' if result['alignment_version'] is None else result['alignment_version']}"
    )
    emit(f"Artifact path    : {artifact_path}")

    if result.get("artifact"):
        artifact = result["artifact"]
        summary_block = artifact["benchmark_summary"]
        emit("")
        emit("--- Benchmark summary ---")
        emit(f"  Total cases              : {summary_block['total_cases']}")
        emit(f"  Single/comparison cases  : {summary_block['single_and_comparison_cases']}")
        emit(f"  Pairwise cases           : {summary_block['pairwise_cases']}")
        emit(f"  Fragmentation detected   : {summary_block['fragmentation_detected_count']}")
        emit(
            f"  Entities w/ claims (canonical) : {summary_block['entities_with_claims_canonical']}"
        )
        emit(
            f"  Entities w/ claims (cluster)   : {summary_block['entities_with_claims_cluster']}"
        )
        emit(f"  Total canonical claims   : {summary_block['total_canonical_claims']}")
        emit(f"  Total cluster claims     : {summary_block['total_cluster_claims']}")
        emit(f"  Total pairwise claims    : {summary_block['total_pairwise_claims']}")

    for warning in result.get("warnings", []):
        warn(warning)

    summary = {
        "run_id": result["run_id"],
        "dataset_id": result["dataset_id"],
        "alignment_version": result["alignment_version"],
        "artifact_path": artifact_path,
        "status": status,
    }
    emit("")
    emit(json.dumps(summary))


__all__ = ["run_retrieval_benchmark_main"]