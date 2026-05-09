from __future__ import annotations

from typing import Any


def align_clusters_to_canonical(
    clusters: list[dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        normalized_text = cluster["normalized_text"]
        cluster_source_uri = cluster.get("source_uri")

        canonical = by_label.get(normalized_text)
        if canonical:
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "canonical_entity_id": canonical["entity_id"],
                    "canonical_run_id": canonical["run_id"],
                    "alignment_method": "label_exact",
                    "alignment_score": 0.9,
                    "alignment_status": "aligned",
                    "source_uri": cluster_source_uri,
                }
            )
            continue

        canonical = by_alias.get(normalized_text)
        if canonical:
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "canonical_entity_id": canonical["entity_id"],
                    "canonical_run_id": canonical["run_id"],
                    "alignment_method": "alias_exact",
                    "alignment_score": 0.8,
                    "alignment_status": "aligned",
                    "source_uri": cluster_source_uri,
                }
            )

    return rows


__all__ = ["align_clusters_to_canonical"]