from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from power_atlas.bootstrap import create_neo4j_driver


@dataclass(frozen=True)
class EntityResolutionLiveResult:
    mentions: list[dict[str, Any]]
    resolved_rows: list[dict[str, Any]]
    unresolved_rows: list[dict[str, Any]]
    resolution_breakdown: dict[str, int]
    graph_mentions_clustered: int
    graph_mentions_unclustered: int
    graph_total_clusters: int
    graph_aligned_clusters: int
    graph_distinct_canonical_entities: int
    graph_mentions_in_aligned: int
    graph_alignment_breakdown: dict[str, int]
    warnings: list[str]


def run_entity_resolution_live(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str,
    effective_dataset_id: str,
    alignment_version: str,
    fetch_mentions: Callable[..., list[dict[str, Any]]],
    cluster_mentions: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    fetch_canonicals: Callable[..., list[dict[str, Any]]],
    build_lookup_tables: Callable[..., tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    make_cluster_id: Callable[[str, str | None, str], str],
    align_clusters_to_canonical: Callable[..., list[dict[str, Any]]],
    resolve_mention: Callable[..., dict[str, Any]],
    write_resolution_results: Callable[..., None],
    write_alignment_results: Callable[..., None],
    fetch_member_of_coverage: Callable[..., Any],
    fetch_alignment_coverage: Callable[..., Any],
) -> EntityResolutionLiveResult:
    graph_mentions_clustered = 0
    graph_mentions_unclustered = 0
    graph_total_clusters = 0
    graph_aligned_clusters = 0
    graph_distinct_canonical_entities = 0
    graph_mentions_in_aligned = 0
    graph_alignment_breakdown: dict[str, int] = {}
    stage_warnings: list[str] = []

    with create_neo4j_driver(config) as driver:
        mentions = fetch_mentions(
            driver,
            run_id=run_id,
            source_uri_fallback=source_uri,
            neo4j_database=config.neo4j_database,
        )

        resolved_rows: list[dict[str, Any]] = []
        unresolved_rows: list[dict[str, Any]] = []
        resolution_breakdown: dict[str, int] = {}
        alignment_rows: list[dict[str, Any]] = []

        if resolution_mode == "unstructured_only":
            cluster_rows_result = cluster_mentions(mentions)
            for row in cluster_rows_result:
                method = row["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1
                unresolved_rows.append(row)
        elif resolution_mode == "hybrid":
            cluster_rows_result = cluster_mentions(mentions)
            for row in cluster_rows_result:
                method = row["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1
                unresolved_rows.append(row)

            canonical_nodes = fetch_canonicals(
                driver,
                dataset_id=effective_dataset_id,
                neo4j_database=config.neo4j_database,
            )
            if not canonical_nodes:
                stage_warnings.append(
                    f"CanonicalEntity lookup returned zero rows for dataset_id={effective_dataset_id!r} "
                    f"(hybrid alignment skipped); check that structured ingest has run for this dataset "
                    f"and that CanonicalEntity nodes carry a matching dataset_id property.  "
                    f"If CanonicalEntity nodes already exist but have dataset_id=null (legacy graph), "
                    f"run the in-place repair Cypher or re-ingest from the structured fixture — "
                    f"see docs/architecture/legacy-dataset-id-migration-v0.1.md."
                )
            if canonical_nodes:
                _, by_label, by_alias = build_lookup_tables(canonical_nodes)
                cluster_entries_by_id: dict[str, tuple[tuple[str, str], dict[str, Any]]] = {}
                for row in unresolved_rows:
                    cluster_id = make_cluster_id(run_id, row.get("entity_type"), row["normalized_text"])
                    if cluster_id not in cluster_entries_by_id:
                        sort_key = (row.get("entity_type") or "", row["normalized_text"])
                        cluster_entries_by_id[cluster_id] = (
                            sort_key,
                            {
                                "cluster_id": cluster_id,
                                "normalized_text": row["normalized_text"],
                            },
                        )
                unique_clusters = [
                    cluster
                    for _, cluster in sorted(cluster_entries_by_id.values(), key=lambda item: item[0])
                ]
                alignment_rows = align_clusters_to_canonical(unique_clusters, by_label, by_alias)
        else:
            canonical_nodes = fetch_canonicals(
                driver,
                dataset_id=effective_dataset_id,
                neo4j_database=config.neo4j_database,
            )
            if not canonical_nodes:
                stage_warnings.append(
                    f"CanonicalEntity lookup returned zero rows for dataset_id={effective_dataset_id!r} "
                    f"(all mentions will be unresolved); check that structured ingest has run for this "
                    f"dataset and that CanonicalEntity nodes carry a matching dataset_id property.  "
                    f"If CanonicalEntity nodes already exist but have dataset_id=null (legacy graph), "
                    f"run the in-place repair Cypher or re-ingest from the structured fixture — "
                    f"see docs/architecture/legacy-dataset-id-migration-v0.1.md."
                )

            by_qid, by_label, by_alias = build_lookup_tables(canonical_nodes)

            for mention in mentions:
                result_rec = resolve_mention(mention, by_qid, by_label, by_alias)
                method = result_rec["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1

                if result_rec["resolved"]:
                    resolved_rows.append(result_rec)
                else:
                    unresolved_rows.append(result_rec)

        write_resolution_results(
            driver,
            run_id=run_id,
            source_uri=source_uri,
            resolved_rows=resolved_rows,
            unresolved_rows=unresolved_rows,
            neo4j_database=config.neo4j_database,
        )

        if resolution_mode == "hybrid":
            write_alignment_results(
                driver,
                run_id=run_id,
                source_uri=source_uri,
                alignment_rows=alignment_rows,
                neo4j_database=config.neo4j_database,
            )

        if resolution_mode in ("unstructured_only", "hybrid"):
            graph_coverage = fetch_member_of_coverage(
                driver,
                run_id=run_id,
                neo4j_database=config.neo4j_database,
            )
            graph_mentions_clustered = graph_coverage.mentions_clustered
            graph_mentions_unclustered = graph_coverage.mentions_unclustered

        if resolution_mode == "hybrid":
            alignment_coverage = fetch_alignment_coverage(
                driver,
                run_id=run_id,
                alignment_version=alignment_version,
                neo4j_database=config.neo4j_database,
            )
            graph_total_clusters = alignment_coverage.total_clusters
            graph_aligned_clusters = alignment_coverage.aligned_clusters
            graph_distinct_canonical_entities = alignment_coverage.distinct_canonical_entities_aligned
            graph_mentions_in_aligned = alignment_coverage.mentions_in_aligned
            graph_alignment_breakdown = alignment_coverage.alignment_breakdown

    return EntityResolutionLiveResult(
        mentions=mentions,
        resolved_rows=resolved_rows,
        unresolved_rows=unresolved_rows,
        resolution_breakdown=resolution_breakdown,
        graph_mentions_clustered=graph_mentions_clustered,
        graph_mentions_unclustered=graph_mentions_unclustered,
        graph_total_clusters=graph_total_clusters,
        graph_aligned_clusters=graph_aligned_clusters,
        graph_distinct_canonical_entities=graph_distinct_canonical_entities,
        graph_mentions_in_aligned=graph_mentions_in_aligned,
        graph_alignment_breakdown=dict(graph_alignment_breakdown),
        warnings=list(stage_warnings),
    )


__all__ = ["EntityResolutionLiveResult", "run_entity_resolution_live"]