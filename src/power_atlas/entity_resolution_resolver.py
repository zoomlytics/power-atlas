from __future__ import annotations

import re
from typing import Any

from power_atlas.contracts import EntityTypeNormalizationPolicy
from power_atlas.contracts import normalize_entity_type as normalize_entity_type_from_policy
from power_atlas.text_utils import normalize_mention_text

_QID_PATTERN = re.compile(r"^Q\d+$")
_normalize = normalize_mention_text


def _split_aliases(raw: Any) -> list[str]:
    """Parse a pipe- or comma-separated alias string into normalised tokens.

    Each token is processed through normalize_mention_text so that alias lookup
    keys are consistent with the normalisation applied to mention text.
    """
    if not raw or not isinstance(raw, str):
        return []
    separator = "|" if "|" in raw else ","
    return [normalized for token in raw.split(separator) if (normalized := _normalize(token))]



def _build_lookup_tables(
    canonical_nodes: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build three lookup dicts for fast resolution.

    Returns:
        by_qid: entity_id -> canonical row
        by_label: normalized_name -> canonical row (first match wins)
        by_alias: normalized_alias -> canonical row (first match wins)
    """
    by_qid: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}

    for row in canonical_nodes:
        entity_id = (row.get("entity_id") or "").strip()
        name = (row.get("name") or "").strip()
        if entity_id and entity_id not in by_qid:
            by_qid[entity_id] = row
        normalized_name = _normalize(name)
        if normalized_name and normalized_name not in by_label:
            by_label[normalized_name] = row
        for alias in _split_aliases(row.get("aliases")):
            if alias and alias not in by_alias:
                by_alias[alias] = row

    return by_qid, by_label, by_alias



def _resolve_mention(
    mention: dict[str, Any],
    by_qid: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> dict[str, Any]:
    """Apply resolution strategies and return a resolution record."""
    name = (mention.get("name") or "").strip()
    normalized = _normalize(name)

    if _QID_PATTERN.match(name):
        canonical = by_qid.get(name)
        if canonical:
            return {
                "mention_id": mention["mention_id"],
                "canonical_entity_id": canonical["entity_id"],
                "canonical_run_id": canonical["run_id"],
                "resolution_method": "qid_exact",
                "resolution_confidence": 1.0,
                "candidate_ids": [canonical["entity_id"]],
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
            "resolution_method": "label_cluster",
            "resolution_confidence": 0.0,
            "candidate_ids": [],
            "resolved": False,
        }

    canonical = by_label.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical["entity_id"],
            "canonical_run_id": canonical["run_id"],
            "resolution_method": "label_exact",
            "resolution_confidence": 0.9,
            "candidate_ids": [canonical["entity_id"]],
            "resolved": True,
        }

    canonical = by_alias.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical["entity_id"],
            "canonical_run_id": canonical["run_id"],
            "resolution_method": "alias_exact",
            "resolution_confidence": 0.8,
            "candidate_ids": [canonical["entity_id"]],
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
        "resolution_method": "label_cluster",
        "resolution_confidence": 0.0,
        "candidate_ids": [],
        "resolved": False,
    }


__all__ = ["_build_lookup_tables", "_resolve_mention", "_split_aliases"]
