from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from power_atlas.api import BackendAppOptions, create_backend_app
from power_atlas.contracts import resolve_dataset_root


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

            datasets_response = await client.get("/datasets")
            assert datasets_response.status_code == 200
            expected_datasets = []
            for dataset_name in ("demo_dataset_v1", "demo_dataset_v2"):
                dataset_root = resolve_dataset_root(dataset_name, environ={})
                expected_datasets.append(
                    {
                        "dataset_id": dataset_root.dataset_id,
                        "manifest_path": str(dataset_root.manifest_path),
                        "name": dataset_name,
                        "pdf_filename": dataset_root.pdf_filename,
                        "root_path": str(dataset_root.root),
                    }
                )
            assert datasets_response.json() == {
                "datasets": expected_datasets,
                "detail": "Multiple datasets are available. Set POWER_ATLAS_DATASET or FIXTURE_DATASET to select one explicitly.",
                "selected_dataset": None,
                "selection_mode": "ambiguous",
            }

            runs_response = await client.get("/runs")
            assert runs_response.status_code == 200
            runs_payload = runs_response.json()
            assert set(runs_payload) == {"output_dir", "runs_root", "runs", "detail"}
            assert isinstance(runs_payload["runs"], list)
            assert runs_payload["output_dir"] == str(Path("artifacts").resolve())
            assert runs_payload["runs_root"] == str((Path("artifacts") / "runs").resolve())

            missing_run_response = await client.get("/runs/unstructured_ingest-test-run")
            assert missing_run_response.status_code == 404
            assert "was not found" in missing_run_response.json()["detail"]

            graph_status_response = await client.get("/graph/status")
            assert graph_status_response.status_code == 503
            assert graph_status_response.json() == {
                "status": "not_configured",
                "detail": "Neo4j password is not configured",
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
            }

    asyncio.run(_exercise_app())


def test_public_api_facade_imports_from_outside_repo_when_installed(tmp_path: Path) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
    repo_src = repo_root / "src"
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    if pythonpath:
        filtered_entries = []
        for raw_entry in pythonpath.split(os.pathsep):
            if not raw_entry:
                continue
            try:
                resolved_entry = Path(raw_entry).resolve()
            except OSError:
                filtered_entries.append(raw_entry)
                continue
            if resolved_entry in {repo_root.resolve(), repo_src.resolve()}:
                continue
            filtered_entries.append(raw_entry)
        if filtered_entries:
            env["PYTHONPATH"] = os.pathsep.join(filtered_entries)
        else:
            env.pop("PYTHONPATH", None)

    script = "\n".join(
        [
            "import json",
            "from power_atlas.api import BackendAppOptions, create_backend_app",
            "app = create_backend_app(BackendAppOptions(version='3.0.0-installed-test'), environ={})",
            "payload = {",
            "    'title': app.title,",
            "    'version': app.version,",
            "    'paths': sorted(",
            "        route.path",
            "        for route in app.routes",
            "        if getattr(route, 'path', None) in {'/', '/datasets', '/runs', '/runs/{run_id}', '/health', '/graph/status'}",
            "    ),",
            "}",
            "print(json.dumps(payload, sort_keys=True))",
        ]
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas API",
        "version": "3.0.0-installed-test",
        "paths": ["/", "/datasets", "/graph/status", "/health", "/runs", "/runs/{run_id}"],
    }


def test_backend_api_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "backend_api_consumer.py")],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas Consumer Example",
        "version": "0.1.0-example",
        "paths": ["/", "/consumer-info", "/datasets", "/graph/status", "/health", "/runs", "/runs/{run_id}"],
    }


def test_public_api_facade_supports_run_detail_endpoint_when_output_dir_has_runs(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
    manifest_path = run_root / "pdf_ingest" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "started_at": "2026-05-12T00:00:00+00:00",
                "finished_at": "2026-05-12T00:01:00+00:00",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    consumer_app = create_backend_app(
        BackendAppOptions(version="2.1.0-test"),
        environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/runs/{run_root.name}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["run"]["run_id"] == run_root.name
            assert payload["run"]["dataset_id"] == "demo_dataset_v1"
            assert payload["stages"][0]["stage_name"] == "pdf_ingest"
            assert payload["stages"][0]["manifest_path"] == str(manifest_path.resolve())

    asyncio.run(_exercise_app())


def test_public_api_facade_supports_filtered_run_queries_when_output_dir_has_runs(
    tmp_path: Path,
) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_pdf_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
    newer_pdf_manifest_path.parent.mkdir(parents=True)
    newer_pdf_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_claim_manifest_path.parent.mkdir(parents=True)
    newer_claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
    structured_manifest_path.parent.mkdir(parents=True)
    structured_manifest_path.write_text(
        json.dumps(
            {
                "run_id": structured_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    consumer_app = create_backend_app(
        BackendAppOptions(version="2.2.0-test"),
        environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            by_dataset = await client.get("/runs", params={"dataset_id": "demo_dataset_v1"})
            assert by_dataset.status_code == 200
            assert [run["run_id"] for run in by_dataset.json()["runs"]] == [
                newer_run_root.name,
                older_run_root.name,
            ]

            by_stage = await client.get("/runs", params={"stage_name": "claim_extraction"})
            assert by_stage.status_code == 200
            assert [run["run_id"] for run in by_stage.json()["runs"]] == [newer_run_root.name]

            latest_per_prefix = await client.get(
                "/runs",
                params={"latest_per_stage_prefix": "true"},
            )
            assert latest_per_prefix.status_code == 200
            assert [run["run_id"] for run in latest_per_prefix.json()["runs"]] == [
                newer_run_root.name,
                structured_run_root.name,
            ]

            detail_by_stage = await client.get(
                f"/runs/{newer_run_root.name}",
                params={"stage_name": "claim_extraction"},
            )
            assert detail_by_stage.status_code == 200
            detail_payload = detail_by_stage.json()
            assert detail_payload["run"]["stage_names"] == ["claim_extraction", "pdf_ingest"]
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

    asyncio.run(_exercise_app())


def test_backend_api_custom_graph_queries_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_custom_graph_queries.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "consumer_info": {
            "backend_title": "Power Atlas Custom Graph Example",
            "backend_version": "0.1.0-custom-example",
            "consumer": "backend_api_custom_graph_queries",
        },
        "graph_status": {
            "database": "example",
            "detail": "Example consumer graph service is active",
            "neo4j_uri": "neo4j://example-consumer:7687",
            "status": "available",
        },
        "graph_summary": {
            "counts": {
                "canonical_entity_count": 1,
                "chunk_count": 4,
                "claim_count": 3,
                "cluster_count": 2,
                "document_count": 2,
                "mention_count": 8,
            },
            "database": "example",
            "detail": "Example consumer summary is active",
            "neo4j_uri": "neo4j://example-consumer:7687",
            "status": "available",
        },
        "title": "Power Atlas Custom Graph Example",
        "version": "0.1.0-custom-example",
    }


def test_backend_api_composed_app_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_composed_app.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload == {
        "backend_datasets": {
            "dataset_names": ["demo_dataset_v1", "demo_dataset_v2"],
            "selected_dataset_name": None,
            "selection_mode": "ambiguous",
        },
        "backend_run_detail": {
            "run_id": "unstructured_ingest-20260512T000100Z-b",
            "run_stage_names": ["claim_extraction", "pdf_ingest"],
            "stages": ["claim_extraction"],
        },
        "backend_runs": {
            "detail": None,
            "run_ids": ["unstructured_ingest-20260512T000100Z-b"],
            "runs_root": payload["backend_runs"]["runs_root"],
        },
        "backend_graph_status": {
            "database": "neo4j",
            "detail": "Neo4j password is not configured",
            "neo4j_uri": "neo4j://localhost:7687",
            "status": "not_configured",
        },
        "backend_health": {
            "message": "Backend is healthy",
            "status": "ok",
        },
        "backend_root": {
            "docs": "/docs",
            "message": "Power Atlas API",
            "version": "0.1.0-mounted",
        },
        "host_info": {
            "host": "backend_api_composed_app",
            "host_title": "Host Application",
            "host_version": "1.0.0-host",
        },
    }
    assert payload["backend_runs"]["runs_root"].endswith("/runs")


def test_backend_api_guarded_app_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_guarded_app.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "authorized_health": {
            "body": {
                "message": "Backend is healthy",
                "status": "ok",
            },
            "status_code": 200,
        },
        "host_info": {
            "host": "backend_api_guarded_app",
            "host_title": "Guarded Host Application",
            "host_version": "1.0.0-guarded",
        },
        "unauthorized_health": {
            "body": {"detail": "Missing or invalid atlas token"},
            "status_code": 401,
        },
    }