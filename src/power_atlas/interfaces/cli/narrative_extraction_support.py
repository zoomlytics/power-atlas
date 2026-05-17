from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
from typing import Any

from power_atlas.bootstrap import AppBaseline
from power_atlas.bootstrap import build_settings
from power_atlas.bootstrap import resolve_app_baseline


def default_narrative_cli_settings(
    *,
    app_baseline: AppBaseline | None = None,
):
    resolved_baseline = resolve_app_baseline() if app_baseline is None else app_baseline
    settings = build_settings(app_baseline=resolved_baseline)
    if resolved_baseline.env_names.openai_model in os.environ:
        return settings
    return replace(settings, openai_model="gpt-4o-mini")


def build_narrative_cli_config(
    args: argparse.Namespace,
    *,
    extraction_config_type: type,
    app_baseline: AppBaseline | None = None,
):
    settings = replace(
        default_narrative_cli_settings(app_baseline=app_baseline),
        neo4j=replace(
            default_narrative_cli_settings(app_baseline=app_baseline).neo4j,
            uri=args.neo4j_uri,
            username=args.neo4j_username,
            password=args.neo4j_password,
            database=args.neo4j_database,
        ),
        openai_model=args.model_name,
    )
    return extraction_config_type(
        run_id=args.run_id,
        source_uri=args.source_uri,
        settings=settings,
        output_root=args.output_root,
        dry_run=args.dry_run,
    )


def parse_narrative_extraction_args(
    argv: list[str] | None = None,
    *,
    default_output_root: Path,
    extraction_config_type: type,
    app_baseline: AppBaseline | None = None,
) -> Any:
    package_settings = default_narrative_cli_settings(app_baseline=app_baseline)
    parser = argparse.ArgumentParser(
        description="Run narrative claim and mention extraction from existing ingested chunks."
    )
    parser.add_argument("--run-id", required=True, help="run_id for the ingested chunks to process")
    parser.add_argument(
        "--source-uri",
        help="Optional source_uri filter to scope chunks within the run",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root,
        help="Directory where run artifacts are written (default: demo/runs)",
    )
    parser.add_argument("--neo4j-uri", default=package_settings.neo4j.uri)
    parser.add_argument("--neo4j-username", default=package_settings.neo4j.username)
    parser.add_argument("--neo4j-password", default=package_settings.neo4j.password)
    parser.add_argument("--neo4j-database", default=package_settings.neo4j.database)
    parser.add_argument("--model-name", default=package_settings.openai_model)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write artifacts without reading chunks or calling the LLM",
    )
    args = parser.parse_args(argv)
    return build_narrative_cli_config(
        args,
        extraction_config_type=extraction_config_type,
        app_baseline=app_baseline,
    )


__all__ = [
    "build_narrative_cli_config",
    "default_narrative_cli_settings",
    "parse_narrative_extraction_args",
]