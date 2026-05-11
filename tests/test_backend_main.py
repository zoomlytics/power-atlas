from __future__ import annotations

import asyncio

import httpx
from fastapi.middleware.cors import CORSMiddleware

from backend.main import app
from power_atlas.api import BackendAppOptions, create_backend_app


def test_backend_root_health_and_graph_status_contract() -> None:
    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            root_response = await client.get("/")
            assert root_response.status_code == 200
            assert root_response.json() == {
                "message": "Power Atlas API",
                "version": "0.1.0",
                "docs": "/docs",
            }

            health_response = await client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json() == {
                "status": "ok",
                "message": "Backend is healthy",
            }

            graph_status_response = await client.get("/graph/status")
            assert graph_status_response.status_code == 503
            assert graph_status_response.json() == {
                "detail": "Graph integration is not configured yet"
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_accepts_options() -> None:
    custom_app = create_backend_app(
        BackendAppOptions(
            title="Atlas Test API",
            description="Test backend facade",
            version="9.9.9",
            cors_allow_origins=("https://atlas.example",),
        )
    )

    assert custom_app.title == "Atlas Test API"
    assert custom_app.description == "Test backend facade"
    assert custom_app.version == "9.9.9"
    assert any(
        middleware.cls is CORSMiddleware
        and middleware.kwargs["allow_origins"] == ["https://atlas.example"]
        for middleware in custom_app.user_middleware
    )