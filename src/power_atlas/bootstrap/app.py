from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Mapping, MutableMapping
import os

from power_atlas.context import AppContext, AppPolicies, RequestContext, build_default_app_policies
from power_atlas.contracts.paths import RepoPaths, resolve_repo_paths
from power_atlas.contracts.pipeline import (
    PipelineContractLoadResult,
    PipelineContractSource,
    get_pipeline_contract_config_data,
    get_pipeline_contract_snapshot,
    load_pipeline_contract,
    resolve_pipeline_contract_source,
)
from power_atlas.contracts.runtime import Config
from power_atlas.contracts.retrieval_policy import RetrievalPolicy, get_default_retrieval_policy
from power_atlas.settings import (
    AppSettings,
    AppSettingsEnvNames,
    DEFAULT_APP_SETTINGS_ENV_NAMES,
)


@dataclass(frozen=True)
class AppBootstrap:
    settings: AppSettings
    app_context: AppContext


@dataclass(frozen=True)
class AppBaseline:
    env_names: AppSettingsEnvNames = field(default_factory=lambda: DEFAULT_APP_SETTINGS_ENV_NAMES)
    repo_paths: RepoPaths = field(default_factory=resolve_repo_paths)
    pipeline_contract_source: PipelineContractSource = field(
        default_factory=resolve_pipeline_contract_source
    )
    retrieval_policy: RetrievalPolicy = field(default_factory=get_default_retrieval_policy)


def resolve_app_baseline(
    *,
    env_names: AppSettingsEnvNames | None = None,
    repo_paths: RepoPaths | None = None,
    pipeline_contract_source: PipelineContractSource | None = None,
    retrieval_policy: RetrievalPolicy | None = None,
) -> AppBaseline:
    resolved_repo_paths = resolve_repo_paths() if repo_paths is None else repo_paths
    return AppBaseline(
        env_names=DEFAULT_APP_SETTINGS_ENV_NAMES if env_names is None else env_names,
        repo_paths=resolved_repo_paths,
        pipeline_contract_source=(
            resolve_pipeline_contract_source(repo_paths=resolved_repo_paths)
            if pipeline_contract_source is None
            else pipeline_contract_source
        ),
        retrieval_policy=(
            get_default_retrieval_policy() if retrieval_policy is None else retrieval_policy
        ),
    )


DEFAULT_APP_BASELINE = resolve_app_baseline()


def _effective_app_baseline(
    app_baseline: AppBaseline | None,
    *,
    env_names: AppSettingsEnvNames | None = None,
    repo_paths: RepoPaths | None = None,
    pipeline_contract_source: PipelineContractSource | None = None,
    retrieval_policy: RetrievalPolicy | None = None,
) -> AppBaseline:
    if app_baseline is None:
        return resolve_app_baseline(
            env_names=env_names,
            repo_paths=repo_paths,
            pipeline_contract_source=pipeline_contract_source,
            retrieval_policy=retrieval_policy,
        )

    resolved_repo_paths = app_baseline.repo_paths if repo_paths is None else repo_paths
    resolved_pipeline_contract_source = pipeline_contract_source
    if resolved_pipeline_contract_source is None:
        resolved_pipeline_contract_source = (
            app_baseline.pipeline_contract_source
            if repo_paths is None
            else resolve_pipeline_contract_source(repo_paths=resolved_repo_paths)
        )

    return resolve_app_baseline(
        env_names=app_baseline.env_names if env_names is None else env_names,
        repo_paths=resolved_repo_paths,
        pipeline_contract_source=resolved_pipeline_contract_source,
        retrieval_policy=(app_baseline.retrieval_policy if retrieval_policy is None else retrieval_policy),
    )


def _load_pipeline_contract_for_baseline(
    app_baseline: AppBaseline | None,
) -> PipelineContractLoadResult | None:
    if app_baseline is None:
        return None
    return load_pipeline_contract(source=app_baseline.pipeline_contract_source)


def build_settings(
    environ: Mapping[str, str] | None = None,
    *,
    env_names: AppSettingsEnvNames | None = None,
    app_baseline: AppBaseline | None = None,
) -> AppSettings:
    resolved_baseline = _effective_app_baseline(app_baseline, env_names=env_names)
    return AppSettings.from_env(environ=environ, env_names=resolved_baseline.env_names)


def build_app_context(
    *,
    settings: AppSettings | None = None,
    policies: AppPolicies | None = None,
    environ: Mapping[str, str] | None = None,
    env_names: AppSettingsEnvNames | None = None,
    app_baseline: AppBaseline | None = None,
) -> AppContext:
    resolved_baseline = _effective_app_baseline(app_baseline, env_names=env_names)
    resolved_settings = (
        build_settings(environ=environ, app_baseline=resolved_baseline)
        if settings is None
        else settings
    )
    pipeline_contract_result = _load_pipeline_contract_for_baseline(app_baseline)
    return AppContext(
        settings=resolved_settings,
        pipeline_contract=(
            get_pipeline_contract_snapshot()
            if pipeline_contract_result is None
            else pipeline_contract_result.snapshot
        ),
        pipeline_contract_config_data=(
            get_pipeline_contract_config_data()
            if pipeline_contract_result is None
            else dict(pipeline_contract_result.config_data)
        ),
        policies=(
            build_default_app_policies(retrieval=resolved_baseline.retrieval_policy)
            if policies is None
            else policies
        ),
    )


def dataset_env_selection(
    environ: Mapping[str, str] | None = None,
    *,
    env_names: AppSettingsEnvNames | None = None,
    app_baseline: AppBaseline | None = None,
) -> tuple[str | None, str | None, str | None]:
    resolved_baseline = _effective_app_baseline(app_baseline, env_names=env_names)
    settings = build_settings(environ=environ, app_baseline=resolved_baseline)
    env = os.environ if environ is None else environ
    power_atlas_dataset = env.get(resolved_baseline.env_names.dataset_name_primary) or None
    fixture_dataset = env.get(resolved_baseline.env_names.dataset_name_fallback) or None
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
    app_baseline: AppBaseline | None = None,
) -> Config:
    pipeline_contract_result = _load_pipeline_contract_for_baseline(app_baseline)
    return Config(
        dry_run=dry_run,
        output_dir=settings.output_dir if output_dir is None else output_dir,
        settings=settings,
        question=question,
        resolution_mode=resolution_mode,
        dataset_name=settings.dataset_name,
        pipeline_contract=(
            get_pipeline_contract_snapshot()
            if pipeline_contract is None and pipeline_contract_result is None
            else (
                pipeline_contract_result.snapshot
                if pipeline_contract is None
                else pipeline_contract
            )
        ),
        pipeline_contract_config_data=(
            get_pipeline_contract_config_data()
            if pipeline_contract_config_data is None and pipeline_contract_result is None
            else (
                dict(pipeline_contract_result.config_data)
                if pipeline_contract_config_data is None
                else dict(pipeline_contract_config_data)
            )
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
    app_baseline: AppBaseline | None = None,
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
            app_baseline=app_baseline,
        ),
        command=command,
        run_id=run_id,
        all_runs=all_runs,
        source_uri=source_uri,
    )


def bootstrap_app(
    environ: Mapping[str, str] | None = None,
    *,
    env_names: AppSettingsEnvNames | None = None,
    app_baseline: AppBaseline | None = None,
) -> AppBootstrap:
    resolved_baseline = _effective_app_baseline(app_baseline, env_names=env_names)
    settings = build_settings(environ=environ, app_baseline=resolved_baseline)
    return AppBootstrap(
        settings=settings,
        app_context=build_app_context(settings=settings, app_baseline=resolved_baseline),
    )


__all__ = [
    "AppBaseline",
    "AppBootstrap",
    "DEFAULT_APP_BASELINE",
    "build_app_context",
    "build_request_context",
    "bootstrap_app",
    "build_runtime_config",
    "build_settings",
    "dataset_env_selection",
    "has_openai_api_key",
    "require_openai_api_key",
    "resolve_app_baseline",
    "temporary_environment",
]
