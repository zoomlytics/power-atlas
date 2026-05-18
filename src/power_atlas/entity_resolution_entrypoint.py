from __future__ import annotations

from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.contracts import (
    EntityResolutionAlignmentContract,
    EntityResolutionCanonicalLookupContract,
    EntityResolutionDatasetSelectionContract,
    EntityResolutionGraphContract,
    get_default_entity_resolution_dataset_selection_contract,
)
from power_atlas.runtime_carriers import RequestRuntime
from power_atlas.settings import Neo4jSettings


RESOLUTION_MODE_STRUCTURED_ANCHOR = "structured_anchor"
RESOLUTION_MODE_UNSTRUCTURED_ONLY = "unstructured_only"
RESOLUTION_MODE_HYBRID = "hybrid"

VALID_RESOLUTION_MODES = frozenset(
    {
        RESOLUTION_MODE_STRUCTURED_ANCHOR,
        RESOLUTION_MODE_UNSTRUCTURED_ONLY,
        RESOLUTION_MODE_HYBRID,
    }
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
        "Live entity resolution requires config.settings.neo4j or an explicit "
        "neo4j_settings argument from RequestContext/AppContext-backed config"
    )


def resolve_effective_dataset_id(
    config: Any,
    dataset_id: str | None,
    *,
    dataset_name: str | None = None,
    entity_resolution_dataset_selection: EntityResolutionDatasetSelectionContract | None = None,
) -> str:
    resolved_dataset_selection = (
        get_default_entity_resolution_dataset_selection_contract()
        if entity_resolution_dataset_selection is None
        else entity_resolution_dataset_selection
    )
    effective_dataset_id = resolved_dataset_selection.select_dataset_id(
        config,
        dataset_id,
        dataset_name,
    )
    if isinstance(effective_dataset_id, str) and effective_dataset_id:
        return effective_dataset_id
    raise ValueError(
        "Entity resolution requires an explicit dataset_id or config.dataset_name from "
        "RequestContext/AppContext-backed config"
    )


def _default_runtime_runner() -> Callable[..., dict[str, Any]]:
    from power_atlas.entity_resolution_runner import run_entity_resolution_runtime_default

    return run_entity_resolution_runtime_default


def _default_config_runner(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    dataset_name: str | None = None,
    entity_type_policy: Any = None,
    entity_resolution_dataset_selection: EntityResolutionDatasetSelectionContract | None = None,
    entity_resolution_alignment: EntityResolutionAlignmentContract | None = None,
    entity_resolution_canonical_lookup: EntityResolutionCanonicalLookupContract | None = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> dict[str, Any]:
    return run_entity_resolution(
        config,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        dataset_name=dataset_name,
        entity_type_policy=entity_type_policy,
        entity_resolution_dataset_selection=entity_resolution_dataset_selection,
        entity_resolution_alignment=entity_resolution_alignment,
        entity_resolution_canonical_lookup=entity_resolution_canonical_lookup,
        entity_resolution_graph=entity_resolution_graph,
    )


def run_entity_resolution(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    dataset_name: str | None = None,
    entity_type_policy: Any = None,
    entity_resolution_dataset_selection: EntityResolutionDatasetSelectionContract | None = None,
    entity_resolution_alignment: EntityResolutionAlignmentContract | None = None,
    entity_resolution_canonical_lookup: EntityResolutionCanonicalLookupContract | None = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
    runtime_runner: Callable[..., dict[str, Any]] | None = None,
    default_resolution_mode: str = RESOLUTION_MODE_STRUCTURED_ANCHOR,
    valid_resolution_modes: frozenset[str] = VALID_RESOLUTION_MODES,
) -> dict[str, Any]:
    effective_resolution_mode = resolution_mode
    if effective_resolution_mode is None:
        effective_resolution_mode = (
            getattr(config, "resolution_mode", default_resolution_mode)
            or default_resolution_mode
        )
    if effective_resolution_mode not in valid_resolution_modes:
        raise ValueError(
            f"Unknown resolution_mode {effective_resolution_mode!r}. "
            f"Valid modes: {sorted(valid_resolution_modes)}"
        )

    effective_dataset_id = resolve_effective_dataset_id(
        config,
        dataset_id,
        dataset_name=dataset_name,
        entity_resolution_dataset_selection=entity_resolution_dataset_selection,
    )
    resolved_neo4j_settings = neo4j_settings_from_config(config, neo4j_settings)
    resolved_runtime_runner = runtime_runner or _default_runtime_runner()
    return resolved_runtime_runner(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=effective_resolution_mode,
        artifact_subdir=artifact_subdir,
        effective_dataset_id=effective_dataset_id,
        neo4j_settings=resolved_neo4j_settings,
        entity_type_policy=entity_type_policy,
        entity_resolution_alignment=entity_resolution_alignment,
        entity_resolution_canonical_lookup=entity_resolution_canonical_lookup,
        entity_resolution_graph=entity_resolution_graph,
    )


def run_entity_resolution_request_context(
    request_context: RequestContext,
    *,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    entity_resolution_dataset_selection: EntityResolutionDatasetSelectionContract | None = None,
    entity_resolution_alignment: EntityResolutionAlignmentContract | None = None,
    entity_resolution_canonical_lookup: EntityResolutionCanonicalLookupContract | None = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return run_entity_resolution_runtime(
        request_context.runtime,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        entity_resolution_dataset_selection=entity_resolution_dataset_selection,
        entity_resolution_alignment=entity_resolution_alignment,
        entity_resolution_canonical_lookup=entity_resolution_canonical_lookup,
        entity_resolution_graph=entity_resolution_graph,
        config_runner=config_runner,
    )


def run_entity_resolution_runtime(
    request_runtime: RequestRuntime,
    *,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    entity_resolution_dataset_selection: EntityResolutionDatasetSelectionContract | None = None,
    entity_resolution_alignment: EntityResolutionAlignmentContract | None = None,
    entity_resolution_canonical_lookup: EntityResolutionCanonicalLookupContract | None = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
    config_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_id = request_runtime.run_id
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Entity resolution requires request_runtime.run_id")

    resolved_config_runner = config_runner or _default_config_runner
    return resolved_config_runner(
        request_runtime.config,
        run_id=run_id,
        source_uri=request_runtime.source_uri,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        neo4j_settings=request_runtime.settings.neo4j,
        dataset_name=request_runtime.settings.dataset_name,
        entity_type_policy=request_runtime.policies.entity_type_normalization,
        entity_resolution_dataset_selection=entity_resolution_dataset_selection,
        entity_resolution_alignment=entity_resolution_alignment,
        entity_resolution_canonical_lookup=entity_resolution_canonical_lookup,
        entity_resolution_graph=entity_resolution_graph,
    )


__all__ = [
    "RESOLUTION_MODE_HYBRID",
    "RESOLUTION_MODE_STRUCTURED_ANCHOR",
    "RESOLUTION_MODE_UNSTRUCTURED_ONLY",
    "VALID_RESOLUTION_MODES",
    "neo4j_settings_from_config",
    "resolve_effective_dataset_id",
    "run_entity_resolution",
    "run_entity_resolution_runtime",
    "run_entity_resolution_request_context",
]