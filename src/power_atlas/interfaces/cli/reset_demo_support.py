from __future__ import annotations

import argparse
import os
from pathlib import Path

from power_atlas.bootstrap import build_app_context, build_settings
from power_atlas.orchestration.context_builder import build_settings_from_overrides


def build_reset_settings_from_args(args: argparse.Namespace):
    return build_settings_from_overrides(
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
    )


def parse_reset_demo_args(
    argv: list[str] | None = None,
    *,
    demo_node_labels: tuple[str, ...],
    demo_owned_indexes_resolver,
    default_output_dir: Path,
) -> argparse.Namespace:
    settings = build_settings()
    app_context = build_app_context(settings=settings)
    parser = argparse.ArgumentParser(
        description="Reset demo nodes and indexes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Deletes all nodes with demo-owned labels ({', '.join(demo_node_labels)})\n"
            f"and drops the following indexes: {', '.join(demo_owned_indexes_resolver(app_context.pipeline_contract))}.\n"
            "Run only against a dedicated demo database to avoid data loss."
        ),
    )
    parser.add_argument("--confirm", action="store_true", help="required safety flag")
    parser.add_argument("--neo4j-uri", default=settings.neo4j.uri)
    parser.add_argument("--neo4j-username", default=settings.neo4j.username)
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--neo4j-database", default=settings.neo4j.database)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory for the reset report JSON (default: demo/artifacts)",
    )
    return parser.parse_args(argv)


__all__ = ["build_reset_settings_from_args", "parse_reset_demo_args"]