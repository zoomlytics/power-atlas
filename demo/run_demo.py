from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.bootstrap import dataset_env_selection
from power_atlas.bootstrap import build_app_context as _build_app_context
from power_atlas.bootstrap import build_request_context as _build_request_context
from power_atlas.bootstrap import build_runtime_config as _build_runtime_config
from power_atlas.bootstrap import build_settings as _build_package_settings
from power_atlas.context import RequestContext
from power_atlas.run_scope_queries import fetch_dataset_id_for_run
from power_atlas.run_scope_queries import fetch_latest_unstructured_run_id

import power_atlas.contracts.pipeline as pipeline_contracts

from power_atlas.contracts import (  # noqa: E402
    ARTIFACTS_DIR,
    Config,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
    resolve_dataset_root,
    write_manifest,
    write_manifest_md,
)
from demo.stages import (  # noqa: E402
    lint_and_clean_structured_csvs,
)
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
_DRY_RUN_NO_SCOPE_RUN_ID = "dry_run_no_scope"


@dataclass(frozen=True)
class _IndependentStageResources:
    dataset_id: str | None
    fixture_dir: Path | None
    pdf_filename: str | None
    pdf_source_uri: str | None


@dataclass(frozen=True)
class _IndependentStageOptions:
    ask_all_runs: bool
    cluster_aware: bool
    expand_graph: bool


@dataclass(frozen=True)
class _IndependentStageSpec:
    stage_name: str
    run_scope_key: str
    runner: Callable[[RequestContext, str, _IndependentStageResources, _IndependentStageOptions], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _scoped_request_context(
    request_context: RequestContext,
    *,
    run_id: str | None,
    source_uri: object = _KEEP_REQUEST_CONTEXT_VALUE,
) -> RequestContext:
    updates: dict[str, object | None] = {"run_id": run_id}
    if source_uri is not _KEEP_REQUEST_CONTEXT_VALUE:
        updates["source_uri"] = source_uri
    return replace(request_context, **updates)


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
    if command in ("extract-claims", "resolve-entities"):
        env_run_id = _current_env_unstructured_run_id()
        if not env_run_id:
            raise ValueError(
                "UNSTRUCTURED_RUN_ID is not set. When running "
                f"'{command}' independently, set this to the run_id from a prior "
                "'ingest' or 'ingest-pdf' command whose unstructured data you want to process "
                "(for example, a value like 'unstructured_ingest-20260304T224739123456Z-1a2b3c4d')."
            )
        return env_run_id
    if command == "ask":
        if ask_all_runs:
            return make_run_id("ask")
        if request_context.run_id is not None:
            return request_context.run_id
        return _DRY_RUN_NO_SCOPE_RUN_ID
    return make_run_id(run_scope)


def _write_independent_stage_manifest(
    *,
    config: Config,
    stage_name: str,
    stage_run_id: str,
    run_scope_key: str,
    scope_run_id: str | None,
    dataset_id: str | None,
    stage_output: dict[str, Any],
    started_at: str,
    finished_at: str,
) -> Path:
    manifest = build_stage_manifest(
        config=config,
        stage_name=stage_name,
        stage_run_id=stage_run_id,
        run_scope_key=run_scope_key,
        scope_run_id=scope_run_id,
        dataset_id=dataset_id,
        stage_output=stage_output,
        started_at=started_at,
        finished_at=finished_at,
    )
    manifest_path = config.output_dir / "runs" / stage_run_id / stage_name / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    package_settings = _build_package_settings()
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Run without live Neo4j/OpenAI calls",
    )
    mode_group.add_argument(
        "--live",
        action="store_false",
        dest="dry_run",
        help="Enable live Neo4j/OpenAI calls",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--neo4j-uri", default=package_settings.neo4j.uri)
    parser.add_argument("--neo4j-username", default=package_settings.neo4j.username)
    parser.add_argument("--neo4j-password", default=package_settings.neo4j.password)
    parser.add_argument("--neo4j-database", default=package_settings.neo4j.database)
    parser.add_argument("--openai-model", default=package_settings.openai_model)
    parser.add_argument(
        "--dataset",
        default=package_settings.dataset_name,
        dest="dataset",
        metavar="DATASET_NAME",
        help=(
            "Name of the fixture dataset to use (directory under demo/fixtures/datasets/). "
            "Defaults to POWER_ATLAS_DATASET or FIXTURE_DATASET; if neither is set, "
            "the single available dataset is auto-discovered."
        ),
    )


def _build_config_from_args(args: argparse.Namespace) -> Config:
    package_settings = _build_package_settings(
        {
            "NEO4J_URI": args.neo4j_uri,
            "NEO4J_USERNAME": args.neo4j_username,
            "NEO4J_PASSWORD": args.neo4j_password,
            "NEO4J_DATABASE": args.neo4j_database,
            "OPENAI_MODEL": args.openai_model,
            "POWER_ATLAS_OUTPUT_DIR": str(args.output_dir),
            "POWER_ATLAS_DATASET": getattr(args, "dataset", None) or "",
        }
    )
    if not args.dry_run and package_settings.neo4j.password in ("", "CHANGE_ME_BEFORE_USE"):
        raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
    return _build_runtime_config(
        package_settings,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        question=getattr(args, "question", None),
        resolution_mode=getattr(args, "resolution_mode", None) or "unstructured_only",
    )


def _build_request_context_from_args(
    args: argparse.Namespace,
    *,
    dry_run: bool | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
):
    package_settings = _build_package_settings(
        {
            "NEO4J_URI": args.neo4j_uri,
            "NEO4J_USERNAME": args.neo4j_username,
            "NEO4J_PASSWORD": args.neo4j_password,
            "NEO4J_DATABASE": args.neo4j_database,
            "OPENAI_MODEL": args.openai_model,
            "POWER_ATLAS_OUTPUT_DIR": str(args.output_dir),
            "POWER_ATLAS_DATASET": getattr(args, "dataset", None) or "",
        }
    )
    app_context = _build_app_context(settings=package_settings)
    return _build_request_context(
        app_context,
        command=getattr(args, "command", None),
        dry_run=args.dry_run if dry_run is None else dry_run,
        output_dir=args.output_dir,
        question=getattr(args, "question", None),
        resolution_mode=getattr(args, "resolution_mode", None) or "unstructured_only",
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
    default_settings = _build_package_settings()
    package_settings = _build_package_settings(
        {
            "NEO4J_URI": getattr(config, "neo4j_uri", default_settings.neo4j.uri),
            "NEO4J_USERNAME": getattr(config, "neo4j_username", default_settings.neo4j.username),
            "NEO4J_PASSWORD": getattr(config, "neo4j_password", default_settings.neo4j.password),
            "NEO4J_DATABASE": getattr(config, "neo4j_database", default_settings.neo4j.database),
            "OPENAI_MODEL": getattr(config, "openai_model", default_settings.openai_model),
            "POWER_ATLAS_OUTPUT_DIR": str(getattr(config, "output_dir", default_settings.output_dir)),
            "POWER_ATLAS_DATASET": getattr(config, "dataset_name", None) or "",
        }
    )
    app_context = _build_app_context(settings=package_settings)
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if config_pipeline_contract is not None:
        app_context = replace(
            app_context,
            pipeline_contract=config_pipeline_contract,
            pipeline_contract_config_data=dict(
                getattr(config, "pipeline_contract_config_data", app_context.pipeline_contract_config_data)
            ),
        )
    return _build_request_context(
        app_context,
        command=command,
        dry_run=getattr(config, "dry_run", True),
        output_dir=getattr(config, "output_dir", default_settings.output_dir),
        question=getattr(config, "question", None),
        resolution_mode=getattr(config, "resolution_mode", "unstructured_only"),
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def _ensure_request_context(
    request_context_or_config: RequestContext | Config,
    *,
    command: str | None = None,
) -> RequestContext:
    if isinstance(request_context_or_config, RequestContext):
        return request_context_or_config
    return _request_context_from_config(request_context_or_config, command=command)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    common_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    _add_common_args(common_parser)
    parser = argparse.ArgumentParser(
        description="Demo workflow orchestrator",
        parents=[common_parser],
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in (
        "lint-structured",
        "ingest-structured",
        "ingest-pdf",
        "extract-claims",
        "resolve-entities",
        "ask",
        "reset",
        "ingest",
    ):
        subparsers.add_parser(command, parents=[common_parser], allow_abbrev=False)
        if command == "ask":
            subparsers.choices[command].add_argument("--question", default=None)
            subparsers.choices[command].add_argument(
                "--interactive",
                action="store_true",
                default=False,
                help="Start an interactive REPL-style Q&A session with message history",
            )
            scope_group = subparsers.choices[command].add_mutually_exclusive_group()
            scope_group.add_argument(
                "--run-id",
                default=None,
                dest="run_id",
                metavar="RUN_ID",
                help="Retrieve from a specific ingest run (overrides UNSTRUCTURED_RUN_ID env var)",
            )
            scope_group.add_argument(
                "--latest",
                action="store_true",
                default=False,
                dest="latest",
                help="Retrieve from the latest unstructured ingest run (default behavior)",
            )
            scope_group.add_argument(
                "--all-runs",
                action="store_true",
                default=False,
                dest="all_runs",
                help="Retrieve across all ingested data (no run_id filter); citations may span multiple runs",
            )
            subparsers.choices[command].add_argument(
                "--cluster-aware",
                action="store_true",
                default=False,
                dest="cluster_aware",
                help=(
                    "Enable cluster-aware retrieval: extends graph expansion with "
                    "ResolvedEntityCluster membership and ALIGNED_WITH edges to canonical "
                    "entities. Implies --expand-graph. Run after 'resolve-entities "
                    "--resolution-mode hybrid' to demonstrate post-alignment enrichment."
                ),
            )
            subparsers.choices[command].add_argument(
                "--expand-graph",
                action="store_true",
                default=False,
                dest="expand_graph",
                help=(
                    "Enable graph-expanded retrieval: adds ExtractedClaim, EntityMention, "
                    "and canonical entity context from the graph alongside each retrieved "
                    "chunk. Use --cluster-aware for the full post-hybrid enrichment path."
                ),
            )
            subparsers.choices[command].add_argument(
                "--debug",
                action="store_true",
                default=False,
                dest="debug",
                help=(
                    "Enable debug output for interactive sessions: prints a compact "
                    "postprocessing summary after each answer showing citation quality "
                    "metadata (raw/final citation state, repair/fallback applied, evidence "
                    "level, warning count).  Has no effect when --interactive is not set."
                ),
            )
        if command == "ingest":
            subparsers.choices[command].add_argument(
                "--question",
                default=None,
                help=(
                    "Optional demo question to run through the Q&A passes in both "
                    "the unstructured-only and hybrid enrichment phases. "
                    "When omitted in --live mode, the Q&A stage is still recorded "
                    "but vector retrieval is skipped."
                ),
            )
        if command == "reset":
            subparsers.choices[command].add_argument(
                "--confirm",
                action="store_true",
                default=False,
                help="Required safety flag; without it the command prints instructions only",
            )
        if command == "resolve-entities":
            subparsers.choices[command].add_argument(
                "--resolution-mode",
                default=None,
                dest="resolution_mode",
                choices=["structured_anchor", "unstructured_only", "hybrid"],
                help=(
                    "Resolution mode: 'unstructured_only' (default) clusters mentions "
                    "against each other without requiring structured ingest; 'hybrid' "
                    "clusters mentions first then optionally aligns clusters to "
                    "CanonicalEntity nodes via ALIGNED_WITH enrichment edges; "
                    "'structured_anchor' resolves mentions against CanonicalEntity nodes "
                    "using exact-match strategies."
                ),
            )
    parser.set_defaults(command="ingest")

    options_with_values = {
        "--output-dir",
        "--neo4j-uri",
        "--neo4j-username",
        "--neo4j-password",
        "--neo4j-database",
        "--openai-model",
        "--question",
        "--run-id",
        "--resolution-mode",
    }
    saw_dry_run_flag = False
    saw_live_flag = False
    i = 0
    while i < len(raw_argv):
        token = raw_argv[i]
        if token in options_with_values:
            i += 2
            continue
        if token == "--dry-run":
            saw_dry_run_flag = True
        elif token == "--live":
            saw_live_flag = True
        i += 1

    if saw_dry_run_flag and saw_live_flag:
        parser.error("argument --dry-run: not allowed with argument --live")
    namespace = parser.parse_args(raw_argv)
    # Argparse subparsers re-apply set_defaults(dry_run=True) from common_parser,
    # which overwrites the top-level parser's parsed value when a flag like --live
    # appears before the subcommand.  Apply the pre-scanned result to guarantee
    # the flag is honoured regardless of its position relative to the subcommand.
    if saw_live_flag:
        namespace.dry_run = False
    elif saw_dry_run_flag:
        namespace.dry_run = True
    return namespace


def _fetch_latest_unstructured_run_id(
    config: Config, dataset_id: str | None = None
) -> str | None:
    return fetch_latest_unstructured_run_id(config, dataset_id=dataset_id, logger=_logger)


def _fetch_dataset_id_for_run(config: Config, run_id: str) -> str | None:
    return fetch_dataset_id_for_run(config, run_id, logger=_logger)


def _format_dataset_label(
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> str:
    """Return a human-readable label for the effective dataset selection.

    When ``--dataset`` overrides an environment-provided dataset selection, both
    values are shown for clarity. Used consistently across all dataset-mismatch
    warnings.
    """
    if config_dataset and power_atlas_dataset and config_dataset != power_atlas_dataset:
        return (
            f"--dataset={config_dataset!r} "
            f"(overrides POWER_ATLAS_DATASET={power_atlas_dataset!r})"
        )
    if config_dataset and fixture_dataset and config_dataset != fixture_dataset:
        return (
            f"--dataset={config_dataset!r} "
            f"(overrides FIXTURE_DATASET={fixture_dataset!r})"
        )
    if power_atlas_dataset and fixture_dataset and power_atlas_dataset != fixture_dataset:
        return (
            f"POWER_ATLAS_DATASET={power_atlas_dataset!r} "
            f"(overrides FIXTURE_DATASET={fixture_dataset!r})"
        )
    if power_atlas_dataset:
        return f"POWER_ATLAS_DATASET={power_atlas_dataset!r}"
    if fixture_dataset:
        return f"FIXTURE_DATASET={fixture_dataset!r}"
    return f"--dataset={config_dataset!r}"


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
    """Emit a WARNING log when --run-id belongs to a different dataset than the one selected.

    Names the effective dataset source (``FIXTURE_DATASET`` or ``--dataset``) for
    operator clarity, consistent with ``_warn_env_run_id_dataset_mismatch``.
    When both ``--dataset`` and ``FIXTURE_DATASET`` are present and differ,
    ``--dataset`` is the effective override and is named as such.
    """
    dataset_label = _format_dataset_label(config_dataset, power_atlas_dataset, fixture_dataset)
    _logger.warning(
        "--run-id=%r belongs to dataset %r, "
        "but %s is selected (expected dataset_id=%r). "
        "Retrieval will be scoped to a run from a different dataset than requested. "
        "Use --latest to select the latest run for the selected dataset instead.",
        explicit_run_id,
        actual_dataset_id,
        dataset_label,
        expected_dataset_id,
    )


def _warn_env_run_id_dataset_mismatch(
    env_run_id: str,
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> None:
    """Emit a WARNING log when UNSTRUCTURED_RUN_ID is set alongside an explicit dataset.

    The env var bypasses dataset-aware run selection, so the run it points to may
    belong to a different dataset than the one explicitly requested.  Callers should
    invoke this whenever both signals are present so the mismatch is operator-visible.

    Names the effective source (``FIXTURE_DATASET`` or ``--dataset``) so operators
    can immediately see which setting to address, consistent with the style of other
    warnings in ``_resolve_ask_scope``. When both are present and ``--dataset``
    overrides ``FIXTURE_DATASET``, the warning names ``--dataset`` and includes the
    overridden fixture value for clarity.
    """
    dataset_label = _format_dataset_label(config_dataset, power_atlas_dataset, fixture_dataset)
    _logger.warning(
        "UNSTRUCTURED_RUN_ID=%r is set and will be "
        "used as the retrieval scope, but %s "
        "is also selected. UNSTRUCTURED_RUN_ID bypasses dataset-aware run "
        "selection and may retrieve from a run that belongs to a different "
        "dataset. Use --latest (in --live mode) to resolve the latest run "
        "for the selected dataset, or --run-id to target a specific run explicitly.",
        env_run_id,
        dataset_label,
    )


def _warn_if_env_run_id_bypasses_dataset_selection(
    env_run_id: str,
    *,
    config_dataset: str | None,
) -> None:
    power_atlas_dataset, fixture_dataset, effective_env_dataset = _current_env_dataset_selection()
    if config_dataset or effective_env_dataset:
        _warn_env_run_id_dataset_mismatch(
            env_run_id,
            config_dataset,
            power_atlas_dataset,
            fixture_dataset,
        )


def _validate_explicit_run_id_dataset_selection(
    config: Config,
    explicit_run_id: str,
) -> None:
    if config.dry_run:
        return

    config_dataset = config.dataset_name
    power_atlas_dataset, fixture_dataset, effective_env_dataset = _current_env_dataset_selection()
    effective_dataset = config_dataset or effective_env_dataset
    if not effective_dataset:
        return

    try:
        expected_dataset_id = resolve_dataset_root(effective_dataset).dataset_id
    except ValueError as exc:
        _logger.warning(
            "Could not resolve dataset %r to "
            "validate --run-id dataset ownership "
            "(%s). Dataset-ownership check skipped.",
            effective_dataset,
            exc,
        )
        return

    actual_dataset_id = _fetch_dataset_id_for_run(config, explicit_run_id)
    if actual_dataset_id is not None and actual_dataset_id != expected_dataset_id:
        _warn_explicit_run_id_dataset_mismatch(
            explicit_run_id,
            expected_dataset_id,
            actual_dataset_id,
            config_dataset=config_dataset,
            power_atlas_dataset=power_atlas_dataset,
            fixture_dataset=fixture_dataset,
        )


def _resolve_latest_dataset_id(config: Config) -> str | None:
    try:
        return resolve_dataset_root(config.dataset_name).dataset_id
    except ValueError as exc:
        _power_atlas_dataset, _fixture_dataset, explicit_env_dataset = _current_env_dataset_selection()
        explicit_source = config.dataset_name or explicit_env_dataset
        if explicit_source:
            raise SystemExit(
                f"Failed to resolve dataset {explicit_source!r}: {exc}"
            ) from exc
        return None


def _resolve_latest_run_scope(
    config: Config,
    *,
    env_run_id: str | None,
    use_latest: bool,
) -> str:
    resolved_dataset_id = _resolve_latest_dataset_id(config)
    latest_run_id = _fetch_latest_unstructured_run_id(config, dataset_id=resolved_dataset_id)
    if latest_run_id is None:
        raise SystemExit(
            "No unstructured ingest runs found in the database. "
            "Run 'ingest-pdf' first, or use --all-runs to query all available data."
        )
    if use_latest and env_run_id and env_run_id != latest_run_id:
        _logger.warning(
            "UNSTRUCTURED_RUN_ID=%r is set but overridden by --latest. "
            "Using latest: %r.",
            env_run_id,
            latest_run_id,
        )
    return latest_run_id


def _resolve_dry_run_ask_scope(
    config: Config,
    *,
    env_run_id: str | None,
) -> tuple[str | None, bool]:
    if env_run_id:
        _warn_if_env_run_id_bypasses_dataset_selection(
            env_run_id,
            config_dataset=config.dataset_name,
        )
        return env_run_id, False
    return None, False


def _resolve_ask_request_context(
    args: argparse.Namespace,
    request_context: RequestContext,
) -> RequestContext:
    config = request_context.config
    env_run_id = _current_env_unstructured_run_id()
    all_runs: bool = getattr(args, "all_runs", False)
    explicit_run_id: str | None = getattr(args, "run_id", None)
    use_latest: bool = getattr(args, "latest", False)

    if all_runs:
        if env_run_id:
            _logger.warning(
                "UNSTRUCTURED_RUN_ID=%r is set "
                "but overridden by --all-runs.",
                env_run_id,
            )
        return replace(request_context, run_id=None, all_runs=True)

    if explicit_run_id:
        if env_run_id and env_run_id != explicit_run_id:
            _logger.warning(
                "UNSTRUCTURED_RUN_ID=%r is set "
                "but overridden by --run-id=%r.",
                env_run_id,
                explicit_run_id,
            )
        _validate_explicit_run_id_dataset_selection(config, explicit_run_id)
        return replace(request_context, run_id=explicit_run_id, all_runs=False)

    if config.dry_run:
        resolved_run_id, resolved_all_runs = _resolve_dry_run_ask_scope(config, env_run_id=env_run_id)
        return replace(request_context, run_id=resolved_run_id, all_runs=resolved_all_runs)

    if not use_latest and env_run_id:
        _warn_if_env_run_id_bypasses_dataset_selection(
            env_run_id,
            config_dataset=config.dataset_name,
        )
        return replace(request_context, run_id=env_run_id, all_runs=False)

    return replace(
        request_context,
        run_id=_resolve_latest_run_scope(config, env_run_id=env_run_id, use_latest=use_latest),
        all_runs=False,
    )


def _resolve_ask_scope(
    args: argparse.Namespace, request_context_or_config: RequestContext | Config
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
    request_context = _ensure_request_context(request_context_or_config, command="ask")
    resolved_request_context = _resolve_ask_request_context(args, request_context)
    return resolved_request_context.run_id, resolved_request_context.all_runs


def _resolve_ask_source_uri(request_context: RequestContext) -> str | None:
    if request_context.all_runs:
        return None
    return str(resolve_dataset_root(request_context.config.dataset_name).pdf_path.resolve().as_uri())


def _prepare_ask_request_context(
    args: argparse.Namespace,
    request_context_or_config: RequestContext | Config,
) -> RequestContext:
    request_context = _ensure_request_context(request_context_or_config, command="ask")
    request_context = _resolve_ask_request_context(args, request_context)
    return replace(request_context, source_uri=_resolve_ask_source_uri(request_context))


def _run_ask_request_context(
    request_context: RequestContext,
    *,
    cluster_aware: bool = False,
    expand_graph: bool = False,
) -> dict[str, Any]:
    return run_retrieval_and_qa_request_context(
        request_context,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )


def _run_claim_extraction_request_context(request_context: RequestContext) -> dict[str, Any]:
    return run_claim_and_mention_extraction_request_context(request_context)


def _run_claim_participation_request_context(request_context: RequestContext) -> dict[str, Any]:
    return run_claim_participation_request_context(request_context)


def _run_entity_resolution_request_context(
    request_context: RequestContext,
    *,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
) -> dict[str, Any]:
    return run_entity_resolution_request_context(
        request_context,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
    )


def _run_pdf_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    pdf_filename: str | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    return run_pdf_ingest_request_context(
        request_context,
        fixtures_dir=fixtures_dir,
        pdf_filename=pdf_filename,
        dataset_id=dataset_id,
    )


def _run_structured_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    return run_structured_ingest_request_context(
        request_context,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
    )


def _run_retrieval_request_context(
    request_context: RequestContext,
    *,
    question: str | None = None,
    cluster_aware: bool = False,
    expand_graph: bool = False,
) -> dict[str, Any]:
    return run_retrieval_and_qa_request_context(
        request_context,
        question=question,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )


def _run_independent_structured_ingest_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: _IndependentStageResources,
    options: _IndependentStageOptions,
) -> dict[str, Any]:
    del options
    return _run_structured_ingest_request_context(
        replace(request_context, run_id=stage_run_id),
        fixtures_dir=resources.fixture_dir,
        dataset_id=resources.dataset_id,
    )


def _run_independent_pdf_ingest_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: _IndependentStageResources,
    options: _IndependentStageOptions,
) -> dict[str, Any]:
    del options
    return _run_pdf_ingest_request_context(
        replace(request_context, run_id=stage_run_id),
        fixtures_dir=resources.fixture_dir,
        pdf_filename=resources.pdf_filename,
        dataset_id=resources.dataset_id,
    )


def _run_independent_claim_extraction_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: _IndependentStageResources,
    options: _IndependentStageOptions,
) -> dict[str, Any]:
    del options
    return _run_claim_extraction_request_context(
        replace(
            request_context,
            run_id=stage_run_id,
            source_uri=resources.pdf_source_uri,
        )
    )


def _run_independent_entity_resolution_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: _IndependentStageResources,
    options: _IndependentStageOptions,
) -> dict[str, Any]:
    del options
    return _run_entity_resolution_request_context(
        replace(
            request_context,
            run_id=stage_run_id,
            source_uri=resources.pdf_source_uri,
        ),
        dataset_id=resources.dataset_id,
    )


def _run_independent_ask_stage(
    request_context: RequestContext,
    stage_run_id: str,
    resources: _IndependentStageResources,
    options: _IndependentStageOptions,
) -> dict[str, Any]:
    del resources
    return _run_ask_request_context(
        replace(
            request_context,
            run_id=stage_run_id if not options.ask_all_runs else None,
        ),
        cluster_aware=options.cluster_aware,
        expand_graph=options.expand_graph,
    )


def _independent_stage_specs() -> dict[str, _IndependentStageSpec]:
    return {
        "ingest-structured": _IndependentStageSpec(
            stage_name="structured_ingest",
            run_scope_key="structured_ingest_run_id",
            runner=_run_independent_structured_ingest_stage,
        ),
        "ingest-pdf": _IndependentStageSpec(
            stage_name="pdf_ingest",
            run_scope_key="unstructured_ingest_run_id",
            runner=_run_independent_pdf_ingest_stage,
        ),
        "extract-claims": _IndependentStageSpec(
            stage_name="claim_and_mention_extraction",
            run_scope_key="unstructured_ingest_run_id",
            runner=_run_independent_claim_extraction_stage,
        ),
        "resolve-entities": _IndependentStageSpec(
            stage_name="entity_resolution",
            run_scope_key="unstructured_ingest_run_id",
            runner=_run_independent_entity_resolution_stage,
        ),
        "ask": _IndependentStageSpec(
            stage_name="retrieval_and_qa",
            run_scope_key="unstructured_ingest_run_id",
            runner=_run_independent_ask_stage,
        ),
    }


def _run_orchestrated_request_context(request_context: RequestContext) -> Path:
    """Run the full demo batch sequence with an unstructured-first posture.

    Sequence:

    **Phase 1 — Unstructured-only pass** (demonstrates meaningful Q&A without structured ingest):

    1. PDF ingest → lexical graph
    2. Claim and mention extraction
    3. Entity resolution in ``unstructured_only`` mode — clusters mentions against each
       other without any structured canonical entity lookup
    4. Q&A — shows that useful retrieval and citation-grounded answers are available
       *before* any structured data is loaded

    **Phase 2 — Structured enrichment pass** (structured ingest is additive):

    5. Structured ingest — writes :CanonicalEntity nodes and structured claims as optional
       verification/enrichment; this step is intentionally deferred to demonstrate that
       unstructured data stands on its own
    6. Entity resolution in ``hybrid`` mode — enriches existing :ResolvedEntityCluster
       nodes with :ALIGNED_WITH edges to matching :CanonicalEntity nodes where available;
       gracefully degrades if no matches exist
    7. Final Q&A — demonstrates enriched retrieval after structured alignment
    """
    config = request_context.config
    config.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now_iso()
    structured_run_id = make_run_id("structured_ingest")
    unstructured_run_id = make_run_id("unstructured_ingest")

    dataset_root = resolve_dataset_root(config.dataset_name)
    structured_request_context = _scoped_request_context(request_context, run_id=structured_run_id)
    unstructured_request_context = _scoped_request_context(request_context, run_id=unstructured_run_id)

    # ── Phase 1: Unstructured-only pass ──────────────────────────────────────
    # Ingest the PDF and build the lexical graph first.
    pdf_stage = _run_pdf_ingest_request_context(
        unstructured_request_context,
        fixtures_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        dataset_id=dataset_root.dataset_id,
    )
    pdf_source_uri = _extract_pdf_source_uri(pdf_stage)
    scoped_unstructured_request_context = _scoped_request_context(
        request_context,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
    )

    claim_stage = _run_claim_extraction_request_context(scoped_unstructured_request_context)
    # Link ExtractedClaim subject/object slots to EntityMention nodes in the same
    # chunk/run via deterministic text matching (raw_exact → casefold_exact →
    # normalized_exact).  Runs after extraction so all nodes are already in the graph.
    claim_participation_stage = _run_claim_participation_request_context(scoped_unstructured_request_context)
    # Cluster extracted mentions against each other; no CanonicalEntity lookup required.
    # Use a mode-specific artifact subdirectory so the hybrid pass does not overwrite
    # the unstructured-only artifacts when both passes share the same run_id.
    # Pass dataset_id explicitly (preferred explicit-scope pattern) rather than relying
    # on the ambient value set by set_dataset_id() earlier in orchestration.
    entity_resolution_unstructured_stage = _run_entity_resolution_request_context(
        scoped_unstructured_request_context,
        resolution_mode="unstructured_only",
        artifact_subdir="entity_resolution_unstructured_only",
        dataset_id=dataset_root.dataset_id,
    )
    # Demonstrate that meaningful Q&A is available before any structured ingest.
    retrieval_unstructured_stage = _run_retrieval_request_context(
        scoped_unstructured_request_context,
        question=getattr(config, "question", None),
    )

    # ── Phase 2: Structured enrichment pass ──────────────────────────────────
    # Structured ingest is deferred to demonstrate it is optional enrichment.
    structured_stage = _run_structured_ingest_request_context(
        structured_request_context,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )
    # Hybrid alignment enriches existing ResolvedEntityCluster nodes with ALIGNED_WITH
    # edges to CanonicalEntity nodes; gracefully degrades when no matches exist.
    # Use a separate artifact subdirectory to preserve the unstructured-only artifacts.
    entity_resolution_hybrid_stage = _run_entity_resolution_request_context(
        scoped_unstructured_request_context,
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution_hybrid",
        dataset_id=dataset_root.dataset_id,
    )
    # Final Q&A after structured enrichment shows the additive benefit.
    retrieval_stage = _run_retrieval_request_context(
        scoped_unstructured_request_context,
        question=getattr(config, "question", None),
    )

    # Post-hybrid retrieval benchmark: validates canonical traversal quality after
    # the full pipeline (including hybrid alignment).  Runs automatically as part of
    # every orchestrated `ingest` to produce a benchmark artifact and regression
    # readout without requiring a separate manual invocation.  The artifact is written
    # to <output_dir>/runs/<unstructured_run_id>/retrieval_benchmark/retrieval_benchmark.json.
    # In dry-run mode a stub artifact is produced (no live Neo4j calls are made).
    # alignment_version is taken from the hybrid stage output so the benchmark
    # queries scope to the exact ALIGNED_WITH edge version that was just written,
    # preventing cross-version aggregation when alignment is re-run on the same run_id.
    _hybrid_alignment_version: str | None = (
        entity_resolution_hybrid_stage.get("alignment_version")
        if isinstance(entity_resolution_hybrid_stage, dict)
        else None
    )
    if _hybrid_alignment_version is None:
        _logger.warning(
            "Orchestrated retrieval benchmark: alignment_version was not forwarded from the "
            "hybrid entity resolution stage (got None). The benchmark will aggregate across "
            "ALL alignment versions in the database rather than scoping to the current "
            "alignment cohort. If this is unexpected, check that the hybrid stage completed "
            "successfully and returned an 'alignment_version' key."
        )
    try:
        benchmark_stage = run_retrieval_benchmark(
            config,
            run_id=unstructured_run_id,
            dataset_id=dataset_root.dataset_id,
            alignment_version=_hybrid_alignment_version,
            output_dir=config.output_dir,
            # Deduplication: the orchestrator already emitted a warning above when
            # alignment_version is None, so suppress the duplicate from the stage.
            suppress_alignment_version_warning=_hybrid_alignment_version is None,
        )
    except Exception as _benchmark_exc:  # noqa: BLE001
        _tb = traceback.format_exc()
        _logger.error(
            "retrieval_benchmark failed; manifest will be written with error status. %s", _tb
        )
        benchmark_stage = {
            "status": "error",
            "error": str(_benchmark_exc),
            "traceback": _tb,
        }

    finished_at = _now_iso()

    # Stage warnings must be surfaced at orchestration boundaries so operators see
    # non-fatal issues without manually inspecting nested stage artifacts.
    for _stage_name, _stage_result in [
        ("pdf_ingest", pdf_stage),
        ("claim_and_mention_extraction", claim_stage),
        ("claim_participation", claim_participation_stage),
        ("entity_resolution_unstructured_only", entity_resolution_unstructured_stage),
        ("retrieval_and_qa_unstructured_only", retrieval_unstructured_stage),
        ("structured_ingest", structured_stage),
        ("entity_resolution_hybrid", entity_resolution_hybrid_stage),
        ("retrieval_and_qa", retrieval_stage),
        ("retrieval_benchmark", benchmark_stage),
    ]:
        if isinstance(_stage_result, dict):
            for _warning in _stage_result.get("warnings") or []:
                _logger.warning("Stage %r warning: %s", _stage_name, _warning)

    manifest = build_batch_manifest(
        config=config,
        structured_run_id=structured_run_id,
        unstructured_run_id=unstructured_run_id,
        structured_stage=structured_stage,
        pdf_stage=pdf_stage,
        claim_stage=claim_stage,
        claim_participation_stage=claim_participation_stage,
        entity_resolution_unstructured_stage=entity_resolution_unstructured_stage,
        retrieval_unstructured_stage=retrieval_unstructured_stage,
        entity_resolution_hybrid_stage=entity_resolution_hybrid_stage,
        retrieval_stage=retrieval_stage,
        retrieval_benchmark_stage=benchmark_stage,
        dataset_id=dataset_root.dataset_id,
        started_at=started_at,
        finished_at=finished_at,
    )

    manifest_path = config.output_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def _run_orchestrated(request_context_or_config: RequestContext | Config) -> Path:
    request_context = _ensure_request_context(request_context_or_config, command="ingest")
    return _run_orchestrated_request_context(request_context)


def _run_independent_stage(
    config_or_request_context: RequestContext | Config,
    command: str,
    *,
    resolved_run_id: str | None = None,
    all_runs: bool = False,
    cluster_aware: bool = False,
    expand_graph: bool = False,
) -> Path:
    request_context = _ensure_request_context(config_or_request_context, command=command)
    request_context = replace(
        request_context,
        run_id=resolved_run_id if resolved_run_id is not None else request_context.run_id,
        all_runs=all_runs or request_context.all_runs,
    )
    if command == "ask" and request_context.source_uri is None and not request_context.all_runs:
        request_context = replace(request_context, source_uri=_resolve_ask_source_uri(request_context))
    config = request_context.config
    config.output_dir.mkdir(parents=True, exist_ok=True)
    # all_runs is only relevant for the ask command.
    _ask_all_runs = request_context.all_runs and command == "ask"

    # Resolve the active dataset root for commands that need fixture paths.
    # For `ask --all-runs`, no dataset-specific fixture path is required, so we
    # skip resolution to avoid raising on a multi-dataset repo.
    if not _ask_all_runs:
        dataset_root = resolve_dataset_root(config.dataset_name)
        _fixture_dir: Path | None = dataset_root.root
        _pdf_filename: str | None = dataset_root.pdf_filename
        _pdf_source_uri: str | None = str((_fixture_dir / "unstructured" / _pdf_filename).resolve().as_uri())
    else:
        dataset_root = None
        _fixture_dir = None
        _pdf_filename = None
        _pdf_source_uri = None

    resources = _IndependentStageResources(
        dataset_id=dataset_root.dataset_id if dataset_root is not None else None,
        fixture_dir=_fixture_dir,
        pdf_filename=_pdf_filename,
        pdf_source_uri=_pdf_source_uri,
    )
    options = _IndependentStageOptions(
        ask_all_runs=_ask_all_runs,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )
    stage_specs = _independent_stage_specs()
    if command not in stage_specs:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_spec = stage_specs[command]
    stage_name = stage_spec.stage_name
    run_scope_key = stage_spec.run_scope_key
    run_scope = run_scope_key.removesuffix("_run_id")
    stage_run_id = _resolve_independent_stage_run_id(
        command,
        request_context,
        run_scope=run_scope,
        ask_all_runs=_ask_all_runs,
    )
    started_at = _now_iso()
    stage_output = stage_spec.runner(request_context, stage_run_id, resources, options)
    finished_at = _now_iso()
    # In all-runs mode the ask run is not associated with any specific ingest run, so
    # run_scopes.unstructured_ingest_run_id must be null rather than a fake sentinel.
    # Retrieval scope details are captured in retrieval_scope within the stage output.
    # For all other commands, scope_run_id == stage_run_id (default behaviour).
    # Write the manifest into a stage-scoped directory: runs/<run_id>/<stage_name>/manifest.json
    # Using a stage-name subdirectory prevents manifests from different stages that share the
    # same run_id (e.g. extract-claims, resolve-entities, ask all use UNSTRUCTURED_RUN_ID) from
    # overwriting each other.  write_manifest() calls mkdir internally so no explicit mkdir needed.
    return _write_independent_stage_manifest(
        config=config,
        stage_name=stage_name,
        stage_run_id=stage_run_id,
        run_scope_key=run_scope_key,
        scope_run_id=None if _ask_all_runs else stage_run_id,
        dataset_id=dataset_root.dataset_id if dataset_root is not None else None,
        stage_output=stage_output,
        started_at=started_at,
        finished_at=finished_at,
    )


def run_demo(config_or_request_context: RequestContext | Config) -> Path:
    return _run_orchestrated(config_or_request_context)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_args(argv)

# Backwards-compatible aliases for legacy tests and scripts.
def _lint_and_clean_structured_csvs(run_id: str, output_dir: Path) -> dict[str, Any]:
    dataset_root = resolve_dataset_root()
    return lint_and_clean_structured_csvs(
        run_id=run_id,
        output_dir=output_dir,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )


def _run_structured_ingest(config: Config, run_id: str) -> dict[str, Any]:
    dataset_root = resolve_dataset_root(config.dataset_name)
    return _run_structured_ingest_request_context(
        _request_context_from_config(config, command="ingest-structured", run_id=run_id),
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )


def _run_pdf_ingest(config: Config, run_id: str | None = None) -> dict[str, Any]:
    dataset_root = resolve_dataset_root(config.dataset_name)
    return _run_pdf_ingest_request_context(
        _request_context_from_config(config, command="ingest-pdf", run_id=run_id),
        fixtures_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        dataset_id=dataset_root.dataset_id,
    )


def _run_claim_and_mention_extraction(
    config: Config,
    *,
    run_id: str,
    source_uri: str | None,
) -> dict[str, Any]:
    return _run_claim_extraction_request_context(
        _request_context_from_config(
            config,
            command="extract-claims",
            run_id=run_id,
            source_uri=source_uri,
        )
    )


def _run_entity_resolution(
    config: Config,
    *,
    run_id: str,
    source_uri: str | None = None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
) -> dict[str, Any]:
    return _run_entity_resolution_request_context(
        _request_context_from_config(
            config,
            command="resolve-entities",
            run_id=run_id,
            source_uri=source_uri,
        ),
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
    )


def _run_retrieval_and_qa(
    config: Config,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    question: str | None = None,
    cluster_aware: bool = False,
    expand_graph: bool = False,
    all_runs: bool = False,
) -> dict[str, Any]:
    return _run_retrieval_request_context(
        _request_context_from_config(
            config,
            command="ask",
            run_id=run_id,
            all_runs=all_runs,
            source_uri=source_uri,
        ),
        question=question,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )


run_independent_demo = _run_independent_stage


def main() -> None:
    args = parse_args()
    if args.command == "lint-structured":
        request_context = _build_request_context_from_args(args, dry_run=True)
        config = request_context.config
        dataset_root = resolve_dataset_root(config.dataset_name)
        run_id = make_run_id("structured_lint")
        lint_result = lint_and_clean_structured_csvs(
            run_id=run_id,
            output_dir=config.output_dir,
            fixtures_dir=dataset_root.root,
            dataset_id=dataset_root.dataset_id,
        )
        print(f"Structured lint report written to: {lint_result['lint_report_path']}")
        return
    config_commands = {"ingest", "ingest-structured", "ingest-pdf", "extract-claims", "resolve-entities", "ask"}
    if args.command in config_commands:
        request_context = _build_request_context_from_args(args)
        try:
            if args.command == "ingest":
                manifest_path = run_demo(request_context)
                print(f"Demo manifest written to: {manifest_path}")
            elif args.command == "ask" and getattr(args, "interactive", False):
                # Interactive mode: start a REPL session; no manifest is written.
                if request_context.config.dry_run:
                    raise SystemExit(
                        "Interactive 'ask' is not supported in dry-run mode. "
                        "Re-run the command with --live to enable live Neo4j/OpenAI calls."
                    )
                request_context = _prepare_ask_request_context(args, request_context)
                print(
                    f"Using retrieval scope: {_format_scope_label(request_context.run_id, request_context.all_runs)}"
                )
                run_interactive_qa_request_context(
                    request_context,
                    cluster_aware=getattr(args, "cluster_aware", False),
                    expand_graph=getattr(args, "expand_graph", False),
                    debug=getattr(args, "debug", False),
                )
            elif args.command == "ask":
                # Non-interactive ask: resolve scope, print it, then run and write manifest.
                request_context = _prepare_ask_request_context(args, request_context)
                print(
                    f"Using retrieval scope: {_format_scope_label(request_context.run_id, request_context.all_runs)}"
                )
                manifest_path = _run_independent_stage(
                    request_context,
                    args.command,
                    resolved_run_id=request_context.run_id,
                    all_runs=request_context.all_runs,
                    cluster_aware=getattr(args, "cluster_aware", False),
                    expand_graph=getattr(args, "expand_graph", False),
                )
                print(f"Independent run manifest written to: {manifest_path}")
            else:
                manifest_path = _run_independent_stage(request_context, args.command)
                print(f"Independent run manifest written to: {manifest_path}")
        except SystemExit:
            raise
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return
    if args.command == "reset":
        if not getattr(args, "confirm", False):
            print(
                "To reset the demo graph, run:\n"
                "  python demo/reset_demo_db.py --confirm\n"
                "Or pass --confirm to this command:\n"
                "  python demo/run_demo.py --live reset --confirm\n"
                "See demo/reset_demo_db.py for full usage."
            )
            return
        if getattr(args, "dry_run", True):
            raise SystemExit(
                "reset --confirm requires --live; re-run with:\n"
                "  python demo/run_demo.py --live reset --confirm"
            )
        if not args.neo4j_password or args.neo4j_password == "CHANGE_ME_BEFORE_USE":
            raise SystemExit(
                "Set NEO4J_PASSWORD or pass --neo4j-password when running reset --confirm"
            )
        from demo.reset_demo_db import run_reset

        request_context = _build_request_context_from_args(args)
        config = request_context.config
        driver = create_neo4j_driver(config)
        with driver:
            report = run_reset(
                driver=driver,
                database=config.neo4j_database,
                output_dir=config.output_dir,
                pipeline_contract=request_context.pipeline_contract,
            )
        print(
            f"Demo graph reset complete: "
            f"database={report['target_database']} "
            f"nodes_deleted={report['deleted_nodes']} "
            f"relationships_deleted={report['deleted_relationships']} "
            f"indexes_dropped={report['indexes_dropped']}"
        )
        if report.get("warnings"):
            for w in report["warnings"]:
                # Intentional passthrough: these are human-readable strings returned
                # by run_reset() (e.g. idempotent no-op notices).  They are not
                # ownership/benchmark warnings and deliberately go to stdout so they
                # appear inline with the reset completion summary printed above.
                print(f"  warning: {w}")
        if report.get("report_path"):
            print(f"Reset report written to: {report['report_path']}")
        return
    print(f"Stub: '{args.command}' command scaffold is ready.")


if __name__ == "__main__":
    main()
