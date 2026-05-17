from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path

from power_atlas.bootstrap import AppBaseline, build_app_context, build_settings
from power_atlas.bootstrap import resolve_app_baseline


def default_reset_cli_settings(
    *,
    app_baseline: AppBaseline | None = None,
):
    resolved_baseline = resolve_app_baseline() if app_baseline is None else app_baseline
    return build_settings(app_baseline=resolved_baseline)


def build_reset_settings_from_args(
    args: argparse.Namespace,
    *,
    app_baseline: AppBaseline | None = None,
):
    base_settings = default_reset_cli_settings(app_baseline=app_baseline)
    return replace(
        base_settings,
        neo4j=replace(
            base_settings.neo4j,
            uri=args.neo4j_uri,
            username=args.neo4j_username,
            password=args.neo4j_password,
            database=args.neo4j_database,
        ),
    )


def parse_reset_demo_args(
    argv: list[str] | None = None,
    *,
    demo_node_labels: tuple[str, ...],
    demo_owned_indexes_resolver,
    default_output_dir: Path,
    app_baseline: AppBaseline | None = None,
) -> argparse.Namespace:
    resolved_baseline = resolve_app_baseline() if app_baseline is None else app_baseline
    settings = default_reset_cli_settings(app_baseline=resolved_baseline)
    app_context = build_app_context(settings=settings, app_baseline=resolved_baseline)
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
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv(resolved_baseline.env_names.neo4j_password),
    )
    parser.add_argument("--neo4j-database", default=settings.neo4j.database)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory for the reset report JSON (default: demo/artifacts)",
    )
    return parser.parse_args(argv)


__all__ = ["build_reset_settings_from_args", "default_reset_cli_settings", "parse_reset_demo_args"]