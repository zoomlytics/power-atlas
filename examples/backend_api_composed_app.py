from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI

from power_atlas.api import build_backend_router, build_backend_runtime


def build_example_app() -> FastAPI:
    app = FastAPI(title="Host Application", version="1.0.0-host")
    app.state.backend_runtime = build_backend_runtime(environ={})
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
        backend_runs = await client.get("/atlas/runs")
        backend_health = await client.get("/atlas/health")
        backend_graph_status = await client.get("/atlas/graph/status")
    datasets_payload = backend_datasets.json()
    runs_payload = backend_runs.json()
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
        "backend_runs": {
            "run_ids": [run["run_id"] for run in runs_payload["runs"]],
            "runs_root": runs_payload["runs_root"],
        },
        "backend_health": backend_health.json(),
        "backend_graph_status": backend_graph_status.json(),
    }


app = build_example_app()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_snapshot_app(app)), sort_keys=True))