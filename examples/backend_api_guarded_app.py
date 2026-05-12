from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from power_atlas.api import build_backend_router, build_backend_runtime

ATLAS_TOKEN_HEADER = "x-atlas-token"
ATLAS_TOKEN_VALUE = "example-secret"


def build_example_app() -> FastAPI:
    app = FastAPI(title="Guarded Host Application", version="1.0.0-guarded")
    app.state.backend_runtime = build_backend_runtime(environ={})
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
    }


app = build_example_app()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_snapshot_app(app)), sort_keys=True))