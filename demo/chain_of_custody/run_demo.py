from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")


@dataclass(frozen=True)
class DemoConfig:
    dry_run: bool
    output_dir: Path
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    openai_model: str


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _make_run_id(scope: str) -> str:
    return f"{scope}-{_timestamp()}-{uuid4().hex[:8]}"


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _run_structured_ingest(config: DemoConfig) -> dict[str, Any]:
    claims_path = FIXTURES_DIR / "structured" / "claims.csv"
    entities_path = FIXTURES_DIR / "structured" / "entities.csv"
    relationships_path = FIXTURES_DIR / "structured" / "relationships.csv"

    if config.dry_run:
        return {
            "status": "dry_run",
            "claims": len(_load_csv_rows(claims_path)),
            "entities": len(_load_csv_rows(entities_path)),
            "relationships": len(_load_csv_rows(relationships_path)),
        }
    raise NotImplementedError(
        "Non-dry-run structured ingest is not yet implemented for the current "
        "fixtures/structured CSV schema. Run with --dry-run for now."
    )


def _run_pdf_ingest(config: DemoConfig) -> dict[str, Any]:
    pdf_path = FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")

    if config.dry_run:
        return {
            "status": "dry_run",
            "documents": [str(pdf_path)],
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + FixedSizeSplitter",
        }

    raise NotImplementedError(
        "Non-dry-run PDF ingest is not implemented. "
        "Run this demo with --dry-run until the vendor SimpleKGPipeline wiring is added."
    )


def _run_claim_and_mention_extraction(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "claim_extraction": "planned",
            "mention_resolution": "deterministic by canonical entity_id",
        }
    return {
        "status": "configured",
        "claim_extraction": "LLMEntityRelationExtractor",
        "mention_resolution": "SinglePropertyExactMatchResolver",
    }


def _run_retrieval_and_qa(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
        }
    return {
        "status": "configured",
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
    }


def run_demo(config: DemoConfig) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    structured_run_id = _make_run_id("structured_ingest")
    unstructured_run_id = _make_run_id("unstructured_ingest")
    resolution_run_id = _make_run_id("resolution")

    manifest = {
        "run_id": _make_run_id("chain_of_custody_batch"),
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "sequential_independent_runs",
            "structured_ingest_run_id": structured_run_id,
            "unstructured_ingest_run_id": unstructured_run_id,
            "resolution_run_id": resolution_run_id,
        },
        "config": {
            "dry_run": config.dry_run,
            "neo4j_database": config.neo4j_database,
            "openai_model": config.openai_model,
        },
        "stages": {
            "structured_ingest": {
                "run_id": structured_run_id,
                **_run_structured_ingest(config),
            },
            "pdf_ingest": {
                "run_id": unstructured_run_id,
                **_run_pdf_ingest(config),
            },
            "claim_and_mention_extraction": {
                "run_id": resolution_run_id,
                **_run_claim_and_mention_extraction(config),
            },
            "retrieval_and_qa": {
                "run_id": resolution_run_id,
                **_run_retrieval_and_qa(config),
            },
        },
    }

    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def run_independent_demo(config: DemoConfig, command: str) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stage_runners: dict[str, tuple[str, str, Any]] = {
        "ingest-structured": ("structured_ingest", "structured_ingest_run_id", _run_structured_ingest),
        "ingest-pdf": ("pdf_ingest", "unstructured_ingest_run_id", _run_pdf_ingest),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    stage_run_id = _make_run_id(run_scope)
    manifest = {
        "run_id": stage_run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "single_independent_run",
            run_scope_key: stage_run_id,
        },
        "config": {
            "dry_run": config.dry_run,
            "neo4j_database": config.neo4j_database,
            "openai_model": config.openai_model,
        },
        "stages": {
            stage_name: {
                "run_id": stage_run_id,
                **stage_runner(config),
            }
        },
    }
    manifest_path = config.output_dir / f"{stage_name}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    common_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    _add_common_args(common_parser)
    parser = argparse.ArgumentParser(
        description="Chain of Custody demo orchestrator",
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
    parser.set_defaults(command="ingest")

    # Enforce mutual exclusivity of --dry-run/--live while ignoring cases where
    # those strings are used as *values* to other options that take an argument.
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
            # Skip the value associated with this option, even if it looks like a flag.
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


def main() -> None:
    args = parse_args()
    if args.command in {"ingest", "ingest-structured", "ingest-pdf"}:
        if not args.dry_run and args.neo4j_password in ("", "CHANGE_ME_BEFORE_USE"):
            raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
        config = DemoConfig(
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            neo4j_uri=args.neo4j_uri,
            neo4j_username=args.neo4j_username,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.neo4j_database,
            openai_model=args.openai_model,
        )
    if args.command == "ingest":
        manifest_path = run_demo(config)
        print(f"Demo manifest written to: {manifest_path}")
        return
    if args.command in {"ingest-structured", "ingest-pdf"}:
        manifest_path = run_independent_demo(config, args.command)
        print(f"Independent run manifest written to: {manifest_path}")
        return
    if args.command == "reset":
        print("Stub: use demo/chain_of_custody/reset_demo_db.py --confirm to reset demo data.")
        return
    if args.command == "ask":
        question = args.question or "<question>"
        print(f"Stub: '{args.command}' planned for question: {question}")
        return
    print(f"Stub: '{args.command}' command scaffold is ready.")


if __name__ == "__main__":
    main()
