from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from power_atlas.backend_dataset_catalog import resolve_backend_dataset_catalog
from power_atlas.backend_graph import BackendGraphQueryService, build_backend_graph_query_service
from power_atlas.backend_graph_router import build_backend_graph_router
from power_atlas.backend_run_catalog import (
    resolve_backend_current_run_catalog,
    resolve_backend_current_run_details,
    resolve_backend_run_catalog,
    resolve_backend_run_details,
)
from power_atlas.claim_extraction_diagnostics_artifact import (
    resolve_current_claim_extraction_diagnostics_artifact,
    resolve_claim_extraction_diagnostics_artifact,
)
from power_atlas.bootstrap import AppBaseline, build_app_context
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


class DatasetResponse(BaseModel):
    name: str
    dataset_id: str
    pdf_filename: str
    manifest_path: str
    root_path: str


class DatasetsResponse(BaseModel):
    datasets: list[DatasetResponse]
    selected_dataset: DatasetResponse | None = None
    selection_mode: str
    detail: str | None = None


class RunResponse(BaseModel):
    run_id: str
    dataset_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    stage_names: list[str]
    root_path: str


class RunsResponse(BaseModel):
    output_dir: str
    runs_root: str
    runs: list[RunResponse]
    detail: str | None = None


class CurrentRunsResponse(RunsResponse):
    inferred_dataset_id: str | None = None


class RunStageResponse(BaseModel):
    stage_name: str
    status: str | None = None
    manifest_path: str | None = None
    manifest: dict[str, Any] | None = None


class RunDetailResponse(BaseModel):
    output_dir: str
    runs_root: str
    run: RunResponse
    stages: list[RunStageResponse]


class CurrentRunDetailResponse(RunDetailResponse):
    inferred_dataset_id: str | None = None


class ClaimExtractionDiagnosticsParticipationSummaryResponse(BaseModel):
    total_edges: int
    edges_by_role: dict[str, int]
    total_claims: int
    claims_with_zero_edges: int
    claim_coverage_pct: float | None


class ClaimExtractionDiagnosticsMatchSummaryResponse(BaseModel):
    total_edges_with_match_method: int
    edges_by_match_method: dict[str, int]


class ClaimExtractionDiagnosticsResponse(BaseModel):
    status: str
    detail: str
    run_id: str
    generated_at: str | None = None
    source_uri: str | None = None
    artifact_path: str
    participation_summary: ClaimExtractionDiagnosticsParticipationSummaryResponse | None = None
    match_summary: ClaimExtractionDiagnosticsMatchSummaryResponse | None = None
    warnings: list[str]


class CurrentClaimExtractionDiagnosticsResponse(ClaimExtractionDiagnosticsResponse):
    inferred_dataset_id: str | None = None


@dataclass(frozen=True, slots=True)
class BackendRuntime:
    app_context: AppContext
    graph_queries: BackendGraphQueryService
    app_baseline: AppBaseline | None = None


def build_backend_runtime(
    *,
    app_context: AppContext | None = None,
    environ: Mapping[str, str] | None = None,
    graph_queries: BackendGraphQueryService | None = None,
    app_baseline: AppBaseline | None = None,
) -> BackendRuntime:
    resolved_app_context = (
        build_app_context(environ=environ, app_baseline=app_baseline)
        if app_context is None
        else app_context
    )
    return BackendRuntime(
        app_context=resolved_app_context,
        graph_queries=(graph_queries or build_backend_graph_query_service(resolved_app_context)),
        app_baseline=app_baseline,
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

    @router.get("/datasets", response_model=DatasetsResponse)
    async def datasets(request: Request) -> DatasetsResponse:
        runtime = get_backend_runtime(request.app)
        dataset_catalog = resolve_backend_dataset_catalog(
            runtime.app_context.settings,
            repo_paths=(None if runtime.app_baseline is None else runtime.app_baseline.repo_paths),
        )
        selected_dataset = None
        if dataset_catalog.selected_dataset is not None:
            selected_dataset = DatasetResponse(
                name=dataset_catalog.selected_dataset.name,
                dataset_id=dataset_catalog.selected_dataset.dataset_id,
                pdf_filename=dataset_catalog.selected_dataset.pdf_filename,
                manifest_path=dataset_catalog.selected_dataset.manifest_path,
                root_path=dataset_catalog.selected_dataset.root_path,
            )
        return DatasetsResponse(
            datasets=[
                DatasetResponse(
                    name=dataset.name,
                    dataset_id=dataset.dataset_id,
                    pdf_filename=dataset.pdf_filename,
                    manifest_path=dataset.manifest_path,
                    root_path=dataset.root_path,
                )
                for dataset in dataset_catalog.datasets
            ],
            selected_dataset=selected_dataset,
            selection_mode=dataset_catalog.selection_mode,
            detail=dataset_catalog.detail,
        )

    @router.get("/runs", response_model=RunsResponse)
    async def runs(
        request: Request,
        dataset_id: str | None = None,
        stage_name: str | None = None,
        latest_per_stage_prefix: bool = False,
    ) -> RunsResponse:
        run_catalog = resolve_backend_run_catalog(
            get_backend_runtime(request.app).app_context.settings,
            dataset_id=dataset_id,
            stage_name=stage_name,
            latest_per_stage_prefix=latest_per_stage_prefix,
        )
        return RunsResponse(
            output_dir=run_catalog.output_dir,
            runs_root=run_catalog.runs_root,
            runs=[
                RunResponse(
                    run_id=run.run_id,
                    dataset_id=run.dataset_id,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    stage_names=run.stage_names,
                    root_path=run.root_path,
                )
                for run in run_catalog.runs
            ],
            detail=run_catalog.detail,
        )

    @router.get("/runs/current", response_model=CurrentRunsResponse)
    async def current_runs(
        request: Request,
        dataset_id: str | None = None,
        stage_name: str | None = None,
    ) -> CurrentRunsResponse:
        runtime = get_backend_runtime(request.app)
        run_catalog = resolve_backend_current_run_catalog(
            runtime.app_context.settings,
            dataset_id=dataset_id,
            stage_name=stage_name,
            repo_paths=(None if runtime.app_baseline is None else runtime.app_baseline.repo_paths),
        )
        return CurrentRunsResponse(
            output_dir=run_catalog.output_dir,
            runs_root=run_catalog.runs_root,
            runs=[
                RunResponse(
                    run_id=run.run_id,
                    dataset_id=run.dataset_id,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    stage_names=run.stage_names,
                    root_path=run.root_path,
                )
                for run in run_catalog.runs
            ],
            detail=run_catalog.detail,
            inferred_dataset_id=run_catalog.inferred_dataset_id,
        )

    @router.get("/runs/current/{stage_prefix}", response_model=CurrentRunDetailResponse)
    async def current_run_detail(
        stage_prefix: str,
        request: Request,
        dataset_id: str | None = None,
        stage_name: str | None = None,
    ) -> CurrentRunDetailResponse:
        runtime = get_backend_runtime(request.app)
        try:
            run_detail_result = resolve_backend_current_run_details(
                runtime.app_context.settings,
                stage_prefix,
                dataset_id=dataset_id,
                stage_name=stage_name,
                repo_paths=(None if runtime.app_baseline is None else runtime.app_baseline.repo_paths),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return CurrentRunDetailResponse(
            output_dir=run_detail_result.output_dir,
            runs_root=run_detail_result.runs_root,
            run=RunResponse(
                run_id=run_detail_result.run.run_id,
                dataset_id=run_detail_result.run.dataset_id,
                started_at=run_detail_result.run.started_at,
                finished_at=run_detail_result.run.finished_at,
                stage_names=run_detail_result.run.stage_names,
                root_path=run_detail_result.run.root_path,
            ),
            stages=[
                RunStageResponse(
                    stage_name=stage.stage_name,
                    status=stage.status,
                    manifest_path=stage.manifest_path,
                    manifest=stage.manifest,
                )
                for stage in run_detail_result.stages
            ],
            inferred_dataset_id=run_detail_result.inferred_dataset_id,
        )

    @router.get(
        "/runs/current/{stage_prefix}/claim-extraction-diagnostics",
        response_model=CurrentClaimExtractionDiagnosticsResponse,
    )
    async def current_claim_extraction_diagnostics(
        stage_prefix: str,
        request: Request,
        dataset_id: str | None = None,
    ) -> CurrentClaimExtractionDiagnosticsResponse:
        runtime = get_backend_runtime(request.app)
        try:
            result = resolve_current_claim_extraction_diagnostics_artifact(
                runtime.app_context.settings,
                stage_prefix,
                dataset_id=dataset_id,
                repo_paths=(None if runtime.app_baseline is None else runtime.app_baseline.repo_paths),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return CurrentClaimExtractionDiagnosticsResponse(
            status=result.status,
            detail=result.detail,
            run_id=result.run_id,
            generated_at=result.generated_at,
            source_uri=result.source_uri,
            artifact_path=result.artifact_path,
            participation_summary=(
                None
                if result.participation_summary is None
                else ClaimExtractionDiagnosticsParticipationSummaryResponse(
                    total_edges=result.participation_summary.total_edges,
                    edges_by_role=result.participation_summary.edges_by_role,
                    total_claims=result.participation_summary.total_claims,
                    claims_with_zero_edges=result.participation_summary.claims_with_zero_edges,
                    claim_coverage_pct=result.participation_summary.claim_coverage_pct,
                )
            ),
            match_summary=(
                None
                if result.match_summary is None
                else ClaimExtractionDiagnosticsMatchSummaryResponse(
                    total_edges_with_match_method=result.match_summary.total_edges_with_match_method,
                    edges_by_match_method=result.match_summary.edges_by_match_method,
                )
            ),
            warnings=[] if result.warnings is None else result.warnings,
            inferred_dataset_id=result.inferred_dataset_id,
        )

    @router.get("/runs/{run_id}", response_model=RunDetailResponse)
    async def run_detail(
        run_id: str,
        request: Request,
        stage_name: str | None = None,
    ) -> RunDetailResponse:
        try:
            run_detail_result = resolve_backend_run_details(
                get_backend_runtime(request.app).app_context.settings,
                run_id,
                stage_name=stage_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return RunDetailResponse(
            output_dir=run_detail_result.output_dir,
            runs_root=run_detail_result.runs_root,
            run=RunResponse(
                run_id=run_detail_result.run.run_id,
                dataset_id=run_detail_result.run.dataset_id,
                started_at=run_detail_result.run.started_at,
                finished_at=run_detail_result.run.finished_at,
                stage_names=run_detail_result.run.stage_names,
                root_path=run_detail_result.run.root_path,
            ),
            stages=[
                RunStageResponse(
                    stage_name=stage.stage_name,
                    status=stage.status,
                    manifest_path=stage.manifest_path,
                    manifest=stage.manifest,
                )
                for stage in run_detail_result.stages
            ],
        )

    @router.get(
        "/runs/{run_id}/claim-extraction-diagnostics",
        response_model=ClaimExtractionDiagnosticsResponse,
    )
    async def claim_extraction_diagnostics(
        run_id: str,
        request: Request,
    ) -> ClaimExtractionDiagnosticsResponse:
        try:
            result = resolve_claim_extraction_diagnostics_artifact(
                get_backend_runtime(request.app).app_context.settings,
                run_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return ClaimExtractionDiagnosticsResponse(
            status=result.status,
            detail=result.detail,
            run_id=result.run_id,
            generated_at=result.generated_at,
            source_uri=result.source_uri,
            artifact_path=result.artifact_path,
            participation_summary=(
                None
                if result.participation_summary is None
                else ClaimExtractionDiagnosticsParticipationSummaryResponse(
                    total_edges=result.participation_summary.total_edges,
                    edges_by_role=result.participation_summary.edges_by_role,
                    total_claims=result.participation_summary.total_claims,
                    claims_with_zero_edges=result.participation_summary.claims_with_zero_edges,
                    claim_coverage_pct=result.participation_summary.claim_coverage_pct,
                )
            ),
            match_summary=(
                None
                if result.match_summary is None
                else ClaimExtractionDiagnosticsMatchSummaryResponse(
                    total_edges_with_match_method=result.match_summary.total_edges_with_match_method,
                    edges_by_match_method=result.match_summary.edges_by_match_method,
                )
            ),
            warnings=[] if result.warnings is None else result.warnings,
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
    app_baseline: AppBaseline | None = None,
) -> FastAPI:
    app_options = options or BackendAppOptions()
    resolved_runtime = runtime or build_backend_runtime(
        app_context=app_context,
        environ=environ,
        graph_queries=graph_queries,
        app_baseline=app_baseline,
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
    "ClaimExtractionDiagnosticsMatchSummaryResponse",
    "ClaimExtractionDiagnosticsParticipationSummaryResponse",
    "ClaimExtractionDiagnosticsResponse",
    "CurrentClaimExtractionDiagnosticsResponse",
    "CurrentRunDetailResponse",
    "CurrentRunsResponse",
    "DEFAULT_API_DESCRIPTION",
    "DEFAULT_API_TITLE",
    "DEFAULT_API_VERSION",
    "DEFAULT_CORS_ALLOW_ORIGINS",
    "DatasetResponse",
    "DatasetsResponse",
    "HealthResponse",
    "CurrentRunDetailResponse",
    "CurrentRunsResponse",
    "RunDetailResponse",
    "RunResponse",
    "RootResponse",
    "RunStageResponse",
    "RunsResponse",
    "backend_router",
    "build_backend_graph_query_service",
    "build_backend_runtime",
    "build_backend_router",
    "create_backend_app",
    "get_backend_runtime",
    "lifespan",
]