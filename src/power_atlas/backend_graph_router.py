from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Request, Response

from power_atlas.backend_graph import (
    BackendGraphQueryService,
    GraphHealthSummaryRequest,
    RunScopedGraphCountsRequest,
)
from power_atlas.backend_graph_api_models import (
    GraphHealthSummaryRequestBody,
    GraphHealthSummaryResponse,
    GraphStatusResponse,
    GraphSummaryResponse,
    RunScopedGraphCountsRequestBody,
    RunScopedGraphCountsResponse,
)
from power_atlas.backend_graph_response_adapters import (
    build_graph_health_summary_response_payload,
    build_graph_status_response_payload,
    build_graph_summary_response_payload,
    build_run_scoped_graph_counts_response_payload,
)


def build_backend_graph_router(
    *,
    get_graph_queries: Callable[[FastAPI], BackendGraphQueryService],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/graph/status",
        response_model=GraphStatusResponse,
        responses={503: {"description": "Graph integration is not configured yet"}},
    )
    async def graph_status(request: Request, response: Response) -> GraphStatusResponse:
        probe = get_graph_queries(request.app).graph_status()
        response.status_code = probe.http_status_code
        return GraphStatusResponse(**build_graph_status_response_payload(probe))

    @router.get(
        "/graph/summary",
        response_model=GraphSummaryResponse,
        responses={503: {"description": "Graph summary is unavailable"}},
    )
    async def graph_summary(request: Request, response: Response) -> GraphSummaryResponse:
        probe = get_graph_queries(request.app).graph_summary()
        response.status_code = probe.http_status_code
        return GraphSummaryResponse(**build_graph_summary_response_payload(probe))

    @router.post(
        "/graph/health-summary",
        response_model=GraphHealthSummaryResponse,
        responses={404: {"description": "Graph health data was not found"}, 503: {"description": "Graph health summary is unavailable"}},
    )
    async def graph_health_summary(
        request: Request,
        response: Response,
        body: GraphHealthSummaryRequestBody,
    ) -> GraphHealthSummaryResponse:
        probe = get_graph_queries(request.app).graph_health_summary(
            GraphHealthSummaryRequest(
                run_id=body.run_id,
                alignment_version=body.alignment_version,
            ),
        )
        response.status_code = probe.http_status_code
        return GraphHealthSummaryResponse(
            **build_graph_health_summary_response_payload(probe)
        )

    @router.post(
        "/graph/run-scoped-counts",
        response_model=RunScopedGraphCountsResponse,
        responses={404: {"description": "Run-scoped graph data was not found"}, 503: {"description": "Run-scoped graph counts are unavailable"}},
    )
    async def run_scoped_graph_counts(
        request: Request,
        response: Response,
        body: RunScopedGraphCountsRequestBody,
    ) -> RunScopedGraphCountsResponse:
        probe = get_graph_queries(request.app).run_scoped_graph_counts(
            RunScopedGraphCountsRequest(run_id=body.run_id),
        )
        response.status_code = probe.http_status_code
        return RunScopedGraphCountsResponse(
            **build_run_scoped_graph_counts_response_payload(probe)
        )

    return router


__all__ = ["build_backend_graph_router"]