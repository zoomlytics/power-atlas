from __future__ import annotations

import argparse
import os
from pathlib import Path

from power_atlas.bootstrap import build_runtime_config, build_settings
from power_atlas.orchestration.context_builder import build_request_context_from_config


def build_graph_health_cli_request_context(args: argparse.Namespace):
    settings = build_settings(
        {
            **os.environ,
            "NEO4J_URI": args.neo4j_uri,
            "NEO4J_USERNAME": args.neo4j_username,
            "NEO4J_PASSWORD": args.neo4j_password,
            "NEO4J_DATABASE": args.neo4j_database,
            "POWER_ATLAS_OUTPUT_DIR": str(args.output_dir),
        }
    )
    config = build_runtime_config(settings, dry_run=False, output_dir=args.output_dir)
    return build_request_context_from_config(
        config,
        command="graph-health",
        run_id=args.run_id,
    )


def parse_graph_health_diagnostics_args(
    argv: list[str] | None = None,
    *,
    default_output_dir: Path,
    doc_epilog: str | None,
) -> argparse.Namespace:
    package_settings = build_settings()
    parser = argparse.ArgumentParser(
        description="Generate a repeatable graph-health diagnostics artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=doc_epilog,
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
            "Artifacts are written under <output_dir>/runs/<run_id>/graph_health/ "
            "when --run-id is given, or <output_dir>/runs/graph_health/ otherwise."
        ),
    )
    return parser.parse_args(argv)


__all__ = [
    "build_graph_health_cli_request_context",
    "parse_graph_health_diagnostics_args",
]