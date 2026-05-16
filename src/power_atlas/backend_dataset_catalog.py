from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from power_atlas.contracts import (
    DatasetRoot,
    RepoPaths,
    list_available_datasets,
    resolve_dataset_root,
)
from power_atlas.settings import AppSettings


@dataclass(frozen=True, slots=True)
class DatasetCatalogEntry:
    name: str
    dataset_id: str
    pdf_filename: str
    manifest_path: str
    root_path: str


@dataclass(frozen=True, slots=True)
class DatasetCatalogResult:
    datasets: list[DatasetCatalogEntry]
    selected_dataset: DatasetCatalogEntry | None
    selection_mode: str
    detail: str | None = None


def _entry_from_root(name: str, dataset_root: DatasetRoot) -> DatasetCatalogEntry:
    return DatasetCatalogEntry(
        name=name,
        dataset_id=dataset_root.dataset_id,
        pdf_filename=dataset_root.pdf_filename,
        manifest_path=str(dataset_root.manifest_path),
        root_path=str(dataset_root.root),
    )


def _default_dataset_root_resolver(name: str | None) -> DatasetRoot:
    return resolve_dataset_root(name, environ={})


def _build_dataset_root_resolver(repo_paths: RepoPaths) -> Callable[[str | None], DatasetRoot]:
    return lambda name: resolve_dataset_root(name, environ={}, repo_paths=repo_paths)


def _build_list_datasets(repo_paths: RepoPaths) -> Callable[[], list[str]]:
    return lambda: list_available_datasets(repo_paths=repo_paths)


def resolve_backend_dataset_catalog(
    settings: AppSettings,
    *,
    repo_paths: RepoPaths | None = None,
    list_datasets: Callable[[], list[str]] = list_available_datasets,
    dataset_root_resolver: Callable[[str | None], DatasetRoot] = _default_dataset_root_resolver,
) -> DatasetCatalogResult:
    if repo_paths is not None:
        list_datasets = _build_list_datasets(repo_paths)
        dataset_root_resolver = _build_dataset_root_resolver(repo_paths)
    available_dataset_names = list_datasets()
    datasets = [
        _entry_from_root(dataset_name, dataset_root_resolver(dataset_name))
        for dataset_name in available_dataset_names
    ]

    if settings.dataset_name:
        try:
            selected_dataset = _entry_from_root(
                settings.dataset_name,
                dataset_root_resolver(settings.dataset_name),
            )
        except ValueError as exc:
            return DatasetCatalogResult(
                datasets=datasets,
                selected_dataset=None,
                selection_mode="unresolved",
                detail=str(exc),
            )
        return DatasetCatalogResult(
            datasets=datasets,
            selected_dataset=selected_dataset,
            selection_mode="configured",
        )

    if len(datasets) == 1:
        return DatasetCatalogResult(
            datasets=datasets,
            selected_dataset=datasets[0],
            selection_mode="auto_discovered",
        )

    if len(datasets) > 1:
        return DatasetCatalogResult(
            datasets=datasets,
            selected_dataset=None,
            selection_mode="ambiguous",
            detail=(
                "Multiple datasets are available. Set POWER_ATLAS_DATASET or "
                "FIXTURE_DATASET to select one explicitly."
            ),
        )

    selected_dataset_root = dataset_root_resolver(None)
    return DatasetCatalogResult(
        datasets=[],
        selected_dataset=_entry_from_root(
            selected_dataset_root.root.name,
            selected_dataset_root,
        ),
        selection_mode="legacy_fallback",
    )


__all__ = [
    "DatasetCatalogEntry",
    "DatasetCatalogResult",
    "resolve_backend_dataset_catalog",
]