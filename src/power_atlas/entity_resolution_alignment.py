from __future__ import annotations

from typing import Any

from power_atlas.contracts import EntityResolutionCanonicalLookupContract
from power_atlas.contracts import (
    get_default_entity_resolution_canonical_lookup_contract,
)


def align_clusters_to_canonical(
    clusters: list[dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
    canonical_lookup_contract: EntityResolutionCanonicalLookupContract | None = None,
) -> list[dict[str, Any]]:
    resolved_lookup = (
        get_default_entity_resolution_canonical_lookup_contract()
        if canonical_lookup_contract is None
        else canonical_lookup_contract
    )
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
                    "canonical_entity_id": canonical[
                        resolved_lookup.canonical_entity_id_field
                    ],
                    "canonical_run_id": canonical[
                        resolved_lookup.canonical_run_id_field
                    ],
                    "alignment_method": resolved_lookup.label_exact_method,
                    "alignment_score": resolved_lookup.label_exact_confidence,
                    "alignment_status": resolved_lookup.aligned_status,
                    "source_uri": cluster_source_uri,
                }
            )
            continue

        canonical = by_alias.get(normalized_text)
        if canonical:
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "canonical_entity_id": canonical[
                        resolved_lookup.canonical_entity_id_field
                    ],
                    "canonical_run_id": canonical[
                        resolved_lookup.canonical_run_id_field
                    ],
                    "alignment_method": resolved_lookup.alias_exact_method,
                    "alignment_score": resolved_lookup.alias_exact_confidence,
                    "alignment_status": resolved_lookup.aligned_status,
                    "source_uri": cluster_source_uri,
                }
            )

    return rows


__all__ = ["align_clusters_to_canonical"]