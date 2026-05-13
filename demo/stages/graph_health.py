"""Compatibility shim for the package-owned graph-health diagnostics runtime."""

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
from power_atlas.graph_health_diagnostics import run_graph_health_diagnostics
from power_atlas.graph_health_diagnostics import run_graph_health_diagnostics_request_context

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
    "run_graph_health_diagnostics",
    "run_graph_health_diagnostics_request_context",
]
