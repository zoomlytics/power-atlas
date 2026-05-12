from __future__ import annotations

import asyncio

import httpx

from power_atlas.api import BackendAppOptions, create_backend_app


def test_public_api_facade_supports_consumer_app_smoke() -> None:
    consumer_app = create_backend_app(
        BackendAppOptions(version="2.0.0-test"),
        environ={},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            root_response = await client.get("/")
            assert root_response.status_code == 200
            assert root_response.json() == {
                "message": "Power Atlas API",
                "version": "2.0.0-test",
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
                "status": "not_configured",
                "detail": "Neo4j password is not configured",
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
            }

    asyncio.run(_exercise_app())