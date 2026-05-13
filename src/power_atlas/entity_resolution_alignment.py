from __future__ import annotations

from typing import Any

from power_atlas.contracts import EntityResolutionAlignmentContract
from power_atlas.contracts import EntityResolutionCanonicalLookupContract
from power_atlas.contracts import (
    get_default_entity_resolution_alignment_contract,
)
from power_atlas.contracts import (
    get_default_entity_resolution_canonical_lookup_contract,
)


def align_clusters_to_canonical(
    clusters: list[dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
    canonical_lookup_contract: EntityResolutionCanonicalLookupContract | None = None,
    entity_resolution_alignment: EntityResolutionAlignmentContract | None = None,
) -> list[dict[str, Any]]:
    resolved_alignment = (
        get_default_entity_resolution_alignment_contract()
        if entity_resolution_alignment is None
        else entity_resolution_alignment
    )
    resolved_lookup = (
        get_default_entity_resolution_canonical_lookup_contract()
        if canonical_lookup_contract is None
        else canonical_lookup_contract
    )
    lookup_tables = {
        "label": by_label,
        "alias": by_alias,
    }
    default_step_values = {
        "label": (
            resolved_lookup.label_exact_method,
            resolved_lookup.label_exact_confidence,
            resolved_lookup.aligned_status,
        ),
        "alias": (
            resolved_lookup.alias_exact_method,
            resolved_lookup.alias_exact_confidence,
            resolved_lookup.aligned_status,
        ),
    }
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        cluster_source_uri = cluster.get("source_uri")
        for step in resolved_alignment.steps:
            if step.lookup_table not in lookup_tables:
                raise ValueError(
                    f"Unknown alignment lookup_table {step.lookup_table!r}. "
                    f"Valid values: {sorted(lookup_tables)}"
                )
            method, score, status = default_step_values[step.lookup_table]
            lookup_table = lookup_tables[step.lookup_table]
            candidate_keys = step.cluster_keys(cluster) or ()
            canonical = next(
                (lookup_table[key] for key in candidate_keys if key in lookup_table),
                None,
            )
            if canonical is None:
                continue
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "canonical_entity_id": canonical[
                        resolved_lookup.canonical_entity_id_field
                    ],
                    "canonical_run_id": canonical[
                        resolved_lookup.canonical_run_id_field
                    ],
                    "alignment_method": step.method or method,
                    "alignment_score": step.score if step.score is not None else score,
                    "alignment_status": step.status or status,
                    "source_uri": cluster_source_uri,
                }
            )
            break

    return rows


__all__ = ["align_clusters_to_canonical"]