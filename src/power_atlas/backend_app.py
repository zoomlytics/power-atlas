from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from power_atlas.backend_graph import BackendGraphQueryService, build_backend_graph_query_service
from power_atlas.backend_graph_router import build_backend_graph_router
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
        graph_queries=(graph_queries or build_backend_graph_query_service(resolved_app_context)),
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
    router.include_router(
        build_backend_graph_router(
            get_graph_queries=lambda app: get_backend_runtime(app).graph_queries,
        )
    )

    @router.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        return HealthResponse(status="ok", message="Backend is healthy")

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
    "HealthResponse",
    "RootResponse",
    "backend_router",
    "build_backend_graph_query_service",
    "build_backend_runtime",
    "build_backend_router",
    "create_backend_app",
    "get_backend_runtime",
    "lifespan",
]