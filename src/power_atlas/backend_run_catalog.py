from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from power_atlas.settings import AppSettings


@dataclass(frozen=True, slots=True)
class RunCatalogEntry:
    run_id: str
    dataset_id: str | None
    started_at: str | None
    finished_at: str | None
    stage_names: list[str]
    root_path: str


@dataclass(frozen=True, slots=True)
class RunCatalogResult:
    output_dir: str
    runs_root: str
    runs: list[RunCatalogEntry]
    detail: str | None = None


def _read_manifest(manifest_path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _build_run_entry(run_dir: Path) -> RunCatalogEntry:
    stage_dirs = sorted(
        child for child in run_dir.iterdir() if child.is_dir() and not child.name.startswith(".")
    )
    manifest_data: dict[str, Any] | None = None
    for stage_dir in stage_dirs:
        manifest_path = stage_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest_data = _read_manifest(manifest_path)
        if manifest_data is not None:
            break

    return RunCatalogEntry(
        run_id=run_dir.name,
        dataset_id=(None if manifest_data is None else manifest_data.get("dataset_id")),
        started_at=(None if manifest_data is None else manifest_data.get("started_at")),
        finished_at=(None if manifest_data is None else manifest_data.get("finished_at")),
        stage_names=[stage_dir.name for stage_dir in stage_dirs],
        root_path=str(run_dir),
    )


def resolve_backend_run_catalog(settings: AppSettings) -> RunCatalogResult:
    output_dir = settings.output_dir.resolve()
    runs_root = (output_dir / "runs").resolve()

    if not runs_root.is_dir():
        return RunCatalogResult(
            output_dir=str(output_dir),
            runs_root=str(runs_root),
            runs=[],
            detail="No run directories were found under the configured output directory.",
        )

    run_dirs = sorted(
        (child for child in runs_root.iterdir() if child.is_dir() and not child.name.startswith(".")),
        key=lambda child: child.name,
        reverse=True,
    )
    return RunCatalogResult(
        output_dir=str(output_dir),
        runs_root=str(runs_root),
        runs=[_build_run_entry(run_dir) for run_dir in run_dirs],
    )


__all__ = [
    "RunCatalogEntry",
    "RunCatalogResult",
    "resolve_backend_run_catalog",
]