from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demo.chain_of_custody.contracts.runtime import make_run_id


def build_batch_manifest(
    *,
    config: Any,
    structured_run_id: str,
    unstructured_run_id: str,
    resolution_run_id: str,
    structured_stage: dict[str, Any],
    pdf_stage: dict[str, Any],
    claim_stage: dict[str, Any],
    retrieval_stage: dict[str, Any],
    entity_resolution_stage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stages: dict[str, Any] = {
        "structured_ingest": {**structured_stage, "run_id": structured_run_id},
        "pdf_ingest": {**pdf_stage, "run_id": unstructured_run_id},
        "claim_and_mention_extraction": {**claim_stage, "run_id": unstructured_run_id},
        "retrieval_and_qa": {**retrieval_stage, "run_id": resolution_run_id},
    }
    if entity_resolution_stage is not None:
        stages["entity_resolution"] = {**entity_resolution_stage, "run_id": resolution_run_id}
    return {
        "run_id": make_run_id("chain_of_custody_batch"),
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "sequential_independent_runs",
            "structured_ingest_run_id": structured_run_id,
            "unstructured_ingest_run_id": unstructured_run_id,
            "resolution_run_id": resolution_run_id,
        },
        "config": {
            "dry_run": getattr(config, "dry_run", False),
            "neo4j_database": getattr(config, "neo4j_database", None),
            "openai_model": getattr(config, "openai_model", None),
        },
        "stages": stages,
    }


def build_stage_manifest(
    *,
    config: Any,
    stage_name: str,
    stage_run_id: str,
    run_scope_key: str,
    stage_output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": stage_run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "single_independent_run",
            run_scope_key: stage_run_id,
        },
        "config": {
            "dry_run": getattr(config, "dry_run", False),
            "neo4j_database": getattr(config, "neo4j_database", None),
            "openai_model": getattr(config, "openai_model", None),
        },
        "stages": {
            stage_name: {**stage_output, "run_id": stage_run_id},
        },
    }


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


__all__ = ["build_batch_manifest", "build_stage_manifest", "write_manifest"]
