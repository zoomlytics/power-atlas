from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from demo.chain_of_custody.extraction_utils import (
    chunk_id_from_node_id,
    coerce_confidence,
    fallback_identifier,
    prepare_extracted_rows,
    write_extracted_rows,
)
from demo.chain_of_custody.run_scoped_chunk_reader import RunScopedNeo4jChunkReader
from neo4j_graphrag.experimental.components.entity_relation_extractor import (
    LLMEntityRelationExtractor,
)
from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    NodeType,
    PropertyType,
    RelationshipType,
)
from neo4j_graphrag.experimental.components.types import (
    LexicalGraphConfig,
    Neo4jGraph,
    TextChunk,
    TextChunks,
)
from neo4j_graphrag.llm import OpenAILLM

import neo4j

DEFAULT_CHUNK_LABEL = "Chunk"
DEFAULT_CHUNK_ID_PROPERTY = "chunk_id"
DEFAULT_CHUNK_TEXT_PROPERTY = "text"
DEFAULT_CHUNK_INDEX_PROPERTY = "chunk_index"
DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
DEFAULT_NODE_TO_CHUNK_RELATIONSHIP = "MENTIONED_IN"
PROMPT_VERSION = "narrative_claims_v1"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "runs"
DEFAULT_NEO4J_PASSWORD = "CHANGE_ME_BEFORE_USE"

# Backward-compatible aliases for shared helpers
_write_extracted_rows = write_extracted_rows


@dataclass(frozen=True)
class ExtractionConfig:
    run_id: str
    source_uri: str | None
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    model_name: str
    output_root: Path
    dry_run: bool = False


def build_lexical_config() -> LexicalGraphConfig:
    return LexicalGraphConfig(
        chunk_node_label=DEFAULT_CHUNK_LABEL,
        chunk_id_property=DEFAULT_CHUNK_ID_PROPERTY,
        chunk_index_property=DEFAULT_CHUNK_INDEX_PROPERTY,
        chunk_text_property=DEFAULT_CHUNK_TEXT_PROPERTY,
        chunk_embedding_property=DEFAULT_CHUNK_EMBEDDING_PROPERTY,
        node_to_chunk_relationship_type=DEFAULT_NODE_TO_CHUNK_RELATIONSHIP,
    )


def _extraction_schema() -> GraphSchema:
    return GraphSchema(
        node_types=[
            NodeType(
                label="ExtractedClaim",
                properties=[
                    PropertyType(name="claim_text", type="STRING", required=True),
                    PropertyType(name="subject", type="STRING"),
                    PropertyType(name="predicate", type="STRING"),
                    PropertyType(name="object", type="STRING"),
                    PropertyType(name="value", type="STRING"),
                    PropertyType(name="claim_type", type="STRING"),
                    PropertyType(name="confidence", type="FLOAT"),
                ],
                additional_properties=True,
            ),
            NodeType(
                label="EntityMention",
                properties=[
                    PropertyType(name="name", type="STRING", required=True),
                    PropertyType(name="entity_type", type="STRING"),
                    PropertyType(name="confidence", type="FLOAT"),
                ],
                additional_properties=True,
            ),
        ],
        relationship_types=[
            RelationshipType(label="SUPPORTED_BY"),
            RelationshipType(label="MENTIONED_IN"),
            RelationshipType(label="MENTIONS"),
        ],
    )


async def _read_chunks_and_extract(
    driver: neo4j.Driver,
    *,
    config: ExtractionConfig,
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[Neo4jGraph, list[TextChunk]]:
    chunk_reader = RunScopedNeo4jChunkReader(
        driver,
        run_id=config.run_id,
        source_uri=config.source_uri,
        fetch_embeddings=False,
        neo4j_database=config.neo4j_database,
    )
    text_chunks: TextChunks = await chunk_reader.run(lexical_graph_config=lexical_graph_config)
    llm = OpenAILLM(
        model_name=config.model_name,
        model_params={"temperature": 0},
    )
    extractor = LLMEntityRelationExtractor(
        llm=llm,
        create_lexical_graph=False,
        use_structured_output=True,
    )
    try:
        graph = await extractor.run(
            chunks=text_chunks,
            schema=_extraction_schema(),
            lexical_graph_config=lexical_graph_config,
        )
    finally:
        await llm.async_client.close()
    return graph, text_chunks.chunks


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_warnings(warnings: Iterable[str] | None) -> list[str]:
    if not warnings:
        return []
    return [str(w) for w in warnings if w is not None]


def _update_manifest(manifest_path: Path, run_id: str, stage_payload: dict[str, Any]) -> None:
    manifest: dict[str, Any]
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    else:
        manifest = {}

    manifest.setdefault("run_id", run_id)
    manifest.setdefault("run_scopes", {})["unstructured_ingest_run_id"] = run_id
    manifest.setdefault("stages", {})
    manifest["stages"]["narrative_extraction"] = stage_payload
    manifest.setdefault("created_at", datetime.now(UTC).isoformat())
    _write_json(manifest_path, manifest)


def _build_summary(
    *,
    run_id: str,
    source_uri: str | None,
    model_name: str,
    prompt_version: str,
    extracted_at: str,
    chunk_count: int,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
    warnings: Iterable[str],
) -> dict[str, Any]:
    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {chunk_id for row in all_extracted_rows for chunk_id in row["chunk_ids"]}
    return {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "extractor_model": model_name,
        "prompt_version": prompt_version,
        "extracted_at": extracted_at,
        "chunks_processed": chunk_count,
        "claims": len(claim_rows),
        "mentions": len(mention_rows),
        "chunk_ids": sorted(unique_chunk_ids),
        "warnings": _normalize_warnings(warnings),
    }


def run_narrative_extraction(config: ExtractionConfig) -> dict[str, Any]:
    extracted_at = datetime.now(UTC).isoformat()
    run_root = config.output_root / config.run_id
    extraction_dir = run_root / "narrative_extraction"
    _ensure_dir(extraction_dir)
    summary_path = extraction_dir / "summary.json"
    manifest_path = run_root / "manifest.json"
    lexical_config = build_lexical_config()

    if config.dry_run:
        summary = {
            "status": "dry_run",
            "run_id": config.run_id,
            "source_uri": config.source_uri,
            "extractor_model": config.model_name,
            "prompt_version": PROMPT_VERSION,
            "extracted_at": extracted_at,
            "chunks_processed": 0,
            "claims": 0,
            "mentions": 0,
            "chunk_ids": [],
            "warnings": ["narrative extraction skipped in dry_run mode"],
        }
        _write_json(summary_path, summary)
        _update_manifest(
            manifest_path,
            config.run_id,
            {
                **summary,
                "summary_path": str(summary_path),
                "output_dir": str(extraction_dir),
            },
        )
        return summary

    if config.neo4j_password in ("", DEFAULT_NEO4J_PASSWORD):
        raise ValueError(
            "NEO4J_PASSWORD must be set (not empty and not CHANGE_ME_BEFORE_USE) for live narrative extraction. "
            "Use --neo4j-password or the NEO4J_PASSWORD environment variable."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required for narrative extraction.")

    with neo4j.GraphDatabase.driver(
        config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password)
    ) as driver:
        graph, text_chunks = asyncio.run(
            _read_chunks_and_extract(
                driver,
                config=config,
                lexical_graph_config=lexical_config,
            )
        )
        claim_rows, mention_rows, warnings = prepare_extracted_rows(
            graph=graph,
            text_chunks=text_chunks,
            run_id=config.run_id,
            source_uri=config.source_uri,
            extractor_model=config.model_name,
            extracted_at=extracted_at,
            prompt_version=PROMPT_VERSION,
            lexical_graph_config=lexical_config,
        )
        _write_extracted_rows(
            driver,
            neo4j_database=config.neo4j_database,
            lexical_graph_config=lexical_config,
            claim_rows=claim_rows,
            mention_rows=mention_rows,
        )

    summary = _build_summary(
        run_id=config.run_id,
        source_uri=config.source_uri,
        model_name=config.model_name,
        prompt_version=PROMPT_VERSION,
        extracted_at=extracted_at,
        chunk_count=len(text_chunks),
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        warnings=warnings,
    )
    _write_json(summary_path, summary)
    _update_manifest(
        manifest_path,
        config.run_id,
        {
            **summary,
            "summary_path": str(summary_path),
            "output_dir": str(extraction_dir),
        },
    )
    return summary


def _parse_args() -> ExtractionConfig:
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
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where run artifacts are written (default: demo/chain_of_custody/runs)",
    )
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD))
    parser.add_argument("--neo4j-database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--model-name", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write artifacts without reading chunks or calling the LLM",
    )
    args = parser.parse_args()
    return ExtractionConfig(
        run_id=args.run_id,
        source_uri=args.source_uri,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        model_name=args.model_name,
        output_root=args.output_root,
        dry_run=args.dry_run,
    )


def main() -> None:
    config = _parse_args()
    summary = run_narrative_extraction(config)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
