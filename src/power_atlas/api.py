from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from power_atlas.graph_status import GraphStatusResult, resolve_graph_status
from power_atlas.graph_summary import GraphSummaryCounts, GraphSummaryResult, resolve_graph_summary

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


class RootResponse(BaseModel):
	message: str
	version: str
	docs: str


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
	graph_status_resolver: Callable[[], GraphStatusResult] | None = None,
	graph_summary_resolver: Callable[[], GraphSummaryResult] | None = None,
) -> APIRouter:
	router = APIRouter()
	resolved_graph_status = graph_status_resolver or resolve_graph_status
	resolved_graph_summary = graph_summary_resolver or resolve_graph_summary

	@router.get("/health", response_model=HealthResponse)
	async def health_check() -> HealthResponse:
		return HealthResponse(status="ok", message="Backend is healthy")

	@router.get(
		"/graph/status",
		response_model=GraphStatusResponse,
		responses={503: {"description": "Graph integration is not configured yet"}},
	)
	async def graph_status(response: Response) -> GraphStatusResponse:
		probe = resolved_graph_status()
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
	async def graph_summary(response: Response) -> GraphSummaryResponse:
		probe = resolved_graph_summary()
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
	graph_status_resolver: Callable[[], GraphStatusResult] | None = None,
	graph_summary_resolver: Callable[[], GraphSummaryResult] | None = None,
) -> FastAPI:
	app_options = options or BackendAppOptions()
	selected_router = router
	if selected_router is None:
		selected_router = (
			backend_router
			if app_options.version == DEFAULT_API_VERSION
			and graph_status_resolver is None
			and graph_summary_resolver is None
			else build_backend_router(
				version=app_options.version,
				graph_status_resolver=graph_status_resolver,
				graph_summary_resolver=graph_summary_resolver,
			)
		)

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

	app.include_router(selected_router)

	return app


__all__ = [
	"BackendAppOptions",
	"DEFAULT_API_DESCRIPTION",
	"DEFAULT_API_TITLE",
	"DEFAULT_API_VERSION",
	"DEFAULT_CORS_ALLOW_ORIGINS",
	"GraphSummaryCountsResponse",
	"GraphSummaryResponse",
	"GraphStatusResponse",
	"HealthResponse",
	"RootResponse",
	"backend_router",
	"build_backend_router",
	"create_backend_app",
	"lifespan",
]