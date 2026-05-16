from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI

from power_atlas.api import backend_router, build_backend_runtime, get_backend_runtime, lifespan
from power_atlas.bootstrap import AppBaseline


def build_example_app(
    *,
    environ: dict[str, str] | None = None,
    app_baseline: AppBaseline | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Power Atlas Direct Hooks Example",
        version="0.1.0-direct-hooks",
        lifespan=lifespan,
    )
    app.state.backend_runtime = build_backend_runtime(
        environ={} if environ is None else environ,
        app_baseline=app_baseline,
    )
    app.include_router(backend_router, prefix="/atlas")

    @app.get("/host-info")
    async def host_info() -> dict[str, object]:
        return {
            "host": "backend_api_direct_hooks",
            "host_title": app.title,
            "host_version": app.version,
        }

    return app


async def _snapshot_app(app: FastAPI) -> dict[str, object]:
    runtime = get_backend_runtime(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        host_info = await client.get("/host-info")
        backend_root = await client.get("/atlas/")
        backend_health = await client.get("/atlas/health")
    return {
        "consumer": "backend_api_direct_hooks",
        "host_info": host_info.json(),
        "backend_root": backend_root.json(),
        "backend_health": backend_health.json(),
        "runtime": {
            "dataset_name": runtime.app_context.settings.dataset_name,
            "graph_queries_type": type(runtime.graph_queries).__name__,
            "output_dir_name": runtime.app_context.settings.output_dir.name,
            "runtime_on_app_state": runtime is app.state.backend_runtime,
        },
        "uses_prebuilt_router": any(
            getattr(route, "path", None) == "/atlas/health" for route in app.routes
        ),
        "uses_public_lifespan_hook": getattr(app.router.lifespan_context, "__name__", None)
        == "lifespan",
    }


app = build_example_app()


if __name__ == "__main__":
    example_app = build_example_app(
        environ={
            "POWER_ATLAS_OUTPUT_DIR": "build/backend-direct-hooks",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    print(json.dumps(asyncio.run(_snapshot_app(example_app)), sort_keys=True))