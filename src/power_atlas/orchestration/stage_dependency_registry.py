from __future__ import annotations

from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.orchestration.demo_planner import (
    IndependentStageOptions,
    IndependentStageResources,
    IndependentStageSpec,
)
from power_atlas.orchestration.independent_stage_runners import (
    build_independent_stage_specs,
)


def make_bound_independent_stage_runner(
    impl: Callable[..., dict[str, Any]],
    *,
    keyword_name: str,
    resolve_dependency: Callable[[], Callable[..., dict[str, Any]]],
) -> Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]]:
    def _runner(
        request_context: RequestContext,
        stage_run_id: str,
        resources: IndependentStageResources,
        options: IndependentStageOptions,
    ) -> dict[str, Any]:
        return impl(
            request_context,
            stage_run_id,
            resources,
            options,
            **{keyword_name: resolve_dependency()},
        )

    return _runner


def build_demo_independent_stage_specs(
    *,
    run_independent_structured_ingest_stage_impl: Callable[..., dict[str, Any]],
    resolve_run_structured_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    run_independent_pdf_ingest_stage_impl: Callable[..., dict[str, Any]],
    resolve_run_pdf_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    run_independent_claim_extraction_stage_impl: Callable[..., dict[str, Any]],
    resolve_run_claim_extraction_request_context: Callable[[], Callable[..., dict[str, Any]]],
    run_independent_entity_resolution_stage_impl: Callable[..., dict[str, Any]],
    resolve_run_entity_resolution_request_context: Callable[[], Callable[..., dict[str, Any]]],
    run_independent_ask_stage_impl: Callable[..., dict[str, Any]],
    resolve_run_ask_request_context: Callable[[], Callable[..., dict[str, Any]]],
) -> dict[str, IndependentStageSpec]:
    return build_independent_stage_specs(
        run_independent_structured_ingest_stage=make_bound_independent_stage_runner(
            run_independent_structured_ingest_stage_impl,
            keyword_name="run_structured_ingest_request_context",
            resolve_dependency=resolve_run_structured_ingest_request_context,
        ),
        run_independent_pdf_ingest_stage=make_bound_independent_stage_runner(
            run_independent_pdf_ingest_stage_impl,
            keyword_name="run_pdf_ingest_request_context",
            resolve_dependency=resolve_run_pdf_ingest_request_context,
        ),
        run_independent_claim_extraction_stage=make_bound_independent_stage_runner(
            run_independent_claim_extraction_stage_impl,
            keyword_name="run_claim_extraction_request_context",
            resolve_dependency=resolve_run_claim_extraction_request_context,
        ),
        run_independent_entity_resolution_stage=make_bound_independent_stage_runner(
            run_independent_entity_resolution_stage_impl,
            keyword_name="run_entity_resolution_request_context",
            resolve_dependency=resolve_run_entity_resolution_request_context,
        ),
        run_independent_ask_stage=make_bound_independent_stage_runner(
            run_independent_ask_stage_impl,
            keyword_name="run_ask_request_context",
            resolve_dependency=resolve_run_ask_request_context,
        ),
    )


__all__ = [
    "build_demo_independent_stage_specs",
    "make_bound_independent_stage_runner",
]