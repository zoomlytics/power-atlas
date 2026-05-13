from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.contracts import StructuredSchemaContract
from power_atlas.settings import Neo4jSettings


def _default_runtime_runner() -> Callable[..., dict[str, Any]]:
    from power_atlas.structured_ingest_runner import run_structured_ingest_runtime_default

    return run_structured_ingest_runtime_default


def _default_config_runner(
    config: Any,
    *,
    run_id: str,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    structured_schema: StructuredSchemaContract | None = None,
) -> dict[str, Any]:
    return run_structured_ingest(
        config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        structured_schema=structured_schema,
    )


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
    structured_schema: StructuredSchemaContract | None = None,
    runtime_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_runtime_runner = runtime_runner or _default_runtime_runner()
    return resolved_runtime_runner(
        config=config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings_from_config(config, neo4j_settings),
        structured_schema=structured_schema,
    )


def run_structured_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    structured_schema: StructuredSchemaContract | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_config_runner = config_runner or _default_config_runner
    return resolved_config_runner(
        request_context.config,
        run_id=request_context.run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=request_context.settings.neo4j,
        structured_schema=structured_schema,
    )


__all__ = [
    "neo4j_settings_from_config",
    "run_structured_ingest",
    "run_structured_ingest_request_context",
]