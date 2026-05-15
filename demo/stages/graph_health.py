"""Compatibility shim for the package-owned graph-health diagnostics runtime."""

from pathlib import Path

import power_atlas.graph_health_diagnostics as _graph_health_diagnostics_impl
from power_atlas.graph_health_diagnostics import GraphHealthArtifact
from power_atlas.graph_health_diagnostics import _CANONICAL_CHAIN_HEALTH_LIMIT
from power_atlas.graph_health_diagnostics import _PER_CANONICAL_ALIGNMENT_LIMIT
from power_atlas.graph_health_diagnostics import _compute_alignment_summary
from power_atlas.graph_health_diagnostics import _compute_mention_summary
from power_atlas.graph_health_diagnostics import _compute_participation_summary
from power_atlas.graph_health_diagnostics import _get_cluster_type_fragmentation_query
from power_atlas.graph_health_diagnostics import _neo4j_settings_from_config
from power_atlas.graph_health_diagnostics import _records_to_dicts
from power_atlas.graph_health_diagnostics import build_graph_health_artifact
from power_atlas.graph_health_queries import fetch_graph_health_query_rows


def run_graph_health_diagnostics(
    config,
    *,
    run_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, object]:
    resolved_output_dir = Path(output_dir if output_dir is not None else config.output_dir)
    dry_run = bool(getattr(config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else _neo4j_settings_from_config(config)
    return _graph_health_diagnostics_impl._run_graph_health_diagnostics_impl(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=run_id,
        alignment_version=alignment_version,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        query_rows_fetcher=fetch_graph_health_query_rows,
    )


def run_graph_health_diagnostics_request_context(
    request_context,
    *,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, object]:
    resolved_output_dir = Path(
        output_dir if output_dir is not None else request_context.config.output_dir
    )
    dry_run = bool(getattr(request_context.config, "dry_run", False))
    resolved_neo4j_settings = None if dry_run else _graph_health_diagnostics_impl._neo4j_settings_from_request_context(
        request_context
    )
    return _graph_health_diagnostics_impl._run_graph_health_diagnostics_impl(
        dry_run=dry_run,
        output_dir=resolved_output_dir,
        neo4j_settings=resolved_neo4j_settings,
        run_id=request_context.run_id,
        alignment_version=alignment_version,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        entity_type_policy=request_context.policies.entity_type_normalization,
        query_rows_fetcher=fetch_graph_health_query_rows,
    )

__all__ = [
    "GraphHealthArtifact",
    "_CANONICAL_CHAIN_HEALTH_LIMIT",
    "_PER_CANONICAL_ALIGNMENT_LIMIT",
    "_compute_alignment_summary",
    "_compute_mention_summary",
    "_compute_participation_summary",
    "_get_cluster_type_fragmentation_query",
    "_neo4j_settings_from_config",
    "_records_to_dicts",
    "build_graph_health_artifact",
    "fetch_graph_health_query_rows",
    "run_graph_health_diagnostics",
    "run_graph_health_diagnostics_request_context",
]
