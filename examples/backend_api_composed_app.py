from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import FastAPI

from power_atlas.api import build_backend_router, build_backend_runtime
from power_atlas.contracts import resolve_dataset_root


def _write_manifest(manifest_path: Path, payload: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_example_runs(output_dir: Path) -> tuple[str, str, str]:
    selected_dataset_id = resolve_dataset_root("demo_dataset_v1", environ={}).dataset_id
    older_run_id = "unstructured_ingest-20260512T000000Z-a"
    newer_run_id = "unstructured_ingest-20260512T000100Z-b"
    structured_run_id = "structured_ingest-20260512T000050Z-c"

    _write_manifest(
        output_dir / "runs" / older_run_id / "pdf_ingest" / "manifest.json",
        {
            "run_id": older_run_id,
            "dataset_id": selected_dataset_id,
            "stages": {"pdf_ingest": {"status": "live"}},
        },
    )
    _write_manifest(
        output_dir / "runs" / older_run_id / "claim_extraction" / "manifest.json",
        {
            "run_id": older_run_id,
            "dataset_id": selected_dataset_id,
            "stages": {"claim_extraction": {"status": "live"}},
        },
    )
    _write_manifest(
        output_dir / "runs" / newer_run_id / "pdf_ingest" / "manifest.json",
        {
            "run_id": newer_run_id,
            "dataset_id": "demo_dataset_v2",
            "stages": {"pdf_ingest": {"status": "live"}},
        },
    )
    _write_manifest(
        output_dir / "runs" / newer_run_id / "claim_extraction" / "manifest.json",
        {
            "run_id": newer_run_id,
            "dataset_id": "demo_dataset_v2",
            "stages": {"claim_extraction": {"status": "live"}},
        },
    )
    _write_manifest(
        output_dir / "runs" / structured_run_id / "structured_ingest" / "manifest.json",
        {
            "run_id": structured_run_id,
            "dataset_id": "demo_dataset_v2",
            "stages": {"structured_ingest": {"status": "live"}},
        },
    )
    return older_run_id, newer_run_id, structured_run_id


def build_example_app(*, environ: dict[str, str] | None = None) -> FastAPI:
    app = FastAPI(title="Host Application", version="1.0.0-host")
    app.state.backend_runtime = build_backend_runtime(environ={} if environ is None else environ)
    app.include_router(build_backend_router(version="0.1.0-mounted"), prefix="/atlas")

    @app.get("/host-info")
    async def host_info() -> dict[str, object]:
        return {
            "host": "backend_api_composed_app",
            "host_title": app.title,
            "host_version": app.version,
        }

    return app


async def _snapshot_app(app: FastAPI) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        host_info = await client.get("/host-info")
        backend_root = await client.get("/atlas/")
        backend_datasets = await client.get("/atlas/datasets")
        backend_current_runs = await client.get("/atlas/runs/current")
        backend_current_run_detail = await client.get(
            "/atlas/runs/current/unstructured_ingest",
            params={"stage_name": "claim_extraction"},
        )
        backend_health = await client.get("/atlas/health")
        backend_graph_status = await client.get("/atlas/graph/status")
    datasets_payload = backend_datasets.json()
    current_runs_payload = backend_current_runs.json()
    current_run_detail_payload = backend_current_run_detail.json()
    return {
        "host_info": host_info.json(),
        "backend_root": backend_root.json(),
        "backend_datasets": {
            "dataset_names": [
                dataset["name"] for dataset in datasets_payload["datasets"]
            ],
            "selected_dataset_name": (
                None
                if datasets_payload["selected_dataset"] is None
                else datasets_payload["selected_dataset"]["name"]
            ),
            "selection_mode": datasets_payload["selection_mode"],
        },
        "backend_current_runs": {
            "run_ids": [run["run_id"] for run in current_runs_payload["runs"]],
            "detail": current_runs_payload["detail"],
            "runs_root": current_runs_payload["runs_root"],
        },
        "backend_current_run_detail": {
            "run_id": current_run_detail_payload["run"]["run_id"],
            "run_stage_names": current_run_detail_payload["run"]["stage_names"],
            "stages": [stage["stage_name"] for stage in current_run_detail_payload["stages"]],
        },
        "backend_health": backend_health.json(),
        "backend_graph_status": backend_graph_status.json(),
    }


app = build_example_app()


if __name__ == "__main__":
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        _seed_example_runs(output_dir)
        example_app = build_example_app(
            environ={
                "POWER_ATLAS_OUTPUT_DIR": str(output_dir),
                "POWER_ATLAS_DATASET": "demo_dataset_v1",
            }
        )
        print(json.dumps(asyncio.run(_snapshot_app(example_app)), sort_keys=True))