from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from demo.contracts import pipeline as pipeline_contracts

pipeline_contracts.refresh_pipeline_contract()

from demo.contracts import (  # noqa: E402
    ARTIFACTS_DIR,
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
    CHUNK_FALLBACK_STRIDE,
    DEFAULT_DB,
    Config,
    EMBEDDER_MODEL_NAME,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
    resolve_dataset_root,
    set_dataset_id,
)
from demo.contracts.manifest import write_manifest, write_manifest_md  # noqa: E402
from demo.stages import (  # noqa: E402
    lint_and_clean_structured_csvs,
    run_claim_and_mention_extraction,
    run_claim_participation,
    run_entity_resolution,
    run_interactive_qa,
    run_pdf_ingest,
    run_retrieval_and_qa,
    run_structured_ingest,
)
from demo.stages.retrieval_and_qa import _format_scope_label  # noqa: E402
from demo.stages.retrieval_benchmark import run_retrieval_benchmark  # noqa: E402
from demo.stages.pdf_ingest import sha256_file  # noqa: E402, F401 - re-exported for callers and tests

_logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "CHANGE_ME_BEFORE_USE"))
    parser.add_argument("--neo4j-database", default=DEFAULT_DB)
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--dataset",
        default=os.getenv("FIXTURE_DATASET"),
        dest="dataset",
        metavar="DATASET_NAME",
        help=(
            "Name of the fixture dataset to use (directory under demo/fixtures/datasets/). "
            "Defaults to the FIXTURE_DATASET environment variable; if neither is set, "
            "the single available dataset is auto-discovered."
        ),
    )


def _build_config_from_args(args: argparse.Namespace) -> Config:
    if not args.dry_run and args.neo4j_password in ("", "CHANGE_ME_BEFORE_USE"):
        raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
    return Config(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model=args.openai_model,
        question=getattr(args, "question", None),
        resolution_mode=getattr(args, "resolution_mode", None) or "unstructured_only",
        dataset_name=getattr(args, "dataset", None) or None,
    )


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
    """Query Neo4j for the latest unstructured ingest run_id from Chunk nodes.

    When *dataset_id* is provided, only Chunk nodes stamped with that
    dataset_id are considered, ensuring dataset-aware run selection in
    multi-dataset repositories.  Without *dataset_id*, the query spans all
    datasets (legacy behaviour, single-dataset repos).

    Returns the run_id of the most recently created unstructured ingest run
    (filtered to *dataset_id* when given), or None if no matching Chunk nodes
    exist.  Only call this in live mode; it opens a real Neo4j connection.

    Ordering assumption: run_ids are formatted as
    ``unstructured_ingest-<ISO8601_timestamp>-<uuid8>`` (e.g.
    ``unstructured_ingest-20260312T055234558447Z-47b28b7f``).  The embedded
    timestamp string is lexicographically sortable so ``ORDER BY run_id DESC``
    reliably returns the most recent run.  If the run_id format ever changes
    to a non-sortable scheme, this query must be updated accordingly.
    """
    import neo4j as _neo4j

    with _neo4j.GraphDatabase.driver(
        config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password)
    ) as driver:
        with driver.session(database=config.neo4j_database) as session:
            if dataset_id is not None:
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.run_id STARTS WITH 'unstructured_ingest' "
                    "AND c.dataset_id = $dataset_id "
                    "RETURN c.run_id ORDER BY c.run_id DESC LIMIT 1",
                    dataset_id=dataset_id,
                )
            else:
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.run_id STARTS WITH 'unstructured_ingest' "
                    "RETURN c.run_id ORDER BY c.run_id DESC LIMIT 1"
                )
            record = result.single()
            return record[0] if record else None


def _fetch_dataset_id_for_run(config: Config, run_id: str) -> str | None:
    """Query Neo4j for the dataset_id stamped on Chunk nodes belonging to *run_id*.

    Fetches up to two distinct dataset_id values across Chunk nodes for this run.
    This is enough to distinguish among zero, one, or multiple stamped dataset
    ids without collecting the full distinct set for very large runs.

    If multiple distinct values are found (indicating an inconsistently-ingested
    graph), a WARNING is logged and the first sorted dataset_id is returned so
    callers can continue deterministic dataset-ownership mismatch checks.

    Returns None if no Chunk nodes with a non-null dataset_id exist for the run.
    If multiple distinct non-null dataset_id values are present on the run's
    Chunk nodes, returns the first sorted value after printing a warning.
    Only call this in live mode; it opens a real Neo4j connection.
    """
    import neo4j as _neo4j

    with _neo4j.GraphDatabase.driver(
        config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password)
    ) as driver:
        with driver.session(database=config.neo4j_database) as session:
            result = session.run(
                "MATCH (c:Chunk) WHERE c.run_id = $run_id AND c.dataset_id IS NOT NULL "
                "RETURN DISTINCT c.dataset_id AS dataset_id "
                "ORDER BY dataset_id "
                "LIMIT 2",
                run_id=run_id,
            )
            dataset_ids = [record["dataset_id"] for record in result]
            if not dataset_ids:
                return None
            if len(dataset_ids) > 1:
                first_dataset_id = dataset_ids[0]
                _logger.warning(
                    "run_id=%r has Chunk nodes stamped with multiple "
                    "distinct dataset_ids (including %r and "
                    "%r). The graph may have been inconsistently "
                    "ingested. Proceeding with dataset-ownership validation using "
                    "the first sorted dataset_id, %r.",
                    run_id,
                    first_dataset_id,
                    dataset_ids[1],
                    first_dataset_id,
                )
                return first_dataset_id
            return dataset_ids[0]


def _format_dataset_label(
    config_dataset: str | None,
    fixture_dataset: str | None,
) -> str:
    """Return a human-readable label for the effective dataset selection.

    When ``--dataset`` overrides ``FIXTURE_DATASET``, both values are shown for
    clarity.  Used consistently across all dataset-mismatch warnings.
    """
    if config_dataset and fixture_dataset and config_dataset != fixture_dataset:
        return (
            f"--dataset={config_dataset!r} "
            f"(overrides FIXTURE_DATASET={fixture_dataset!r})"
        )
    if fixture_dataset:
        return f"FIXTURE_DATASET={fixture_dataset!r}"
    return f"--dataset={config_dataset!r}"


def _warn_explicit_run_id_dataset_mismatch(
    explicit_run_id: str,
    expected_dataset_id: str,
    actual_dataset_id: str,
    *,
    config_dataset: str | None,
    fixture_dataset: str | None,
) -> None:
    """Emit a WARNING log when --run-id belongs to a different dataset than the one selected.

    Names the effective dataset source (``FIXTURE_DATASET`` or ``--dataset``) for
    operator clarity, consistent with ``_warn_env_run_id_dataset_mismatch``.
    When both ``--dataset`` and ``FIXTURE_DATASET`` are present and differ,
    ``--dataset`` is the effective override and is named as such.
    """
    dataset_label = _format_dataset_label(config_dataset, fixture_dataset)
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
    dataset_label = _format_dataset_label(config_dataset, fixture_dataset)
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


def _resolve_ask_scope(
    args: argparse.Namespace, config: Config
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
    env_run_id = os.getenv("UNSTRUCTURED_RUN_ID")
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
        return None, True

    if explicit_run_id:
        if env_run_id and env_run_id != explicit_run_id:
            _logger.warning(
                "UNSTRUCTURED_RUN_ID=%r is set "
                "but overridden by --run-id=%r.",
                env_run_id,
                explicit_run_id,
            )
        # Dataset-integrity check: when a dataset is explicitly selected, verify
        # that --run-id actually belongs to that dataset.  Skip in dry-run mode
        # because Neo4j is unavailable and the run cannot be verified.
        if not config.dry_run:
            _cli_dataset = config.dataset_name
            _fixture_dataset = os.getenv("FIXTURE_DATASET")
            effective_dataset = _cli_dataset or _fixture_dataset
            if effective_dataset:
                try:
                    expected_dataset_id = resolve_dataset_root(effective_dataset).dataset_id
                except ValueError as exc:
                    # Dataset resolution failed (e.g. typo or unknown dataset name).
                    # Emit a visible warning so the operator knows validation was
                    # skipped; do not raise so the pipeline can still proceed with
                    # the explicitly-requested run-id.
                    _logger.warning(
                        "Could not resolve dataset %r to "
                        "validate --run-id dataset ownership "
                        "(%s). Dataset-ownership check skipped.",
                        effective_dataset,
                        exc,
                    )
                else:
                    actual_dataset_id = _fetch_dataset_id_for_run(config, explicit_run_id)
                    if actual_dataset_id is not None and actual_dataset_id != expected_dataset_id:
                        _warn_explicit_run_id_dataset_mismatch(
                            explicit_run_id,
                            expected_dataset_id,
                            actual_dataset_id,
                            config_dataset=_cli_dataset,
                            fixture_dataset=_fixture_dataset,
                        )
        return explicit_run_id, False

    # Default / --latest: resolve the latest run_id.
    if config.dry_run:
        # In dry-run mode, Neo4j is unavailable; honour env var if set, else proceed
        # without a run scope (dry-run stubs don't require a real run_id).
        if env_run_id:
            # Dataset-integrity warning (dry-run): UNSTRUCTURED_RUN_ID bypasses
            # dataset-aware run selection when an explicit dataset is also provided.
            # The run pointed to by the env var may belong to a different dataset.
            # Use --latest (in --live mode) or --run-id for guaranteed
            # dataset-scoped selection.
            config_dataset = config.dataset_name
            fixture_dataset = os.getenv("FIXTURE_DATASET")
            if config_dataset or fixture_dataset:
                _warn_env_run_id_dataset_mismatch(env_run_id, config_dataset, fixture_dataset)
            return env_run_id, False
        return None, False

    # Live mode: resolve run_id according to precedence:
    # CLI flags (--run-id/--latest/--all-runs) > UNSTRUCTURED_RUN_ID > implicit latest.
    if not use_latest and env_run_id:
        # No explicit --latest flag; honour UNSTRUCTURED_RUN_ID if set.
        # Dataset-integrity warning: UNSTRUCTURED_RUN_ID bypasses dataset-aware run
        # selection when an explicit dataset is also provided (via --dataset or
        # FIXTURE_DATASET).  The run pointed to by the env var may belong to a
        # different dataset, which would silently retrieve from the wrong scope.
        # Warn the operator so the mismatch is visible.  Use --latest or --run-id
        # to enforce dataset-scoped selection.
        config_dataset = config.dataset_name
        fixture_dataset = os.getenv("FIXTURE_DATASET")
        if config_dataset or fixture_dataset:
            _warn_env_run_id_dataset_mismatch(env_run_id, config_dataset, fixture_dataset)
        return env_run_id, False

    # Either --latest was explicitly requested, or no env var is set: query Neo4j.
    # Resolve dataset_id for dataset-aware latest run selection so that in a
    # multi-dataset repo ``ask --dataset demo_dataset_v1`` never picks up a run
    # that belongs to demo_dataset_v2.
    resolved_dataset_id: str | None = None
    try:
        resolved_dataset_id = resolve_dataset_root(config.dataset_name).dataset_id
    except ValueError as exc:
        # Treat both --dataset <name> and FIXTURE_DATASET=<name> as explicit
        # selections; a failure to resolve an explicit name must never silently
        # fall through to an unfiltered query that could pick the wrong run.
        explicit_source = config.dataset_name or os.getenv("FIXTURE_DATASET")
        if explicit_source:
            raise SystemExit(
                f"Failed to resolve dataset {explicit_source!r}: {exc}"
            ) from exc
        # Implicit/auto-discovered dataset resolution failed (e.g.
        # AmbiguousDatasetError with no explicit selection): preserve legacy
        # behaviour by falling back to an unfiltered latest-run query.
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
    return latest_run_id, False


def _run_orchestrated(config: Config) -> Path:
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
    config.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now_iso()
    structured_run_id = make_run_id("structured_ingest")
    unstructured_run_id = make_run_id("unstructured_ingest")

    dataset_root = resolve_dataset_root(config.dataset_name)
    set_dataset_id(dataset_root.dataset_id)

    # ── Phase 1: Unstructured-only pass ──────────────────────────────────────
    # Ingest the PDF and build the lexical graph first.
    pdf_stage = run_pdf_ingest(
        config,
        unstructured_run_id,
        fixtures_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        dataset_id=dataset_root.dataset_id,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        chunk_label=CHUNK_EMBEDDING_LABEL,
        embedding_property=CHUNK_EMBEDDING_PROPERTY,
        embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model=EMBEDDER_MODEL_NAME,
        chunk_stride=CHUNK_FALLBACK_STRIDE,
    )
    pdf_source_uri = pdf_stage.get("provenance", {}).get("source_uri") if isinstance(pdf_stage, dict) else None
    if not pdf_source_uri and isinstance(pdf_stage, dict):
        documents = pdf_stage.get("documents") if isinstance(pdf_stage.get("documents"), list) else []
        pdf_source_uri = documents[0] if documents else None

    claim_stage = run_claim_and_mention_extraction(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
    )
    # Link ExtractedClaim subject/object slots to EntityMention nodes in the same
    # chunk/run via deterministic text matching (raw_exact → casefold_exact →
    # normalized_exact).  Runs after extraction so all nodes are already in the graph.
    claim_participation_stage = run_claim_participation(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
    )
    # Cluster extracted mentions against each other; no CanonicalEntity lookup required.
    # Use a mode-specific artifact subdirectory so the hybrid pass does not overwrite
    # the unstructured-only artifacts when both passes share the same run_id.
    # Pass dataset_id explicitly (preferred explicit-scope pattern) rather than relying
    # on the ambient value set by set_dataset_id() earlier in orchestration.
    entity_resolution_unstructured_stage = run_entity_resolution(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        resolution_mode="unstructured_only",
        artifact_subdir="entity_resolution_unstructured_only",
        dataset_id=dataset_root.dataset_id,
    )
    # Demonstrate that meaningful Q&A is available before any structured ingest.
    retrieval_unstructured_stage = run_retrieval_and_qa(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        question=getattr(config, "question", None),
    )

    # ── Phase 2: Structured enrichment pass ──────────────────────────────────
    # Structured ingest is deferred to demonstrate it is optional enrichment.
    structured_stage = run_structured_ingest(
        config, structured_run_id,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )
    # Hybrid alignment enriches existing ResolvedEntityCluster nodes with ALIGNED_WITH
    # edges to CanonicalEntity nodes; gracefully degrades when no matches exist.
    # Use a separate artifact subdirectory to preserve the unstructured-only artifacts.
    entity_resolution_hybrid_stage = run_entity_resolution(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution_hybrid",
        dataset_id=dataset_root.dataset_id,
    )
    # Final Q&A after structured enrichment shows the additive benefit.
    retrieval_stage = run_retrieval_and_qa(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
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


def _run_independent_stage(
    config: Config,
    command: str,
    *,
    resolved_run_id: str | None = None,
    all_runs: bool = False,
    cluster_aware: bool = False,
    expand_graph: bool = False,
) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    # all_runs is only relevant for the ask command.
    _ask_all_runs = all_runs and command == "ask"

    # Resolve the active dataset root for commands that need fixture paths.
    # For `ask --all-runs`, no dataset-specific fixture path is required, so we
    # skip resolution to avoid raising on a multi-dataset repo.
    if not _ask_all_runs:
        dataset_root = resolve_dataset_root(config.dataset_name)
        set_dataset_id(dataset_root.dataset_id)
        _fixture_dir: Path | None = dataset_root.root
        _pdf_filename: str | None = dataset_root.pdf_filename
        _pdf_source_uri: str | None = str((_fixture_dir / "unstructured" / _pdf_filename).resolve().as_uri())
    else:
        dataset_root = None
        _fixture_dir = None
        _pdf_filename = None
        _pdf_source_uri = None

    stage_runners: dict[str, tuple[str, str, Callable[[Config, str], dict[str, Any]]]] = {
        "ingest-structured": (
            "structured_ingest",
            "structured_ingest_run_id",
            lambda cfg, stage_run_id: run_structured_ingest(
                cfg, stage_run_id,
                fixtures_dir=_fixture_dir,
                dataset_id=dataset_root.dataset_id,
            ),
        ),
        "ingest-pdf": (
            "pdf_ingest",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_pdf_ingest(
                cfg,
                stage_run_id,
                fixtures_dir=_fixture_dir,
                pdf_filename=_pdf_filename,
                dataset_id=dataset_root.dataset_id,
                index_name=CHUNK_EMBEDDING_INDEX_NAME,
                chunk_label=CHUNK_EMBEDDING_LABEL,
                embedding_property=CHUNK_EMBEDDING_PROPERTY,
                embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                embedder_model=EMBEDDER_MODEL_NAME,
                chunk_stride=CHUNK_FALLBACK_STRIDE,
            ),
        ),
        "extract-claims": (
            "claim_and_mention_extraction",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_claim_and_mention_extraction(
                cfg,
                run_id=stage_run_id,
                # Independent-stage default: use the active dataset's PDF URI.
                # This is intentional — the dataset fixture is the stable source for all
                # independent runs.  In the orchestrated batch path, source_uri is
                # derived from the prior pdf_ingest stage output instead.
                source_uri=_pdf_source_uri,
            ),
        ),
        "resolve-entities": (
            "entity_resolution",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_entity_resolution(
                cfg,
                run_id=stage_run_id,
                # Independent-stage default: use the active dataset's PDF URI.
                # See note above for extract-claims.
                source_uri=_pdf_source_uri,
                dataset_id=dataset_root.dataset_id,
            ),
        ),
        "ask": (
            "retrieval_and_qa",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_retrieval_and_qa(
                cfg,
                run_id=stage_run_id if not _ask_all_runs else None,
                question=getattr(cfg, "question", None),
                # In all-runs mode, do not constrain by source_uri so that retrieval
                # queries the whole database (no run_id and no source_uri filter).
                # In single-run mode, default to the active dataset's PDF URI.
                source_uri=None if _ask_all_runs else _pdf_source_uri,
                index_name=CHUNK_EMBEDDING_INDEX_NAME,
                all_runs=_ask_all_runs,
                cluster_aware=cluster_aware,
                expand_graph=expand_graph,
            ),
        ),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    if command in ("extract-claims", "resolve-entities"):
        env_run_id = os.getenv("UNSTRUCTURED_RUN_ID")
        if not env_run_id:
            raise ValueError(
                "UNSTRUCTURED_RUN_ID is not set. When running "
                f"'{command}' independently, set this to the run_id from a prior "
                "'ingest' or 'ingest-pdf' command whose unstructured data you want to process "
                "(for example, a value like 'unstructured_ingest-20260304T224739123456Z-1a2b3c4d')."
            )
        stage_run_id = env_run_id
    elif command == "ask":
        # Scope for ask has already been resolved by _resolve_ask_scope in main().
        # resolved_run_id may be None when all_runs=True or in dry-run without a scope.
        if _ask_all_runs:
            # Whole-database retrieval is not scoped to any ingest run, so we generate
            # a unique artifact id for this ask execution rather than using the sentinel
            # "all_runs" string, which is not a real ingest run id.
            stage_run_id = make_run_id("ask")
        elif resolved_run_id is not None:
            stage_run_id = resolved_run_id
        else:
            # dry-run without a specific run scope; use a placeholder to keep the path valid.
            stage_run_id = "dry_run_no_scope"
    else:
        stage_run_id = make_run_id(run_scope)
    started_at = _now_iso()
    stage_output = stage_runner(config, stage_run_id)
    finished_at = _now_iso()
    # In all-runs mode the ask run is not associated with any specific ingest run, so
    # run_scopes.unstructured_ingest_run_id must be null rather than a fake sentinel.
    # Retrieval scope details are captured in retrieval_scope within the stage output.
    # For all other commands, scope_run_id == stage_run_id (default behaviour).
    manifest = build_stage_manifest(
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
    # Write the manifest into a stage-scoped directory: runs/<run_id>/<stage_name>/manifest.json
    # Using a stage-name subdirectory prevents manifests from different stages that share the
    # same run_id (e.g. extract-claims, resolve-entities, ask all use UNSTRUCTURED_RUN_ID) from
    # overwriting each other.  write_manifest() calls mkdir internally so no explicit mkdir needed.
    manifest_path = config.output_dir / "runs" / stage_run_id / stage_name / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_manifest_md(manifest_path, manifest)
    return manifest_path


def run_demo(config: Config) -> Path:
    return _run_orchestrated(config)


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
    return run_structured_ingest(config, run_id, fixtures_dir=dataset_root.root, dataset_id=dataset_root.dataset_id)


def _run_pdf_ingest(config: Config, run_id: str | None = None) -> dict[str, Any]:
    dataset_root = resolve_dataset_root(config.dataset_name)
    return run_pdf_ingest(
        config,
        run_id,
        fixtures_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        dataset_id=dataset_root.dataset_id,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        chunk_label=CHUNK_EMBEDDING_LABEL,
        embedding_property=CHUNK_EMBEDDING_PROPERTY,
        embedding_dimensions=CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model=EMBEDDER_MODEL_NAME,
        chunk_stride=CHUNK_FALLBACK_STRIDE,
    )


_run_claim_and_mention_extraction = run_claim_and_mention_extraction
_run_entity_resolution = run_entity_resolution
_run_retrieval_and_qa = run_retrieval_and_qa
run_independent_demo = _run_independent_stage


def main() -> None:
    args = parse_args()
    if args.command == "lint-structured":
        config = Config(
            dry_run=True,
            output_dir=args.output_dir,
            neo4j_uri=args.neo4j_uri,
            neo4j_username=args.neo4j_username,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.neo4j_database,
            openai_model=args.openai_model,
            dataset_name=getattr(args, "dataset", None) or None,
        )
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
        config = _build_config_from_args(args)
        try:
            if args.command == "ingest":
                manifest_path = run_demo(config)
                print(f"Demo manifest written to: {manifest_path}")
            elif args.command == "ask" and getattr(args, "interactive", False):
                # Interactive mode: start a REPL session; no manifest is written.
                if config.dry_run:
                    raise SystemExit(
                        "Interactive 'ask' is not supported in dry-run mode. "
                        "Re-run the command with --live to enable live Neo4j/OpenAI calls."
                    )
                resolved_run_id, ask_all_runs = _resolve_ask_scope(args, config)
                print(f"Using retrieval scope: {_format_scope_label(resolved_run_id, ask_all_runs)}")
                run_interactive_qa(
                    config,
                    run_id=resolved_run_id,
                    all_runs=ask_all_runs,
                    # In all-runs mode, do not constrain by source_uri so that retrieval
                    # queries the whole database (no run_id and no source_uri filter).
                    # In single-run mode, default to the active dataset's PDF URI.
                    source_uri=None if ask_all_runs else str(
                        resolve_dataset_root(config.dataset_name).pdf_path.resolve().as_uri()
                    ),
                    index_name=CHUNK_EMBEDDING_INDEX_NAME,
                    cluster_aware=getattr(args, "cluster_aware", False),
                    expand_graph=getattr(args, "expand_graph", False),
                    debug=getattr(args, "debug", False),
                )
            elif args.command == "ask":
                # Non-interactive ask: resolve scope, print it, then run and write manifest.
                resolved_run_id, ask_all_runs = _resolve_ask_scope(args, config)
                print(f"Using retrieval scope: {_format_scope_label(resolved_run_id, ask_all_runs)}")
                manifest_path = _run_independent_stage(
                    config,
                    args.command,
                    resolved_run_id=resolved_run_id,
                    all_runs=ask_all_runs,
                    cluster_aware=getattr(args, "cluster_aware", False),
                    expand_graph=getattr(args, "expand_graph", False),
                )
                print(f"Independent run manifest written to: {manifest_path}")
            else:
                manifest_path = _run_independent_stage(config, args.command)
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
        import neo4j as _neo4j
        from demo.reset_demo_db import run_reset

        driver = _neo4j.GraphDatabase.driver(
            args.neo4j_uri, auth=(args.neo4j_username, args.neo4j_password)
        )
        with driver:
            report = run_reset(
                driver=driver,
                database=args.neo4j_database,
                output_dir=args.output_dir,
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
                print(f"  warning: {w}")
        if report.get("report_path"):
            print(f"Reset report written to: {report['report_path']}")
        return
    print(f"Stub: '{args.command}' command scaffold is ready.")


if __name__ == "__main__":
    main()
