from __future__ import annotations

import json
from pathlib import Path

import pytest

from power_atlas.backend_dataset_catalog import DatasetCatalogEntry, DatasetCatalogResult
from power_atlas.backend_run_catalog import (
    extract_run_stage_prefix,
    resolve_backend_current_run_catalog,
    resolve_backend_current_run_details,
    resolve_backend_run_catalog,
    resolve_backend_run_details,
    resolve_run_root,
)
from power_atlas.settings import AppSettings, Neo4jSettings


def test_backend_run_catalog_summarizes_run_stage_manifests(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
    manifest_path = run_root / "pdf_ingest" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "started_at": "2026-05-12T00:00:00+00:00",
                "finished_at": "2026-05-12T00:01:00+00:00",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    (run_root / "claim_extraction").mkdir()

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_run_catalog(settings)

    assert result.detail is None
    assert result.output_dir == str(tmp_path.resolve())
    assert result.runs_root == str((tmp_path / "runs").resolve())
    assert len(result.runs) == 1
    assert result.runs[0].run_id == run_root.name
    assert result.runs[0].dataset_id == "demo_dataset_v1"
    assert result.runs[0].stage_names == ["claim_extraction", "pdf_ingest"]


def test_backend_run_catalog_reports_missing_runs_root(tmp_path: Path) -> None:
    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_run_catalog(settings)

    assert result.runs == []
    assert result.detail == "No run directories were found under the configured output directory."


def test_backend_run_details_returns_stage_manifests(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "structured_ingest-20260512T000000Z-test"
    manifest_path = run_root / "structured_ingest" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "started_at": "2026-05-12T00:00:00+00:00",
                "finished_at": "2026-05-12T00:01:00+00:00",
                "stages": {"structured_ingest": {"status": "live", "claims": 4}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_run_details(settings, run_root.name)

    assert result.run.run_id == run_root.name
    assert len(result.stages) == 1
    assert result.stages[0].stage_name == "structured_ingest"
    assert result.stages[0].status == "live"
    assert result.stages[0].manifest is not None
    assert result.stages[0].manifest["dataset_id"] == "demo_dataset_v1"


def test_backend_run_details_filters_stage_manifests(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
    pdf_manifest_path = run_root / "pdf_ingest" / "manifest.json"
    pdf_manifest_path.parent.mkdir(parents=True)
    pdf_manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    claim_manifest_path = run_root / "claim_extraction" / "manifest.json"
    claim_manifest_path.parent.mkdir(parents=True)
    claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_run_details(settings, run_root.name, stage_name="claim_extraction")

    assert result.run.run_id == run_root.name
    assert result.run.stage_names == ["claim_extraction", "pdf_ingest"]
    assert [stage.stage_name for stage in result.stages] == ["claim_extraction"]


def test_resolve_run_root_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a simple relative name"):
        resolve_run_root(tmp_path, "../escape")


def test_backend_run_catalog_filters_by_dataset_and_stage(tmp_path: Path) -> None:
    first_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    first_manifest_path = first_run_root / "pdf_ingest" / "manifest.json"
    first_manifest_path.parent.mkdir(parents=True)
    first_manifest_path.write_text(
        json.dumps(
            {
                "run_id": first_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    (first_run_root / "claim_extraction").mkdir()

    second_run_root = tmp_path / "runs" / "structured_ingest-20260512T000000Z-b"
    second_manifest_path = second_run_root / "structured_ingest" / "manifest.json"
    second_manifest_path.parent.mkdir(parents=True)
    second_manifest_path.write_text(
        json.dumps(
            {
                "run_id": second_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    dataset_filtered = resolve_backend_run_catalog(settings, dataset_id="demo_dataset_v1")
    stage_filtered = resolve_backend_run_catalog(settings, stage_name="structured_ingest")
    combined_filtered = resolve_backend_run_catalog(
        settings,
        dataset_id="demo_dataset_v2",
        stage_name="structured_ingest",
    )

    assert [run.run_id for run in dataset_filtered.runs] == [first_run_root.name]
    assert [run.run_id for run in stage_filtered.runs] == [second_run_root.name]
    assert [run.run_id for run in combined_filtered.runs] == [second_run_root.name]


def test_backend_run_catalog_keeps_latest_run_per_stage_prefix(tmp_path: Path) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
    newer_manifest_path.parent.mkdir(parents=True)
    newer_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
    structured_manifest_path.parent.mkdir(parents=True)
    structured_manifest_path.write_text(
        json.dumps(
            {
                "run_id": structured_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_run_catalog(settings, latest_per_stage_prefix=True)

    assert [run.run_id for run in result.runs] == [newer_run_root.name, structured_run_root.name]
    assert extract_run_stage_prefix(newer_run_root.name) == "unstructured_ingest"
    assert extract_run_stage_prefix(structured_run_root.name) == "structured_ingest"


def test_backend_current_run_catalog_applies_latest_per_prefix_with_filters(tmp_path: Path) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_manifest_path.parent.mkdir(parents=True)
    newer_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
    structured_manifest_path.parent.mkdir(parents=True)
    structured_manifest_path.write_text(
        json.dumps(
            {
                "run_id": structured_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_current_run_catalog(
        settings,
        dataset_id="demo_dataset_v1",
        stage_name="claim_extraction",
    )

    assert [run.run_id for run in result.runs] == [newer_run_root.name]
    assert result.inferred_dataset_id is None


def test_backend_current_run_catalog_defaults_to_configured_selected_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newer_selected_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_selected_manifest_path = newer_selected_run_root / "claim_extraction" / "manifest.json"
    newer_selected_manifest_path.parent.mkdir(parents=True)
    newer_selected_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_selected_run_root.name,
                "dataset_id": "resolved-demo-dataset",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    other_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    other_manifest_path = other_run_root / "structured_ingest" / "manifest.json"
    other_manifest_path.parent.mkdir(parents=True)
    other_manifest_path.write_text(
        json.dumps(
            {
                "run_id": other_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "power_atlas.backend_run_catalog.resolve_backend_dataset_catalog",
        lambda settings, **_: DatasetCatalogResult(
            datasets=[],
            selected_dataset=DatasetCatalogEntry(
                name="demo_dataset_v1",
                dataset_id="resolved-demo-dataset",
                pdf_filename="example.pdf",
                manifest_path="/tmp/manifest.json",
                root_path="/tmp/dataset",
            ),
            selection_mode="configured",
        ),
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
        dataset_name="demo_dataset_v1",
    )

    result = resolve_backend_current_run_catalog(settings)

    assert [run.run_id for run in result.runs] == [newer_selected_run_root.name]
    assert result.inferred_dataset_id == "resolved-demo-dataset"


def test_backend_current_run_details_returns_latest_matching_prefix(tmp_path: Path) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_pdf_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
    newer_pdf_manifest_path.parent.mkdir(parents=True)
    newer_pdf_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_claim_manifest_path.parent.mkdir(parents=True)
    newer_claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings(
        neo4j=Neo4jSettings(password="secret"),
        output_dir=tmp_path,
    )

    result = resolve_backend_current_run_details(
        settings,
        "unstructured_ingest",
        dataset_id="demo_dataset_v1",
        stage_name="claim_extraction",
    )

    assert result.run.run_id == newer_run_root.name
    assert result.run.stage_names == ["claim_extraction", "pdf_ingest"]
    assert [stage.stage_name for stage in result.stages] == ["claim_extraction"]
    assert result.inferred_dataset_id is None