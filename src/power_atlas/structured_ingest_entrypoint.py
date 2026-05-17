from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext, RequestRuntime
from power_atlas.contracts import (
    StructuredGraphShapeContract,
    StructuredSchemaContract,
)
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
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
) -> dict[str, Any]:
    return run_structured_ingest(
        config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        structured_graph_shape=structured_graph_shape,
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
    structured_graph_shape: StructuredGraphShapeContract | None = None,
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
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
    )


def run_structured_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return run_structured_ingest_runtime(
        request_context.runtime,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
        config_runner=config_runner,
    )


def run_structured_ingest_runtime(
    request_runtime: RequestRuntime,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_config_runner = config_runner or _default_config_runner
    return resolved_config_runner(
        request_runtime.config,
        run_id=request_runtime.run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=request_runtime.settings.neo4j,
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
    )


__all__ = [
    "neo4j_settings_from_config",
    "run_structured_ingest",
    "run_structured_ingest_runtime",
    "run_structured_ingest_request_context",
]