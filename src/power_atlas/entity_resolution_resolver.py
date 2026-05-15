from __future__ import annotations

import re
from typing import Any

from power_atlas.contracts import EntityResolutionCanonicalLookupContract
from power_atlas.contracts import EntityTypeNormalizationPolicy
from power_atlas.contracts import (
    get_default_entity_resolution_canonical_lookup_contract,
)
from power_atlas.contracts import normalize_entity_type as normalize_entity_type_from_policy
from power_atlas.text_utils import normalize_mention_text

_QID_PATTERN = re.compile(r"^Q\d+$")
_normalize = normalize_mention_text


def split_aliases(
    raw: Any,
    canonical_lookup_contract: EntityResolutionCanonicalLookupContract | None = None,
) -> list[str]:
    """Parse a pipe- or comma-separated alias string into normalised tokens.

    Each token is processed through normalize_mention_text so that alias lookup
    keys are consistent with the normalisation applied to mention text.
    """
    resolved_lookup = (
        get_default_entity_resolution_canonical_lookup_contract()
        if canonical_lookup_contract is None
        else canonical_lookup_contract
    )
    if not raw or not isinstance(raw, str):
        return []
    delimiters = [re.escape(delimiter) for delimiter in resolved_lookup.alias_delimiters]
    separator_pattern = "|".join(delimiters) if delimiters else re.escape("|")
    return [
        normalized
        for token in re.split(separator_pattern, raw)
        if (normalized := _normalize(token))
    ]


def build_lookup_tables(
    canonical_nodes: list[dict[str, Any]],
    canonical_lookup_contract: EntityResolutionCanonicalLookupContract | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build three lookup dicts for fast resolution.

    Returns:
        by_qid: entity_id -> canonical row
        by_label: normalized_name -> canonical row (first match wins)
        by_alias: normalized_alias -> canonical row (first match wins)
    """
    resolved_lookup = (
        get_default_entity_resolution_canonical_lookup_contract()
        if canonical_lookup_contract is None
        else canonical_lookup_contract
    )
    by_qid: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}

    for row in canonical_nodes:
        entity_id = (row.get(resolved_lookup.canonical_entity_id_field) or "").strip()
        name = (row.get(resolved_lookup.canonical_name_field) or "").strip()
        if entity_id and entity_id not in by_qid:
            by_qid[entity_id] = row
        normalized_name = _normalize(name)
        if normalized_name and normalized_name not in by_label:
            by_label[normalized_name] = row
        for alias in split_aliases(
            row.get(resolved_lookup.canonical_aliases_field),
            canonical_lookup_contract=resolved_lookup,
        ):
            if alias and alias not in by_alias:
                by_alias[alias] = row

    return by_qid, by_label, by_alias


def resolve_mention(
    mention: dict[str, Any],
    by_qid: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
    canonical_lookup_contract: EntityResolutionCanonicalLookupContract | None = None,
) -> dict[str, Any]:
    """Apply resolution strategies and return a resolution record."""
    resolved_lookup = (
        get_default_entity_resolution_canonical_lookup_contract()
        if canonical_lookup_contract is None
        else canonical_lookup_contract
    )
    name = (mention.get("name") or "").strip()
    normalized = _normalize(name)

    qid_pattern = resolved_lookup.qid_pattern or _QID_PATTERN
    if qid_pattern.match(name):
        canonical = by_qid.get(name)
        if canonical:
            return {
                "mention_id": mention["mention_id"],
                "canonical_entity_id": canonical[
                    resolved_lookup.canonical_entity_id_field
                ],
                "canonical_run_id": canonical[
                    resolved_lookup.canonical_run_id_field
                ],
                "resolution_method": resolved_lookup.qid_exact_method,
                "resolution_confidence": resolved_lookup.qid_exact_confidence,
                "candidate_ids": [
                    canonical[resolved_lookup.canonical_entity_id_field]
                ],
                "resolved": True,
            }
        return {
            "mention_id": mention["mention_id"],
            "normalized_text": normalized,
            "mention_name": name,
            "entity_type": normalize_entity_type_from_policy(
                mention.get("entity_type") or None,
                entity_type_policy,
            ),
            "source_uri": mention.get("source_uri") or None,
            "resolution_method": resolved_lookup.unresolved_method,
            "resolution_confidence": 0.0,
            "candidate_ids": [],
            "resolved": False,
        }

    canonical = by_label.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical[
                resolved_lookup.canonical_entity_id_field
            ],
            "canonical_run_id": canonical[
                resolved_lookup.canonical_run_id_field
            ],
            "resolution_method": resolved_lookup.label_exact_method,
            "resolution_confidence": resolved_lookup.label_exact_confidence,
            "candidate_ids": [canonical[resolved_lookup.canonical_entity_id_field]],
            "resolved": True,
        }

    canonical = by_alias.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical[
                resolved_lookup.canonical_entity_id_field
            ],
            "canonical_run_id": canonical[
                resolved_lookup.canonical_run_id_field
            ],
            "resolution_method": resolved_lookup.alias_exact_method,
            "resolution_confidence": resolved_lookup.alias_exact_confidence,
            "candidate_ids": [canonical[resolved_lookup.canonical_entity_id_field]],
            "resolved": True,
        }

    return {
        "mention_id": mention["mention_id"],
        "normalized_text": normalized,
        "mention_name": name,
        "entity_type": normalize_entity_type_from_policy(
            mention.get("entity_type") or None,
            entity_type_policy,
        ),
        "source_uri": mention.get("source_uri") or None,
        "resolution_method": resolved_lookup.unresolved_method,
        "resolution_confidence": 0.0,
        "candidate_ids": [],
        "resolved": False,
    }


_split_aliases = split_aliases
_build_lookup_tables = build_lookup_tables
_resolve_mention = resolve_mention


__all__ = ["build_lookup_tables", "resolve_mention", "split_aliases"]
