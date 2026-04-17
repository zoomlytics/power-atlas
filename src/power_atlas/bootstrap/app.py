from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, MutableMapping
import os

from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppBootstrap:
    settings: AppSettings


def build_settings(environ: Mapping[str, str] | None = None) -> AppSettings:
    return AppSettings.from_env(environ=environ)


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
    )


def bootstrap_app(environ: Mapping[str, str] | None = None) -> AppBootstrap:
    return AppBootstrap(settings=build_settings(environ=environ))


__all__ = [
    "AppBootstrap",
    "bootstrap_app",
    "build_runtime_config",
    "build_settings",
    "has_openai_api_key",
    "require_openai_api_key",
    "temporary_environment",
]
