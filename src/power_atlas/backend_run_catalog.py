from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from power_atlas.backend_dataset_catalog import resolve_backend_dataset_catalog
from power_atlas.contracts import RepoPaths
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
    inferred_dataset_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunStageDetailEntry:
    stage_name: str
    status: str | None
    manifest_path: str | None
    manifest: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class RunDetailResult:
    output_dir: str
    runs_root: str
    run: RunCatalogEntry
    stages: list[RunStageDetailEntry]
    inferred_dataset_id: str | None = None


def _read_manifest(manifest_path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_runs_root(output_dir: Path) -> Path:
    return (Path(output_dir).resolve() / "runs").resolve()


def resolve_run_root(output_dir: Path, run_id: str) -> Path:
    runs_root = resolve_runs_root(output_dir)
    run_id_path = Path(run_id)
    if (
        not run_id
        or run_id_path.is_absolute()
        or ".." in run_id_path.parts
        or run_id_path.name != run_id
    ):
        raise ValueError(
            f"Invalid run_id {run_id!r}: must be a simple relative name without path separators or '..'."
        )
    run_root = (runs_root / run_id_path).resolve()
    if run_root == runs_root or runs_root not in run_root.parents:
        raise ValueError(
            f"Invalid run_id {run_id!r}: must resolve to a subdirectory of the runs directory."
        )
    return run_root


def _build_run_stage_entry(stage_dir: Path) -> RunStageDetailEntry:
    manifest_path = stage_dir / "manifest.json"
    manifest = _read_manifest(manifest_path) if manifest_path.is_file() else None
    stage_manifest = None if manifest is None else manifest.get("stages", {}).get(stage_dir.name)
    status = stage_manifest.get("status") if isinstance(stage_manifest, dict) else None
    return RunStageDetailEntry(
        stage_name=stage_dir.name,
        status=status if isinstance(status, str) else None,
        manifest_path=(str(manifest_path) if manifest_path.is_file() else None),
        manifest=manifest,
    )


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


def extract_run_stage_prefix(run_id: str) -> str:
    parts = run_id.rsplit("-", 2)
    if len(parts) == 3 and all(parts):
        return parts[0]
    return run_id


def _resolve_effective_current_dataset_id(
    settings: AppSettings,
    dataset_id: str | None,
    *,
    repo_paths: RepoPaths | None = None,
) -> tuple[str | None, str | None]:
    if dataset_id is not None:
        return dataset_id, None
    dataset_catalog = resolve_backend_dataset_catalog(settings, repo_paths=repo_paths)
    if (
        dataset_catalog.selection_mode == "configured"
        and dataset_catalog.selected_dataset is not None
    ):
        return (
            dataset_catalog.selected_dataset.dataset_id,
            dataset_catalog.selected_dataset.dataset_id,
        )
    return None, None


def resolve_backend_run_details(
    settings: AppSettings,
    run_id: str,
    *,
    stage_name: str | None = None,
) -> RunDetailResult:
    output_dir = settings.output_dir.resolve()
    runs_root = resolve_runs_root(output_dir)
    run_root = resolve_run_root(output_dir, run_id)
    if not run_root.is_dir():
        raise FileNotFoundError(f"Run {run_id!r} was not found under {runs_root}.")

    stage_dirs = sorted(
        child for child in run_root.iterdir() if child.is_dir() and not child.name.startswith(".")
    )
    if stage_name is not None:
        stage_dirs = [stage_dir for stage_dir in stage_dirs if stage_dir.name == stage_name]
    return RunDetailResult(
        output_dir=str(output_dir),
        runs_root=str(runs_root),
        run=_build_run_entry(run_root),
        stages=[_build_run_stage_entry(stage_dir) for stage_dir in stage_dirs],
    )


def resolve_backend_run_catalog(
    settings: AppSettings,
    *,
    dataset_id: str | None = None,
    stage_name: str | None = None,
    latest_per_stage_prefix: bool = False,
) -> RunCatalogResult:
    output_dir = settings.output_dir.resolve()
    runs_root = resolve_runs_root(output_dir)

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
    runs = [_build_run_entry(run_dir) for run_dir in run_dirs]
    if dataset_id is not None:
        runs = [run for run in runs if run.dataset_id == dataset_id]
    if stage_name is not None:
        runs = [run for run in runs if stage_name in run.stage_names]
    if latest_per_stage_prefix:
        seen_prefixes: set[str] = set()
        latest_runs: list[RunCatalogEntry] = []
        for run in runs:
            prefix = extract_run_stage_prefix(run.run_id)
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            latest_runs.append(run)
        runs = latest_runs
    return RunCatalogResult(
        output_dir=str(output_dir),
        runs_root=str(runs_root),
        runs=runs,
    )


def resolve_backend_current_run_catalog(
    settings: AppSettings,
    *,
    dataset_id: str | None = None,
    stage_name: str | None = None,
    repo_paths: RepoPaths | None = None,
) -> RunCatalogResult:
    effective_dataset_id, inferred_dataset_id = _resolve_effective_current_dataset_id(
        settings,
        dataset_id,
        repo_paths=repo_paths,
    )
    result = resolve_backend_run_catalog(
        settings,
        dataset_id=effective_dataset_id,
        stage_name=stage_name,
        latest_per_stage_prefix=True,
    )
    return RunCatalogResult(
        output_dir=result.output_dir,
        runs_root=result.runs_root,
        runs=result.runs,
        detail=result.detail,
        inferred_dataset_id=inferred_dataset_id,
    )


def resolve_backend_current_run_details(
    settings: AppSettings,
    stage_prefix: str,
    *,
    dataset_id: str | None = None,
    stage_name: str | None = None,
    repo_paths: RepoPaths | None = None,
) -> RunDetailResult:
    run_catalog = resolve_backend_current_run_catalog(
        settings,
        dataset_id=dataset_id,
        repo_paths=repo_paths,
    )
    matching_run = next(
        (run for run in run_catalog.runs if extract_run_stage_prefix(run.run_id) == stage_prefix),
        None,
    )
    if matching_run is None:
        raise FileNotFoundError(
            f"Current run for stage_prefix {stage_prefix!r} was not found under {run_catalog.runs_root}."
        )
    result = resolve_backend_run_details(
        settings,
        matching_run.run_id,
        stage_name=stage_name,
    )
    return RunDetailResult(
        output_dir=result.output_dir,
        runs_root=result.runs_root,
        run=result.run,
        stages=result.stages,
        inferred_dataset_id=run_catalog.inferred_dataset_id,
    )


__all__ = [
    "RunCatalogEntry",
    "RunDetailResult",
    "RunCatalogResult",
    "RunStageDetailEntry",
    "extract_run_stage_prefix",
    "resolve_backend_current_run_catalog",
    "resolve_backend_current_run_details",
    "resolve_backend_run_details",
    "resolve_backend_run_catalog",
    "resolve_run_root",
    "resolve_runs_root",
]