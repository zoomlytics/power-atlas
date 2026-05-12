from __future__ import annotations

from pathlib import Path

from power_atlas.backend_dataset_catalog import resolve_backend_dataset_catalog
from power_atlas.contracts import DatasetRoot
from power_atlas.settings import AppSettings, Neo4jSettings


def test_backend_dataset_catalog_uses_configured_dataset() -> None:
    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        dataset_name="demo_dataset_v1",
    )

    def _dataset_root_resolver(name: str | None) -> DatasetRoot:
        assert name == "demo_dataset_v1"
        root = Path("demo/fixtures/datasets/demo_dataset_v1")
        return DatasetRoot(
            root=root,
            dataset_id="demo_dataset_v1",
            pdf_filename="chain_of_custody.pdf",
        )

    result = resolve_backend_dataset_catalog(
        settings,
        list_datasets=lambda: ["demo_dataset_v1"],
        dataset_root_resolver=_dataset_root_resolver,
    )

    assert result.selection_mode == "configured"
    assert result.detail is None
    assert result.selected_dataset is not None
    assert result.selected_dataset.name == "demo_dataset_v1"
    assert result.selected_dataset.dataset_id == "demo_dataset_v1"
    assert result.datasets[0].manifest_path.endswith("manifest.json")


def test_backend_dataset_catalog_reports_ambiguous_selection() -> None:
    settings = AppSettings(neo4j=Neo4jSettings(password="secret"))

    def _dataset_root_resolver(name: str | None) -> DatasetRoot:
        assert name in {"dataset_a", "dataset_b"}
        root = Path("demo/fixtures/datasets") / str(name)
        return DatasetRoot(
            root=root,
            dataset_id=str(name),
            pdf_filename="chain_of_custody.pdf",
        )

    result = resolve_backend_dataset_catalog(
        settings,
        list_datasets=lambda: ["dataset_a", "dataset_b"],
        dataset_root_resolver=_dataset_root_resolver,
    )

    assert result.selection_mode == "ambiguous"
    assert result.selected_dataset is None
    assert result.detail is not None
    assert len(result.datasets) == 2