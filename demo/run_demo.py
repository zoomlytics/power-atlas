from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from demo.contracts import pipeline as pipeline_contracts

pipeline_contracts.refresh_pipeline_contract()

from demo.contracts import (  # noqa: E402
    ARTIFACTS_DIR,
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
    CHUNK_FALLBACK_STRIDE,
    DATASET_ID,
    DEFAULT_DB,
    Config,
    EMBEDDER_MODEL_NAME,
    FIXTURES_DIR,
    PROMPT_IDS,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
)
from demo.contracts.manifest import write_manifest, write_manifest_md
from demo.stages import (
    lint_and_clean_structured_csvs,
    run_claim_and_mention_extraction,
    run_entity_resolution,
    run_interactive_qa,
    run_pdf_ingest,
    run_retrieval_and_qa,
    run_structured_ingest,
)
from demo.stages.pdf_ingest import _sha256_file  # noqa: F401 - re-exported so run_demo module exposes it for callers and tests


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "CHANGE_ME_BEFORE_USE"))
    parser.add_argument("--neo4j-database", default=DEFAULT_DB)
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


def _build_config_from_args(args: argparse.Namespace) -> Config:
    if not args.dry_run and args.neo4j_password in ("", "CHANGE_ME_BEFORE_USE"):
        raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
    return Config(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model=args.openai_model,
        question=getattr(args, "question", None),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    common_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    _add_common_args(common_parser)
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
        if command == "reset":
            subparsers.choices[command].add_argument(
                "--confirm",
                action="store_true",
                default=False,
                help="Required safety flag; without it the command prints instructions only",
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
    return parser.parse_args(raw_argv)


def _run_orchestrated(config: Config) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now_iso()
    structured_run_id = make_run_id("structured_ingest")
    unstructured_run_id = make_run_id("unstructured_ingest")
    resolution_run_id = make_run_id("resolution")

    structured_stage = run_structured_ingest(config, structured_run_id, fixtures_dir=FIXTURES_DIR)
    pdf_stage = run_pdf_ingest(
        config,
        unstructured_run_id,
        fixtures_dir=FIXTURES_DIR,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        chunk_label=CHUNK_EMBEDDING_LABEL,
        embedding_property=CHUNK_EMBEDDING_PROPERTY,
        embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model=EMBEDDER_MODEL_NAME,
        chunk_stride=CHUNK_FALLBACK_STRIDE,
    )
    pdf_source_uri = pdf_stage.get("provenance", {}).get("source_uri") if isinstance(pdf_stage, dict) else None
    if not pdf_source_uri and isinstance(pdf_stage, dict):
        documents = pdf_stage.get("documents") if isinstance(pdf_stage.get("documents"), list) else []
        pdf_source_uri = documents[0] if documents else None

    claim_stage = run_claim_and_mention_extraction(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
    )
    entity_resolution_stage = run_entity_resolution(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
    )
    retrieval_stage = run_retrieval_and_qa(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
    )
    finished_at = _now_iso()
    manifest = build_batch_manifest(
        config=config,
        structured_run_id=structured_run_id,
        unstructured_run_id=unstructured_run_id,
        resolution_run_id=resolution_run_id,
        structured_stage=structured_stage,
        pdf_stage=pdf_stage,
        claim_stage=claim_stage,
        entity_resolution_stage=entity_resolution_stage,
        retrieval_stage=retrieval_stage,
        started_at=started_at,
        finished_at=finished_at,
    )

    manifest_path = config.output_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def _run_independent_stage(config: Config, command: str) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stage_runners: dict[str, tuple[str, str, Callable[[Config, str], dict[str, Any]]]] = {
        "ingest-structured": (
            "structured_ingest",
            "structured_ingest_run_id",
            lambda cfg, stage_run_id: run_structured_ingest(cfg, stage_run_id, fixtures_dir=FIXTURES_DIR),
        ),
        "ingest-pdf": (
            "pdf_ingest",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_pdf_ingest(
                cfg,
                stage_run_id,
                fixtures_dir=FIXTURES_DIR,
                index_name=CHUNK_EMBEDDING_INDEX_NAME,
                chunk_label=CHUNK_EMBEDDING_LABEL,
                embedding_property=CHUNK_EMBEDDING_PROPERTY,
                embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                embedder_model=EMBEDDER_MODEL_NAME,
                chunk_stride=CHUNK_FALLBACK_STRIDE,
            ),
        ),
        "extract-claims": (
            "claim_and_mention_extraction",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_claim_and_mention_extraction(
                cfg,
                run_id=stage_run_id,
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
            ),
        ),
        "resolve-entities": (
            "entity_resolution",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_entity_resolution(
                cfg,
                run_id=stage_run_id,
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
            ),
        ),
        "ask": (
            "retrieval_and_qa",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_retrieval_and_qa(
                cfg,
                run_id=stage_run_id,
                question=getattr(cfg, "question", None),
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
                index_name=CHUNK_EMBEDDING_INDEX_NAME,
            ),
        ),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    if command in ("extract-claims", "resolve-entities", "ask"):
        env_run_id = os.getenv("UNSTRUCTURED_RUN_ID")
        if not env_run_id:
            raise ValueError(
                "UNSTRUCTURED_RUN_ID is not set. When running "
                f"'{command}' independently, set this to the run_id from a prior "
                "'ingest' or 'ingest-pdf' command whose unstructured data you want to process "
                "(for example, a value like 'unstructured_ingest-20260304T224739123456Z-1a2b3c4d')."
            )
        stage_run_id = env_run_id
    else:
        stage_run_id = make_run_id(run_scope)
    started_at = _now_iso()
    stage_output = stage_runner(config, stage_run_id)
    finished_at = _now_iso()
    manifest = build_stage_manifest(
        config=config,
        stage_name=stage_name,
        stage_run_id=stage_run_id,
        run_scope_key=run_scope_key,
        stage_output=stage_output,
        started_at=started_at,
        finished_at=finished_at,
    )
    # Write the manifest into a run-scoped directory: runs/<run_id>/manifest.json
    run_dir = config.output_dir / "runs" / stage_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def run_demo(config: Config) -> Path:
    return _run_orchestrated(config)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_args(argv)

# Backwards-compatible aliases for legacy tests and scripts.
def _lint_and_clean_structured_csvs(run_id: str, output_dir: Path) -> dict[str, Any]:
    return lint_and_clean_structured_csvs(run_id=run_id, output_dir=output_dir, fixtures_dir=FIXTURES_DIR)


def _run_structured_ingest(config: Config, run_id: str) -> dict[str, Any]:
    return run_structured_ingest(config, run_id, fixtures_dir=FIXTURES_DIR)


def _run_pdf_ingest(config: Config, run_id: str | None = None) -> dict[str, Any]:
    return run_pdf_ingest(
        config,
        run_id,
        fixtures_dir=FIXTURES_DIR,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        chunk_label=CHUNK_EMBEDDING_LABEL,
        embedding_property=CHUNK_EMBEDDING_PROPERTY,
        embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model=EMBEDDER_MODEL_NAME,
        chunk_stride=CHUNK_FALLBACK_STRIDE,
    )


_run_claim_and_mention_extraction = run_claim_and_mention_extraction
_run_entity_resolution = run_entity_resolution
_run_retrieval_and_qa = run_retrieval_and_qa
run_independent_demo = _run_independent_stage


def main() -> None:
    args = parse_args()
    if args.command == "lint-structured":
        config = Config(
            dry_run=True,
            output_dir=args.output_dir,
            neo4j_uri=args.neo4j_uri,
            neo4j_username=args.neo4j_username,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.neo4j_database,
            openai_model=args.openai_model,
        )
        run_id = make_run_id("structured_lint")
        lint_result = lint_and_clean_structured_csvs(run_id=run_id, output_dir=config.output_dir)
        print(f"Structured lint report written to: {lint_result['lint_report_path']}")
        return
    config_commands = {"ingest", "ingest-structured", "ingest-pdf", "extract-claims", "resolve-entities", "ask"}
    if args.command in config_commands:
        config = _build_config_from_args(args)
        if args.command == "ingest":
            manifest_path = run_demo(config)
            print(f"Demo manifest written to: {manifest_path}")
        elif args.command == "ask" and getattr(args, "interactive", False):
            # Interactive mode: start a REPL session; no manifest is written.
            if config.dry_run:
                raise SystemExit(
                    "Interactive 'ask' is not supported in dry-run mode. "
                    "Re-run the command with --live to enable live Neo4j/OpenAI calls."
                )
            env_run_id = os.getenv("UNSTRUCTURED_RUN_ID")
            if not env_run_id:
                raise SystemExit(
                    "UNSTRUCTURED_RUN_ID is not set. When running 'ask' interactively, "
                    "set this to the run_id from a prior 'ingest' or 'ingest-pdf' command."
                )
            run_interactive_qa(
                config,
                run_id=env_run_id,
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
                index_name=CHUNK_EMBEDDING_INDEX_NAME,
            )
        else:
            manifest_path = _run_independent_stage(config, args.command)
            print(f"Independent run manifest written to: {manifest_path}")
        return
    if args.command == "reset":
        if not getattr(args, "confirm", False):
            print(
                "To reset the demo graph, run:\n"
                "  python demo/reset_demo_db.py --confirm\n"
                "Or pass --confirm to this command:\n"
                "  python demo/run_demo.py --live reset --confirm\n"
                "See demo/reset_demo_db.py for full usage."
            )
            return
        if getattr(args, "dry_run", True):
            raise SystemExit(
                "reset --confirm requires --live; re-run with:\n"
                "  python demo/run_demo.py --live reset --confirm"
            )
        if not args.neo4j_password or args.neo4j_password == "CHANGE_ME_BEFORE_USE":
            raise SystemExit(
                "Set NEO4J_PASSWORD or pass --neo4j-password when running reset --confirm"
            )
        import neo4j as _neo4j
        from demo.reset_demo_db import run_reset

        driver = _neo4j.GraphDatabase.driver(
            args.neo4j_uri, auth=(args.neo4j_username, args.neo4j_password)
        )
        with driver:
            report = run_reset(
                driver=driver,
                database=args.neo4j_database,
                output_dir=args.output_dir,
            )
        print(
            f"Demo graph reset complete: "
            f"database={report['target_database']} "
            f"nodes_deleted={report['deleted_nodes']} "
            f"relationships_deleted={report['deleted_relationships']} "
            f"indexes_dropped={report['indexes_dropped']}"
        )
        if report.get("warnings"):
            for w in report["warnings"]:
                print(f"  warning: {w}")
        if report.get("report_path"):
            print(f"Reset report written to: {report['report_path']}")
        return
    print(f"Stub: '{args.command}' command scaffold is ready.")


if __name__ == "__main__":
    main()
