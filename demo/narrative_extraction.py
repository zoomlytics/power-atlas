from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from power_atlas.bootstrap import build_app_context
from power_atlas.bootstrap import build_settings
from power_atlas.bootstrap import require_openai_api_key
from power_atlas.contracts import (
    PROMPT_IDS,
    claim_extraction_lexical_config,
)
from power_atlas.narrative_extraction_artifacts import (
    build_narrative_extraction_summary,
    normalize_stage_warnings,
    write_narrative_extraction_artifacts,
)
from power_atlas.narrative_extraction_readers import (
    read_chunks_and_extract_narrative_graph,
)
from power_atlas.narrative_extraction_runtime import run_narrative_extraction_live
from power_atlas.extraction_rows import prepare_extracted_rows
from power_atlas.extraction_writes import write_extracted_rows
from power_atlas.interfaces.cli.narrative_extraction_entrypoint import (
    run_narrative_extraction_main as _run_narrative_extraction_main_impl,
)
from power_atlas.interfaces.cli.narrative_extraction_support import (
    build_narrative_cli_config as _build_narrative_cli_config_impl,
    default_narrative_cli_settings as _default_narrative_cli_settings_impl,
    parse_narrative_extraction_args as _parse_narrative_extraction_args_impl,
)
from power_atlas.settings import AppSettings
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig

PROMPT_VERSION = PROMPT_IDS["narrative_extraction"]
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "runs"
DEFAULT_NEO4J_PASSWORD = "CHANGE_ME_BEFORE_USE"


@dataclass(frozen=True)
class ExtractionConfig:
    run_id: str
    source_uri: str | None
    settings: AppSettings
    output_root: Path
    dry_run: bool = False


def build_lexical_config() -> LexicalGraphConfig:
    app_context = build_app_context(settings=build_settings())
    return claim_extraction_lexical_config(app_context.pipeline_contract)


_read_chunks_and_extract = read_chunks_and_extract_narrative_graph


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _default_cli_settings():
    return _default_narrative_cli_settings_impl()


def _build_cli_config(args: argparse.Namespace) -> ExtractionConfig:
    return _build_narrative_cli_config_impl(
        args,
        extraction_config_type=ExtractionConfig,
    )


def run_narrative_extraction(config: ExtractionConfig) -> dict[str, Any]:
    extracted_at = datetime.now(UTC).isoformat()
    run_root = config.output_root / config.run_id
    extraction_dir = run_root / "narrative_extraction"
    _ensure_dir(extraction_dir)
    summary_path = extraction_dir / "summary.json"
    # Write the manifest inside the stage subdirectory so independent invocations
    # sharing the same run_id do not overwrite each other's manifests.
    # In run_demo.py, the independent-stage manifest path is:
    #   config.output_dir / "runs" / <run_id> / <stage_name> / manifest.json
    # In this script, output_root is expected to correspond to output_dir / "runs",
    # so the local pattern is: <output_root>/<run_id>/<stage_name>/manifest.json
    manifest_path = extraction_dir / "manifest.json"
    lexical_config = build_lexical_config()

    if config.dry_run:
        summary = {
            "status": "dry_run",
            "run_id": config.run_id,
            "source_uri": config.source_uri,
            "extractor_model": config.settings.openai_model,
            "prompt_version": PROMPT_VERSION,
            "extracted_at": extracted_at,
            "chunks_processed": 0,
            "claims": 0,
            "mentions": 0,
            "chunk_ids": [],
            "warnings": normalize_stage_warnings(
                ["narrative extraction skipped in dry_run mode"]
            ),
        }
        write_narrative_extraction_artifacts(
            summary_path=summary_path,
            manifest_path=manifest_path,
            config_dry_run=config.dry_run,
            neo4j_database=config.settings.neo4j.database,
            openai_model=config.settings.openai_model,
            run_id=config.run_id,
            stage_payload={
                **summary,
                "summary_path": str(summary_path),
                "output_dir": str(extraction_dir),
            },
        )
        return summary

    if config.settings.neo4j.password in ("", DEFAULT_NEO4J_PASSWORD):
        raise ValueError(
            "NEO4J_PASSWORD must be set (not empty and not CHANGE_ME_BEFORE_USE) for live narrative extraction. "
            "Use --neo4j-password or the NEO4J_PASSWORD environment variable."
        )

    require_openai_api_key(
        "OPENAI_API_KEY environment variable is required for narrative extraction."
    )

    live_result = run_narrative_extraction_live(
        config.settings.neo4j,
        run_id=config.run_id,
        source_uri=config.source_uri,
        neo4j_database=config.settings.neo4j.database,
        model_name=config.settings.openai_model,
        lexical_graph_config=lexical_config,
        read_chunks_and_extract=_read_chunks_and_extract,
        prepare_rows=prepare_extracted_rows,
        write_rows=write_extracted_rows,
    )
    text_chunks = live_result.text_chunks
    claim_rows = live_result.claim_rows
    mention_rows = live_result.mention_rows
    warnings = live_result.warnings

    summary = build_narrative_extraction_summary(
        run_id=config.run_id,
        source_uri=config.source_uri,
        model_name=config.settings.openai_model,
        prompt_version=PROMPT_VERSION,
        extracted_at=extracted_at,
        chunk_count=len(text_chunks),
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        warnings=warnings,
    )
    write_narrative_extraction_artifacts(
        summary_path=summary_path,
        manifest_path=manifest_path,
        config_dry_run=config.dry_run,
        neo4j_database=config.settings.neo4j.database,
        openai_model=config.settings.openai_model,
        run_id=config.run_id,
        stage_payload={
            **summary,
            "summary_path": str(summary_path),
            "output_dir": str(extraction_dir),
        },
    )
    return summary


def _parse_args(argv: list[str] | None = None) -> ExtractionConfig:
    return _parse_narrative_extraction_args_impl(
        argv,
        default_output_root=DEFAULT_OUTPUT_ROOT,
        extraction_config_type=ExtractionConfig,
    )


def main() -> None:
    _run_narrative_extraction_main_impl(
        parse_args=_parse_args,
        run_narrative_extraction=run_narrative_extraction,
    )


if __name__ == "__main__":
    main()
