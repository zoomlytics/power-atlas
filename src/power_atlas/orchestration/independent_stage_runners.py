from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

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


def run_independent_stage_request_context(
    request_context: RequestContext,
    *,
    command: str,
    resolved_run_id: str | None,
    all_runs: bool,
    cluster_aware: bool,
    expand_graph: bool,
    resolve_ask_source_uri: Callable[[RequestContext], str | None],
    resolve_dataset_root: Callable[[str], object],
    build_independent_stage_plan: Callable[..., Any],
    stage_specs: Mapping[str, IndependentStageSpec],
    resolve_stage_run_id: Callable[..., str],
    now_iso: Callable[[], str],
    write_independent_stage_manifest: Callable[..., Path],
) -> Path:
    if command == "ask" and request_context.source_uri is None and not (all_runs or request_context.all_runs):
        request_context = replace(request_context, source_uri=resolve_ask_source_uri(request_context))

    config = request_context.config
    config.output_dir.mkdir(parents=True, exist_ok=True)

    ask_all_runs = (all_runs or request_context.all_runs) and command == "ask"
    dataset_root = None if ask_all_runs else resolve_dataset_root(config.dataset_name)
    plan = build_independent_stage_plan(
        request_context,
        command=command,
        resolved_run_id=resolved_run_id,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
        dataset_root=dataset_root,
        stage_specs=stage_specs,
        resolve_stage_run_id=resolve_stage_run_id,
    )
    started_at = now_iso()
    stage_output = plan.stage_spec.runner(
        plan.request_context,
        plan.stage_run_id,
        plan.resources,
        plan.options,
    )
    finished_at = now_iso()
    return write_independent_stage_manifest(
        config=config,
        stage_name=plan.stage_spec.stage_name,
        stage_run_id=plan.stage_run_id,
        run_scope_key=plan.stage_spec.run_scope_key,
        scope_run_id=None if plan.options.ask_all_runs else plan.stage_run_id,
        dataset_id=plan.dataset_id,
        stage_output=stage_output,
        started_at=started_at,
        finished_at=finished_at,
    )


__all__ = [
    "build_independent_stage_specs",
    "run_independent_stage_request_context",
    "run_independent_ask_stage",
    "run_independent_claim_extraction_stage",
    "run_independent_entity_resolution_stage",
    "run_independent_pdf_ingest_stage",
    "run_independent_structured_ingest_stage",
]