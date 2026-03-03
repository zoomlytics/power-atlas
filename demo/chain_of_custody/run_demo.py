from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"
DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")
CHUNK_EMBEDDING_INDEX_NAME = "chain_custody_chunk_embedding_index"
CHUNK_EMBEDDING_LABEL = "Chunk"
CHUNK_EMBEDDING_PROPERTY = "embedding"
CHUNK_EMBEDDING_DIMENSIONS = 1536


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


def _run_pdf_ingest(config: DemoConfig, run_id: str | None = None) -> dict[str, Any]:
    pdf_path = FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")
    pdf_source_uri = str(pdf_path)
    stage_run_id = run_id or _make_run_id("unstructured_ingest")

    if config.dry_run:
        return {
            "status": "dry_run",
            "documents": [pdf_source_uri],
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + FixedSizeSplitter",
            "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
            "vector_index": {
                "index_name": CHUNK_EMBEDDING_INDEX_NAME,
                "label": CHUNK_EMBEDDING_LABEL,
                "embedding_property": CHUNK_EMBEDDING_PROPERTY,
                "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            },
        }

    import neo4j
    from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner
    from neo4j_graphrag.indexes import create_vector_index

    os.environ["NEO4J_URI"] = config.neo4j_uri
    os.environ["NEO4J_USERNAME"] = config.neo4j_username
    os.environ["NEO4J_PASSWORD"] = config.neo4j_password
    os.environ["NEO4J_DATABASE"] = config.neo4j_database
    os.environ["OPENAI_MODEL"] = config.openai_model

    driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
    with driver:
        try:
            create_vector_index(
                driver,
                CHUNK_EMBEDDING_INDEX_NAME,
                label=CHUNK_EMBEDDING_LABEL,
                embedding_property=CHUNK_EMBEDDING_PROPERTY,
                dimensions=CHUNK_EMBEDDING_DIMENSIONS,
            )
        except Exception:
            with driver.session(database=config.neo4j_database) as session:
                session.run(
                    f"""
                    CREATE VECTOR INDEX `{CHUNK_EMBEDDING_INDEX_NAME}` IF NOT EXISTS
                    FOR (n:{CHUNK_EMBEDDING_LABEL}) ON (n.{CHUNK_EMBEDDING_PROPERTY})
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: $dimensions,
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """,
                    dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                ).consume()

        pipeline = PipelineRunner.from_config_file(PDF_PIPELINE_CONFIG_PATH)
        pipeline_result = asyncio.run(
            pipeline.run(
                {
                    "file_path": pdf_source_uri,
                    "document_metadata": {
                        "run_id": stage_run_id,
                        "source_uri": pdf_source_uri,
                    },
                }
            )
        )

        with driver.session(database=config.neo4j_database) as session:
            session.run(
                """
                MATCH (d:Document)
                WHERE d.path = $source_uri OR d.source_uri = $source_uri
                SET d.run_id = coalesce(d.run_id, $run_id),
                    d.source_uri = coalesce(d.source_uri, $source_uri)
                WITH d
                MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                WITH d, c ORDER BY coalesce(c.index, c.chunk_index, id(c))
                WITH d, collect(c) AS chunks
                UNWIND range(0, size(chunks) - 1) AS chunk_order
                WITH d, chunks[chunk_order] AS c, chunk_order
                SET c.run_id = coalesce(c.run_id, $run_id),
                    c.source_uri = coalesce(c.source_uri, d.source_uri, $source_uri),
                    c.chunk_order = coalesce(c.chunk_order, chunk_order),
                    c.chunk_id = coalesce(c.chunk_id, c.uid, d.source_uri + ':' + toString(chunk_order)),
                    c.page_number = coalesce(c.page_number, c.page),
                    c.embedding = coalesce(c.embedding, c.embedding_vector, c.vector, c.embeddings)
                """,
                run_id=stage_run_id,
                source_uri=pdf_source_uri,
            ).consume()

    return {
        "status": "live",
        "documents": [pdf_source_uri],
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        "vector_index": {
            "index_name": CHUNK_EMBEDDING_INDEX_NAME,
            "label": CHUNK_EMBEDDING_LABEL,
            "embedding_property": CHUNK_EMBEDDING_PROPERTY,
            "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
        },
        "pipeline_result": str(pipeline_result),
        "provenance": {
            "run_id": stage_run_id,
            "source_uri": pdf_source_uri,
            "chunk_order_property": "chunk_order",
            "chunk_id_property": "chunk_id",
            "page_property": "page_number",
        },
    }


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
                **_run_structured_ingest(config),
                "run_id": structured_run_id,
            },
            "pdf_ingest": {
                **_run_pdf_ingest(config, unstructured_run_id),
                "run_id": unstructured_run_id,
            },
            "claim_and_mention_extraction": {
                **_run_claim_and_mention_extraction(config),
                "run_id": resolution_run_id,
            },
            "retrieval_and_qa": {
                **_run_retrieval_and_qa(config),
                "run_id": resolution_run_id,
            },
        },
    }

    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def run_independent_demo(config: DemoConfig, command: str) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stage_runners: dict[str, tuple[str, str, Callable[[DemoConfig], dict[str, Any]]]] = {
        "ingest-structured": ("structured_ingest", "structured_ingest_run_id", _run_structured_ingest),
        "ingest-pdf": ("pdf_ingest", "unstructured_ingest_run_id", _run_pdf_ingest),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    stage_run_id = _make_run_id(run_scope)
    stage_output = (
        _run_pdf_ingest(config, stage_run_id)
        if command == "ingest-pdf"
        else stage_runner(config)
    )
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
                **stage_output,
                "run_id": stage_run_id,
            }
        },
    }
    manifest_path = config.output_dir / f"{stage_name}_{stage_run_id}_manifest.json"
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
        elif args.command in {"ingest-structured", "ingest-pdf"}:
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
