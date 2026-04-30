from __future__ import annotations

import argparse
import os
from pathlib import Path

from power_atlas.bootstrap import build_runtime_config, build_settings
from power_atlas.orchestration.context_builder import (
    build_request_context_from_config,
    build_settings_from_overrides,
)


def build_retrieval_benchmark_cli_request_context(args: argparse.Namespace):
    settings = build_settings_from_overrides(
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        output_dir=args.output_dir,
    )
    config = build_runtime_config(settings, dry_run=False, output_dir=args.output_dir)
    return build_request_context_from_config(
        config,
        command="retrieval-benchmark",
        run_id=args.run_id,
    )


def parse_retrieval_benchmark_args(
    argv: list[str] | None = None,
    *,
    default_output_dir: Path,
    doc_epilog: str | None,
) -> argparse.Namespace:
    package_settings = build_settings()
    parser = argparse.ArgumentParser(
        description="Run the post-hybrid retrieval benchmark and write a JSON artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=doc_epilog,
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help=(
            "Dataset identifier to scope all CanonicalEntity lookups.  "
            "In a multi-dataset graph, always pass this to prevent shared "
            "entity names from matching canonical nodes across datasets.  "
            "If omitted, queries aggregate across all datasets."
        ),
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
        default=package_settings.neo4j.uri,
        help="Neo4j bolt URI (default: $NEO4J_URI or bolt://localhost:7687).",
    )
    parser.add_argument(
        "--neo4j-username",
        default=package_settings.neo4j.username,
        help="Neo4j username (default: $NEO4J_USERNAME or 'neo4j').",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("NEO4J_PASSWORD", ""),
        help="Neo4j password (default: $NEO4J_PASSWORD).",
    )
    parser.add_argument(
        "--neo4j-database",
        default=package_settings.neo4j.database,
        help="Neo4j database name (default: $NEO4J_DATABASE or 'neo4j').",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=(
            "Base output directory (default: pipelines/).  "
            "Artifacts are written under <output_dir>/runs/<run_id>/retrieval_benchmark/ "
            "when --run-id is given, or <output_dir>/runs/retrieval_benchmark/ otherwise."
        ),
    )
    return parser.parse_args(argv)


__all__ = [
    "build_retrieval_benchmark_cli_request_context",
    "parse_retrieval_benchmark_args",
]