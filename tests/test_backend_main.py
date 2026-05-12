from __future__ import annotations

import asyncio
import importlib

import httpx
from fastapi.middleware.cors import CORSMiddleware

from power_atlas.api import (
    BackendAppOptions,
    build_backend_graph_query_service,
    create_backend_app,
    get_backend_runtime,
)
from power_atlas.bootstrap import build_app_context
from power_atlas.context import AppContext
from power_atlas.graph_status import DEFAULT_UNCONFIGURED_DETAIL, GraphStatusResult
from power_atlas.graph_health_summary import (
    GraphHealthAlignmentSummary,
    GraphHealthMentionSummary,
    GraphHealthParticipationSummary,
    GraphHealthSummaryRequest,
    GraphHealthSummaryResult,
)
from power_atlas.graph_summary import GraphSummaryCounts, GraphSummaryResult
from power_atlas.run_scoped_graph_counts import (
    RunScopedGraphCounts,
    RunScopedGraphCountsRequest,
    RunScopedGraphCountsResult,
)


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

            datasets_response = await client.get("/datasets")
            assert datasets_response.status_code == 200
            datasets_payload = datasets_response.json()
            assert set(datasets_payload) == {
                "datasets",
                "selected_dataset",
                "selection_mode",
                "detail",
            }
            assert isinstance(datasets_payload["datasets"], list)
            assert datasets_payload["selection_mode"] in {
                "configured",
                "auto_discovered",
                "ambiguous",
                "legacy_fallback",
                "unresolved",
            }

            runs_response = await client.get("/runs")
            assert runs_response.status_code == 200
            runs_payload = runs_response.json()
            assert set(runs_payload) == {
                "output_dir",
                "runs_root",
                "runs",
                "detail",
            }
            assert isinstance(runs_payload["runs"], list)

            missing_run_response = await client.get("/runs/unstructured_ingest-test-run")
            assert missing_run_response.status_code == 404
            assert "was not found" in missing_run_response.json()["detail"]

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

            graph_health_summary_response = await client.post(
                "/graph/health-summary",
                json={"run_id": "unstructured_ingest-test-run", "alignment_version": "v1"},
            )
            assert graph_health_summary_response.status_code == 503
            assert graph_health_summary_response.json() == {
                "status": "not_configured",
                "detail": DEFAULT_UNCONFIGURED_DETAIL,
                "run_id": "unstructured_ingest-test-run",
                "alignment_version": "v1",
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
                "participation_summary": None,
                "mention_summary": None,
                "alignment_summary": None,
            }

            run_scoped_counts_response = await client.post(
                "/graph/run-scoped-counts",
                json={"run_id": "unstructured_ingest-test-run"},
            )
            assert run_scoped_counts_response.status_code == 503
            assert run_scoped_counts_response.json() == {
                "status": "not_configured",
                "detail": DEFAULT_UNCONFIGURED_DETAIL,
                "run_id": "unstructured_ingest-test-run",
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
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    custom_app = create_backend_app(
        app_context=app_context,
        graph_queries=build_backend_graph_query_service(
            app_context,
            graph_status_resolver=lambda runtime_app_context: GraphStatusResult(
                http_status_code=200,
                status="available",
                detail="Neo4j graph is reachable",
                neo4j_uri=runtime_app_context.settings.neo4j.uri,
                database=runtime_app_context.settings.neo4j.database,
            ),
        ),
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
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    custom_app = create_backend_app(
        app_context=app_context,
        graph_queries=build_backend_graph_query_service(
            app_context,
            graph_summary_resolver=lambda runtime_app_context: GraphSummaryResult(
                http_status_code=200,
                status="available",
                detail="Graph summary retrieved successfully",
                neo4j_uri=runtime_app_context.settings.neo4j.uri,
                database=runtime_app_context.settings.neo4j.database,
                counts=GraphSummaryCounts(
                    document_count=4,
                    chunk_count=12,
                    claim_count=9,
                    mention_count=27,
                    cluster_count=8,
                    canonical_entity_count=5,
                ),
            ),
        ),
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


def test_create_backend_app_exposes_run_detail_endpoint(tmp_path) -> None:
    run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
    manifest_path = run_root / "pdf_ingest" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
{
  "run_id": "unstructured_ingest-20260512T000000Z-test",
  "dataset_id": "demo_dataset_v1",
  "started_at": "2026-05-12T00:00:00+00:00",
  "finished_at": "2026-05-12T00:01:00+00:00",
  "stages": {
    "pdf_ingest": {
      "status": "live"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    custom_app = create_backend_app(environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)})

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/runs/{run_root.name}")
            assert response.status_code == 200
            assert response.json() == {
                "output_dir": str(tmp_path.resolve()),
                "runs_root": str((tmp_path / "runs").resolve()),
                "run": {
                    "run_id": run_root.name,
                    "dataset_id": "demo_dataset_v1",
                    "started_at": "2026-05-12T00:00:00+00:00",
                    "finished_at": "2026-05-12T00:01:00+00:00",
                    "stage_names": ["pdf_ingest"],
                    "root_path": str(run_root.resolve()),
                },
                "stages": [
                    {
                        "stage_name": "pdf_ingest",
                        "status": "live",
                        "manifest_path": str(manifest_path.resolve()),
                        "manifest": {
                            "run_id": run_root.name,
                            "dataset_id": "demo_dataset_v1",
                            "started_at": "2026-05-12T00:00:00+00:00",
                            "finished_at": "2026-05-12T00:01:00+00:00",
                            "stages": {
                                "pdf_ingest": {
                                    "status": "live",
                                }
                            },
                        },
                    }
                ],
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_filters_runs_endpoint(tmp_path) -> None:
        first_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
        first_manifest_path = first_run_root / "pdf_ingest" / "manifest.json"
        first_manifest_path.parent.mkdir(parents=True)
        first_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000000Z-a",
    "dataset_id": "demo_dataset_v1",
    "stages": {
        "pdf_ingest": {
            "status": "live"
        }
    }
}
""".strip(),
                encoding="utf-8",
        )
        second_run_root = tmp_path / "runs" / "structured_ingest-20260512T000000Z-b"
        second_manifest_path = second_run_root / "structured_ingest" / "manifest.json"
        second_manifest_path.parent.mkdir(parents=True)
        second_manifest_path.write_text(
                """
{
    "run_id": "structured_ingest-20260512T000000Z-b",
    "dataset_id": "demo_dataset_v2",
    "stages": {
        "structured_ingest": {
            "status": "live"
        }
    }
}
""".strip(),
                encoding="utf-8",
        )
        custom_app = create_backend_app(environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)})

        async def _exercise_app() -> None:
                transport = httpx.ASGITransport(app=custom_app)
                async with httpx.AsyncClient(
                        transport=transport,
                        base_url="http://testserver",
                ) as client:
                        by_dataset = await client.get("/runs", params={"dataset_id": "demo_dataset_v1"})
                        by_stage = await client.get("/runs", params={"stage_name": "structured_ingest"})
                        assert by_dataset.status_code == 200
                        assert [run["run_id"] for run in by_dataset.json()["runs"]] == [first_run_root.name]
                        assert by_stage.status_code == 200
                        assert [run["run_id"] for run in by_stage.json()["runs"]] == [second_run_root.name]

        asyncio.run(_exercise_app())


def test_create_backend_app_bootstraps_shared_app_context_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "neo4j://bootstrap.example:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "initial-secret")
    monkeypatch.setenv("NEO4J_DATABASE", "bootstrap")

    custom_app = create_backend_app(
        graph_queries=build_backend_graph_query_service(
            build_app_context(),
            graph_status_resolver=lambda runtime_app_context: GraphStatusResult(
                http_status_code=200,
                status="available",
                detail="Neo4j graph is reachable",
                neo4j_uri=runtime_app_context.settings.neo4j.uri,
                database=runtime_app_context.settings.neo4j.database,
            ),
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


def test_create_backend_app_accepts_run_scoped_graph_counts_resolver() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    custom_app = create_backend_app(
        app_context=app_context,
        graph_queries=build_backend_graph_query_service(
            app_context,
            run_scoped_graph_counts_resolver=lambda runtime_app_context, request: RunScopedGraphCountsResult(
                http_status_code=200,
                status="available",
                detail="Run-scoped graph counts retrieved successfully",
                run_id=request.run_id,
                neo4j_uri=runtime_app_context.settings.neo4j.uri,
                database=runtime_app_context.settings.neo4j.database,
                counts=RunScopedGraphCounts(
                    chunk_count=11,
                    claim_count=7,
                    mention_count=21,
                    cluster_count=6,
                ),
            ),
        ),
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/graph/run-scoped-counts",
                json={"run_id": "unstructured_ingest-20260511T000000Z-test"},
            )
            assert response.status_code == 200
            assert response.json() == {
                "status": "available",
                "detail": "Run-scoped graph counts retrieved successfully",
                "run_id": "unstructured_ingest-20260511T000000Z-test",
                "neo4j_uri": "neo4j://graph.example:7687",
                "database": "atlas",
                "counts": {
                    "chunk_count": 11,
                    "claim_count": 7,
                    "mention_count": 21,
                    "cluster_count": 6,
                },
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_accepts_graph_health_summary_resolver() -> None:
    app_context = build_app_context(
        environ={
            "NEO4J_URI": "neo4j://graph.example:7687",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "atlas",
        }
    )
    custom_app = create_backend_app(
        app_context=app_context,
        graph_queries=build_backend_graph_query_service(
            app_context,
            graph_health_summary_resolver=lambda runtime_app_context, request: GraphHealthSummaryResult(
                http_status_code=200,
                status="available",
                detail="Graph health summary retrieved successfully",
                run_id=request.run_id,
                alignment_version=request.alignment_version,
                neo4j_uri=runtime_app_context.settings.neo4j.uri,
                database=runtime_app_context.settings.neo4j.database,
                participation_summary=GraphHealthParticipationSummary(
                    total_edges=14,
                    edges_by_role={"subject": 9, "object": 5},
                    total_claims=6,
                    claims_with_zero_edges=1,
                    claim_coverage_pct=83.33,
                ),
                mention_summary=GraphHealthMentionSummary(
                    total_mentions=10,
                    clustered_mentions=8,
                    unclustered_mentions=2,
                    unresolved_rate_pct=20.0,
                ),
                alignment_summary=GraphHealthAlignmentSummary(
                    total_clusters=5,
                    aligned_clusters=4,
                    unaligned_clusters=1,
                    alignment_coverage_pct=80.0,
                ),
            ),
        ),
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/graph/health-summary",
                json={
                    "run_id": "unstructured_ingest-20260511T000000Z-test",
                    "alignment_version": "v1",
                },
            )
            assert response.status_code == 200
            assert response.json() == {
                "status": "available",
                "detail": "Graph health summary retrieved successfully",
                "run_id": "unstructured_ingest-20260511T000000Z-test",
                "alignment_version": "v1",
                "neo4j_uri": "neo4j://graph.example:7687",
                "database": "atlas",
                "participation_summary": {
                    "total_edges": 14,
                    "edges_by_role": {"subject": 9, "object": 5},
                    "total_claims": 6,
                    "claims_with_zero_edges": 1,
                    "claim_coverage_pct": 83.33,
                },
                "mention_summary": {
                    "total_mentions": 10,
                    "clustered_mentions": 8,
                    "unclustered_mentions": 2,
                    "unresolved_rate_pct": 20.0,
                },
                "alignment_summary": {
                    "total_clusters": 5,
                    "aligned_clusters": 4,
                    "unaligned_clusters": 1,
                    "alignment_coverage_pct": 80.0,
                },
            }

    asyncio.run(_exercise_app())