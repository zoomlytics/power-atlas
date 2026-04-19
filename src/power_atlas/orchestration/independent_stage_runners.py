from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.orchestration.demo_planner import (
    IndependentStageOptions,
    IndependentStageResources,
    IndependentStageSpec,
)


def run_independent_structured_ingest_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: IndependentStageResources,
    options: IndependentStageOptions,
    *,
    run_structured_ingest_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    del options
    return run_structured_ingest_request_context(
        replace(request_context, run_id=stage_run_id),
        fixtures_dir=resources.fixture_dir,
        dataset_id=resources.dataset_id,
    )


def run_independent_pdf_ingest_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: IndependentStageResources,
    options: IndependentStageOptions,
    *,
    run_pdf_ingest_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    del options
    return run_pdf_ingest_request_context(
        replace(request_context, run_id=stage_run_id),
        fixtures_dir=resources.fixture_dir,
        pdf_filename=resources.pdf_filename,
        dataset_id=resources.dataset_id,
    )


def run_independent_claim_extraction_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: IndependentStageResources,
    options: IndependentStageOptions,
    *,
    run_claim_extraction_request_context: Callable[[RequestContext], dict[str, Any]],
) -> dict[str, Any]:
    del options
    return run_claim_extraction_request_context(
        replace(
            request_context,
            run_id=stage_run_id,
            source_uri=resources.pdf_source_uri,
        )
    )


def run_independent_entity_resolution_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: IndependentStageResources,
    options: IndependentStageOptions,
    *,
    run_entity_resolution_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    del options
    return run_entity_resolution_request_context(
        replace(
            request_context,
            run_id=stage_run_id,
            source_uri=resources.pdf_source_uri,
        ),
        dataset_id=resources.dataset_id,
    )


def run_independent_ask_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: IndependentStageResources,
    options: IndependentStageOptions,
    *,
    run_ask_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    del resources
    return run_ask_request_context(
        replace(
            request_context,
            run_id=stage_run_id if not options.ask_all_runs else None,
        ),
        cluster_aware=options.cluster_aware,
        expand_graph=options.expand_graph,
    )


def build_independent_stage_specs(
    *,
    run_independent_structured_ingest_stage: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]],
    run_independent_pdf_ingest_stage: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]],
    run_independent_claim_extraction_stage: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]],
    run_independent_entity_resolution_stage: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]],
    run_independent_ask_stage: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]],
) -> dict[str, IndependentStageSpec]:
    return {
        "ingest-structured": IndependentStageSpec(
            stage_name="structured_ingest",
            run_scope_key="structured_ingest_run_id",
            runner=run_independent_structured_ingest_stage,
        ),
        "ingest-pdf": IndependentStageSpec(
            stage_name="pdf_ingest",
            run_scope_key="unstructured_ingest_run_id",
            runner=run_independent_pdf_ingest_stage,
        ),
        "extract-claims": IndependentStageSpec(
            stage_name="claim_and_mention_extraction",
            run_scope_key="unstructured_ingest_run_id",
            runner=run_independent_claim_extraction_stage,
        ),
        "resolve-entities": IndependentStageSpec(
            stage_name="entity_resolution",
            run_scope_key="unstructured_ingest_run_id",
            runner=run_independent_entity_resolution_stage,
        ),
        "ask": IndependentStageSpec(
            stage_name="retrieval_and_qa",
            run_scope_key="unstructured_ingest_run_id",
            runner=run_independent_ask_stage,
        ),
    }


__all__ = [
    "build_independent_stage_specs",
    "run_independent_ask_stage",
    "run_independent_claim_extraction_stage",
    "run_independent_entity_resolution_stage",
    "run_independent_pdf_ingest_stage",
    "run_independent_structured_ingest_stage",
]