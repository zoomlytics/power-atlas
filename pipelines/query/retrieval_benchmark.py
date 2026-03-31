"""Post-hybrid retrieval benchmark script.

Connects to a running Neo4j instance, runs the full retrieval benchmark defined
in ``demo/stages/retrieval_benchmark.py``, and writes a JSON artifact to
``pipelines/runs/<run_id>/retrieval_benchmark/`` when ``--run-id`` is provided,
or to ``pipelines/runs/retrieval_benchmark/`` when it is omitted.

The benchmark covers five canonical case types:

1. ``single_entity`` — single-entity canonical traversal (MercadoLibre, Xapo,
   Endeavor, Linda Rottenberg).
2. ``pairwise_entity`` — pairwise canonical claim lookup (Amazon ↔ eBay).
3. ``fragmented_entity`` — entities known to fragment under raw cluster-name
   traversal.
4. ``composite_claim`` — entities with list-valued claim slots.
5. ``canonical_vs_cluster`` — side-by-side claim-count comparison.

For each case the artifact records the canonical traversal rows, the parallel
cluster-name traversal rows, the full lower-layer chain inspection rows, and
derived fragmentation metrics.

Usage
-----
Set Neo4j connection env vars (or pass via CLI flags), then run:

    # Scoped to a specific run and alignment version
    python pipelines/query/retrieval_benchmark.py \\
        --run-id unstructured_ingest-20240101T000000000000Z-abcd1234 \\
        --alignment-version v1.0

    # Unscoped — aggregates across all runs
    python pipelines/query/retrieval_benchmark.py

Environment variables
---------------------
NEO4J_URI       (default: bolt://localhost:7687)
NEO4J_USERNAME  (default: neo4j)
NEO4J_PASSWORD  (required)
NEO4J_DATABASE  (default: neo4j)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the repository root is on sys.path when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.contracts.runtime import Config  # noqa: E402
from demo.stages.retrieval_benchmark import run_retrieval_benchmark  # noqa: E402

# Base output directory — the parent of `runs/`, matching Config.output_dir conventions.
_PIPELINES_DIR = Path(__file__).resolve().parent.parent


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the post-hybrid retrieval benchmark and write a JSON artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Pipeline run_id to scope all queries.  If omitted, "
            "queries aggregate across all runs in the database."
        ),
    )
    parser.add_argument(
        "--alignment-version",
        default=None,
        help=(
            "Alignment version to scope ALIGNED_WITH queries (e.g. 'v1.0').  "
            "If omitted, alignment queries aggregate across all versions."
        ),
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j bolt URI (default: $NEO4J_URI or bolt://localhost:7687).",
    )
    parser.add_argument(
        "--neo4j-username",
        default=os.getenv("NEO4J_USERNAME", "neo4j"),
        help="Neo4j username (default: $NEO4J_USERNAME or 'neo4j').",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("NEO4J_PASSWORD", ""),
        help="Neo4j password (default: $NEO4J_PASSWORD).",
    )
    parser.add_argument(
        "--neo4j-database",
        default=os.getenv("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name (default: $NEO4J_DATABASE or 'neo4j').",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PIPELINES_DIR,
        help=(
            "Base output directory (default: pipelines/).  "
            "Artifacts are written under <output_dir>/runs/<run_id>/retrieval_benchmark/ "
            "when --run-id is given, or <output_dir>/runs/retrieval_benchmark/ otherwise."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    args = _parse_args(argv)

    if not args.neo4j_password:
        print(
            "ERROR: Neo4j password is required.  Set NEO4J_PASSWORD or pass --neo4j-password.",
            file=sys.stderr,
        )
        sys.exit(1)

    config = Config(
        dry_run=False,
        output_dir=args.output_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model="",  # not needed for read-only benchmark queries
    )

    result = run_retrieval_benchmark(
        config,
        run_id=args.run_id,
        alignment_version=args.alignment_version,
        output_dir=args.output_dir,
    )

    artifact_path = result["artifact_path"]
    status = result["status"]
    print(f"Status           : {status}")
    print(f"Run ID           : {result['run_id'] or '(all runs)'}")
    print(f"Align version    : {result['alignment_version'] or '(all versions)'}")
    print(f"Artifact path    : {artifact_path}")

    if result.get("artifact"):
        artifact = result["artifact"]
        s = artifact["benchmark_summary"]
        print()
        print("--- Benchmark summary ---")
        print(f"  Total cases              : {s['total_cases']}")
        print(f"  Single/comparison cases  : {s['single_and_comparison_cases']}")
        print(f"  Pairwise cases           : {s['pairwise_cases']}")
        print(f"  Fragmentation detected   : {s['fragmentation_detected_count']}")
        print(f"  Entities w/ claims (canonical) : {s['entities_with_claims_canonical']}")
        print(f"  Entities w/ claims (cluster)   : {s['entities_with_claims_cluster']}")
        print(f"  Total canonical claims   : {s['total_canonical_claims']}")
        print(f"  Total cluster claims     : {s['total_cluster_claims']}")
        print(f"  Total pairwise claims    : {s['total_pairwise_claims']}")

    for w in result.get("warnings", []):
        print(f"WARNING: {w}", file=sys.stderr)

    summary = {
        "run_id": result["run_id"],
        "alignment_version": result["alignment_version"],
        "artifact_path": artifact_path,
        "status": status,
    }
    print()
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
