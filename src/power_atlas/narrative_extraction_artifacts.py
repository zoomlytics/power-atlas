from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from power_atlas.contracts import build_stage_manifest, write_manifest


def normalize_stage_warnings(warnings: Iterable[str] | None) -> list[str]:
    if not warnings:
        return []
    return [str(warning) for warning in warnings if warning is not None]


def build_narrative_extraction_summary(
    *,
    run_id: str,
    source_uri: str | None,
    model_name: str,
    prompt_version: str,
    extracted_at: str,
    chunk_count: int,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
    warnings: Iterable[str] | None,
) -> dict[str, Any]:
    all_extracted_rows = claim_rows + mention_rows
    unique_chunk_ids = {
        chunk_id
        for row in all_extracted_rows
        for chunk_id in row["chunk_ids"]
    }
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
        "warnings": normalize_stage_warnings(warnings),
    }


def write_narrative_extraction_artifacts(
    *,
    summary_path: Path,
    manifest_path: Path,
    config_dry_run: bool,
    neo4j_database: str | None,
    openai_model: str,
    run_id: str,
    stage_payload: dict[str, Any],
) -> None:
    summary_path.write_text(json.dumps(stage_payload, indent=2), encoding="utf-8")
    manifest = build_stage_manifest(
        config=SimpleNamespace(
            dry_run=config_dry_run,
            neo4j_database=neo4j_database,
            openai_model=openai_model,
        ),
        stage_name="narrative_extraction",
        stage_run_id=run_id,
        run_scope_key="unstructured_ingest_run_id",
        stage_output=stage_payload,
    )
    write_manifest(manifest_path, manifest)


__all__ = [
    "build_narrative_extraction_summary",
    "normalize_stage_warnings",
    "write_narrative_extraction_artifacts",
]