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


def build_runtime_config_from_overrides(
    *,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str,
    openai_model: str | None,
    output_dir: Path,
    dataset_name: str | None,
    dry_run: bool,
    question: str | None = None,
    resolution_mode: str = "unstructured_only",
) -> Config:
    settings = build_settings_from_overrides(
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        openai_model=openai_model,
        output_dir=output_dir,
        dataset_name=dataset_name,
    )
    return build_runtime_config(
        settings,
        dry_run=dry_run,
        output_dir=output_dir,
        question=question,
        resolution_mode=resolution_mode,
    )


def build_request_context_from_overrides(
    *,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str,
    openai_model: str | None,
    output_dir: Path,
    dataset_name: str | None,
    command: str | None,
    dry_run: bool,
    question: str | None = None,
    resolution_mode: str = "unstructured_only",
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    settings = build_settings_from_overrides(
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        openai_model=openai_model,
        output_dir=output_dir,
        dataset_name=dataset_name,
    )
    app_context = build_app_context(settings=settings)
    return build_request_context(
        app_context,
        command=command,
        dry_run=dry_run,
        output_dir=output_dir,
        question=question,
        resolution_mode=resolution_mode,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def build_request_context_from_config(
    config: Config,
    *,
    command: str | None = None,
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    default_settings = build_settings()
    request_context = build_request_context_from_overrides(
        neo4j_uri=getattr(config, "neo4j_uri", default_settings.neo4j.uri),
        neo4j_username=getattr(config, "neo4j_username", default_settings.neo4j.username),
        neo4j_password=getattr(config, "neo4j_password", default_settings.neo4j.password),
        neo4j_database=getattr(config, "neo4j_database", default_settings.neo4j.database),
        openai_model=getattr(config, "openai_model", default_settings.openai_model),
        output_dir=getattr(config, "output_dir", default_settings.output_dir),
        dataset_name=getattr(config, "dataset_name", None) or "",
        command=command,
        dry_run=getattr(config, "dry_run", True),
        question=getattr(config, "question", None),
        resolution_mode=getattr(config, "resolution_mode", "unstructured_only"),
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if config_pipeline_contract is None:
        return request_context
    return replace(
        request_context,
        app=replace(
            request_context.app,
            pipeline_contract=config_pipeline_contract,
            pipeline_contract_config_data=dict(
                getattr(
                    config,
                    "pipeline_contract_config_data",
                    request_context.app.pipeline_contract_config_data,
                )
            ),
        ),
    )


__all__ = [
    "build_request_context_from_config",
    "build_request_context_from_overrides",
    "build_runtime_config_from_overrides",
    "build_settings_from_overrides",
]