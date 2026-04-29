from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
import logging
from pathlib import Path
from typing import Any

from power_atlas.context import RequestContext
from power_atlas.orchestration.ask_scope import resolve_ask_scope as resolve_ask_scope_impl
from power_atlas.orchestration.run_scope_bridge import prepare_ask_request_context_from_scope


def load_demo_reset_runner() -> Callable[..., Any]:
    return __import__("demo.reset_demo_db", fromlist=["run_reset"]).run_reset


def resolve_run_demo_ask_scope(
    args: Namespace,
    request_context: RequestContext,
    *,
    current_env_unstructured_run_id: Callable[[], str | None],
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    fetch_latest_unstructured_run_id: Callable[[object, str | None], str | None],
    resolve_dataset_root: Callable[[str], object],
    logger: logging.Logger,
) -> tuple[str | None, bool]:
    return resolve_ask_scope_impl(
        args,
        request_context,
        current_env_unstructured_run_id=current_env_unstructured_run_id,
        current_env_dataset_selection=current_env_dataset_selection,
        fetch_dataset_id_for_run=fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=fetch_latest_unstructured_run_id,
        resolve_dataset_root=resolve_dataset_root,
        logger=logger,
    )


def prepare_run_demo_ask_request_context(
    args: Namespace,
    request_context: RequestContext,
    *,
    resolve_ask_scope: Callable[[Namespace, RequestContext], tuple[str | None, bool]],
    resolve_ask_source_uri: Callable[[RequestContext], str | None],
) -> RequestContext:
    resolved_run_id, all_runs = resolve_ask_scope(args, request_context)
    return prepare_ask_request_context_from_scope(
        request_context,
        resolved_run_id=resolved_run_id,
        all_runs=all_runs,
        resolve_ask_source_uri=resolve_ask_source_uri,
    )


def run_demo_independent_stage(
    request_context: RequestContext,
    command: str,
    *,
    resolved_run_id: str | None = None,
    all_runs: bool = False,
    cluster_aware: bool = False,
    expand_graph: bool = False,
    run_independent_stage_request_context: Callable[..., Path],
    resolve_ask_source_uri: Callable[[RequestContext], str | None],
    resolve_dataset_root: Callable[[str], object],
    build_independent_stage_plan: Callable[..., Any],
    stage_specs: dict[str, Any],
    resolve_stage_run_id: Callable[..., str],
    now_iso: Callable[[], str],
    write_independent_stage_manifest_impl: Callable[..., Path],
    build_stage_manifest: Callable[..., dict[str, Any]],
    write_stage_manifest_artifacts: Callable[..., Path],
    build_demo_independent_stage_runner_kwargs: Callable[..., dict[str, Any]],
) -> Path:
    return run_independent_stage_request_context(
        request_context,
        command=command,
        resolved_run_id=resolved_run_id,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
        **build_demo_independent_stage_runner_kwargs(
            resolve_ask_source_uri=resolve_ask_source_uri,
            resolve_dataset_root=resolve_dataset_root,
            build_independent_stage_plan=build_independent_stage_plan,
            stage_specs=stage_specs,
            resolve_stage_run_id=resolve_stage_run_id,
            now_iso=now_iso,
            write_independent_stage_manifest_impl=write_independent_stage_manifest_impl,
            build_stage_manifest=build_stage_manifest,
            write_stage_manifest_artifacts=write_stage_manifest_artifacts,
        ),
    )


def run_demo_orchestrated_request_context(
    request_context: RequestContext,
    *,
    run_orchestrated_request_context_impl: Callable[..., Path],
    build_demo_orchestrated_runner_kwargs: Callable[..., dict[str, Any]],
    resolve_dataset_root: Callable[[], Callable[[str], object]],
    build_orchestrated_run_plan: Callable[..., Any],
    make_run_id: Callable[[str], str],
    now_iso: Callable[[], str],
    resolve_run_pdf_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    extract_pdf_source_uri: Callable[[dict[str, Any] | object], str | None],
    scope_request_context: Callable[..., RequestContext],
    resolve_run_claim_extraction_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_claim_participation_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_entity_resolution_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_retrieval_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_structured_ingest_request_context: Callable[[], Callable[..., dict[str, Any]]],
    resolve_run_retrieval_benchmark: Callable[[], Callable[..., dict[str, Any]]],
    emit_stage_warnings: Callable[[Any, list[tuple[str, object]]], None],
    build_batch_manifest: Callable[..., dict[str, Any]],
    write_batch_manifest_artifacts: Callable[..., Path],
    logger: logging.Logger,
    format_traceback: Callable[[], str],
) -> Path:
    return run_orchestrated_request_context_impl(
        request_context,
        **build_demo_orchestrated_runner_kwargs(
            resolve_dataset_root=resolve_dataset_root,
            build_orchestrated_run_plan=build_orchestrated_run_plan,
            make_run_id=make_run_id,
            now_iso=now_iso,
            resolve_run_pdf_ingest_request_context=resolve_run_pdf_ingest_request_context,
            extract_pdf_source_uri=extract_pdf_source_uri,
            scope_request_context=scope_request_context,
            resolve_run_claim_extraction_request_context=resolve_run_claim_extraction_request_context,
            resolve_run_claim_participation_request_context=resolve_run_claim_participation_request_context,
            resolve_run_entity_resolution_request_context=resolve_run_entity_resolution_request_context,
            resolve_run_retrieval_request_context=resolve_run_retrieval_request_context,
            resolve_run_structured_ingest_request_context=resolve_run_structured_ingest_request_context,
            resolve_run_retrieval_benchmark=resolve_run_retrieval_benchmark,
            emit_stage_warnings=emit_stage_warnings,
            build_batch_manifest=build_batch_manifest,
            write_batch_manifest_artifacts=write_batch_manifest_artifacts,
            logger=logger,
            format_traceback=format_traceback,
        ),
    )


def run_demo_main(
    *,
    parse_args: Callable[[], Namespace],
    dispatch_cli_command: Callable[..., Any],
    build_demo_cli_dispatch_kwargs: Callable[..., dict[str, Any]],
    build_request_context_from_args: Callable[..., Any],
    lint_and_clean_structured_csvs: Callable[..., Any],
    make_run_id: Callable[..., str],
    resolve_dataset_root: Callable[..., Any],
    run_demo: Callable[..., Path],
    prepare_ask_request_context: Callable[..., Any],
    resolve_run_interactive_qa_request_context: Callable[[], Callable[..., Any]],
    run_independent_stage: Callable[..., Path],
    format_scope_label: Callable[..., str],
    resolve_create_driver: Callable[[], Callable[..., Any]],
    resolve_load_reset_runner: Callable[[], Callable[..., Any]],
    emit: Callable[[str], None] = print,
) -> None:
    args = parse_args()
    try:
        dispatch_cli_command(
            args,
            emit=emit,
            **build_demo_cli_dispatch_kwargs(
                build_request_context_from_args=build_request_context_from_args,
                lint_and_clean_structured_csvs=lint_and_clean_structured_csvs,
                make_run_id=make_run_id,
                resolve_dataset_root=resolve_dataset_root,
                run_demo=run_demo,
                prepare_ask_request_context=prepare_ask_request_context,
                resolve_run_interactive_qa_request_context=resolve_run_interactive_qa_request_context,
                run_independent_stage=run_independent_stage,
                format_scope_label=format_scope_label,
                resolve_create_driver=resolve_create_driver,
                resolve_load_reset_runner=resolve_load_reset_runner,
            ),
        )
    except SystemExit:
        raise
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


__all__ = [
    "load_demo_reset_runner",
    "prepare_run_demo_ask_request_context",
    "resolve_run_demo_ask_scope",
    "run_demo_independent_stage",
    "run_demo_orchestrated_request_context",
    "run_demo_main",
]