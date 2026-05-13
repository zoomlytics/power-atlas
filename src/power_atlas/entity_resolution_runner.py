from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from power_atlas.backend_run_catalog import resolve_run_root
from power_atlas.contracts import (
    EntityResolutionGraphContract,
    get_default_entity_resolution_graph_contract,
)
from power_atlas.entity_resolution_runtime import run_entity_resolution_live
from power_atlas.entity_resolution_writes import (
    write_alignment_results as _write_alignment_results_live,
    write_cluster_memberships as _write_cluster_memberships_live,
    write_resolved_mentions as _write_resolved_mentions_live,
)
from power_atlas.settings import Neo4jSettings


WriteResolutionResults = Callable[[
    Any,
], None]

DEFAULT_RESOLVER_VERSION = "v1.2"
DEFAULT_CLUSTER_VERSION = "v1.3"


def write_cluster_memberships(
    driver: Any,
    *,
    run_id: str,
    cluster_rows: list[dict[str, Any]],
    neo4j_database: str,
    created_at: str,
    cluster_version: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    _write_cluster_memberships_live(
        driver,
        run_id=run_id,
        cluster_rows=cluster_rows,
        neo4j_database=neo4j_database,
        resolver_version=cluster_version,
        created_at=created_at,
        entity_resolution_graph=entity_resolution_graph,
    )



def write_resolved_mentions(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    neo4j_database: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    _write_resolved_mentions_live(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        resolved_rows=resolved_rows,
        neo4j_database=neo4j_database,
        entity_resolution_graph=entity_resolution_graph,
    )



def write_alignment_results(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    alignment_rows: list[dict[str, Any]],
    neo4j_database: str,
    alignment_version: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    _write_alignment_results_live(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        alignment_rows=alignment_rows,
        neo4j_database=neo4j_database,
        alignment_version=alignment_version,
        entity_resolution_graph=entity_resolution_graph,
    )



def write_resolution_results(
    driver: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    neo4j_database: str,
    make_cluster_id: Callable[[str, str | None, str], str],
    membership_score: Callable[[str, float], float],
    membership_status: Callable[[str, float], str],
    cluster_version: str,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> None:
    write_resolved_mentions(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        resolved_rows=resolved_rows,
        neo4j_database=neo4j_database,
        entity_resolution_graph=entity_resolution_graph,
    )

    if unresolved_rows:
        created_at = datetime.now(UTC).isoformat()
        cluster_rows = []
        for row in unresolved_rows:
            method = row.get("resolution_method", "label_cluster")
            entity_type = row.get("entity_type")
            row_source_uri = row.get("source_uri")
            score = membership_score(method, row.get("resolution_confidence", 1.0))
            cluster_rows.append(
                {
                    "mention_id": row["mention_id"],
                    "cluster_id": make_cluster_id(run_id, entity_type, row["normalized_text"]),
                    "canonical_name": row["normalized_text"].title(),
                    "normalized_text": row["normalized_text"],
                    "entity_type": entity_type,
                    "source_uri": row_source_uri,
                    "score": score,
                    "method": method,
                    "status": membership_status(method, score),
                }
            )
        write_cluster_memberships(
            driver,
            run_id=run_id,
            cluster_rows=cluster_rows,
            neo4j_database=neo4j_database,
            cluster_version=cluster_version,
            created_at=created_at,
            entity_resolution_graph=entity_resolution_graph,
        )



def run_entity_resolution_runtime(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str,
    artifact_subdir: str,
    effective_dataset_id: str,
    neo4j_settings: Neo4jSettings,
    entity_type_policy: Any = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
    resolver_version: str,
    cluster_version: str,
    alignment_version: str,
    build_entity_type_report: Callable[[list[dict[str, Any]], Any], dict[str, Any]],
    cluster_mentions: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    fetch_mentions: Callable[..., list[dict[str, Any]]],
    fetch_canonicals: Callable[..., list[dict[str, Any]]],
    build_lookup_tables: Callable[[list[dict[str, Any]]], tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]],
    make_cluster_id: Callable[[str, str | None, str], str],
    align_clusters_to_canonical: Callable[[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]], list[dict[str, Any]]],
    resolve_mention: Callable[[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]], dict[str, Any]],
    write_resolution_results: Callable[..., None],
    write_alignment_results: Callable[..., None],
    fetch_member_of_coverage: Callable[..., Any],
    fetch_alignment_coverage: Callable[..., Any],
    resolution_mode_structured_anchor: str,
    resolution_mode_unstructured_only: str,
    resolution_mode_hybrid: str,
    live_runner: Callable[..., Any] = run_entity_resolution_live,
) -> dict[str, Any]:
    resolved_entity_resolution_graph = (
        get_default_entity_resolution_graph_contract()
        if entity_resolution_graph is None
        else entity_resolution_graph
    )
    resolved_at = datetime.now(UTC).isoformat()

    run_root = resolve_run_root(config.output_dir, run_id)

    artifact_subdir_path = Path(artifact_subdir)
    if artifact_subdir_path.is_absolute() or ".." in artifact_subdir_path.parts:
        raise ValueError(
            f"Invalid artifact_subdir {artifact_subdir!r}: must be a relative path without '..'."
        )

    resolution_dir = (run_root / artifact_subdir_path).resolve()
    if resolution_dir == run_root or run_root not in resolution_dir.parents:
        raise ValueError(
            f"Invalid artifact_subdir {artifact_subdir!r}: must resolve to a subdirectory of the run directory."
        )

    resolution_dir.mkdir(parents=True, exist_ok=True)
    summary_path = resolution_dir / "entity_resolution_summary.json"
    unresolved_path = resolution_dir / "unresolved_mentions.json"

    if config.dry_run:
        if resolution_mode == resolution_mode_unstructured_only:
            resolver_method = "unstructured_clustering"
        elif resolution_mode == resolution_mode_hybrid:
            resolver_method = "unstructured_clustering_with_canonical_alignment"
        else:
            resolver_method = "canonical_exact_match"
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "resolution_mode": resolution_mode,
            "dataset_id": effective_dataset_id,
            "resolver_method": resolver_method,
            "resolver_version": resolver_version,
            "cluster_version": cluster_version,
            "mentions_total": 0,
            "resolved": 0,
            "unresolved": 0,
            "clusters_created": 0,
            "resolution_breakdown": {},
            "entity_type_report": build_entity_type_report([], entity_type_policy),
            "warnings": ["entity resolution skipped in dry_run mode"],
        }
        if resolution_mode in (resolution_mode_unstructured_only, resolution_mode_hybrid):
            summary["mentions_clustered"] = 0
            summary["mentions_unclustered"] = 0
        if resolution_mode == resolution_mode_hybrid:
            summary["alignment_version"] = alignment_version
            summary["aligned_clusters"] = 0
            summary["alignment_breakdown"] = {}
            summary["distinct_canonical_entities_aligned"] = 0
            summary["mentions_in_aligned_clusters"] = 0
            summary["clusters_pending_alignment"] = 0
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        unresolved_path.write_text(json.dumps([], indent=2), encoding="utf-8")
        return summary

    live_result = live_runner(
        neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        effective_dataset_id=effective_dataset_id,
        alignment_version=alignment_version,
        neo4j_database=neo4j_settings.database,
        entity_resolution_graph=resolved_entity_resolution_graph,
        fetch_mentions=fetch_mentions,
        cluster_mentions=cluster_mentions,
        fetch_canonicals=fetch_canonicals,
        build_lookup_tables=build_lookup_tables,
        make_cluster_id=make_cluster_id,
        align_clusters_to_canonical=align_clusters_to_canonical,
        resolve_mention=resolve_mention,
        write_resolution_results=write_resolution_results,
        write_alignment_results=write_alignment_results,
        fetch_member_of_coverage=fetch_member_of_coverage,
        fetch_alignment_coverage=fetch_alignment_coverage,
    )

    mentions = live_result.mentions
    resolved_rows = live_result.resolved_rows
    unresolved_rows = live_result.unresolved_rows
    resolution_breakdown = live_result.resolution_breakdown
    graph_mentions_clustered = live_result.graph_mentions_clustered
    graph_mentions_unclustered = live_result.graph_mentions_unclustered
    graph_total_clusters = live_result.graph_total_clusters
    graph_aligned_clusters = live_result.graph_aligned_clusters
    graph_distinct_canonical_entities = live_result.graph_distinct_canonical_entities
    graph_mentions_in_aligned = live_result.graph_mentions_in_aligned
    graph_alignment_breakdown = live_result.graph_alignment_breakdown
    stage_warnings = live_result.warnings

    unresolved_list = [
        {
            "mention_id": row["mention_id"],
            "mention_name": row["mention_name"],
            "normalized_text": row["normalized_text"],
            "entity_type": row.get("entity_type") or None,
            "cluster_id": make_cluster_id(
                run_id,
                row.get("entity_type"),
                row["normalized_text"],
            ),
        }
        for row in unresolved_rows
    ]
    unresolved_path.write_text(json.dumps(unresolved_list, indent=2), encoding="utf-8")

    clusters_created = len({
        (row.get("entity_type") or "", row["normalized_text"]) for row in unresolved_rows
    })

    if resolution_mode == resolution_mode_unstructured_only:
        live_resolver_method = "unstructured_clustering"
    elif resolution_mode == resolution_mode_hybrid:
        live_resolver_method = "unstructured_clustering_with_canonical_alignment"
    else:
        live_resolver_method = "canonical_exact_match"

    entity_type_report = build_entity_type_report(mentions, entity_type_policy)
    stage_warnings.extend(entity_type_report.get("sentinel_label_warnings") or [])

    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "resolution_mode": resolution_mode,
        "dataset_id": effective_dataset_id,
        "resolver_method": live_resolver_method,
        "resolver_version": resolver_version,
        "cluster_version": cluster_version,
        "resolved_at": resolved_at,
        "mentions_total": len(mentions),
        "resolved": len(resolved_rows),
        "unresolved": len(unresolved_rows),
        "clusters_created": clusters_created,
        "resolution_breakdown": resolution_breakdown,
        "entity_type_report": entity_type_report,
        "entity_resolution_summary_path": str(summary_path),
        "unresolved_mentions_path": str(unresolved_path),
        "warnings": list(stage_warnings),
    }
    if resolution_mode in (resolution_mode_unstructured_only, resolution_mode_hybrid):
        summary["mentions_clustered"] = graph_mentions_clustered
        summary["mentions_unclustered"] = graph_mentions_unclustered
        if graph_mentions_unclustered:
            summary["warnings"].append(
                f"{graph_mentions_unclustered} mentions were not assigned to any cluster"
            )
    if resolution_mode == resolution_mode_hybrid:
        summary["alignment_version"] = alignment_version
        summary["aligned_clusters"] = graph_aligned_clusters
        summary["alignment_breakdown"] = graph_alignment_breakdown
        summary["distinct_canonical_entities_aligned"] = graph_distinct_canonical_entities
        summary["mentions_in_aligned_clusters"] = graph_mentions_in_aligned
        summary["clusters_pending_alignment"] = max(
            0, graph_total_clusters - graph_aligned_clusters
        )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_entity_resolution_runtime_default(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str,
    artifact_subdir: str,
    effective_dataset_id: str,
    neo4j_settings: Neo4jSettings,
    entity_type_policy: Any = None,
    entity_resolution_graph: EntityResolutionGraphContract | None = None,
) -> dict[str, Any]:
    from power_atlas.contracts.resolution import ALIGNMENT_VERSION
    from power_atlas.entity_resolution_alignment import align_clusters_to_canonical
    from power_atlas.entity_resolution_clustering import (
        _cluster_mentions_unstructured_only,
        _make_cluster_id,
        _membership_score,
        _membership_status,
    )
    from power_atlas.entity_resolution_entrypoint import (
        RESOLUTION_MODE_HYBRID,
        RESOLUTION_MODE_STRUCTURED_ANCHOR,
        RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    )
    from power_atlas.entity_resolution_queries import (
        fetch_alignment_coverage,
        fetch_canonical_entities,
        fetch_entity_mentions,
        fetch_member_of_coverage,
    )
    from power_atlas.entity_resolution_reporting import build_entity_type_report
    from power_atlas.entity_resolution_resolver import _build_lookup_tables, _resolve_mention

    def _default_make_cluster_id(
        current_run_id: str,
        current_entity_type: str | None,
        normalized_text: str,
    ) -> str:
        return _make_cluster_id(
            current_run_id,
            current_entity_type,
            normalized_text,
            entity_type_policy,
        )

    def _default_write_resolution_results(
        driver: Any,
        *,
        run_id: str,
        source_uri: str | None,
        resolved_rows: list[dict[str, Any]],
        unresolved_rows: list[dict[str, Any]],
        neo4j_database: str,
            entity_resolution_graph: EntityResolutionGraphContract | None = None,
    ) -> None:
        write_resolution_results(
            driver,
            run_id=run_id,
            source_uri=source_uri,
            resolved_rows=resolved_rows,
            unresolved_rows=unresolved_rows,
            neo4j_database=neo4j_database,
            make_cluster_id=_default_make_cluster_id,
            membership_score=_membership_score,
            membership_status=_membership_status,
            cluster_version=DEFAULT_CLUSTER_VERSION,
            entity_resolution_graph=entity_resolution_graph,
        )

    def _default_write_alignment_results(
        driver: Any,
        *,
        run_id: str,
        source_uri: str | None,
        alignment_rows: list[dict[str, Any]],
        neo4j_database: str,
            entity_resolution_graph: EntityResolutionGraphContract | None = None,
    ) -> None:
        write_alignment_results(
            driver,
            run_id=run_id,
            source_uri=source_uri,
            alignment_rows=alignment_rows,
            neo4j_database=neo4j_database,
            alignment_version=ALIGNMENT_VERSION,
            entity_resolution_graph=entity_resolution_graph,
        )

    return run_entity_resolution_runtime(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        effective_dataset_id=effective_dataset_id,
        neo4j_settings=neo4j_settings,
        entity_type_policy=entity_type_policy,
        entity_resolution_graph=entity_resolution_graph,
        resolver_version=DEFAULT_RESOLVER_VERSION,
        cluster_version=DEFAULT_CLUSTER_VERSION,
        alignment_version=ALIGNMENT_VERSION,
        build_entity_type_report=build_entity_type_report,
        cluster_mentions=lambda mentions: _cluster_mentions_unstructured_only(
            mentions,
            entity_type_policy=entity_type_policy,
        ),
        fetch_mentions=fetch_entity_mentions,
        fetch_canonicals=fetch_canonical_entities,
        build_lookup_tables=_build_lookup_tables,
        make_cluster_id=_default_make_cluster_id,
        align_clusters_to_canonical=align_clusters_to_canonical,
        resolve_mention=lambda mention, by_qid, by_label, by_alias: _resolve_mention(
            mention,
            by_qid,
            by_label,
            by_alias,
            entity_type_policy,
        ),
        write_resolution_results=_default_write_resolution_results,
        write_alignment_results=_default_write_alignment_results,
        fetch_member_of_coverage=fetch_member_of_coverage,
        fetch_alignment_coverage=fetch_alignment_coverage,
        resolution_mode_structured_anchor=RESOLUTION_MODE_STRUCTURED_ANCHOR,
        resolution_mode_unstructured_only=RESOLUTION_MODE_UNSTRUCTURED_ONLY,
        resolution_mode_hybrid=RESOLUTION_MODE_HYBRID,
    )


__all__ = [
    "DEFAULT_CLUSTER_VERSION",
    "DEFAULT_RESOLVER_VERSION",
    "run_entity_resolution_runtime",
    "write_alignment_results",
    "write_cluster_memberships",
    "write_resolution_results",
    "write_resolved_mentions",
]
