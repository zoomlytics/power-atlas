from __future__ import annotations

import json
from pathlib import Path

from power_atlas.backend_run_catalog import resolve_backend_run_catalog
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