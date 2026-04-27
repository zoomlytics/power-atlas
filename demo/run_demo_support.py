from __future__ import annotations

import argparse
import sys
from pathlib import Path

from power_atlas.bootstrap import build_app_context as _build_app_context
from power_atlas.bootstrap import build_request_context as _build_request_context
from power_atlas.bootstrap import build_runtime_config as _build_runtime_config
from power_atlas.bootstrap import build_settings as _build_package_settings
from power_atlas.context import RequestContext
from power_atlas.orchestration.context_builder import (
    build_request_context_from_config as _build_request_context_from_config,
    build_settings_from_overrides as _build_settings_from_overrides,
)

from power_atlas.contracts import ARTIFACTS_DIR, Config


def add_common_args(parser: argparse.ArgumentParser) -> None:
    package_settings = _build_package_settings()
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Run without live Neo4j/OpenAI calls",
    )
    mode_group.add_argument(
        "--live",
        action="store_false",
        dest="dry_run",
        help="Enable live Neo4j/OpenAI calls",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--neo4j-uri", default=package_settings.neo4j.uri)
    parser.add_argument("--neo4j-username", default=package_settings.neo4j.username)
    parser.add_argument("--neo4j-password", default=package_settings.neo4j.password)
    parser.add_argument("--neo4j-database", default=package_settings.neo4j.database)
    parser.add_argument("--openai-model", default=package_settings.openai_model)
    parser.add_argument(
        "--dataset",
        default=package_settings.dataset_name,
        dest="dataset",
        metavar="DATASET_NAME",
        help=(
            "Name of the fixture dataset to use (directory under demo/fixtures/datasets/). "
            "Defaults to POWER_ATLAS_DATASET or FIXTURE_DATASET; if neither is set, "
            "the single available dataset is auto-discovered."
        ),
    )


def build_config_from_args(args: argparse.Namespace) -> Config:
    settings = _build_settings_from_overrides(
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model=args.openai_model,
        output_dir=args.output_dir,
        dataset_name=getattr(args, "dataset", None) or "",
    )
    config = _build_runtime_config(
        settings,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        question=getattr(args, "question", None),
        resolution_mode=getattr(args, "resolution_mode", None) or "unstructured_only",
    )
    if not args.dry_run and config.settings.neo4j.password in ("", "CHANGE_ME_BEFORE_USE"):
        raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
    return config


def build_request_context_from_args(
    args: argparse.Namespace,
    *,
    dry_run: bool | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    settings = _build_settings_from_overrides(
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model=args.openai_model,
        output_dir=args.output_dir,
        dataset_name=getattr(args, "dataset", None) or "",
    )
    app_context = _build_app_context(settings=settings)
    return _build_request_context(
        app_context,
        command=getattr(args, "command", None),
        dry_run=args.dry_run if dry_run is None else dry_run,
        output_dir=args.output_dir,
        question=getattr(args, "question", None),
        resolution_mode=getattr(args, "resolution_mode", None) or "unstructured_only",
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def request_context_from_config(
    config: Config,
    *,
    command: str | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    return _build_request_context_from_config(
        config,
        command=command,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    common_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    add_common_args(common_parser)
    parser = argparse.ArgumentParser(
        description="Demo workflow orchestrator",
        parents=[common_parser],
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in (
        "lint-structured",
        "ingest-structured",
        "ingest-pdf",
        "extract-claims",
        "resolve-entities",
        "ask",
        "reset",
        "ingest",
    ):
        subparsers.add_parser(command, parents=[common_parser], allow_abbrev=False)
        if command == "ask":
            subparsers.choices[command].add_argument("--question", default=None)
            subparsers.choices[command].add_argument(
                "--interactive",
                action="store_true",
                default=False,
                help="Start an interactive REPL-style Q&A session with message history",
            )
            scope_group = subparsers.choices[command].add_mutually_exclusive_group()
            scope_group.add_argument(
                "--run-id",
                default=None,
                dest="run_id",
                metavar="RUN_ID",
                help="Retrieve from a specific ingest run (overrides UNSTRUCTURED_RUN_ID env var)",
            )
            scope_group.add_argument(
                "--latest",
                action="store_true",
                default=False,
                dest="latest",
                help="Retrieve from the latest unstructured ingest run (default behavior)",
            )
            scope_group.add_argument(
                "--all-runs",
                action="store_true",
                default=False,
                dest="all_runs",
                help="Retrieve across all ingested data (no run_id filter); citations may span multiple runs",
            )
            subparsers.choices[command].add_argument(
                "--cluster-aware",
                action="store_true",
                default=False,
                dest="cluster_aware",
                help=(
                    "Enable cluster-aware retrieval: extends graph expansion with "
                    "ResolvedEntityCluster membership and ALIGNED_WITH edges to canonical "
                    "entities. Implies --expand-graph. Run after 'resolve-entities "
                    "--resolution-mode hybrid' to demonstrate post-alignment enrichment."
                ),
            )
            subparsers.choices[command].add_argument(
                "--expand-graph",
                action="store_true",
                default=False,
                dest="expand_graph",
                help=(
                    "Enable graph-expanded retrieval: adds ExtractedClaim, EntityMention, "
                    "and canonical entity context from the graph alongside each retrieved "
                    "chunk. Use --cluster-aware for the full post-hybrid enrichment path."
                ),
            )
            subparsers.choices[command].add_argument(
                "--debug",
                action="store_true",
                default=False,
                dest="debug",
                help=(
                    "Enable debug output for interactive sessions: prints a compact "
                    "postprocessing summary after each answer showing citation quality "
                    "metadata (raw/final citation state, repair/fallback applied, evidence "
                    "level, warning count).  Has no effect when --interactive is not set."
                ),
            )
        if command == "ingest":
            subparsers.choices[command].add_argument(
                "--question",
                default=None,
                help=(
                    "Optional demo question to run through the Q&A passes in both "
                    "the unstructured-only and hybrid enrichment phases. "
                    "When omitted in --live mode, the Q&A stage is still recorded "
                    "but vector retrieval is skipped."
                ),
            )
        if command == "reset":
            subparsers.choices[command].add_argument(
                "--confirm",
                action="store_true",
                default=False,
                help="Required safety flag; without it the command prints instructions only",
            )
        if command == "resolve-entities":
            subparsers.choices[command].add_argument(
                "--resolution-mode",
                default=None,
                dest="resolution_mode",
                choices=["structured_anchor", "unstructured_only", "hybrid"],
                help=(
                    "Resolution mode: 'unstructured_only' (default) clusters mentions "
                    "against each other without requiring structured ingest; 'hybrid' "
                    "clusters mentions first then optionally aligns clusters to "
                    "CanonicalEntity nodes via ALIGNED_WITH enrichment edges; "
                    "'structured_anchor' resolves mentions against CanonicalEntity nodes "
                    "using exact-match strategies."
                ),
            )
    parser.set_defaults(command="ingest")

    options_with_values = {
        "--output-dir",
        "--neo4j-uri",
        "--neo4j-username",
        "--neo4j-password",
        "--neo4j-database",
        "--openai-model",
        "--question",
        "--run-id",
        "--resolution-mode",
    }
    saw_dry_run_flag = False
    saw_live_flag = False
    i = 0
    while i < len(raw_argv):
        token = raw_argv[i]
        if token in options_with_values:
            i += 2
            continue
        if token == "--dry-run":
            saw_dry_run_flag = True
        elif token == "--live":
            saw_live_flag = True
        i += 1

    if saw_dry_run_flag and saw_live_flag:
        parser.error("argument --dry-run: not allowed with argument --live")
    namespace = parser.parse_args(raw_argv)
    if saw_live_flag:
        namespace.dry_run = False
    elif saw_dry_run_flag:
        namespace.dry_run = True
    return namespace


__all__ = [
    "add_common_args",
    "build_config_from_args",
    "build_request_context_from_args",
    "parse_args",
    "request_context_from_config",
]