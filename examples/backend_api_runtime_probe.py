from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI

from power_atlas.api import BackendAppOptions, create_backend_app, get_backend_runtime


def build_example_app(*, environ: dict[str, str] | None = None) -> FastAPI:
    app = create_backend_app(
        BackendAppOptions(
            title="Power Atlas Runtime Probe Example",
            version="0.1.0-runtime-probe",
        ),
        environ={} if environ is None else environ,
    )

    @app.get("/runtime-info")
    async def runtime_info() -> dict[str, object]:
        runtime = get_backend_runtime(app)
        return {
            "app_context_type": type(runtime.app_context).__name__,
            "dataset_name": runtime.app_context.settings.dataset_name,
            "graph_queries_type": type(runtime.graph_queries).__name__,
            "neo4j_database": runtime.app_context.settings.neo4j.database,
            "output_dir_name": runtime.app_context.settings.output_dir.name,
            "runtime_on_app_state": runtime is app.state.backend_runtime,
        }

    return app


async def _snapshot_app(app: FastAPI) -> dict[str, object]:
    runtime = get_backend_runtime(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        runtime_info = await client.get("/runtime-info")
    return {
        "consumer": "backend_api_runtime_probe",
        "title": app.title,
        "version": app.version,
        "runtime": runtime_info.json(),
        "runtime_retrieved_directly": isinstance(runtime.app_context.settings.dataset_name, str),
    }


app = build_example_app()


if __name__ == "__main__":
    example_app = build_example_app(
        environ={
            "POWER_ATLAS_OUTPUT_DIR": "build/backend-runtime-example",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    print(json.dumps(asyncio.run(_snapshot_app(example_app)), sort_keys=True))