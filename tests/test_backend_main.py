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
from power_atlas.bootstrap import AppSettingsEnvNames, build_app_context, resolve_app_baseline
from power_atlas.context import AppContext
from power_atlas.contracts import RepoPaths, resolve_pipeline_contract_source
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

            missing_claim_diagnostics_response = await client.get(
                "/runs/unstructured_ingest-test-run/claim-extraction-diagnostics"
            )
            assert missing_claim_diagnostics_response.status_code == 404
            assert "was not found" in missing_claim_diagnostics_response.json()["detail"]

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


def test_create_backend_app_filters_run_detail_endpoint_stages(tmp_path) -> None:
        run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
        pdf_manifest_path = run_root / "pdf_ingest" / "manifest.json"
        pdf_manifest_path.parent.mkdir(parents=True)
        pdf_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000000Z-test",
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
        claim_manifest_path = run_root / "claim_extraction" / "manifest.json"
        claim_manifest_path.parent.mkdir(parents=True)
        claim_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000000Z-test",
    "dataset_id": "demo_dataset_v1",
    "stages": {
        "claim_extraction": {
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
                        response = await client.get(
                                f"/runs/{run_root.name}",
                                params={"stage_name": "claim_extraction"},
                        )
                        assert response.status_code == 200
                        payload = response.json()
                        assert payload["run"]["stage_names"] == ["claim_extraction", "pdf_ingest"]
                        assert [stage["stage_name"] for stage in payload["stages"]] == ["claim_extraction"]

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


def test_create_backend_app_supports_explicit_app_baseline(tmp_path) -> None:
    pipeline_config_path = tmp_path / "host-app" / "config" / "pipeline.yaml"
    pipeline_config_path.parent.mkdir(parents=True)
    pipeline_config_path.write_text(
        """
contract:
  chunk_embedding:
    index_name: backend_host_chunk_index
    label: BackendHostChunk
    embedding_property: backend_host_embedding
    dimensions: 2048
embedder_config:
  params_:
    model: text-embedding-3-large
text_splitter:
  params_:
    chunk_size: 1100
    chunk_overlap: 125
""".strip(),
        encoding="utf-8",
    )
    app_baseline = resolve_app_baseline(
        env_names=AppSettingsEnvNames(
            output_dir="HOSTAPP_OUTPUT_DIR",
            dataset_name_primary="HOSTAPP_DATASET",
            dataset_name_fallback="HOSTAPP_LEGACY_DATASET",
        ),
        pipeline_contract_source=resolve_pipeline_contract_source(
            config_path=pipeline_config_path,
        ),
    )
    custom_app = create_backend_app(
        environ={
            "HOSTAPP_OUTPUT_DIR": str(tmp_path / "host-app-output"),
            "HOSTAPP_DATASET": "demo_dataset_v1",
        },
        app_baseline=app_baseline,
    )

    runtime = get_backend_runtime(custom_app)
    assert runtime.app_context.settings.output_dir == tmp_path / "host-app-output"
    assert runtime.app_context.settings.dataset_name == "demo_dataset_v1"
    assert runtime.app_context.pipeline_contract.chunk_embedding_index_name == "backend_host_chunk_index"
    assert runtime.app_context.pipeline_contract.chunk_embedding_label == "BackendHostChunk"
    assert runtime.app_context.pipeline_contract.chunk_embedding_property == "backend_host_embedding"
    assert runtime.app_context.pipeline_contract.chunk_embedding_dimensions == 2048
    assert runtime.app_context.pipeline_contract.chunk_fallback_stride == 975

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            runs_response = await client.get("/runs")
            assert runs_response.status_code == 200
            assert runs_response.json()["output_dir"] == str(tmp_path / "host-app-output")

    asyncio.run(_exercise_app())


def test_create_backend_app_datasets_and_current_runs_support_explicit_repo_paths(
    tmp_path,
) -> None:
    host_root = tmp_path / "host-app"
    selected_dataset_root = host_root / "fixtures" / "datasets" / "host_dataset_v1"
    selected_dataset_root.mkdir(parents=True)
    (selected_dataset_root / "manifest.json").write_text(
        """
{
  "dataset": "host-dataset-id-v1",
  "provenance": [{"kind": "pdf", "path": "unstructured/host-one.pdf"}]
}
""".strip(),
        encoding="utf-8",
    )
    other_dataset_root = host_root / "fixtures" / "datasets" / "host_dataset_v2"
    other_dataset_root.mkdir(parents=True)
    (other_dataset_root / "manifest.json").write_text(
        """
{
  "dataset": "host-dataset-id-v2",
  "provenance": [{"kind": "pdf", "path": "unstructured/host-two.pdf"}]
}
""".strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "host-app-output"
    selected_run_root = output_dir / "runs" / "unstructured_ingest-20260512T000100Z-b"
    selected_claim_manifest_path = selected_run_root / "claim_extraction" / "manifest.json"
    selected_claim_manifest_path.parent.mkdir(parents=True)
    selected_claim_manifest_path.write_text(
        """
{
  "run_id": "unstructured_ingest-20260512T000100Z-b",
  "dataset_id": "host-dataset-id-v1",
  "stages": {
    "claim_extraction": {"status": "live"}
  }
}
""".strip(),
        encoding="utf-8",
    )
    other_run_root = output_dir / "runs" / "structured_ingest-20260512T000050Z-c"
    other_manifest_path = other_run_root / "structured_ingest" / "manifest.json"
    other_manifest_path.parent.mkdir(parents=True)
    other_manifest_path.write_text(
        """
{
  "run_id": "structured_ingest-20260512T000050Z-c",
  "dataset_id": "host-dataset-id-v2",
  "stages": {
    "structured_ingest": {"status": "live"}
  }
}
""".strip(),
        encoding="utf-8",
    )
    custom_app = create_backend_app(
        environ={
            "HOSTAPP_OUTPUT_DIR": str(output_dir),
            "HOSTAPP_DATASET": "host_dataset_v1",
        },
        app_baseline=resolve_app_baseline(
            env_names=AppSettingsEnvNames(
                output_dir="HOSTAPP_OUTPUT_DIR",
                dataset_name_primary="HOSTAPP_DATASET",
                dataset_name_fallback="HOSTAPP_LEGACY_DATASET",
            ),
            repo_paths=RepoPaths(
                base_dir=host_root,
                fixtures_dir=host_root / "fixtures",
                artifacts_dir=host_root / "artifacts",
                config_dir=host_root / "config",
                pdf_pipeline_config_path=host_root / "config" / "pipeline.yaml",
                datasets_container_dir=host_root / "fixtures" / "datasets",
            ),
        ),
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            datasets_response = await client.get("/datasets")
            assert datasets_response.status_code == 200
            assert datasets_response.json() == {
                "datasets": [
                    {
                        "name": "host_dataset_v1",
                        "dataset_id": "host-dataset-id-v1",
                        "pdf_filename": "host-one.pdf",
                        "manifest_path": str(selected_dataset_root / "manifest.json"),
                        "root_path": str(selected_dataset_root),
                    },
                    {
                        "name": "host_dataset_v2",
                        "dataset_id": "host-dataset-id-v2",
                        "pdf_filename": "host-two.pdf",
                        "manifest_path": str(other_dataset_root / "manifest.json"),
                        "root_path": str(other_dataset_root),
                    },
                ],
                "selected_dataset": {
                    "name": "host_dataset_v1",
                    "dataset_id": "host-dataset-id-v1",
                    "pdf_filename": "host-one.pdf",
                    "manifest_path": str(selected_dataset_root / "manifest.json"),
                    "root_path": str(selected_dataset_root),
                },
                "selection_mode": "configured",
                "detail": None,
            }

            current_runs_response = await client.get("/runs/current")
            assert current_runs_response.status_code == 200
            current_runs_payload = current_runs_response.json()
            assert [run["run_id"] for run in current_runs_payload["runs"]] == [
                selected_run_root.name,
            ]
            assert current_runs_payload["inferred_dataset_id"] == "host-dataset-id-v1"

    asyncio.run(_exercise_app())


def test_create_backend_app_filters_runs_to_latest_stage_prefix(tmp_path) -> None:
        older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
        older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
        older_manifest_path.parent.mkdir(parents=True)
        older_manifest_path.write_text(
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
        newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
        newer_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
        newer_manifest_path.parent.mkdir(parents=True)
        newer_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
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
        structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
        structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
        structured_manifest_path.parent.mkdir(parents=True)
        structured_manifest_path.write_text(
                """
{
    "run_id": "structured_ingest-20260512T000050Z-c",
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
                        response = await client.get("/runs", params={"latest_per_stage_prefix": "true"})
                        assert response.status_code == 200
                        assert [run["run_id"] for run in response.json()["runs"]] == [
                                newer_run_root.name,
                                structured_run_root.name,
                        ]

        asyncio.run(_exercise_app())


def test_create_backend_app_exposes_current_runs_endpoint(tmp_path) -> None:
        older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
        older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
        older_manifest_path.parent.mkdir(parents=True)
        older_manifest_path.write_text(
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
        newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
        newer_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
        newer_manifest_path.parent.mkdir(parents=True)
        newer_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
    "dataset_id": "demo_dataset_v1",
    "stages": {
        "claim_extraction": {
            "status": "live"
        }
    }
}
""".strip(),
                encoding="utf-8",
        )
        structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
        structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
        structured_manifest_path.parent.mkdir(parents=True)
        structured_manifest_path.write_text(
                """
{
    "run_id": "structured_ingest-20260512T000050Z-c",
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
                        response = await client.get(
                                "/runs/current",
                                params={"dataset_id": "demo_dataset_v1"},
                        )
                        assert response.status_code == 200
                        assert [run["run_id"] for run in response.json()["runs"]] == [
                                newer_run_root.name,
                        ]

        asyncio.run(_exercise_app())


def test_create_backend_app_exposes_current_run_detail_endpoint(tmp_path) -> None:
        older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
        older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
        older_manifest_path.parent.mkdir(parents=True)
        older_manifest_path.write_text(
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
        newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
        newer_pdf_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
        newer_pdf_manifest_path.parent.mkdir(parents=True)
        newer_pdf_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
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
        newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
        newer_claim_manifest_path.parent.mkdir(parents=True)
        newer_claim_manifest_path.write_text(
                """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
    "dataset_id": "demo_dataset_v1",
    "stages": {
        "claim_extraction": {
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
                        response = await client.get(
                                "/runs/current/unstructured_ingest",
                                params={
                                        "dataset_id": "demo_dataset_v1",
                                        "stage_name": "claim_extraction",
                                },
                        )
                        assert response.status_code == 200
                        payload = response.json()
                        assert payload["run"]["run_id"] == newer_run_root.name
                        assert payload["run"]["stage_names"] == ["claim_extraction", "pdf_ingest"]
                        assert [stage["stage_name"] for stage in payload["stages"]] == [
                                "claim_extraction"
                        ]

        asyncio.run(_exercise_app())


def test_create_backend_app_defaults_current_run_routes_to_configured_dataset(
    tmp_path,
    monkeypatch,
) -> None:
    selected_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    selected_claim_manifest_path = selected_run_root / "claim_extraction" / "manifest.json"
    selected_claim_manifest_path.parent.mkdir(parents=True)
    selected_claim_manifest_path.write_text(
        """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
    "dataset_id": "resolved-demo-dataset",
    "stages": {
        "claim_extraction": {
            "status": "live"
        }
    }
}
""".strip(),
        encoding="utf-8",
    )
    other_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    other_manifest_path = other_run_root / "structured_ingest" / "manifest.json"
    other_manifest_path.parent.mkdir(parents=True)
    other_manifest_path.write_text(
        """
{
    "run_id": "structured_ingest-20260512T000050Z-c",
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

    monkeypatch.setattr(
        "power_atlas.backend_run_catalog.resolve_backend_dataset_catalog",
        lambda settings, **_: importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogResult(
            datasets=[],
            selected_dataset=importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogEntry(
                name="demo_dataset_v1",
                dataset_id="resolved-demo-dataset",
                pdf_filename="example.pdf",
                manifest_path="/tmp/manifest.json",
                root_path="/tmp/dataset",
            ),
            selection_mode="configured",
        ),
    )
    custom_app = create_backend_app(
        environ={
            "POWER_ATLAS_OUTPUT_DIR": str(tmp_path),
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            current_runs_response = await client.get("/runs/current")
            assert current_runs_response.status_code == 200
            current_runs_payload = current_runs_response.json()
            assert [run["run_id"] for run in current_runs_payload["runs"]] == [
                selected_run_root.name,
            ]
            assert current_runs_payload["inferred_dataset_id"] == "resolved-demo-dataset"

            current_detail_response = await client.get(
                "/runs/current/unstructured_ingest",
                params={"stage_name": "claim_extraction"},
            )
            assert current_detail_response.status_code == 200
            detail_payload = current_detail_response.json()
            assert detail_payload["run"]["run_id"] == selected_run_root.name
            assert detail_payload["inferred_dataset_id"] == "resolved-demo-dataset"
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

            current_claim_diagnostics_response = await client.get(
                "/runs/current/unstructured_ingest/claim-extraction-diagnostics"
            )
            assert current_claim_diagnostics_response.status_code == 404
            assert "was not found" in current_claim_diagnostics_response.json()["detail"]

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


def test_create_backend_app_exposes_claim_extraction_diagnostics_artifact() -> None:
    app_context = build_app_context(
        environ={
            "POWER_ATLAS_OUTPUT_DIR": "/tmp/power-atlas-backend-claim-diagnostics",
        }
    )
    run_root = (
        app_context.settings.output_dir
        / "runs"
        / "unstructured_ingest-20260511T000000Z-test"
        / "claim_extraction_diagnostics"
    )
    run_root.mkdir(parents=True, exist_ok=True)
    artifact_path = (run_root / "claim_extraction_diagnostics.json").resolve()
    artifact_path.write_text(
        """
{
  "status": "live",
  "generated_at": "2026-05-13T12:00:00+00:00",
  "run_id": "unstructured_ingest-20260511T000000Z-test",
  "source_uri": "file:///example/doc.pdf",
  "artifact_path": "ignored-by-reader",
  "participation_summary": {
    "total_edges": 4,
    "edges_by_role": {"subject": 3, "object": 1},
    "total_claims": 5,
    "claims_with_zero_edges": 1,
    "claim_coverage_pct": 80.0
  },
  "match_summary": {
    "total_edges_with_match_method": 3,
    "edges_by_match_method": {"normalized_exact": 2, "list_split": 1}
  },
  "warnings": []
}
        """.strip(),
        encoding="utf-8",
    )
    custom_app = create_backend_app(app_context=app_context)

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/runs/unstructured_ingest-20260511T000000Z-test/claim-extraction-diagnostics"
            )
            assert response.status_code == 200
            assert response.json() == {
                "status": "live",
                "detail": "Claim extraction diagnostics artifact retrieved successfully",
                "run_id": "unstructured_ingest-20260511T000000Z-test",
                "generated_at": "2026-05-13T12:00:00+00:00",
                "source_uri": "file:///example/doc.pdf",
                "artifact_path": str(artifact_path),
                "participation_summary": {
                    "total_edges": 4,
                    "edges_by_role": {"subject": 3, "object": 1},
                    "total_claims": 5,
                    "claims_with_zero_edges": 1,
                    "claim_coverage_pct": 80.0,
                },
                "match_summary": {
                    "total_edges_with_match_method": 3,
                    "edges_by_match_method": {
                        "normalized_exact": 2,
                        "list_split": 1,
                    },
                },
                "warnings": [],
            }

    asyncio.run(_exercise_app())


def test_create_backend_app_exposes_current_claim_extraction_diagnostics_artifact(
    tmp_path,
    monkeypatch,
) -> None:
    selected_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    selected_claim_manifest_path = selected_run_root / "claim_extraction" / "manifest.json"
    selected_claim_manifest_path.parent.mkdir(parents=True)
    selected_claim_manifest_path.write_text(
        """
{
    "run_id": "unstructured_ingest-20260512T000100Z-b",
    "dataset_id": "resolved-demo-dataset",
    "stages": {
        "claim_extraction": {
            "status": "live"
        }
    }
}
""".strip(),
        encoding="utf-8",
    )
    artifact_path = (
        selected_run_root
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        """
{
  "status": "dry_run",
  "generated_at": "2026-05-13T12:00:00+00:00",
  "run_id": "unstructured_ingest-20260512T000100Z-b",
  "source_uri": "file:///example/doc.pdf",
  "artifact_path": "ignored-by-reader",
  "participation_summary": {
    "total_edges": 0,
    "edges_by_role": {},
    "total_claims": 0,
    "claims_with_zero_edges": 0,
    "claim_coverage_pct": null
  },
  "match_summary": {
    "total_edges_with_match_method": 0,
    "edges_by_match_method": {}
  },
  "warnings": ["claim extraction diagnostics skipped in dry_run mode"]
}
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "power_atlas.backend_run_catalog.resolve_backend_dataset_catalog",
        lambda settings, **_: importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogResult(
            datasets=[],
            selected_dataset=importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogEntry(
                name="demo_dataset_v1",
                dataset_id="resolved-demo-dataset",
                pdf_filename="example.pdf",
                manifest_path="/tmp/manifest.json",
                root_path="/tmp/dataset",
            ),
            selection_mode="configured",
        ),
    )
    custom_app = create_backend_app(
        environ={
            "POWER_ATLAS_OUTPUT_DIR": str(tmp_path),
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=custom_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/runs/current/unstructured_ingest/claim-extraction-diagnostics"
            )
            assert response.status_code == 200
            assert response.json() == {
                "status": "dry_run",
                "detail": "Claim extraction diagnostics artifact retrieved successfully",
                "run_id": "unstructured_ingest-20260512T000100Z-b",
                "generated_at": "2026-05-13T12:00:00+00:00",
                "source_uri": "file:///example/doc.pdf",
                "artifact_path": str(artifact_path.resolve()),
                "participation_summary": {
                    "total_edges": 0,
                    "edges_by_role": {},
                    "total_claims": 0,
                    "claims_with_zero_edges": 0,
                    "claim_coverage_pct": None,
                },
                "match_summary": {
                    "total_edges_with_match_method": 0,
                    "edges_by_match_method": {},
                },
                "warnings": [
                    "claim extraction diagnostics skipped in dry_run mode"
                ],
                "inferred_dataset_id": "resolved-demo-dataset",
            }

    asyncio.run(_exercise_app())