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
            "        if getattr(route, 'path', None) in {'/', '/health', '/graph/status'}",
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
        "paths": ["/", "/graph/status", "/health"],
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
        "paths": ["/", "/consumer-info", "/graph/status", "/health"],
    }


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

    assert json.loads(completed.stdout) == {
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