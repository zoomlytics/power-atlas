from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from power_atlas.api import BackendAppOptions, BackendGraphQueryService, create_backend_app


@dataclass(frozen=True, slots=True)
class _GraphStatusProbe:
    http_status_code: int
    status: str
    detail: str
    neo4j_uri: str
    database: str


@dataclass(frozen=True, slots=True)
class _GraphSummaryCountsProbe:
    document_count: int
    chunk_count: int
    claim_count: int
    mention_count: int
    cluster_count: int
    canonical_entity_count: int


@dataclass(frozen=True, slots=True)
class _GraphSummaryProbe:
    http_status_code: int
    status: str
    detail: str
    neo4j_uri: str
    database: str
    counts: _GraphSummaryCountsProbe | None = None


class ExampleGraphQueries(BackendGraphQueryService):
    def graph_status(self):
        return _GraphStatusProbe(
            http_status_code=200,
            status="available",
            detail="Example consumer graph service is active",
            neo4j_uri="neo4j://example-consumer:7687",
            database="example",
        )

    def graph_summary(self):
        return _GraphSummaryProbe(
            http_status_code=200,
            status="available",
            detail="Example consumer summary is active",
            neo4j_uri="neo4j://example-consumer:7687",
            database="example",
            counts=_GraphSummaryCountsProbe(
                document_count=2,
                chunk_count=4,
                claim_count=3,
                mention_count=8,
                cluster_count=2,
                canonical_entity_count=1,
            ),
        )

    def run_scoped_graph_counts(self, request):
        raise NotImplementedError(f"not used in example: {request.run_id}")

    def graph_health_summary(self, request):
        raise NotImplementedError(
            f"not used in example: {request.run_id}/{request.alignment_version}"
        )


def build_example_app() -> FastAPI:
    app = create_backend_app(
        BackendAppOptions(
            title="Power Atlas Custom Graph Example",
            version="0.1.0-custom-example",
        ),
        graph_queries=ExampleGraphQueries(),
        environ={},
    )

    @app.get("/consumer-info")
    async def consumer_info() -> dict[str, object]:
        return {
            "consumer": "backend_api_custom_graph_queries",
            "backend_title": app.title,
            "backend_version": app.version,
        }

    return app


async def _snapshot_app(app: FastAPI) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        graph_status = await client.get("/graph/status")
        graph_summary = await client.get("/graph/summary")
        consumer_info = await client.get("/consumer-info")
    return {
        "title": app.title,
        "version": app.version,
        "graph_status": graph_status.json(),
        "graph_summary": graph_summary.json(),
        "consumer_info": consumer_info.json(),
    }


app = build_example_app()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_snapshot_app(app)), sort_keys=True))