from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from power_atlas.bootstrap import build_app_context
from power_atlas.bootstrap import build_request_context
from power_atlas.bootstrap import build_runtime_config
from power_atlas.bootstrap import build_settings
from power_atlas.context import RequestContext
from power_atlas.contracts.runtime import Config


def build_settings_from_overrides(
    *,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str,
    openai_model: str | None = None,
    output_dir: Path | None = None,
    dataset_name: str | None = None,
):
    environ = {
        "NEO4J_URI": neo4j_uri,
        "NEO4J_USERNAME": neo4j_username,
        "NEO4J_PASSWORD": neo4j_password,
        "NEO4J_DATABASE": neo4j_database,
    }
    if openai_model is not None:
        environ["OPENAI_MODEL"] = openai_model
    if output_dir is not None:
        environ["POWER_ATLAS_OUTPUT_DIR"] = str(output_dir)
    if dataset_name is not None:
        environ["POWER_ATLAS_DATASET"] = dataset_name
    return build_settings(environ)


def build_request_context_from_config(
    config: Config,
    *,
    command: str | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    app_context = build_app_context(settings=config.settings)
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if config_pipeline_contract is not None:
        app_context = replace(
            app_context,
            pipeline_contract=config_pipeline_contract,
            pipeline_contract_config_data=dict(
                getattr(
                    config,
                    "pipeline_contract_config_data",
                    app_context.pipeline_contract_config_data,
                )
            ),
        )
    return build_request_context(
        app_context,
        command=command,
        dry_run=config.dry_run,
        output_dir=config.output_dir,
        question=config.question,
        resolution_mode=config.resolution_mode,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


__all__ = [
    "build_request_context_from_config",
    "build_settings_from_overrides",
]