from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demo.contracts.runtime import make_run_id


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
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    stages: dict[str, Any] = {
        "structured_ingest": {**structured_stage, "run_id": structured_run_id},
        "pdf_ingest": {**pdf_stage, "run_id": unstructured_run_id},
        "claim_and_mention_extraction": {**claim_stage, "run_id": unstructured_run_id},
        "retrieval_and_qa": {**retrieval_stage, "run_id": unstructured_run_id},
    }
    if entity_resolution_stage is not None:
        stages["entity_resolution"] = {**entity_resolution_stage, "run_id": unstructured_run_id}

    # Surface per-answer citation completeness and warning status at the batch level so
    # consumers can assess QA quality without inspecting stage-level details.
    _cq = retrieval_stage.get("citation_quality")
    retrieval_citation_quality: dict[str, Any] = _cq if isinstance(_cq, dict) else {}

    # Derive warnings from citation_quality so the warning list and count stay consistent.
    _citation_warnings = retrieval_citation_quality.get("citation_warnings", [])
    citation_warnings = _citation_warnings if isinstance(_citation_warnings, list) else []

    qa_signals: dict[str, Any] = {
        "all_answers_cited": retrieval_stage.get("all_answers_cited", False),
        "evidence_level": retrieval_citation_quality.get("evidence_level", "no_answer"),
        "warning_count": len(citation_warnings),
        "warnings": citation_warnings,
    }

    now = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "run_id": make_run_id("batch"),
        "created_at": now,
        "started_at": started_at or now,
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
        "qa_signals": qa_signals,
        "stages": stages,
    }
    if finished_at is not None:
        manifest["finished_at"] = finished_at
    return manifest


def build_stage_manifest(
    *,
    config: Any,
    stage_name: str,
    stage_run_id: str,
    run_scope_key: str,
    stage_output: dict[str, Any],
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "run_id": stage_run_id,
        "created_at": now,
        "started_at": started_at or now,
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
    if finished_at is not None:
        manifest["finished_at"] = finished_at
    return manifest


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    """Write *manifest* to *manifest_path* atomically using a temp-file + rename pattern.

    Writing to a temp file in the same directory and then renaming avoids leaving
    a partially written manifest if the process is interrupted mid-write.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, indent=2, sort_keys=True)
    tmp_path = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=manifest_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        # Adjust permissions of the temporary file so the final manifest
        # does not unexpectedly inherit mkstemp's restrictive default (0o600).
        if manifest_path.exists():
            # Preserve permissions from the existing manifest, if any.
            target_mode = manifest_path.stat().st_mode & 0o777
        else:
            # Derive default file mode from the current umask.
            current_umask = os.umask(0)
            os.umask(current_umask)
            target_mode = 0o666 & ~current_umask
        os.fchmod(fd, target_mode)
        os.close(fd)
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(manifest_path)
        tmp_path = None  # rename succeeded; nothing to clean up
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    return manifest_path


def _manifest_md_summary(manifest: dict[str, Any]) -> str:
    """Return a lightweight human-readable Markdown summary of *manifest*."""
    lines: list[str] = ["# Run Manifest Summary", ""]

    run_id = manifest.get("run_id", "unknown")
    started = manifest.get("started_at") or manifest.get("created_at", "")
    finished = manifest.get("finished_at", "")
    lines.append(f"**Run ID:** `{run_id}`  ")
    if started:
        lines.append(f"**Started:** {started}  ")
    if finished:
        lines.append(f"**Finished:** {finished}  ")
    lines.append("")

    cfg = manifest.get("config", {})
    if cfg:
        lines.append("## Configuration")
        lines.append("")
        dry_run = cfg.get("dry_run", False)
        lines.append(f"- **Mode:** {'dry-run' if dry_run else 'live'}")
        db = cfg.get("neo4j_database")
        if db:
            lines.append(f"- **Neo4j database:** {db}")
        model = cfg.get("openai_model")
        if model:
            lines.append(f"- **OpenAI model:** {model}")
        lines.append("")

    run_scopes = manifest.get("run_scopes", {})
    if run_scopes:
        lines.append("## Run Scopes")
        lines.append("")
        for key, value in run_scopes.items():
            lines.append(f"- **{key}:** `{value}`")
        lines.append("")

    stages = manifest.get("stages", {})
    if stages:
        lines.append("## Stages")
        lines.append("")
        for stage_name, stage_data in stages.items():
            if not isinstance(stage_data, dict):
                continue
            lines.append(f"### {stage_name}")
            stage_run_id = stage_data.get("run_id", "")
            if stage_run_id:
                lines.append(f"- **run_id:** `{stage_run_id}`")
            status = stage_data.get("status", "")
            if status:
                lines.append(f"- **status:** {status}")
            # Surface key numeric counts when present
            counts = stage_data.get("counts")
            if isinstance(counts, dict):
                count_parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                lines.append(f"- **counts:** {count_parts}")
            else:
                for count_key in ("claims", "entities", "relationships", "facts", "chunks"):
                    val = stage_data.get(count_key)
                    if val is not None:
                        lines.append(f"- **{count_key}:** {val}")
            lines.append("")

    qa_signals = manifest.get("qa_signals", {})
    if qa_signals:
        lines.append("## QA Signals")
        lines.append("")
        evidence = qa_signals.get("evidence_level", "")
        if evidence:
            lines.append(f"- **evidence_level:** {evidence}")
        all_cited = qa_signals.get("all_answers_cited")
        if all_cited is not None:
            lines.append(f"- **all_answers_cited:** {all_cited}")
        warn_count = qa_signals.get("warning_count", 0)
        lines.append(f"- **warning_count:** {warn_count}")
        lines.append("")

    return "\n".join(lines)


def write_manifest_md(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    """Write a human-readable Markdown summary alongside the JSON manifest.

    The Markdown file uses the same stem as *manifest_path* with a ``.md`` suffix.
    Returns the path to the written ``.md`` file.
    """
    md_path = manifest_path.with_suffix(".md")
    content = _manifest_md_summary(manifest)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=md_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        os.close(fd)
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(md_path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    return md_path


__all__ = [
    "build_batch_manifest",
    "build_stage_manifest",
    "write_manifest",
    "write_manifest_md",
]
