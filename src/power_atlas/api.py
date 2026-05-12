from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from power_atlas.bootstrap import build_app_context
from power_atlas.context import AppContext
from power_atlas.graph_status import GraphStatusResult, resolve_graph_status
from power_atlas.graph_health_summary import (
	GraphHealthAlignmentSummary,
	GraphHealthMentionSummary,
	GraphHealthParticipationSummary,
	GraphHealthSummaryRequest,
	GraphHealthSummaryResult,
	resolve_graph_health_summary,
)
from power_atlas.graph_summary import GraphSummaryCounts, GraphSummaryResult, resolve_graph_summary
from power_atlas.run_scoped_graph_counts import (
	RunScopedGraphCounts,
	RunScopedGraphCountsRequest,
	RunScopedGraphCountsResult,
	resolve_run_scoped_graph_counts,
)

DEFAULT_API_TITLE = "Power Atlas API"
DEFAULT_API_DESCRIPTION = "Backend API for Power Atlas"
DEFAULT_API_VERSION = "0.1.0"
DEFAULT_CORS_ALLOW_ORIGINS = ("http://localhost:3000",)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
	status: str
	message: str


class GraphStatusResponse(BaseModel):
	status: str
	detail: str
	neo4j_uri: str | None = None
	database: str | None = None


class GraphSummaryCountsResponse(BaseModel):
	document_count: int
	chunk_count: int
	claim_count: int
	mention_count: int
	cluster_count: int
	canonical_entity_count: int


class GraphSummaryResponse(BaseModel):
	status: str
	detail: str
	neo4j_uri: str | None = None
	database: str | None = None
	counts: GraphSummaryCountsResponse | None = None


class RunScopedGraphCountsRequestBody(BaseModel):
	run_id: str = Field(min_length=1)


class RunScopedGraphCountsResponseBody(BaseModel):
	chunk_count: int
	claim_count: int
	mention_count: int
	cluster_count: int


class RunScopedGraphCountsResponse(BaseModel):
	status: str
	detail: str
	run_id: str
	neo4j_uri: str
	database: str
	counts: RunScopedGraphCountsResponseBody | None = None


class GraphHealthSummaryRequestBody(BaseModel):
	run_id: str = Field(min_length=1)
	alignment_version: str | None = None


class GraphHealthParticipationSummaryResponse(BaseModel):
	total_edges: int
	edges_by_role: dict[str, int]
	total_claims: int
	claims_with_zero_edges: int
	claim_coverage_pct: float | None


class GraphHealthMentionSummaryResponse(BaseModel):
	total_mentions: int
	clustered_mentions: int
	unclustered_mentions: int
	unresolved_rate_pct: float | None


class GraphHealthAlignmentSummaryResponse(BaseModel):
	total_clusters: int
	aligned_clusters: int
	unaligned_clusters: int
	alignment_coverage_pct: float | None


class GraphHealthSummaryResponse(BaseModel):
	status: str
	detail: str
	run_id: str
	alignment_version: str | None
	neo4j_uri: str
	database: str
	participation_summary: GraphHealthParticipationSummaryResponse | None = None
	mention_summary: GraphHealthMentionSummaryResponse | None = None
	alignment_summary: GraphHealthAlignmentSummaryResponse | None = None


class RootResponse(BaseModel):
	message: str
	version: str
	docs: str


@dataclass(frozen=True, slots=True)
class BackendRuntime:
	app_context: AppContext
	graph_status_resolver: Callable[[AppContext], GraphStatusResult]
	graph_health_summary_resolver: Callable[[AppContext, GraphHealthSummaryRequest], GraphHealthSummaryResult]
	graph_summary_resolver: Callable[[AppContext], GraphSummaryResult]
	run_scoped_graph_counts_resolver: Callable[[AppContext, RunScopedGraphCountsRequest], RunScopedGraphCountsResult]


def build_backend_runtime(
	*,
	app_context: AppContext | None = None,
	environ: Mapping[str, str] | None = None,
	graph_status_resolver: Callable[[AppContext], GraphStatusResult] | None = None,
	graph_health_summary_resolver: Callable[[AppContext, GraphHealthSummaryRequest], GraphHealthSummaryResult] | None = None,
	graph_summary_resolver: Callable[[AppContext], GraphSummaryResult] | None = None,
	run_scoped_graph_counts_resolver: Callable[[AppContext, RunScopedGraphCountsRequest], RunScopedGraphCountsResult] | None = None,
) -> BackendRuntime:
	resolved_app_context = (
		build_app_context(environ=environ) if app_context is None else app_context
	)
	return BackendRuntime(
		app_context=resolved_app_context,
		graph_status_resolver=(
			graph_status_resolver
			or (lambda runtime_app_context: resolve_graph_status(settings=runtime_app_context.settings))
		),
		graph_health_summary_resolver=(
			graph_health_summary_resolver or resolve_graph_health_summary
		),
		graph_summary_resolver=(
			graph_summary_resolver
			or (lambda runtime_app_context: resolve_graph_summary(settings=runtime_app_context.settings))
		),
		run_scoped_graph_counts_resolver=(
			run_scoped_graph_counts_resolver or resolve_run_scoped_graph_counts
		),
	)


def get_backend_runtime(app: FastAPI) -> BackendRuntime:
	runtime = getattr(app.state, "backend_runtime", None)
	if isinstance(runtime, BackendRuntime):
		return runtime
	raise RuntimeError("Backend runtime is not configured on the FastAPI app state")


@dataclass(frozen=True, slots=True)
class BackendAppOptions:
	title: str = DEFAULT_API_TITLE
	description: str = DEFAULT_API_DESCRIPTION
	version: str = DEFAULT_API_VERSION
	cors_allow_origins: tuple[str, ...] = field(
		default_factory=lambda: DEFAULT_CORS_ALLOW_ORIGINS
	)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
	del app
	logger.info("Power Atlas API starting up")
	yield


def build_backend_router(
	*,
	version: str = DEFAULT_API_VERSION,
) -> APIRouter:
	router = APIRouter()

	@router.get("/health", response_model=HealthResponse)
	async def health_check() -> HealthResponse:
		return HealthResponse(status="ok", message="Backend is healthy")

	@router.get(
		"/graph/status",
		response_model=GraphStatusResponse,
		responses={503: {"description": "Graph integration is not configured yet"}},
	)
	async def graph_status(request: Request, response: Response) -> GraphStatusResponse:
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_status_resolver(runtime.app_context)
		response.status_code = probe.http_status_code
		return GraphStatusResponse(
			status=probe.status,
			detail=probe.detail,
			neo4j_uri=probe.neo4j_uri,
			database=probe.database,
		)

	@router.get(
		"/graph/summary",
		response_model=GraphSummaryResponse,
		responses={503: {"description": "Graph summary is unavailable"}},
	)
	async def graph_summary(request: Request, response: Response) -> GraphSummaryResponse:
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_summary_resolver(runtime.app_context)
		response.status_code = probe.http_status_code
		counts = None
		if probe.counts is not None:
			counts = GraphSummaryCountsResponse(
				document_count=probe.counts.document_count,
				chunk_count=probe.counts.chunk_count,
				claim_count=probe.counts.claim_count,
				mention_count=probe.counts.mention_count,
				cluster_count=probe.counts.cluster_count,
				canonical_entity_count=probe.counts.canonical_entity_count,
			)
		return GraphSummaryResponse(
			status=probe.status,
			detail=probe.detail,
			neo4j_uri=probe.neo4j_uri,
			database=probe.database,
			counts=counts,
		)

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
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_health_summary_resolver(
			runtime.app_context,
			GraphHealthSummaryRequest(
				run_id=body.run_id,
				alignment_version=body.alignment_version,
			),
		)
		response.status_code = probe.http_status_code
		participation_summary = None
		mention_summary = None
		alignment_summary = None
		if probe.participation_summary is not None:
			participation_summary = GraphHealthParticipationSummaryResponse(
				total_edges=probe.participation_summary.total_edges,
				edges_by_role=probe.participation_summary.edges_by_role,
				total_claims=probe.participation_summary.total_claims,
				claims_with_zero_edges=probe.participation_summary.claims_with_zero_edges,
				claim_coverage_pct=probe.participation_summary.claim_coverage_pct,
			)
		if probe.mention_summary is not None:
			mention_summary = GraphHealthMentionSummaryResponse(
				total_mentions=probe.mention_summary.total_mentions,
				clustered_mentions=probe.mention_summary.clustered_mentions,
				unclustered_mentions=probe.mention_summary.unclustered_mentions,
				unresolved_rate_pct=probe.mention_summary.unresolved_rate_pct,
			)
		if probe.alignment_summary is not None:
			alignment_summary = GraphHealthAlignmentSummaryResponse(
				total_clusters=probe.alignment_summary.total_clusters,
				aligned_clusters=probe.alignment_summary.aligned_clusters,
				unaligned_clusters=probe.alignment_summary.unaligned_clusters,
				alignment_coverage_pct=probe.alignment_summary.alignment_coverage_pct,
			)
		return GraphHealthSummaryResponse(
			status=probe.status,
			detail=probe.detail,
			run_id=probe.run_id,
			alignment_version=probe.alignment_version,
			neo4j_uri=probe.neo4j_uri,
			database=probe.database,
			participation_summary=participation_summary,
			mention_summary=mention_summary,
			alignment_summary=alignment_summary,
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
		runtime = get_backend_runtime(request.app)
		probe = runtime.run_scoped_graph_counts_resolver(
			runtime.app_context,
			RunScopedGraphCountsRequest(run_id=body.run_id),
		)
		response.status_code = probe.http_status_code
		counts = None
		if probe.counts is not None:
			counts = RunScopedGraphCountsResponseBody(
				chunk_count=probe.counts.chunk_count,
				claim_count=probe.counts.claim_count,
				mention_count=probe.counts.mention_count,
				cluster_count=probe.counts.cluster_count,
			)
		return RunScopedGraphCountsResponse(
			status=probe.status,
			detail=probe.detail,
			run_id=probe.run_id,
			neo4j_uri=probe.neo4j_uri,
			database=probe.database,
			counts=counts,
		)

	@router.get("/", response_model=RootResponse)
	async def root() -> RootResponse:
		return RootResponse(
			message=DEFAULT_API_TITLE,
			version=version,
			docs="/docs",
		)

	return router


backend_router = build_backend_router()


def create_backend_app(
	options: BackendAppOptions | None = None,
	*,
	router: APIRouter | None = None,
	runtime: BackendRuntime | None = None,
	app_context: AppContext | None = None,
	environ: Mapping[str, str] | None = None,
	graph_status_resolver: Callable[[AppContext], GraphStatusResult] | None = None,
	graph_health_summary_resolver: Callable[[AppContext, GraphHealthSummaryRequest], GraphHealthSummaryResult] | None = None,
	graph_summary_resolver: Callable[[AppContext], GraphSummaryResult] | None = None,
	run_scoped_graph_counts_resolver: Callable[[AppContext, RunScopedGraphCountsRequest], RunScopedGraphCountsResult] | None = None,
) -> FastAPI:
	app_options = options or BackendAppOptions()
	resolved_runtime = runtime or build_backend_runtime(
		app_context=app_context,
		environ=environ,
		graph_status_resolver=graph_status_resolver,
		graph_health_summary_resolver=graph_health_summary_resolver,
		graph_summary_resolver=graph_summary_resolver,
		run_scoped_graph_counts_resolver=run_scoped_graph_counts_resolver,
	)
	selected_router = router or build_backend_router(version=app_options.version)

	app = FastAPI(
		title=app_options.title,
		description=app_options.description,
		version=app_options.version,
		lifespan=lifespan,
	)

	app.add_middleware(
		CORSMiddleware,
		allow_origins=list(app_options.cors_allow_origins),
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	app.state.backend_runtime = resolved_runtime
	app.include_router(selected_router)

	return app


__all__ = [
	"BackendAppOptions",
	"BackendRuntime",
	"DEFAULT_API_DESCRIPTION",
	"DEFAULT_API_TITLE",
	"DEFAULT_API_VERSION",
	"DEFAULT_CORS_ALLOW_ORIGINS",
	"GraphHealthAlignmentSummaryResponse",
	"GraphHealthMentionSummaryResponse",
	"GraphHealthParticipationSummaryResponse",
	"GraphHealthSummaryRequestBody",
	"GraphHealthSummaryResponse",
	"GraphSummaryCountsResponse",
	"GraphSummaryResponse",
	"GraphStatusResponse",
	"HealthResponse",
	"RunScopedGraphCountsRequestBody",
	"RunScopedGraphCountsResponse",
	"RunScopedGraphCountsResponseBody",
	"RootResponse",
	"backend_router",
	"build_backend_runtime",
	"build_backend_router",
	"create_backend_app",
	"get_backend_runtime",
	"lifespan",
]