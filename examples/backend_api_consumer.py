from __future__ import annotations

import json
import os

from fastapi import FastAPI

from power_atlas.api import BackendAppOptions, create_backend_app


def _example_environ() -> dict[str, str]:
    return {
        "NEO4J_URI": os.environ.get("NEO4J_URI", "neo4j://localhost:7687"),
        "NEO4J_USERNAME": os.environ.get("NEO4J_USERNAME", "neo4j"),
        "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD", "password-not-set"),
        "NEO4J_DATABASE": os.environ.get("NEO4J_DATABASE", "neo4j"),
    }


def build_example_app() -> FastAPI:
    app = create_backend_app(
        BackendAppOptions(
            title="Power Atlas Consumer Example",
            version="0.1.0-example",
            cors_allow_origins=("https://consumer.example",),
        ),
        environ=_example_environ(),
    )

    @app.get("/consumer-info")
    async def consumer_info() -> dict[str, object]:
        return {
            "consumer": "backend_api_consumer",
            "backend_title": app.title,
            "backend_version": app.version,
        }

    return app


app = build_example_app()


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "title": app.title,
                "version": app.version,
                "paths": sorted(
                    route.path
                    for route in app.routes
                    if getattr(route, "path", None)
                    in {
                        "/",
                        "/datasets",
                        "/runs",
                        "/runs/current",
                        "/runs/{run_id}",
                        "/health",
                        "/graph/status",
                        "/consumer-info",
                    }
                ),
            },
            sort_keys=True,
        )
    )