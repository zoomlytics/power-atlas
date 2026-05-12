from __future__ import annotations

from fastapi.routing import APIRoute

from power_atlas.api import build_backend_router


def test_build_backend_router_composes_core_and_graph_routes() -> None:
    router = build_backend_router()

    route_methods_by_path = {
        route.path: {method for method in route.methods if method != "HEAD"}
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    assert route_methods_by_path == {
        "/graph/status": {"GET"},
        "/graph/summary": {"GET"},
        "/graph/health-summary": {"POST"},
        "/graph/run-scoped-counts": {"POST"},
        "/health": {"GET"},
        "/": {"GET"},
    }