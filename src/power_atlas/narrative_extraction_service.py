from __future__ import annotations

from datetime import timezone, datetime
from pathlib import Path
from typing import Any

from power_atlas.narrative_extraction_artifacts import (
    build_narrative_extraction_summary,
    normalize_stage_warnings,
    write_narrative_extraction_artifacts,
)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_narrative_extraction_stage(
    config: Any,
    *,
    prompt_version: str,
    default_neo4j_password: str,
    build_lexical_config,
    require_openai_api_key,
    run_narrative_extraction_live,
    read_chunks_and_extract,
    prepare_rows,
    write_rows,
) -> dict[str, Any]:
    extracted_at = datetime.now(timezone.utc).isoformat()
    run_root = config.output_root / config.run_id
    extraction_dir = run_root / "narrative_extraction"
    ensure_directory(extraction_dir)
    summary_path = extraction_dir / "summary.json"
    manifest_path = extraction_dir / "manifest.json"
    lexical_config = build_lexical_config()

    if config.dry_run:
        summary = {
            "status": "dry_run",
            "run_id": config.run_id,
            "source_uri": config.source_uri,
            "extractor_model": config.settings.openai_model,
            "prompt_version": prompt_version,
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

    if config.settings.neo4j.password in ("", default_neo4j_password):
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
        read_chunks_and_extract=read_chunks_and_extract,
        prepare_rows=prepare_rows,
        write_rows=write_rows,
    )
    summary = build_narrative_extraction_summary(
        run_id=config.run_id,
        source_uri=config.source_uri,
        model_name=config.settings.openai_model,
        prompt_version=prompt_version,
        extracted_at=extracted_at,
        chunk_count=len(live_result.text_chunks),
        claim_rows=live_result.claim_rows,
        mention_rows=live_result.mention_rows,
        warnings=live_result.warnings,
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


__all__ = ["ensure_directory", "run_narrative_extraction_stage"]