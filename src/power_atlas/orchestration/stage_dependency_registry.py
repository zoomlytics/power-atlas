from __future__ import annotations

from pathlib import Path
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


def build_demo_orchestrated_runner_kwargs(
    *,
    resolve_dataset_root: Callable[[], Callable[[str], object]],
    build_orchestrated_run_plan: Callable[..., object],
    make_run_id: Callable[[str], str],
    now_iso: Callable[[], str],
    resolve_run_pdf_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    extract_pdf_source_uri: Callable[[dict[str, Any] | object], str | None],
    scope_request_context: Callable[..., RequestContext],
    resolve_run_claim_extraction_request_context: Callable[[], Callable[[RequestContext], dict[str, Any]]],
    resolve_run_claim_participation_request_context: Callable[[], Callable[[RequestContext], dict[str, Any]]],
    resolve_run_entity_resolution_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_retrieval_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_structured_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_retrieval_benchmark: Callable[[], Callable[..., dict[str, Any]]],
    emit_stage_warnings: Callable[[Any, list[tuple[str, object]]], None],
    build_batch_manifest: Callable[..., dict[str, Any]],
    write_batch_manifest_artifacts: Callable[..., Path],
    logger: Any,
    format_traceback: Callable[[], str],
) -> dict[str, Any]:
    return {
        "resolve_dataset_root": resolve_dataset_root(),
        "build_orchestrated_run_plan": build_orchestrated_run_plan,
        "make_run_id": make_run_id,
        "now_iso": now_iso,
        "run_pdf_ingest_request_context": resolve_run_pdf_ingest_request_context(),
        "extract_pdf_source_uri": extract_pdf_source_uri,
        "scope_request_context": scope_request_context,
        "run_claim_extraction_request_context": resolve_run_claim_extraction_request_context(),
        "run_claim_participation_request_context": resolve_run_claim_participation_request_context(),
        "run_entity_resolution_request_context": resolve_run_entity_resolution_request_context(),
        "run_retrieval_request_context": resolve_run_retrieval_request_context(),
        "run_structured_ingest_request_context": resolve_run_structured_ingest_request_context(),
        "run_retrieval_benchmark": resolve_run_retrieval_benchmark(),
        "emit_stage_warnings": emit_stage_warnings,
        "build_batch_manifest": build_batch_manifest,
        "write_batch_manifest_artifacts": write_batch_manifest_artifacts,
        "logger": logger,
        "format_traceback": format_traceback,
    }


def build_demo_cli_dispatch_kwargs(
    *,
    build_request_context_from_args: Callable[..., Any],
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]],
    make_run_id: Callable[[str], str],
    resolve_dataset_root: Callable[[str | None], Any],
    run_demo: Callable[[RequestContext], Path],
    prepare_ask_request_context: Callable[..., RequestContext],
    resolve_run_interactive_qa_request_context: Callable[[], Callable[..., None]],
    run_independent_stage: Callable[..., Path],
    format_scope_label: Callable[[str | None, bool], str],
    resolve_create_driver: Callable[[], Callable[[Any], Any]],
    resolve_load_reset_runner: Callable[[], Callable[[], Callable[..., dict[str, Any]]]],
) -> dict[str, Any]:
    return {
        "build_request_context_from_args": build_request_context_from_args,
        "lint_and_clean_structured_csvs": lint_and_clean_structured_csvs,
        "make_run_id": make_run_id,
        "resolve_dataset_root": resolve_dataset_root,
        "run_demo": run_demo,
        "prepare_ask_request_context": prepare_ask_request_context,
        "run_interactive_qa_request_context": resolve_run_interactive_qa_request_context(),
        "run_independent_stage": run_independent_stage,
        "format_scope_label": format_scope_label,
        "create_driver": resolve_create_driver(),
        "load_reset_runner": resolve_load_reset_runner(),
    }


def build_demo_independent_stage_runner_kwargs(
    *,
    resolve_ask_source_uri: Callable[[RequestContext], str | None],
    resolve_dataset_root: Callable[[str], object],
    build_independent_stage_plan: Callable[..., Any],
    stage_specs: dict[str, IndependentStageSpec],
    resolve_stage_run_id: Callable[..., str],
    now_iso: Callable[[], str],
    write_independent_stage_manifest_impl: Callable[..., Path],
    build_stage_manifest: Callable[..., dict[str, Any]],
    write_stage_manifest_artifacts: Callable[..., Path],
) -> dict[str, Any]:
    return {
        "resolve_ask_source_uri": resolve_ask_source_uri,
        "resolve_dataset_root": resolve_dataset_root,
        "build_independent_stage_plan": build_independent_stage_plan,
        "stage_specs": stage_specs,
        "resolve_stage_run_id": resolve_stage_run_id,
        "now_iso": now_iso,
        "write_independent_stage_manifest": lambda **kwargs: write_independent_stage_manifest_impl(
            **kwargs,
            build_stage_manifest=build_stage_manifest,
            write_stage_manifest_artifacts=write_stage_manifest_artifacts,
        ),
    }


def build_demo_dataset_selection_kwargs(
    *,
    resolve_current_env_dataset_selection: Callable[[], Callable[[], tuple[str | None, str | None, str | None]]],
    resolve_dataset_root: Callable[[str], object],
) -> dict[str, Any]:
    return {
        "current_env_dataset_selection": resolve_current_env_dataset_selection(),
        "resolve_dataset_root": resolve_dataset_root,
    }


def build_demo_ask_scope_resolution_kwargs(
    *,
    resolve_current_env_unstructured_run_id: Callable[[], Callable[[], str | None]],
    resolve_current_env_dataset_selection: Callable[[], Callable[[], tuple[str | None, str | None, str | None]]],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    resolve_fetch_latest_unstructured_run_id: Callable[[], Callable[[object, str | None], str | None]],
    resolve_dataset_root: Callable[[str], object],
    logger: Any,
) -> dict[str, Any]:
    return {
        "current_env_unstructured_run_id": resolve_current_env_unstructured_run_id(),
        "current_env_dataset_selection": resolve_current_env_dataset_selection(),
        "fetch_dataset_id_for_run": fetch_dataset_id_for_run,
        "fetch_latest_unstructured_run_id": resolve_fetch_latest_unstructured_run_id(),
        "resolve_dataset_root": resolve_dataset_root,
        "logger": logger,
    }


__all__ = [
    "build_demo_ask_scope_resolution_kwargs",
    "build_demo_cli_dispatch_kwargs",
    "build_demo_dataset_selection_kwargs",
    "build_demo_independent_stage_runner_kwargs",
    "build_demo_orchestrated_runner_kwargs",
    "build_demo_independent_stage_specs",
    "make_bound_independent_stage_runner",
]