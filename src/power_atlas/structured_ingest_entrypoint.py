from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.settings import Neo4jSettings


def neo4j_settings_from_config(
    config: object,
    neo4j_settings: Neo4jSettings | None = None,
) -> Neo4jSettings:
    if neo4j_settings is not None:
        return neo4j_settings
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Live structured ingest requires config.settings.neo4j to be configured"
    )


def run_structured_ingest(
    config: Any,
    *,
    run_id: str,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    runtime_runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return runtime_runner(
        config=config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings_from_config(config, neo4j_settings),
    )


def run_structured_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    config_runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return config_runner(
        request_context.config,
        run_id=request_context.run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=request_context.settings.neo4j,
    )


__all__ = [
    "neo4j_settings_from_config",
    "run_structured_ingest",
    "run_structured_ingest_request_context",
]