from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, MutableMapping
import os

from power_atlas.context import AppContext, RequestContext
from power_atlas.contracts.pipeline import get_pipeline_contract_config_data, get_pipeline_contract_snapshot
from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppBootstrap:
    settings: AppSettings
    app_context: AppContext


def build_settings(environ: Mapping[str, str] | None = None) -> AppSettings:
    return AppSettings.from_env(environ=environ)


def build_app_context(
    *,
    settings: AppSettings | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppContext:
    resolved_settings = build_settings(environ=environ) if settings is None else settings
    return AppContext(
        settings=resolved_settings,
        pipeline_contract=get_pipeline_contract_snapshot(),
        pipeline_contract_config_data=get_pipeline_contract_config_data(),
    )


def dataset_env_selection(
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None, str | None]:
    settings = build_settings(environ=environ)
    env = os.environ if environ is None else environ
    power_atlas_dataset = env.get("POWER_ATLAS_DATASET") or None
    fixture_dataset = env.get("FIXTURE_DATASET") or None
    return power_atlas_dataset, fixture_dataset, settings.dataset_name


def has_openai_api_key(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("OPENAI_API_KEY"))


def require_openai_api_key(
    error_message: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    if not has_openai_api_key(environ=environ):
        raise ValueError(error_message)


@contextmanager
def temporary_environment(
    overrides: Mapping[str, str],
    *,
    environ: MutableMapping[str, str] | None = None,
) -> Iterator[None]:
    target_env = os.environ if environ is None else environ
    previous_env = {key: (key in target_env, target_env.get(key)) for key in overrides}
    target_env.update(overrides)
    try:
        yield
    finally:
        for key, (had_key, previous_value) in previous_env.items():
            if not had_key:
                target_env.pop(key, None)
            elif previous_value is not None:
                target_env[key] = previous_value


def build_runtime_config(
    settings: AppSettings,
    *,
    dry_run: bool,
    output_dir: Path | None = None,
    question: str | None = None,
    resolution_mode: str = "unstructured_only",
    pipeline_contract=None,
    pipeline_contract_config_data=None,
) -> Config:
    return Config(
        dry_run=dry_run,
        output_dir=settings.output_dir if output_dir is None else output_dir,
        neo4j_uri=settings.neo4j.uri,
        neo4j_username=settings.neo4j.username,
        neo4j_password=settings.neo4j.password,
        neo4j_database=settings.neo4j.database,
        openai_model=settings.openai_model,
        question=question,
        resolution_mode=resolution_mode,
        dataset_name=settings.dataset_name,
        pipeline_contract=(
            get_pipeline_contract_snapshot() if pipeline_contract is None else pipeline_contract
        ),
        pipeline_contract_config_data=(
            get_pipeline_contract_config_data()
            if pipeline_contract_config_data is None
            else dict(pipeline_contract_config_data)
        ),
    )


def build_request_context(
    app_context: AppContext,
    *,
    command: str | None,
    dry_run: bool,
    output_dir: Path | None = None,
    question: str | None = None,
    resolution_mode: str = "unstructured_only",
    run_id: str | None = None,
    all_runs: bool = False,
    source_uri: str | None = None,
) -> RequestContext:
    return RequestContext(
        app=app_context,
        config=build_runtime_config(
            app_context.settings,
            dry_run=dry_run,
            output_dir=output_dir,
            question=question,
            resolution_mode=resolution_mode,
            pipeline_contract=app_context.pipeline_contract,
            pipeline_contract_config_data=app_context.pipeline_contract_config_data,
        ),
        command=command,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def bootstrap_app(environ: Mapping[str, str] | None = None) -> AppBootstrap:
    settings = build_settings(environ=environ)
    return AppBootstrap(settings=settings, app_context=build_app_context(settings=settings))


__all__ = [
    "AppBootstrap",
    "build_app_context",
    "build_request_context",
    "bootstrap_app",
    "build_runtime_config",
    "build_settings",
    "dataset_env_selection",
    "has_openai_api_key",
    "require_openai_api_key",
    "temporary_environment",
]
