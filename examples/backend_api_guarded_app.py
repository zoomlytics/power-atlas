from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from power_atlas.api import build_backend_router, build_backend_runtime

ATLAS_TOKEN_HEADER = "x-atlas-token"
ATLAS_TOKEN_VALUE = "example-secret"


def _write_manifest(manifest_path: Path, payload: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_example_runs(output_dir: Path) -> str:
    run_id = "unstructured_ingest-20260512T000100Z-b"
    _write_manifest(
        output_dir / "runs" / run_id / "pdf_ingest" / "manifest.json",
        {
            "run_id": run_id,
            "dataset_id": "demo_dataset_v1",
            "stages": {"pdf_ingest": {"status": "live"}},
        },
    )
    _write_manifest(
        output_dir / "runs" / run_id / "claim_extraction" / "manifest.json",
        {
            "run_id": run_id,
            "dataset_id": "demo_dataset_v1",
            "stages": {"claim_extraction": {"status": "live"}},
        },
    )
    return run_id


def build_example_app(*, environ: dict[str, str] | None = None) -> FastAPI:
    app = FastAPI(title="Guarded Host Application", version="1.0.0-guarded")
    app.state.backend_runtime = build_backend_runtime(environ={} if environ is None else environ)
    app.include_router(build_backend_router(version="0.1.0-guarded"), prefix="/atlas")

    @app.middleware("http")
    async def guard_atlas_routes(request: Request, call_next):
        if request.url.path.startswith("/atlas"):
            if request.headers.get(ATLAS_TOKEN_HEADER) != ATLAS_TOKEN_VALUE:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid atlas token"},
                )
        return await call_next(request)

    @app.get("/host-info")
    async def host_info() -> dict[str, object]:
        return {
            "host": "backend_api_guarded_app",
            "host_title": app.title,
            "host_version": app.version,
        }

    return app


async def _snapshot_app(app: FastAPI) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        host_info = await client.get("/host-info")
        unauthorized_health = await client.get("/atlas/health")
        authorized_health = await client.get(
            "/atlas/health",
            headers={ATLAS_TOKEN_HEADER: ATLAS_TOKEN_VALUE},
        )
        authorized_runs = await client.get(
            "/atlas/runs",
            params={"dataset_id": "demo_dataset_v1", "stage_name": "claim_extraction"},
            headers={ATLAS_TOKEN_HEADER: ATLAS_TOKEN_VALUE},
        )
        authorized_run_detail = await client.get(
            "/atlas/runs/unstructured_ingest-20260512T000100Z-b",
            params={"stage_name": "claim_extraction"},
            headers={ATLAS_TOKEN_HEADER: ATLAS_TOKEN_VALUE},
        )
    runs_payload = authorized_runs.json()
    run_detail_payload = authorized_run_detail.json()
    return {
        "host_info": host_info.json(),
        "unauthorized_health": {
            "status_code": unauthorized_health.status_code,
            "body": unauthorized_health.json(),
        },
        "authorized_health": {
            "status_code": authorized_health.status_code,
            "body": authorized_health.json(),
        },
        "authorized_runs": {
            "run_ids": [run["run_id"] for run in runs_payload["runs"]],
            "stage_names": [run["stage_names"] for run in runs_payload["runs"]],
        },
        "authorized_run_detail": {
            "run_id": run_detail_payload["run"]["run_id"],
            "run_stage_names": run_detail_payload["run"]["stage_names"],
            "stages": [stage["stage_name"] for stage in run_detail_payload["stages"]],
        },
    }


app = build_example_app()


if __name__ == "__main__":
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        _seed_example_runs(output_dir)
        example_app = build_example_app(environ={"POWER_ATLAS_OUTPUT_DIR": str(output_dir)})
        print(json.dumps(asyncio.run(_snapshot_app(example_app)), sort_keys=True))