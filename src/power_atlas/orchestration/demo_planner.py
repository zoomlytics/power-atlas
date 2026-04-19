from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from power_atlas.context import RequestContext


@dataclass(frozen=True)
class IndependentStageResources:
    dataset_id: str | None
    fixture_dir: Path | None
    pdf_filename: str | None
    pdf_source_uri: str | None


@dataclass(frozen=True)
class IndependentStageOptions:
    ask_all_runs: bool
    cluster_aware: bool
    expand_graph: bool


@dataclass(frozen=True)
class IndependentStageSpec:
    stage_name: str
    run_scope_key: str
    runner: Callable[[RequestContext, str, IndependentStageResources, IndependentStageOptions], dict[str, Any]]


@dataclass(frozen=True)
class IndependentStagePlan:
    request_context: RequestContext
    resources: IndependentStageResources
    options: IndependentStageOptions
    stage_spec: IndependentStageSpec
    stage_run_id: str
    dataset_id: str | None


@dataclass(frozen=True)
class OrchestratedRunPlan:
    request_context: RequestContext
    started_at: str
    structured_run_id: str
    unstructured_run_id: str
    dataset_id: str
    fixture_dir: Path
    pdf_filename: str
    question: str | None
    structured_request_context: RequestContext
    unstructured_request_context: RequestContext


def scope_request_context(
    request_context: RequestContext,
    *,
    run_id: str | None,
    source_uri: object,
    keep_source_uri_value: object,
) -> RequestContext:
    updates: dict[str, object | None] = {"run_id": run_id}
    if source_uri is not keep_source_uri_value:
        updates["source_uri"] = source_uri
    return replace(request_context, **updates)


def build_orchestrated_run_plan(
    request_context: RequestContext,
    *,
    dataset_id: str,
    fixture_dir: Path,
    pdf_filename: str,
    started_at: str,
    structured_run_id: str,
    unstructured_run_id: str,
) -> OrchestratedRunPlan:
    return OrchestratedRunPlan(
        request_context=request_context,
        started_at=started_at,
        structured_run_id=structured_run_id,
        unstructured_run_id=unstructured_run_id,
        dataset_id=dataset_id,
        fixture_dir=fixture_dir,
        pdf_filename=pdf_filename,
        question=getattr(request_context.config, "question", None),
        structured_request_context=replace(request_context, run_id=structured_run_id),
        unstructured_request_context=replace(request_context, run_id=unstructured_run_id),
    )


def build_independent_stage_plan(
    request_context: RequestContext,
    *,
    command: str,
    resolved_run_id: str | None,
    all_runs: bool,
    cluster_aware: bool,
    expand_graph: bool,
    dataset_root: object | None,
    stage_specs: Mapping[str, IndependentStageSpec],
    resolve_stage_run_id: Callable[..., str],
) -> IndependentStagePlan:
    request_context = replace(
        request_context,
        run_id=resolved_run_id if resolved_run_id is not None else request_context.run_id,
        all_runs=all_runs or request_context.all_runs,
    )
    ask_all_runs = request_context.all_runs and command == "ask"
    if not ask_all_runs and dataset_root is not None:
        fixture_dir = dataset_root.root
        pdf_filename = dataset_root.pdf_filename
        pdf_source_uri = str((fixture_dir / "unstructured" / pdf_filename).resolve().as_uri())
        dataset_id = dataset_root.dataset_id
    else:
        fixture_dir = None
        pdf_filename = None
        pdf_source_uri = None
        dataset_id = None

    resources = IndependentStageResources(
        dataset_id=dataset_id,
        fixture_dir=fixture_dir,
        pdf_filename=pdf_filename,
        pdf_source_uri=pdf_source_uri,
    )
    options = IndependentStageOptions(
        ask_all_runs=ask_all_runs,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )
    if command not in stage_specs:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_spec = stage_specs[command]
    run_scope = stage_spec.run_scope_key.removesuffix("_run_id")
    stage_run_id = resolve_stage_run_id(
        command,
        request_context,
        run_scope=run_scope,
        ask_all_runs=ask_all_runs,
    )
    return IndependentStagePlan(
        request_context=request_context,
        resources=resources,
        options=options,
        stage_spec=stage_spec,
        stage_run_id=stage_run_id,
        dataset_id=dataset_id,
    )


def emit_stage_warnings(
    logger,
    stage_results: list[tuple[str, object]],
) -> None:
    for stage_name, stage_result in stage_results:
        if not isinstance(stage_result, dict):
            continue
        for warning in stage_result.get("warnings") or []:
            logger.warning("Stage %r warning: %s", stage_name, warning)


__all__ = [
    "IndependentStageOptions",
    "IndependentStagePlan",
    "IndependentStageResources",
    "IndependentStageSpec",
    "OrchestratedRunPlan",
    "build_independent_stage_plan",
    "build_orchestrated_run_plan",
    "emit_stage_warnings",
    "scope_request_context",
]