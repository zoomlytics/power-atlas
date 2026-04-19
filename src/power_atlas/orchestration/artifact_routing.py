from __future__ import annotations

from pathlib import Path
from typing import Any

from power_atlas.contracts import write_manifest, write_manifest_md


def compute_stage_manifest_path(output_dir: Path, *, run_id: str, stage_name: str) -> Path:
    return output_dir / "runs" / run_id / stage_name / "manifest.json"


def compute_batch_manifest_path(output_dir: Path) -> Path:
    return output_dir / "manifest.json"


def write_stage_manifest_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    stage_name: str,
    manifest: dict[str, Any],
) -> Path:
    manifest_path = compute_stage_manifest_path(output_dir, run_id=run_id, stage_name=stage_name)
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def write_batch_manifest_artifacts(output_dir: Path, *, manifest: dict[str, Any]) -> Path:
    manifest_path = compute_batch_manifest_path(output_dir)
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


__all__ = [
    "compute_batch_manifest_path",
    "compute_stage_manifest_path",
    "write_batch_manifest_artifacts",
    "write_stage_manifest_artifacts",
]