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
        "Retrieval benchmark requires config.settings.neo4j from "
        "RequestContext/AppContext-backed config"
    )


def neo4j_settings_from_request_context(request_context: RequestContext) -> Neo4jSettings:
    request_settings_neo4j = getattr(request_context.settings, "neo4j", None)
    if isinstance(request_settings_neo4j, Neo4jSettings):
        return request_settings_neo4j
    return neo4j_settings_from_config(request_context.config)


def run_retrieval_benchmark(
    config: Any,
    *,
    run_id: str | None = None,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    benchmark_cases: list[Any] | None = None,
    suppress_alignment_version_warning: bool = False,
    impl_runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    resolved_output_dir = Path(output_dir if output_dir is not None else config.output_dir)
    dry_run = bool(getattr(config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else neo4j_settings_from_config(config)
    return impl_runner(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        benchmark_cases=benchmark_cases,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
    )


def run_retrieval_benchmark_request_context(
    request_context: RequestContext,
    *,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    benchmark_cases: list[Any] | None = None,
    suppress_alignment_version_warning: bool = False,
    impl_runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    resolved_output_dir = Path(
        output_dir if output_dir is not None else request_context.config.output_dir
    )
    dry_run = bool(getattr(request_context.config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else neo4j_settings_from_request_context(
        request_context
    )
    return impl_runner(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=request_context.run_id,
        dataset_id=(
            dataset_id
            if dataset_id is not None
            else getattr(request_context.config, "dataset_name", None)
        ),
        alignment_version=alignment_version,
        benchmark_cases=benchmark_cases,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
    )


__all__ = [
    "neo4j_settings_from_config",
    "neo4j_settings_from_request_context",
    "run_retrieval_benchmark",
    "run_retrieval_benchmark_request_context",
]