from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"
DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")

# Default values for the chunk embedding index contract.
# These are used as fallbacks if the YAML configuration does not provide them.
_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME = "chain_custody_chunk_embedding_index"
_DEFAULT_CHUNK_EMBEDDING_LABEL = "Chunk"
_DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS = 1536

# Load the vector index contract from the pipeline config (if available) to avoid
# drifting from the configuration defined under `demo_contract` in
# pdf_simple_kg_pipeline.yaml.
_demo_contract: dict[str, Any] = {}
if PDF_PIPELINE_CONFIG_PATH.is_file():
    try:
        with PDF_PIPELINE_CONFIG_PATH.open("r", encoding="utf-8") as _cfg_handle:
            _cfg_data = yaml.safe_load(_cfg_handle) or {}
        _demo_contract = _cfg_data.get("demo_contract") or {}
    except (OSError, yaml.YAMLError) as exc:
        warnings.warn(
            f"Falling back to default chunk embedding contract; unable to load "
            f"{PDF_PIPELINE_CONFIG_PATH}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        # If the config cannot be read or parsed, fall back to the defaults.
        _demo_contract = {}

# The chunk embedding index contract lives under `demo_contract.chunk_embedding`
# in pdf_simple_kg_pipeline.yaml. Use that if present; otherwise, fall back to
# the hard-coded defaults above.
_chunk_embedding_contract: dict[str, Any] = _demo_contract.get("chunk_embedding") or {}

CHUNK_EMBEDDING_INDEX_NAME = _chunk_embedding_contract.get(
    "index_name", _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
)
CHUNK_EMBEDDING_LABEL = _chunk_embedding_contract.get(
    "label", _DEFAULT_CHUNK_EMBEDDING_LABEL
)
CHUNK_EMBEDDING_PROPERTY = _chunk_embedding_contract.get(
    "embedding_property", _DEFAULT_CHUNK_EMBEDDING_PROPERTY
)
CHUNK_EMBEDDING_DIMENSIONS = _chunk_embedding_contract.get(
    "dimensions", _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
)
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


def _validate_cypher_identifier(value: str, kind: str) -> None:
    """Allow only Cypher-safe identifiers ([A-Za-z_][A-Za-z0-9_]*) for fallback interpolation."""
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {kind} for Cypher fallback: expected a string, got "
            f"{value!r} (type {type(value).__name__})"
        )
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind} for Cypher fallback: {value!r}")


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

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY when using --live ingest-pdf")

    import neo4j
    from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner
    from neo4j_graphrag.indexes import create_vector_index

    env_updates = {
        "NEO4J_URI": config.neo4j_uri,
        "NEO4J_USERNAME": config.neo4j_username,
        "NEO4J_PASSWORD": config.neo4j_password,
        "NEO4J_DATABASE": config.neo4j_database,
        "OPENAI_MODEL": config.openai_model,
    }
    previous_env = {key: (key in os.environ, os.environ.get(key)) for key in env_updates}
    os.environ.update(env_updates)

    try:
        driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver:
            index_creation_strategy = "neo4j_graphrag.indexes.create_vector_index"
            index_fallback_reason: str | None = None
            try:
                create_vector_index(
                    driver,
                    CHUNK_EMBEDDING_INDEX_NAME,
                    label=CHUNK_EMBEDDING_LABEL,
                    embedding_property=CHUNK_EMBEDDING_PROPERTY,
                    dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                    similarity_fn="cosine",
                    database_=config.neo4j_database,
                )
            except Exception as exc:
                index_creation_strategy = "cypher_fallback"
                exc_message = str(exc).splitlines()[0].strip()
                index_fallback_reason = (
                    f"{type(exc).__name__}: {exc_message}" if exc_message else type(exc).__name__
                )
                _validate_cypher_identifier(CHUNK_EMBEDDING_INDEX_NAME, "index name")
                _validate_cypher_identifier(CHUNK_EMBEDDING_LABEL, "label")
                _validate_cypher_identifier(CHUNK_EMBEDDING_PROPERTY, "property")
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
                    }
                )
            )

            with driver.session(database=config.neo4j_database) as session:
                # Vendor versions can emit Chunk ordering/embedding fields as
                # index/chunk_index and embedding/embedding_vector/vector/embeddings.
                # Normalize them into the demo retrieval contract:
                # Chunk.chunk_order + Chunk.embedding on every ingested Chunk.
                session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND (d.run_id IS NULL OR d.run_id = $run_id)
                    SET d.run_id = coalesce(d.run_id, $run_id),
                        d.source_uri = coalesce(d.source_uri, $source_uri)
                    WITH d
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id IS NULL OR c.run_id = $run_id
                    WITH d, c,
                         toInteger(coalesce(c.chunk_order, c.index, c.chunk_index)) AS normalized_chunk_order
                    SET c.run_id = coalesce(c.run_id, $run_id),
                        c.source_uri = coalesce(c.source_uri, d.source_uri, $source_uri),
                        c.chunk_order = normalized_chunk_order,
                        c.chunk_id = coalesce(
                            c.chunk_id,
                            c.uid,
                            d.source_uri + ':' + toString(normalized_chunk_order)
                        ),
                        c.page_number = coalesce(c.page_number, c.page),
                        c.embedding = coalesce(c.embedding, c.embedding_vector, c.vector, c.embeddings)
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).consume()
                run_counts = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                    RETURN count(DISTINCT d) AS document_count, count(c) AS chunk_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single()
                if run_counts["document_count"] == 0 or run_counts["chunk_count"] == 0:
                    raise ValueError(
                        "Ingest contract violation: expected at least one Document and Chunk for this run"
                    )
                missing_chunk_order_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.chunk_order IS NULL
                    RETURN count(c) AS missing_chunk_order_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single()["missing_chunk_order_count"]
                if missing_chunk_order_count:
                    raise ValueError(
                        "Chunk ordering contract violation: expected stable chunk index on all ingested chunks"
                    )
                missing_embedding_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.embedding IS NULL
                    RETURN count(c) AS missing_embedding_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single()["missing_embedding_count"]
                if missing_embedding_count:
                    raise ValueError(
                        "Chunk embedding contract violation: expected :Chunk.embedding for all ingested chunks"
                    )
    finally:
        for key, (had_key, previous_value) in previous_env.items():
            if not had_key:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value

    return {
        "status": "live",
        "documents": [pdf_source_uri],
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        "vector_index": {
            "index_name": CHUNK_EMBEDDING_INDEX_NAME,
            "label": CHUNK_EMBEDDING_LABEL,
            "embedding_property": CHUNK_EMBEDDING_PROPERTY,
            "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            "creation_strategy": index_creation_strategy,
        },
        "pipeline_result": str(pipeline_result),
        "provenance": {
            "run_id": stage_run_id,
            "source_uri": pdf_source_uri,
            "chunk_order_property": "chunk_order",
            "chunk_id_property": "chunk_id",
            "page_property": "page_number",
        },
        **({"vector_index_fallback_reason": index_fallback_reason} if index_fallback_reason else {}),
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
    stage_runners: dict[str, tuple[str, str, Callable[[DemoConfig, str], dict[str, Any]]]] = {
        "ingest-structured": (
            "structured_ingest",
            "structured_ingest_run_id",
            lambda cfg, _stage_run_id: _run_structured_ingest(cfg),
        ),
        "ingest-pdf": ("pdf_ingest", "unstructured_ingest_run_id", _run_pdf_ingest),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    stage_run_id = _make_run_id(run_scope)
    stage_output = stage_runner(config, stage_run_id)
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
