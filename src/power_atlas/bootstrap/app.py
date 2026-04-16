from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppBootstrap:
    settings: AppSettings


def build_settings(environ: Mapping[str, str] | None = None) -> AppSettings:
    return AppSettings.from_env(environ=environ)


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


__all__ = ["AppBootstrap", "bootstrap_app", "build_runtime_config", "build_settings"]
