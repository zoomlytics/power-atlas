from __future__ import annotations

import argparse
import os
import sys
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
    FIXTURES_DIR,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
)
from demo.contracts.manifest import write_manifest, write_manifest_md  # noqa: E402
from demo.stages import (  # noqa: E402
    lint_and_clean_structured_csvs,
    run_claim_and_mention_extraction,
    run_entity_resolution,
    run_interactive_qa,
    run_pdf_ingest,
    run_retrieval_and_qa,
    run_structured_ingest,
)
from demo.stages.retrieval_and_qa import _format_scope_label  # noqa: E402
from demo.stages.pdf_ingest import sha256_file  # noqa: E402, F401 - re-exported for callers and tests


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
    return parser.parse_args(raw_argv)


def _fetch_latest_unstructured_run_id(config: Config) -> str | None:
    """Query Neo4j for the latest unstructured ingest run_id from Chunk nodes.

    Returns the run_id of the most recently created unstructured ingest run,
    or None if no Chunk nodes with an unstructured_ingest run_id exist.
    Only call this in live mode; it opens a real Neo4j connection.

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
            result = session.run(
                "MATCH (c:Chunk) WHERE c.run_id STARTS WITH 'unstructured_ingest' "
                "RETURN c.run_id ORDER BY c.run_id DESC LIMIT 1"
            )
            record = result.single()
            return record[0] if record else None


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
    printed whenever the env var is overridden or stale.
    """
    env_run_id = os.getenv("UNSTRUCTURED_RUN_ID")
    all_runs: bool = getattr(args, "all_runs", False)
    explicit_run_id: str | None = getattr(args, "run_id", None)
    use_latest: bool = getattr(args, "latest", False)

    if all_runs:
        if env_run_id:
            print(
                f"WARNING: UNSTRUCTURED_RUN_ID={env_run_id!r} is set "
                "but overridden by --all-runs."
            )
        return None, True

    if explicit_run_id:
        if env_run_id and env_run_id != explicit_run_id:
            print(
                f"WARNING: UNSTRUCTURED_RUN_ID={env_run_id!r} is set "
                f"but overridden by --run-id={explicit_run_id!r}."
            )
        return explicit_run_id, False

    # Default / --latest: resolve the latest run_id.
    if config.dry_run:
        # In dry-run mode, Neo4j is unavailable; honour env var if set, else proceed
        # without a run scope (dry-run stubs don't require a real run_id).
        if env_run_id:
            return env_run_id, False
        return None, False

    # Live mode: resolve run_id according to precedence:
    # CLI flags (--run-id/--latest/--all-runs) > UNSTRUCTURED_RUN_ID > implicit latest.
    if not use_latest and env_run_id:
        # No explicit --latest flag; honour UNSTRUCTURED_RUN_ID if set.
        return env_run_id, False

    # Either --latest was explicitly requested, or no env var is set: query Neo4j.
    latest_run_id = _fetch_latest_unstructured_run_id(config)
    if latest_run_id is None:
        raise SystemExit(
            "No unstructured ingest runs found in the database. "
            "Run 'ingest-pdf' first, or use --all-runs to query all available data."
        )
    if use_latest and env_run_id and env_run_id != latest_run_id:
        print(
            f"WARNING: UNSTRUCTURED_RUN_ID={env_run_id!r} is set but overridden by --latest. "
            f"Using latest: {latest_run_id!r}."
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

    # ── Phase 1: Unstructured-only pass ──────────────────────────────────────
    # Ingest the PDF and build the lexical graph first.
    pdf_stage = run_pdf_ingest(
        config,
        unstructured_run_id,
        fixtures_dir=FIXTURES_DIR,
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
    # Cluster extracted mentions against each other; no CanonicalEntity lookup required.
    # Use a mode-specific artifact subdirectory so the hybrid pass does not overwrite
    # the unstructured-only artifacts when both passes share the same run_id.
    entity_resolution_unstructured_stage = run_entity_resolution(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        resolution_mode="unstructured_only",
        artifact_subdir="entity_resolution_unstructured_only",
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
    structured_stage = run_structured_ingest(config, structured_run_id, fixtures_dir=FIXTURES_DIR)
    # Hybrid alignment enriches existing ResolvedEntityCluster nodes with ALIGNED_WITH
    # edges to CanonicalEntity nodes; gracefully degrades when no matches exist.
    # Use a separate artifact subdirectory to preserve the unstructured-only artifacts.
    entity_resolution_hybrid_stage = run_entity_resolution(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution_hybrid",
    )
    # Final Q&A after structured enrichment shows the additive benefit.
    retrieval_stage = run_retrieval_and_qa(
        config,
        run_id=unstructured_run_id,
        source_uri=pdf_source_uri,
        index_name=CHUNK_EMBEDDING_INDEX_NAME,
        question=getattr(config, "question", None),
    )

    finished_at = _now_iso()
    manifest = build_batch_manifest(
        config=config,
        structured_run_id=structured_run_id,
        unstructured_run_id=unstructured_run_id,
        structured_stage=structured_stage,
        pdf_stage=pdf_stage,
        claim_stage=claim_stage,
        entity_resolution_unstructured_stage=entity_resolution_unstructured_stage,
        retrieval_unstructured_stage=retrieval_unstructured_stage,
        entity_resolution_hybrid_stage=entity_resolution_hybrid_stage,
        retrieval_stage=retrieval_stage,
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
    stage_runners: dict[str, tuple[str, str, Callable[[Config, str], dict[str, Any]]]] = {
        "ingest-structured": (
            "structured_ingest",
            "structured_ingest_run_id",
            lambda cfg, stage_run_id: run_structured_ingest(cfg, stage_run_id, fixtures_dir=FIXTURES_DIR),
        ),
        "ingest-pdf": (
            "pdf_ingest",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_pdf_ingest(
                cfg,
                stage_run_id,
                fixtures_dir=FIXTURES_DIR,
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
                # Independent-stage default: use the canonical demo fixture URI.
                # This is intentional — the demo fixture is the stable source for all
                # independent runs.  In the orchestrated batch path, source_uri is
                # derived from the prior pdf_ingest stage output instead.
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
            ),
        ),
        "resolve-entities": (
            "entity_resolution",
            "unstructured_ingest_run_id",
            lambda cfg, stage_run_id: run_entity_resolution(
                cfg,
                run_id=stage_run_id,
                # Independent-stage default: use the canonical demo fixture URI.
                # See note above for extract-claims.
                source_uri=str((FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()),
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
                # In single-run mode, default to the canonical demo fixture URI.
                source_uri=None if _ask_all_runs else str(
                    (FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
                ),
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
    return lint_and_clean_structured_csvs(run_id=run_id, output_dir=output_dir, fixtures_dir=FIXTURES_DIR)


def _run_structured_ingest(config: Config, run_id: str) -> dict[str, Any]:
    return run_structured_ingest(config, run_id, fixtures_dir=FIXTURES_DIR)


def _run_pdf_ingest(config: Config, run_id: str | None = None) -> dict[str, Any]:
    return run_pdf_ingest(
        config,
        run_id,
        fixtures_dir=FIXTURES_DIR,
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
        )
        run_id = make_run_id("structured_lint")
        lint_result = lint_and_clean_structured_csvs(run_id=run_id, output_dir=config.output_dir)
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
                    # In single-run mode, default to the canonical demo fixture URI.
                    source_uri=None if ask_all_runs else str(
                        (FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
                    ),
                    index_name=CHUNK_EMBEDDING_INDEX_NAME,
                    cluster_aware=getattr(args, "cluster_aware", False),
                    expand_graph=getattr(args, "expand_graph", False),
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
