from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from power_atlas.context import AppContext
from power_atlas.graph_health_summary import (
    GraphHealthSummaryRequest,
    GraphHealthSummaryResult,
    resolve_graph_health_summary,
)
from power_atlas.graph_status import GraphStatusResult, resolve_graph_status
from power_atlas.graph_summary import GraphSummaryResult, resolve_graph_summary
from power_atlas.run_scoped_graph_counts import (
    RunScopedGraphCountsRequest,
    RunScopedGraphCountsResult,
    resolve_run_scoped_graph_counts,
)


class BackendGraphQueryService(Protocol):
    def graph_status(self) -> GraphStatusResult: ...

    def graph_summary(self) -> GraphSummaryResult: ...

    def run_scoped_graph_counts(
        self,
        request: RunScopedGraphCountsRequest,
    ) -> RunScopedGraphCountsResult: ...

    def graph_health_summary(
        self,
        request: GraphHealthSummaryRequest,
    ) -> GraphHealthSummaryResult: ...


@dataclass(frozen=True, slots=True)
class DefaultBackendGraphQueryService:
    app_context: AppContext
    graph_status_resolver: Callable[[AppContext], GraphStatusResult]
    graph_summary_resolver: Callable[[AppContext], GraphSummaryResult]
    run_scoped_graph_counts_resolver: Callable[[AppContext, RunScopedGraphCountsRequest], RunScopedGraphCountsResult]
    graph_health_summary_resolver: Callable[[AppContext, GraphHealthSummaryRequest], GraphHealthSummaryResult]

    def graph_status(self) -> GraphStatusResult:
        return self.graph_status_resolver(self.app_context)

    def graph_summary(self) -> GraphSummaryResult:
        return self.graph_summary_resolver(self.app_context)

    def run_scoped_graph_counts(
        self,
        request: RunScopedGraphCountsRequest,
    ) -> RunScopedGraphCountsResult:
        return self.run_scoped_graph_counts_resolver(self.app_context, request)

    def graph_health_summary(
        self,
        request: GraphHealthSummaryRequest,
    ) -> GraphHealthSummaryResult:
        return self.graph_health_summary_resolver(self.app_context, request)


def build_backend_graph_query_service(
    app_context: AppContext,
    *,
    graph_status_resolver: Callable[[AppContext], GraphStatusResult] | None = None,
    graph_summary_resolver: Callable[[AppContext], GraphSummaryResult] | None = None,
    run_scoped_graph_counts_resolver: Callable[[AppContext, RunScopedGraphCountsRequest], RunScopedGraphCountsResult] | None = None,
    graph_health_summary_resolver: Callable[[AppContext, GraphHealthSummaryRequest], GraphHealthSummaryResult] | None = None,
) -> DefaultBackendGraphQueryService:
    return DefaultBackendGraphQueryService(
        app_context=app_context,
        graph_status_resolver=(
            graph_status_resolver
            or (lambda runtime_app_context: resolve_graph_status(settings=runtime_app_context.settings))
        ),
        graph_summary_resolver=(
            graph_summary_resolver
            or (lambda runtime_app_context: resolve_graph_summary(settings=runtime_app_context.settings))
        ),
        run_scoped_graph_counts_resolver=(
            run_scoped_graph_counts_resolver or resolve_run_scoped_graph_counts
        ),
        graph_health_summary_resolver=(
            graph_health_summary_resolver or resolve_graph_health_summary
        ),
    )


__all__ = [
    "BackendGraphQueryService",
    "DefaultBackendGraphQueryService",
    "build_backend_graph_query_service",
]