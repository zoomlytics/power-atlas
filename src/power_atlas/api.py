from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
	detail: str


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


def build_backend_router(*, version: str = DEFAULT_API_VERSION) -> APIRouter:
	router = APIRouter()

	@router.get("/health", response_model=HealthResponse)
	async def health_check() -> HealthResponse:
		return HealthResponse(status="ok", message="Backend is healthy")

	@router.get(
		"/graph/status",
		response_model=GraphStatusResponse,
		status_code=503,
		responses={503: {"description": "Graph integration is not configured yet"}},
	)
	async def graph_status() -> GraphStatusResponse:
		return GraphStatusResponse(detail="Graph integration is not configured yet")

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
) -> FastAPI:
	app_options = options or BackendAppOptions()
	selected_router = router
	if selected_router is None:
		selected_router = (
			backend_router
			if app_options.version == DEFAULT_API_VERSION
			else build_backend_router(version=app_options.version)
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
	"GraphStatusResponse",
	"HealthResponse",
	"RootResponse",
	"backend_router",
	"build_backend_router",
	"create_backend_app",
	"lifespan",
]