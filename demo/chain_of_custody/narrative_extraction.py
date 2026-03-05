from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

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


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > 1:
        return None
    return numeric


def _fallback_identifier(chunk_ids: list[str]) -> str:
    if not chunk_ids:
        raise ValueError("Cannot build fallback identifier without chunk ids")
    if len(chunk_ids) == 1:
        return chunk_ids[0]
    if len(chunk_ids) == 2:
        return f"{chunk_ids[0]}_and_{chunk_ids[1]}"
    return f"{chunk_ids[0]}_and_{len(chunk_ids) - 1}_more"


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


def _chunk_id_from_node_id(
    node_id: str, node_chunk_map: dict[str, list[str]], *, relationship_type: str
) -> list[str]:
    if node_id in node_chunk_map:
        return node_chunk_map[node_id]
    raise ValueError(
        f"Unable to resolve chunk id(s) for node id {node_id!r}; no {relationship_type!r} "
        "relationships connect it to known chunks."
    )


def prepare_extracted_rows(
    *,
    graph: Neo4jGraph,
    text_chunks: list[TextChunk],
    run_id: str,
    source_uri: str | None,
    extractor_model: str,
    extracted_at: str,
    prompt_version: str,
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    chunk_meta: dict[str, dict[str, Any]] = {}
    for chunk in text_chunks:
        metadata = dict(chunk.metadata or {})
        metadata.setdefault("run_id", run_id)
        if getattr(chunk, "index", None) is not None:
            metadata.setdefault(lexical_graph_config.chunk_index_property, chunk.index)
        chunk_meta[chunk.uid] = metadata

    node_chunk_map: dict[str, list[str]] = {}
    node_chunk_relationship = lexical_graph_config.node_to_chunk_relationship_type
    for relationship in graph.relationships:
        if relationship.type != node_chunk_relationship:
            continue
        source_is_chunk = relationship.start_node_id in chunk_meta
        target_is_chunk = relationship.end_node_id in chunk_meta
        if not source_is_chunk and not target_is_chunk:
            continue
        if source_is_chunk and target_is_chunk:
            continue
        chunk_id = relationship.start_node_id if source_is_chunk else relationship.end_node_id
        node_id = relationship.end_node_id if source_is_chunk else relationship.start_node_id
        node_chunk_map.setdefault(node_id, []).append(chunk_id)

    claim_rows: list[dict[str, Any]] = []
    mention_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for node in graph.nodes:
        if node.label == lexical_graph_config.chunk_node_label:
            continue

        if node.label not in {"ExtractedClaim", "EntityMention"}:
            warnings.append(f"Skipping unsupported node label {node.label!r} for node {node.id!r}")
            continue

        node_chunk_ids = _chunk_id_from_node_id(
            node.id, node_chunk_map, relationship_type=node_chunk_relationship
        )
        seen: set[str] = set()
        chunk_ids: list[str] = []
        for cid in node_chunk_ids:
            if cid in seen:
                continue
            seen.add(cid)
            chunk_ids.append(cid)

        metadata_by_chunk = [chunk_meta[cid] for cid in chunk_ids if cid in chunk_meta]
        base_props = {
            "run_id": run_id,
            "source_uri": source_uri,
            "extractor_model": extractor_model,
            "extracted_at": extracted_at,
            "prompt_version": prompt_version,
            "chunk_ids": chunk_ids,
            "confidence": _coerce_confidence(node.properties.get("confidence")),
        }
        page_numbers = [meta.get("page_number") or meta.get("page") for meta in metadata_by_chunk]
        page_numbers = [p for p in page_numbers if p is not None]
        if page_numbers:
            unique_pages = sorted(set(page_numbers))
            base_props["page"] = unique_pages[0]
            if len(unique_pages) > 1:
                base_props["pages"] = unique_pages

        if node.label == "ExtractedClaim":
            claim_text = (
                str(
                    node.properties.get("claim_text")
                    or node.properties.get("text")
                    or node.properties.get("name")
                    or ""
                ).strip()
            )
            fallback_identifier = _fallback_identifier(chunk_ids)
            properties = dict(base_props)
            properties["claim_text"] = claim_text or f"claim_for_{fallback_identifier}"
            for key in ("subject", "predicate", "object", "value", "claim_type"):
                if key in node.properties:
                    properties[key] = node.properties[key]
            claim_rows.append(
                {
                    "claim_id": node.id,
                    "chunk_id": chunk_ids[0],
                    "chunk_ids": chunk_ids,
                    "run_id": run_id,
                    "source_uri": source_uri,
                    "properties": properties,
                }
            )
            continue

        if node.label == "EntityMention":
            name = str(node.properties.get("name") or "").strip()
            fallback_identifier = _fallback_identifier(chunk_ids)
            properties = dict(base_props)
            properties["name"] = name or f"mention_for_{fallback_identifier}"
            if "entity_type" in node.properties:
                properties["entity_type"] = node.properties["entity_type"]
            mention_rows.append(
                {
                    "mention_id": node.id,
                    "chunk_id": chunk_ids[0],
                    "chunk_ids": chunk_ids,
                    "run_id": run_id,
                    "source_uri": source_uri,
                    "properties": properties,
                }
            )

    return claim_rows, mention_rows, warnings


def _validate_identifier(value: str, kind: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {kind}: expected string, got {type(value).__name__}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind}: {value!r}")
    return value


def _write_extracted_rows(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> None:
    chunk_label = _validate_identifier(lexical_graph_config.chunk_node_label, "chunk label")
    chunk_id_property = _validate_identifier(lexical_graph_config.chunk_id_property, "chunk_id property")
    if claim_rows:
        driver.execute_query(
            f"""
            UNWIND $rows AS row
            MERGE (claim:ExtractedClaim {{claim_id: row.claim_id, run_id: row.run_id}})
            SET claim += row.properties
            WITH row, claim
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (claim)-[supported_by:SUPPORTED_BY]->(chunk)
            SET supported_by.run_id = row.run_id,
                supported_by.source_uri = row.source_uri,
                supported_by.extracted_at = row.properties.extracted_at,
                supported_by.prompt_version = row.properties.prompt_version,
                supported_by.chunk_id = chunk_id
            """,
            parameters_={"rows": claim_rows},
            database_=neo4j_database,
        )
    if mention_rows:
        driver.execute_query(
            f"""
            UNWIND $rows AS row
            MERGE (mention:EntityMention {{mention_id: row.mention_id, run_id: row.run_id}})
            SET mention += row.properties
            WITH row, mention
            UNWIND row.chunk_ids AS chunk_id
            MATCH (chunk:`{chunk_label}` {{{chunk_id_property}: chunk_id, run_id: row.run_id}})
            MERGE (mention)-[mentioned_in:MENTIONED_IN]->(chunk)
            SET mentioned_in.run_id = row.run_id,
                mentioned_in.source_uri = row.source_uri,
                mentioned_in.extracted_at = row.properties.extracted_at,
                mentioned_in.prompt_version = row.properties.prompt_version,
                mentioned_in.chunk_id = chunk_id
            """,
            parameters_={"rows": mention_rows},
            database_=neo4j_database,
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

    if not config.dry_run and config.neo4j_password in ("", DEFAULT_NEO4J_PASSWORD):
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
