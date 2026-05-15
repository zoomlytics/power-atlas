from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from power_atlas.bootstrap import build_app_context
from power_atlas.bootstrap import build_settings
from power_atlas.contracts import PROMPT_IDS, claim_extraction_lexical_config
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
from power_atlas.narrative_extraction_readers import (
    read_chunks_and_extract_narrative_graph,
)
from power_atlas.narrative_extraction_runtime import run_narrative_extraction_live
from power_atlas.narrative_extraction_service import run_narrative_extraction_stage
from power_atlas.settings import AppSettings
from power_atlas.adapters.graphrag_types import LexicalGraphConfig

PROMPT_VERSION = PROMPT_IDS["narrative_extraction"]
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "demo" / "runs"
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


def _default_cli_settings():
    return _default_narrative_cli_settings_impl()


def _build_cli_config(args: argparse.Namespace) -> ExtractionConfig:
    return _build_narrative_cli_config_impl(
        args,
        extraction_config_type=ExtractionConfig,
    )


def run_narrative_extraction(config: ExtractionConfig) -> dict[str, object]:
    from power_atlas.bootstrap import require_openai_api_key

    return run_narrative_extraction_stage(
        config,
        prompt_version=PROMPT_VERSION,
        default_neo4j_password=DEFAULT_NEO4J_PASSWORD,
        build_lexical_config=build_lexical_config,
        require_openai_api_key=require_openai_api_key,
        run_narrative_extraction_live=run_narrative_extraction_live,
        read_chunks_and_extract=_read_chunks_and_extract,
        prepare_rows=prepare_extracted_rows,
        write_rows=write_extracted_rows,
    )


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