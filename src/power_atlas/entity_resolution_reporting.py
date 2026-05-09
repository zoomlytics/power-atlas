from __future__ import annotations

from typing import Any

from power_atlas.contracts import (
    EntityTypeNormalizationPolicy,
    POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY,
    normalize_entity_type as normalize_entity_type_from_policy,
)


ENTITY_TYPE_NULL_SENTINEL = POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY.null_sentinel


def build_entity_type_report(
    mentions: list[dict[str, Any]],
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> dict[str, Any]:
    raw_counts: dict[str | None, int] = {}
    normalized_counts: dict[str, int] = {}
    mapped_variants: dict[str, str] = {}
    passthrough_labels: set[str] = set()
    null_or_empty_count = 0
    raw_null_sentinel_seen = False

    for mention in mentions:
        raw = mention.get("entity_type")
        if isinstance(raw, str) and raw.strip() == ENTITY_TYPE_NULL_SENTINEL:
            raw_null_sentinel_seen = True
        if isinstance(raw, str) and not raw.strip():
            raw = None

        raw_counts[raw] = raw_counts.get(raw, 0) + 1

        if raw is None:
            null_or_empty_count += 1
            norm_key = ENTITY_TYPE_NULL_SENTINEL
        else:
            normalized = normalize_entity_type_from_policy(raw, entity_type_policy)
            if normalized is None:
                null_or_empty_count += 1
                norm_key = ENTITY_TYPE_NULL_SENTINEL
            else:
                norm_key = normalized
                if normalized != raw:
                    mapped_variants[raw] = normalized
                elif raw != ENTITY_TYPE_NULL_SENTINEL:
                    passthrough_labels.add(raw)
        normalized_counts[norm_key] = normalized_counts.get(norm_key, 0) + 1

    serialized_raw_counts: dict[str, int] = {}
    for raw_key, count in raw_counts.items():
        if raw_key is None or (
            isinstance(raw_key, str) and raw_key.strip() == ENTITY_TYPE_NULL_SENTINEL
        ):
            serialized_key = ENTITY_TYPE_NULL_SENTINEL
        else:
            serialized_key = raw_key
        serialized_raw_counts[serialized_key] = (
            serialized_raw_counts.get(serialized_key, 0) + count
        )

    sentinel_label_warnings: list[str] = []
    if raw_null_sentinel_seen and null_or_empty_count > 0:
        sentinel_label_warnings.append(
            f"Upstream extractor emitted the reserved sentinel label "
            f"{ENTITY_TYPE_NULL_SENTINEL!r}; "
            "its counts are merged with the absent/empty bucket in raw_counts "
            "and normalized_counts and cannot be distinguished retroactively."
        )

    return {
        "raw_counts": dict(
            sorted(serialized_raw_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "normalized_counts": dict(
            sorted(normalized_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "mapped_variants": dict(sorted(mapped_variants.items())),
        "passthrough_labels": sorted(passthrough_labels),
        "null_or_empty_count": null_or_empty_count,
        "sentinel_label_warnings": sentinel_label_warnings,
    }


__all__ = ["ENTITY_TYPE_NULL_SENTINEL", "build_entity_type_report"]