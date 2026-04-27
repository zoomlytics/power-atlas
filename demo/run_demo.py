from __future__ import annotations

import argparse
from dataclasses import replace
import logging
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.bootstrap import dataset_env_selection
from power_atlas.context import RequestContext
from power_atlas.orchestration.artifact_routing import (
    write_batch_manifest_artifacts,
    write_stage_manifest_artifacts,
)
from power_atlas.orchestration.cli_dispatch import dispatch_cli_command
from power_atlas.orchestration.demo_planner import (
    IndependentStageOptions as _IndependentStageOptions,
    IndependentStageResources as _IndependentStageResources,
    IndependentStageSpec as _IndependentStageSpec,
    build_independent_stage_plan,
    build_orchestrated_run_plan,
    emit_stage_warnings,
    scope_request_context as _scope_request_context,
)
from power_atlas.orchestration.ask_scope import (
    format_dataset_label as _format_dataset_label_impl,
    prepare_ask_request_context as _prepare_ask_request_context_impl,
    resolve_ask_request_context as _resolve_ask_request_context_impl,
    resolve_ask_scope as _resolve_ask_scope_impl,
    resolve_ask_source_uri as _resolve_ask_source_uri_impl,
    resolve_dry_run_ask_scope as _resolve_dry_run_ask_scope_impl,
    resolve_latest_dataset_id as _resolve_latest_dataset_id_impl,
    resolve_latest_run_scope as _resolve_latest_run_scope_impl,
    validate_explicit_run_id_dataset_selection as _validate_explicit_run_id_dataset_selection_impl,
    warn_env_run_id_dataset_mismatch as _warn_env_run_id_dataset_mismatch_impl,
    warn_explicit_run_id_dataset_mismatch as _warn_explicit_run_id_dataset_mismatch_impl,
    warn_if_env_run_id_bypasses_dataset_selection as _warn_if_env_run_id_bypasses_dataset_selection_impl,
)
from power_atlas.orchestration.independent_stage_runners import (
    DRY_RUN_NO_SCOPE_RUN_ID as _DRY_RUN_NO_SCOPE_RUN_ID,
    resolve_independent_stage_run_id as _resolve_independent_stage_run_id_impl,
    run_independent_stage_request_context as _run_independent_stage_request_context_impl,
    run_independent_ask_stage as _run_independent_ask_stage_impl,
    run_independent_claim_extraction_stage as _run_independent_claim_extraction_stage_impl,
    run_independent_entity_resolution_stage as _run_independent_entity_resolution_stage_impl,
    run_independent_pdf_ingest_stage as _run_independent_pdf_ingest_stage_impl,
    run_independent_structured_ingest_stage as _run_independent_structured_ingest_stage_impl,
    write_independent_stage_manifest as _write_independent_stage_manifest_impl,
)
from power_atlas.orchestration.stage_dependency_registry import (
    build_demo_independent_stage_specs,
)
from power_atlas.orchestration.orchestrated_runner import (
    run_orchestrated_request_context as _run_orchestrated_request_context_impl,
)
from power_atlas.run_scope_queries import fetch_dataset_id_for_run
from power_atlas.run_scope_queries import fetch_latest_unstructured_run_id

import power_atlas.contracts.pipeline as pipeline_contracts

from power_atlas.contracts import (  # noqa: E402
    Config,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
    resolve_dataset_root,
)
from power_atlas.settings import Neo4jSettings  # noqa: E402
from demo.run_demo_support import (  # noqa: E402
    add_common_args as _add_common_args_impl,
    build_config_from_args as _build_config_from_args_impl,
    build_request_context_from_args as _build_request_context_from_args_impl,
    parse_args as _parse_args_impl,
    request_context_from_config as _request_context_from_config_impl,
)
from demo.stages.structured_ingest import lint_and_clean_structured_csvs  # noqa: E402
from demo.stages.retrieval_and_qa import _format_scope_label  # noqa: E402
from demo.stages.claim_extraction import run_claim_and_mention_extraction_request_context  # noqa: E402
from demo.stages.claim_participation import run_claim_participation_request_context  # noqa: E402
from demo.stages.entity_resolution import run_entity_resolution_request_context  # noqa: E402
from demo.stages.pdf_ingest import run_pdf_ingest_request_context  # noqa: E402
from demo.stages.structured_ingest import run_structured_ingest_request_context  # noqa: E402
from demo.stages.retrieval_and_qa import run_interactive_qa_request_context  # noqa: E402
from demo.stages.retrieval_and_qa import run_retrieval_and_qa_request_context  # noqa: E402
from demo.stages.retrieval_benchmark import run_retrieval_benchmark  # noqa: E402
from demo.stages.pdf_ingest import sha256_file  # noqa: E402, F401 - re-exported for callers and tests

_logger = logging.getLogger(__name__)
_KEEP_REQUEST_CONTEXT_VALUE = object()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _scoped_request_context(
    request_context: RequestContext,
    *,
    run_id: str | None,
    source_uri: object = _KEEP_REQUEST_CONTEXT_VALUE,
) -> RequestContext:
    return _scope_request_context(
        request_context,
        run_id=run_id,
        source_uri=source_uri,
        keep_source_uri_value=_KEEP_REQUEST_CONTEXT_VALUE,
    )


def _extract_pdf_source_uri(stage_output: dict[str, Any] | object) -> str | None:
    if not isinstance(stage_output, dict):
        return None
    provenance = stage_output.get("provenance")
    if isinstance(provenance, dict):
        source_uri = provenance.get("source_uri")
        if isinstance(source_uri, str) and source_uri:
            return source_uri
    documents = stage_output.get("documents")
    if isinstance(documents, list) and documents:
        first_document = documents[0]
        if isinstance(first_document, str) and first_document:
            return first_document
    return None


def _resolve_independent_stage_run_id(
    command: str,
    request_context: RequestContext,
    *,
    run_scope: str,
    ask_all_runs: bool,
) -> str:
    return _resolve_independent_stage_run_id_impl(
        command,
        request_context,
        run_scope=run_scope,
        ask_all_runs=ask_all_runs,
        current_env_unstructured_run_id=_current_env_unstructured_run_id,
        make_run_id=make_run_id,
        dry_run_no_scope_run_id=_DRY_RUN_NO_SCOPE_RUN_ID,
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    _add_common_args_impl(parser)


def _build_config_from_args(args: argparse.Namespace) -> Config:
    return _build_config_from_args_impl(args)


def _build_request_context_from_args(
    args: argparse.Namespace,
    *,
    dry_run: bool | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
):
    return _build_request_context_from_args_impl(
        args,
        dry_run=dry_run,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def _request_context_from_config(
    config: Config,
    *,
    command: str | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    return _request_context_from_config_impl(
        config,
        command=command,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_args_impl(argv)


def _neo4j_settings_from_config(config: Config) -> Neo4jSettings:
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "run_demo requires config.settings.neo4j to be configured"
    )


def _fetch_latest_unstructured_run_id(
    config: Config, dataset_id: str | None = None
) -> str | None:
    neo4j_settings = _neo4j_settings_from_config(config)
    return fetch_latest_unstructured_run_id(
        neo4j_settings,
        neo4j_settings.database,
        dataset_id=dataset_id,
        logger=_logger,
    )


def _fetch_dataset_id_for_run(config: Config, run_id: str) -> str | None:
    neo4j_settings = _neo4j_settings_from_config(config)
    return fetch_dataset_id_for_run(
        neo4j_settings,
        neo4j_settings.database,
        run_id,
        logger=_logger,
    )


def _format_dataset_label(
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> str:
    """Return a human-readable label for the effective dataset selection."""
    return _format_dataset_label_impl(config_dataset, power_atlas_dataset, fixture_dataset)


def _current_env_dataset_selection() -> tuple[str | None, str | None, str | None]:
    return dataset_env_selection()


def _current_env_unstructured_run_id() -> str | None:
    return os.getenv("UNSTRUCTURED_RUN_ID") or None


def _warn_explicit_run_id_dataset_mismatch(
    explicit_run_id: str,
    expected_dataset_id: str,
    actual_dataset_id: str,
    *,
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> None:
    """Emit a WARNING log when --run-id belongs to a different dataset than selected."""
    _warn_explicit_run_id_dataset_mismatch_impl(
        explicit_run_id,
        expected_dataset_id,
        actual_dataset_id,
        config_dataset=config_dataset,
        power_atlas_dataset=power_atlas_dataset,
        fixture_dataset=fixture_dataset,
        logger=_logger,
    )


def _warn_env_run_id_dataset_mismatch(
    env_run_id: str,
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> None:
    """Emit a WARNING log when UNSTRUCTURED_RUN_ID is set alongside a dataset selection."""
    _warn_env_run_id_dataset_mismatch_impl(
        env_run_id,
        config_dataset,
        power_atlas_dataset,
        fixture_dataset,
        logger=_logger,
    )


def _warn_if_env_run_id_bypasses_dataset_selection(
    env_run_id: str,
    *,
    config_dataset: str | None,
) -> None:
    _warn_if_env_run_id_bypasses_dataset_selection_impl(
        env_run_id,
        config_dataset=config_dataset,
        current_env_dataset_selection=_current_env_dataset_selection,
        logger=_logger,
    )


def _validate_explicit_run_id_dataset_selection(
    config: Config,
    explicit_run_id: str,
) -> None:
    _validate_explicit_run_id_dataset_selection_impl(
        config,
        explicit_run_id,
        current_env_dataset_selection=_current_env_dataset_selection,
        resolve_dataset_root=resolve_dataset_root,
        fetch_dataset_id_for_run=_fetch_dataset_id_for_run,
        logger=_logger,
    )


def _resolve_latest_dataset_id(config: Config) -> str | None:
    return _resolve_latest_dataset_id_impl(
        config,
        current_env_dataset_selection=_current_env_dataset_selection,
        resolve_dataset_root=resolve_dataset_root,
    )


def _resolve_latest_run_scope(
    config: Config,
    *,
    env_run_id: str | None,
    use_latest: bool,
) -> str:
    return _resolve_latest_run_scope_impl(
        config,
        env_run_id=env_run_id,
        use_latest=use_latest,
        current_env_dataset_selection=_current_env_dataset_selection,
        resolve_dataset_root=resolve_dataset_root,
        fetch_latest_unstructured_run_id=lambda inner_config, dataset_id: _fetch_latest_unstructured_run_id(
            inner_config,
            dataset_id=dataset_id,
        ),
        logger=_logger,
    )


def _resolve_dry_run_ask_scope(
    config: Config,
    *,
    env_run_id: str | None,
) -> tuple[str | None, bool]:
    return _resolve_dry_run_ask_scope_impl(
        config,
        env_run_id=env_run_id,
        current_env_dataset_selection=_current_env_dataset_selection,
        logger=_logger,
    )


def _resolve_ask_request_context(
    args: argparse.Namespace,
    request_context: RequestContext,
) -> RequestContext:
    return _resolve_ask_request_context_impl(
        args,
        request_context,
        current_env_unstructured_run_id=_current_env_unstructured_run_id,
        current_env_dataset_selection=_current_env_dataset_selection,
        fetch_dataset_id_for_run=_fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=lambda inner_config, dataset_id: _fetch_latest_unstructured_run_id(
            inner_config,
            dataset_id=dataset_id,
        ),
        resolve_dataset_root=resolve_dataset_root,
        logger=_logger,
    )


def _resolve_ask_scope(
    args: argparse.Namespace, request_context: RequestContext
) -> tuple[str | None, bool]:
    """Resolve the retrieval scope for the ask command.

    Returns a ``(resolved_run_id, all_runs)`` tuple where:

    - ``all_runs=True`` means no run_id filter (queries all Chunk nodes).
    - ``resolved_run_id`` is the run_id to scope retrieval to; may be ``None``
      in dry-run mode when no scope is available (dry-run handles this gracefully).

    Precedence: CLI flag (``--run-id`` / ``--latest`` / ``--all-runs``)
    overrides the ``UNSTRUCTURED_RUN_ID`` environment variable. Warnings are
    logged whenever the env var is overridden or stale.
    """
    return _resolve_ask_scope_impl(
        args,
        request_context,
        current_env_unstructured_run_id=_current_env_unstructured_run_id,
        current_env_dataset_selection=_current_env_dataset_selection,
        fetch_dataset_id_for_run=_fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=lambda inner_config, dataset_id: _fetch_latest_unstructured_run_id(
            inner_config,
            dataset_id=dataset_id,
        ),
        resolve_dataset_root=resolve_dataset_root,
        logger=_logger,
    )


def _resolve_ask_source_uri(request_context: RequestContext) -> str | None:
    return _resolve_ask_source_uri_impl(
        request_context,
        resolve_dataset_root=resolve_dataset_root,
    )


def _prepare_ask_request_context(
    args: argparse.Namespace,
    request_context: RequestContext,
) -> RequestContext:
    return _prepare_ask_request_context_impl(
        args,
        request_context,
        current_env_unstructured_run_id=_current_env_unstructured_run_id,
        current_env_dataset_selection=_current_env_dataset_selection,
        fetch_dataset_id_for_run=_fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=lambda inner_config, dataset_id: _fetch_latest_unstructured_run_id(
            inner_config,
            dataset_id=dataset_id,
        ),
        resolve_dataset_root=resolve_dataset_root,
        logger=_logger,
    )


_run_ask_request_context = run_retrieval_and_qa_request_context
_run_claim_extraction_request_context = run_claim_and_mention_extraction_request_context
_run_claim_participation_request_context = run_claim_participation_request_context
_run_entity_resolution_request_context = run_entity_resolution_request_context
_run_pdf_ingest_request_context = run_pdf_ingest_request_context
_run_structured_ingest_request_context = run_structured_ingest_request_context
_run_retrieval_request_context = run_retrieval_and_qa_request_context


_INDEPENDENT_STAGE_SPECS: dict[str, _IndependentStageSpec] = build_demo_independent_stage_specs(
    run_independent_structured_ingest_stage_impl=_run_independent_structured_ingest_stage_impl,
    resolve_run_structured_ingest_request_context=lambda: _run_structured_ingest_request_context,
    run_independent_pdf_ingest_stage_impl=_run_independent_pdf_ingest_stage_impl,
    resolve_run_pdf_ingest_request_context=lambda: _run_pdf_ingest_request_context,
    run_independent_claim_extraction_stage_impl=_run_independent_claim_extraction_stage_impl,
    resolve_run_claim_extraction_request_context=lambda: _run_claim_extraction_request_context,
    run_independent_entity_resolution_stage_impl=_run_independent_entity_resolution_stage_impl,
    resolve_run_entity_resolution_request_context=lambda: _run_entity_resolution_request_context,
    run_independent_ask_stage_impl=_run_independent_ask_stage_impl,
    resolve_run_ask_request_context=lambda: _run_ask_request_context,
)

_run_independent_structured_ingest_stage = _INDEPENDENT_STAGE_SPECS["ingest-structured"].runner
_run_independent_pdf_ingest_stage = _INDEPENDENT_STAGE_SPECS["ingest-pdf"].runner
_run_independent_claim_extraction_stage = _INDEPENDENT_STAGE_SPECS["extract-claims"].runner
_run_independent_entity_resolution_stage = _INDEPENDENT_STAGE_SPECS["resolve-entities"].runner
_run_independent_ask_stage = _INDEPENDENT_STAGE_SPECS["ask"].runner


def _run_orchestrated_request_context(request_context: RequestContext) -> Path:
    """Run the full demo batch sequence with an unstructured-first posture."""
    return _run_orchestrated_request_context_impl(
        request_context,
        resolve_dataset_root=resolve_dataset_root,
        build_orchestrated_run_plan=build_orchestrated_run_plan,
        make_run_id=make_run_id,
        now_iso=_now_iso,
        run_pdf_ingest_request_context=_run_pdf_ingest_request_context,
        extract_pdf_source_uri=_extract_pdf_source_uri,
        scope_request_context=_scoped_request_context,
        run_claim_extraction_request_context=_run_claim_extraction_request_context,
        run_claim_participation_request_context=_run_claim_participation_request_context,
        run_entity_resolution_request_context=_run_entity_resolution_request_context,
        run_retrieval_request_context=_run_retrieval_request_context,
        run_structured_ingest_request_context=_run_structured_ingest_request_context,
        run_retrieval_benchmark=run_retrieval_benchmark,
        emit_stage_warnings=emit_stage_warnings,
        build_batch_manifest=build_batch_manifest,
        write_batch_manifest_artifacts=write_batch_manifest_artifacts,
        logger=_logger,
        format_traceback=traceback.format_exc,
    )


def _run_orchestrated(request_context: RequestContext) -> Path:
    return _run_orchestrated_request_context(request_context)


def _run_independent_stage(
    request_context: RequestContext,
    command: str,
    *,
    resolved_run_id: str | None = None,
    all_runs: bool = False,
    cluster_aware: bool = False,
    expand_graph: bool = False,
) -> Path:
    return _run_independent_stage_request_context_impl(
        request_context,
        command=command,
        resolved_run_id=resolved_run_id,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
        resolve_ask_source_uri=_resolve_ask_source_uri,
        resolve_dataset_root=resolve_dataset_root,
        build_independent_stage_plan=build_independent_stage_plan,
        stage_specs=_INDEPENDENT_STAGE_SPECS,
        resolve_stage_run_id=_resolve_independent_stage_run_id,
        now_iso=_now_iso,
        write_independent_stage_manifest=lambda **kwargs: _write_independent_stage_manifest_impl(
            **kwargs,
            build_stage_manifest=build_stage_manifest,
            write_stage_manifest_artifacts=write_stage_manifest_artifacts,
        ),
    )


def run_demo(request_context: RequestContext) -> Path:
    return _run_orchestrated(request_context)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_args(argv)


run_independent_demo = _run_independent_stage


def main() -> None:
    args = parse_args()
    try:
        dispatch_cli_command(
            args,
            emit=print,
            build_request_context_from_args=_build_request_context_from_args,
            lint_and_clean_structured_csvs=lint_and_clean_structured_csvs,
            make_run_id=make_run_id,
            resolve_dataset_root=resolve_dataset_root,
            run_demo=run_demo,
            prepare_ask_request_context=_prepare_ask_request_context,
            run_interactive_qa_request_context=run_interactive_qa_request_context,
            run_independent_stage=_run_independent_stage,
            format_scope_label=_format_scope_label,
            create_driver=create_neo4j_driver,
            load_reset_runner=lambda: __import__("demo.reset_demo_db", fromlist=["run_reset"]).run_reset,
        )
    except SystemExit:
        raise
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
