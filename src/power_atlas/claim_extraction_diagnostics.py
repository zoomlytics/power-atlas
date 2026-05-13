from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.settings import Neo4jSettings


def _default_impl_runner() -> Callable[..., dict[str, Any]]:
    from power_atlas.claim_extraction_diagnostics_runner import (
        run_claim_extraction_diagnostics_runtime_default,
    )

    return run_claim_extraction_diagnostics_runtime_default


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
        "Claim extraction diagnostics requires config.settings.neo4j from "
        "RequestContext/AppContext-backed config"
    )


def neo4j_settings_from_request_context(request_context: RequestContext) -> Neo4jSettings:
    request_settings_neo4j = getattr(request_context.settings, "neo4j", None)
    if isinstance(request_settings_neo4j, Neo4jSettings):
        return request_settings_neo4j
    return neo4j_settings_from_config(request_context.config)


def run_claim_extraction_diagnostics(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None = None,
    output_dir: Path | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    impl_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_output_dir = Path(output_dir if output_dir is not None else config.output_dir)
    dry_run = bool(getattr(config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else neo4j_settings_from_config(
        config,
        neo4j_settings,
    )
    resolved_impl_runner = impl_runner or _default_impl_runner()
    return resolved_impl_runner(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
    )


def run_claim_extraction_diagnostics_request_context(
    request_context: RequestContext,
    *,
    output_dir: Path | None = None,
    impl_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_id = request_context.run_id
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Claim extraction diagnostics requires request_context.run_id")

    resolved_output_dir = Path(
        output_dir if output_dir is not None else request_context.config.output_dir
    )
    dry_run = bool(getattr(request_context.config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else neo4j_settings_from_request_context(
        request_context
    )
    resolved_impl_runner = impl_runner or _default_impl_runner()
    return resolved_impl_runner(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=run_id,
        source_uri=request_context.source_uri,
    )


__all__ = [
    "neo4j_settings_from_config",
    "neo4j_settings_from_request_context",
    "run_claim_extraction_diagnostics",
    "run_claim_extraction_diagnostics_request_context",
]