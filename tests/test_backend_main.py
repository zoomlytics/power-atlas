from __future__ import annotations

import asyncio
import importlib

import httpx
from fastapi.middleware.cors import CORSMiddleware

from power_atlas.api import BackendAppOptions, create_backend_app, get_backend_runtime
from power_atlas.context import AppContext
from power_atlas.graph_status import DEFAULT_UNCONFIGURED_DETAIL, GraphStatusResult
from power_atlas.graph_summary import GraphSummaryCounts, GraphSummaryResult


def test_backend_root_health_and_graph_status_contract(monkeypatch) -> None:
    for env_name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        monkeypatch.delenv(env_name, raising=False)

    backend_main = importlib.import_module("backend.main")
    backend_main = importlib.reload(backend_main)
    app = backend_main.app

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
                "status": "not_configured",
                "detail": DEFAULT_UNCONFIGURED_DETAIL,
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
            }

            graph_summary_response = await client.get("/graph/summary")
            assert graph_summary_response.status_code == 503
            assert graph_summary_response.json() == {
                "status": "not_configured",
                "detail": DEFAULT_UNCONFIGURED_DETAIL,
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
                "counts": None,
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


def test_create_backend_app_accepts_graph_status_resolver() -> None:
    custom_app = create_backend_app(
        graph_status_resolver=lambda app_context: GraphStatusResult(
            http_status_code=200,
            status="available",
            detail="Neo4j graph is reachable",
            neo4j_uri=app_context.settings.neo4j.uri,
            database=app_context.settings.neo4j.database,
        )
        ,
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        },
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            graph_status_response = await client.get("/graph/status")
            assert graph_status_response.status_code == 200
            assert graph_status_response.json() == {
                "status": "available",
                "detail": "Neo4j graph is reachable",
                "neo4j_uri": "neo4j://graph.example:7687",
                "database": "atlas",
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_accepts_graph_summary_resolver() -> None:
    custom_app = create_backend_app(
        graph_summary_resolver=lambda app_context: GraphSummaryResult(
            http_status_code=200,
            status="available",
            detail="Graph summary retrieved successfully",
            neo4j_uri=app_context.settings.neo4j.uri,
            database=app_context.settings.neo4j.database,
            counts=GraphSummaryCounts(
                document_count=4,
                chunk_count=12,
                claim_count=9,
                mention_count=27,
                cluster_count=8,
                canonical_entity_count=5,
            ),
        ),
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        },
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            graph_summary_response = await client.get("/graph/summary")
            assert graph_summary_response.status_code == 200
            assert graph_summary_response.json() == {
                "status": "available",
                "detail": "Graph summary retrieved successfully",
                "neo4j_uri": "neo4j://graph.example:7687",
                "database": "atlas",
                "counts": {
                    "document_count": 4,
                    "chunk_count": 12,
                    "claim_count": 9,
                    "mention_count": 27,
                    "cluster_count": 8,
                    "canonical_entity_count": 5,
                },
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_bootstraps_shared_app_context_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "neo4j://bootstrap.example:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "initial-secret")
    monkeypatch.setenv("NEO4J_DATABASE", "bootstrap")

    custom_app = create_backend_app(
        graph_status_resolver=lambda app_context: GraphStatusResult(
            http_status_code=200,
            status="available",
            detail="Neo4j graph is reachable",
            neo4j_uri=app_context.settings.neo4j.uri,
            database=app_context.settings.neo4j.database,
        )
    )

    runtime = get_backend_runtime(custom_app)
    assert isinstance(runtime.app_context, AppContext)
    assert runtime.app_context.settings.neo4j.uri == "neo4j://bootstrap.example:7687"
    assert runtime.app_context.settings.neo4j.database == "bootstrap"

    monkeypatch.setenv("NEO4J_URI", "neo4j://mutated.example:7687")
    monkeypatch.setenv("NEO4J_DATABASE", "mutated")

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            graph_status_response = await client.get("/graph/status")
            assert graph_status_response.status_code == 200
            assert graph_status_response.json() == {
                "status": "available",
                "detail": "Neo4j graph is reachable",
                "neo4j_uri": "neo4j://bootstrap.example:7687",
                "database": "bootstrap",
            }

    asyncio.run(_exercise_app())