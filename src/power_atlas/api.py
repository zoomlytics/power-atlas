from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


from power_atlas.backend_graph import (
	BackendGraphQueryService,
	GraphHealthSummaryRequest,
	RunScopedGraphCountsRequest,
	build_backend_graph_query_service,
)
from power_atlas.backend_graph_response_adapters import (
	build_graph_health_summary_response_payload,
	build_graph_status_response_payload,
	build_graph_summary_response_payload,
	build_run_scoped_graph_counts_response_payload,
)
from power_atlas.bootstrap import build_app_context
from power_atlas.context import AppContext

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
	graph_queries: BackendGraphQueryService


def build_backend_runtime(
	*,
	app_context: AppContext | None = None,
	environ: Mapping[str, str] | None = None,
	graph_queries: BackendGraphQueryService | None = None,
) -> BackendRuntime:
	resolved_app_context = (
		build_app_context(environ=environ) if app_context is None else app_context
	)
	return BackendRuntime(
		app_context=resolved_app_context,
		graph_queries=(
			graph_queries
			or build_backend_graph_query_service(resolved_app_context)
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
		probe = runtime.graph_queries.graph_status()
		response.status_code = probe.http_status_code
		return GraphStatusResponse(**build_graph_status_response_payload(probe))

	@router.get(
		"/graph/summary",
		response_model=GraphSummaryResponse,
		responses={503: {"description": "Graph summary is unavailable"}},
	)
	async def graph_summary(request: Request, response: Response) -> GraphSummaryResponse:
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_queries.graph_summary()
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
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_queries.graph_health_summary(
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
		runtime = get_backend_runtime(request.app)
		probe = runtime.graph_queries.run_scoped_graph_counts(
			RunScopedGraphCountsRequest(run_id=body.run_id),
		)
		response.status_code = probe.http_status_code
		return RunScopedGraphCountsResponse(
			**build_run_scoped_graph_counts_response_payload(probe)
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
	graph_queries: BackendGraphQueryService | None = None,
) -> FastAPI:
	app_options = options or BackendAppOptions()
	resolved_runtime = runtime or build_backend_runtime(
		app_context=app_context,
		environ=environ,
		graph_queries=graph_queries,
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
	"BackendGraphQueryService",
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
	"build_backend_graph_query_service",
	"build_backend_runtime",
	"build_backend_router",
	"create_backend_app",
	"get_backend_runtime",
	"lifespan",
]