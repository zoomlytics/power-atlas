from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote as _pct_encode

from power_atlas.contracts import EntityTypeNormalizationPolicy
from power_atlas.contracts import normalize_entity_type as normalize_entity_type_from_policy
from power_atlas.text_utils import normalize_mention_text

_FUZZY_REVIEW_THRESHOLD = 0.92
_RE_NON_ALPHA = re.compile(r"[^a-z]")
_normalize = normalize_mention_text

_INITIALISM_STOP_WORDS = frozenset({"of", "the", "and", "for", "in", "on", "at", "to", "a", "an"})


def _make_cluster_id(
    run_id: str,
    entity_type: str | None,
    normalized_text: str,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str:
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    run_id_enc = _pct_encode(run_id, safe="")
    entity_type_enc = _pct_encode(
        normalize_entity_type_from_policy(entity_type, entity_type_policy) or "",
        safe="",
    )
    normalized_text_enc = _pct_encode(normalized_text, safe="")
    return f"cluster::{run_id_enc}::{entity_type_enc}::{normalized_text_enc}"



def _compute_initials(text: str) -> str | None:
    significant: list[str] = []
    for word in text.split():
        word_lower = word.lower()
        alpha = _RE_NON_ALPHA.sub("", word_lower)
        if alpha and alpha not in _INITIALISM_STOP_WORDS:
            significant.append(alpha)
    if len(significant) < 2:
        return None
    return "".join(word[0] for word in significant)



def _is_abbreviation(short: str, long_form: str) -> bool:
    short_alpha = _RE_NON_ALPHA.sub("", short.lower())
    if not short_alpha:
        return False
    initials = _compute_initials(long_form.lower())
    if initials is None:
        return False
    return short_alpha == initials



def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()



def _membership_score(method: str, resolution_confidence: float) -> float:
    if method in ("label_cluster", "normalized_exact"):
        return 1.0
    if method == "abbreviation":
        return 0.75
    return resolution_confidence



def _membership_status(method: str, score: float) -> str:
    if method in ("label_cluster", "normalized_exact"):
        return "accepted"
    if method == "abbreviation":
        return "candidate"
    if method == "fuzzy":
        return "provisional" if score >= _FUZZY_REVIEW_THRESHOLD else "review_required"
    return "provisional"



def _cluster_mentions_unstructured_only(
    mentions: list[dict[str, Any]],
    *,
    fuzzy_threshold: float = 0.85,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> list[dict[str, Any]]:
    mention_to_cluster: dict[str, str] = {}
    mention_to_method: dict[str, tuple[str, float]] = {}
    mention_to_type: dict[str, str | None] = {}
    seen_keys: set[str] = set()
    cluster_to_mentions: dict[str, list[str]] = {}
    initials_to_long_by_type: dict[str | None, dict[str, str]] = {}
    abbrev_alpha_by_type: dict[str | None, dict[str, list[str]]] = {}
    seen_texts_by_type: dict[str | None, list[str]] = {}

    def _register_new_cluster(cluster_key: str, entity_type: str | None) -> None:
        seen_keys.add(cluster_key)
        seen_texts_by_type.setdefault(entity_type, []).append(cluster_key)
        abbrev_alpha_by_type.setdefault(entity_type, {}).setdefault(
            _RE_NON_ALPHA.sub("", cluster_key), []
        ).append(cluster_key)
        initials = _compute_initials(cluster_key)
        if initials is not None:
            initials_to_long_by_type.setdefault(entity_type, {})[initials] = cluster_key

    def _register_cluster_for_type(cluster_key: str, entity_type: str | None) -> None:
        type_texts = seen_texts_by_type.setdefault(entity_type, [])
        if cluster_key not in type_texts:
            type_texts.append(cluster_key)
        alpha = _RE_NON_ALPHA.sub("", cluster_key)
        bucket = abbrev_alpha_by_type.setdefault(entity_type, {}).setdefault(alpha, [])
        if cluster_key not in bucket:
            bucket.append(cluster_key)
        initials = _compute_initials(cluster_key)
        if initials is not None:
            initials_to_long_by_type.setdefault(entity_type, {}).setdefault(initials, cluster_key)

    def _promote_long_form(short_key: str, long_key: str, entity_type: str | None) -> None:
        seen_keys.add(long_key)

        type_texts = seen_texts_by_type.get(entity_type, [])
        if short_key in type_texts:
            type_texts[type_texts.index(short_key)] = long_key
            seen_for_type: set[str] = set()
            deduped_type_texts: list[str] = []
            for text in type_texts:
                if text not in seen_for_type:
                    seen_for_type.add(text)
                    deduped_type_texts.append(text)
            if len(deduped_type_texts) != len(type_texts):
                seen_texts_by_type[entity_type] = deduped_type_texts

        old_alpha = _RE_NON_ALPHA.sub("", short_key)
        type_abbrev = abbrev_alpha_by_type.get(entity_type, {})
        bucket = type_abbrev.get(old_alpha, [])
        if short_key in bucket:
            bucket.remove(short_key)
        if not bucket:
            type_abbrev.pop(old_alpha, None)
        long_alpha = _RE_NON_ALPHA.sub("", long_key)
        long_bucket = abbrev_alpha_by_type.setdefault(entity_type, {}).setdefault(long_alpha, [])
        if long_key not in long_bucket:
            long_bucket.append(long_key)
        initials_map = initials_to_long_by_type.get(entity_type, {})
        for key in [key for key, value in initials_map.items() if value == short_key]:
            del initials_map[key]
        long_initials = _compute_initials(long_key)
        if long_initials is not None:
            initials_to_long_by_type.setdefault(entity_type, {})[long_initials] = long_key

        new_members: list[str] = []
        remaining: list[str] = []
        for prior_mid in cluster_to_mentions.get(short_key, []):
            if mention_to_type.get(prior_mid) == entity_type:
                mention_to_cluster[prior_mid] = long_key
                mention_to_method[prior_mid] = ("abbreviation", 0.75)
                new_members.append(prior_mid)
            else:
                remaining.append(prior_mid)
        cluster_to_mentions.setdefault(long_key, []).extend(new_members)
        if remaining:
            cluster_to_mentions[short_key] = remaining
        elif short_key in cluster_to_mentions:
            del cluster_to_mentions[short_key]

        if not remaining:
            seen_keys.discard(short_key)

    for mention in mentions:
        name = (mention.get("name") or "").strip()
        normalized = _normalize(name)
        mention_id = mention["mention_id"]
        entity_type = normalize_entity_type_from_policy(
            mention.get("entity_type") or None,
            entity_type_policy,
        )
        short_alpha = _RE_NON_ALPHA.sub("", normalized)

        if normalized in seen_keys:
            mapped_long = initials_to_long_by_type.get(entity_type, {}).get(short_alpha)
            if mapped_long is not None and mapped_long != normalized:
                mention_to_cluster[mention_id] = mapped_long
                mention_to_method[mention_id] = ("abbreviation", 0.75)
                mention_to_type[mention_id] = entity_type
                cluster_to_mentions.setdefault(mapped_long, []).append(mention_id)
                continue

            mention_to_cluster[mention_id] = normalized
            mention_to_method[mention_id] = ("normalized_exact", 1.0)
            mention_to_type[mention_id] = entity_type
            cluster_to_mentions.setdefault(normalized, []).append(mention_id)
            _register_cluster_for_type(normalized, entity_type)
            continue

        existing_long = initials_to_long_by_type.get(entity_type, {}).get(short_alpha)
        if existing_long is not None:
            mention_to_cluster[mention_id] = existing_long
            mention_to_method[mention_id] = ("abbreviation", 0.75)
            mention_to_type[mention_id] = entity_type
            cluster_to_mentions.setdefault(existing_long, []).append(mention_id)
            continue

        current_initials = _compute_initials(normalized)
        abbrev_cluster_keys: list[str] = []
        if current_initials is not None:
            abbrev_cluster_keys = list(
                abbrev_alpha_by_type.get(entity_type, {}).get(current_initials, [])
            )
        if abbrev_cluster_keys:
            for abbrev_key in abbrev_cluster_keys:
                _promote_long_form(abbrev_key, normalized, entity_type)
            mention_to_cluster[mention_id] = normalized
            mention_to_method[mention_id] = ("label_cluster", 1.0)
            mention_to_type[mention_id] = entity_type
            cluster_to_mentions.setdefault(normalized, []).append(mention_id)
            continue

        normalized_length = len(normalized)
        fuzzy_target: str | None = None
        fuzzy_score: float = 0.0
        for existing in seen_texts_by_type.get(entity_type, []):
            existing_length = len(existing)
            if existing_length == 0 and normalized_length == 0:
                fuzzy_target = existing
                fuzzy_score = 1.0
                break
            if existing_length == 0 or normalized_length == 0:
                continue
            min_len = min(normalized_length, existing_length)
            max_len = max(normalized_length, existing_length)
            if 2 * min_len / (min_len + max_len) < fuzzy_threshold:
                continue
            ratio = _fuzzy_ratio(normalized, existing)
            if ratio >= fuzzy_threshold:
                fuzzy_target = existing
                fuzzy_score = ratio
                break
        if fuzzy_target is not None:
            mention_to_cluster[mention_id] = fuzzy_target
            mention_to_method[mention_id] = ("fuzzy", fuzzy_score)
            mention_to_type[mention_id] = entity_type
            cluster_to_mentions.setdefault(fuzzy_target, []).append(mention_id)
            continue

        _register_new_cluster(normalized, entity_type)
        mention_to_cluster[mention_id] = normalized
        mention_to_method[mention_id] = ("label_cluster", 1.0)
        mention_to_type[mention_id] = entity_type
        cluster_to_mentions.setdefault(normalized, []).append(mention_id)

    return [
        {
            "mention_id": mention["mention_id"],
            "mention_name": (mention.get("name") or "").strip(),
            "normalized_text": mention_to_cluster[mention["mention_id"]],
            "entity_type": mention_to_type[mention["mention_id"]],
            "source_uri": mention.get("source_uri") or None,
            "resolution_method": mention_to_method[mention["mention_id"]][0],
            "resolution_confidence": mention_to_method[mention["mention_id"]][1],
            "resolved": False,
        }
        for mention in mentions
    ]


__all__ = [
    "_FUZZY_REVIEW_THRESHOLD",
    "_cluster_mentions_unstructured_only",
    "_compute_initials",
    "_fuzzy_ratio",
    "_is_abbreviation",
    "_make_cluster_id",
    "_membership_score",
    "_membership_status",
]
