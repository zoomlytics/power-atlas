from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from typing import Any

from power_atlas.text_utils import normalize_mention_text

MATCH_METHOD_RAW_EXACT = "raw_exact"
MATCH_METHOD_CASEFOLD_EXACT = "casefold_exact"
MATCH_METHOD_NORMALIZED_EXACT = "normalized_exact"
MATCH_METHOD_LIST_SPLIT = "list_split"

MATCH_OUTCOME_AMBIGUOUS = "ambiguous"
_MATCH_OUTCOME_AMBIGUOUS = MATCH_OUTCOME_AMBIGUOUS

EDGE_TYPE_HAS_PARTICIPANT = "HAS_PARTICIPANT"

ROLE_SUBJECT = "subject"
ROLE_OBJECT = "object"

_SLOT_ROLE: dict[str, str] = {
    "subject": ROLE_SUBJECT,
    "object": ROLE_OBJECT,
}

_LIST_SPLIT_RE = re.compile(r",?\s+(?:and|or|&)\s+|,\s+|\s+/\s+|;\s+", re.IGNORECASE)


def split_slot_text(slot_text: str) -> list[str]:
    parts = _LIST_SPLIT_RE.split(slot_text.strip())
    stripped = [s for p in parts if (s := p.strip())]
    return stripped if len(stripped) >= 2 else []


def match_slot_to_mention(
    slot_text: str,
    mentions: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if not slot_text or not mentions:
        return None, None

    slot_stripped = slot_text.strip()
    if not slot_stripped:
        return None, None

    raw_forms: list[tuple[dict[str, Any], str]] = []
    for mention in mentions:
        name = mention.get("name")
        raw_forms.append((mention, "" if name is None else str(name).strip()))

    raw_matches = [mention for mention, raw in raw_forms if raw == slot_stripped]
    if len(raw_matches) == 1:
        return raw_matches[0], MATCH_METHOD_RAW_EXACT
    if len(raw_matches) > 1:
        return None, MATCH_OUTCOME_AMBIGUOUS

    slot_casefold = slot_stripped.casefold()
    casefold_matches = [mention for mention, raw in raw_forms if raw.casefold() == slot_casefold]
    if len(casefold_matches) == 1:
        return casefold_matches[0], MATCH_METHOD_CASEFOLD_EXACT
    if len(casefold_matches) > 1:
        return None, MATCH_OUTCOME_AMBIGUOUS

    slot_normalized = normalize_mention_text(slot_stripped)
    normalized_forms = [(mention, normalize_mention_text(raw)) for mention, raw in raw_forms]
    normalized_matches = [mention for mention, normalized in normalized_forms if normalized == slot_normalized]
    if len(normalized_matches) == 1:
        return normalized_matches[0], MATCH_METHOD_NORMALIZED_EXACT
    if len(normalized_matches) > 1:
        return None, MATCH_OUTCOME_AMBIGUOUS
    return None, None


_METRICS_SAMPLE_SIZE = 20


@dataclasses.dataclass
class ParticipationMatchMetrics:
    claims_processed: int
    slots_processed: int
    edges_by_method: dict[str, int]
    edges_by_role: dict[str, int]
    edges_by_role_and_method: dict[str, dict[str, int]]
    unmatched_slots: int
    unmatched_by_role: dict[str, int]
    ambiguous_slots: int
    ambiguous_by_role: dict[str, int]
    list_split_suppressed: int
    list_split_suppressed_by_role: dict[str, int]
    list_split_full_success: int
    list_split_partial_success: int
    list_split_no_success: int
    list_split_total_parts: int
    list_split_matched_parts: int
    list_split_unmatched_parts: int
    claims_with_any_edge: int
    claims_with_no_edges: int
    sample_list_split_claim_ids: list[str]
    sample_list_split_partial_claim_ids: list[str]
    residual_list_split_partial: list[dict[str, Any]]
    sample_unmatched_claim_ids: list[str]
    sample_ambiguous_claim_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)



def build_participation_edges(
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    edge_rows, _ = build_participation_edges_with_metrics(claim_rows, mention_rows)
    return edge_rows



def build_participation_edges_with_metrics(
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], ParticipationMatchMetrics]:
    mentions_by_run_chunk: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for mention_row in mention_rows:
        mention_run_id = mention_row.get("run_id", "")
        for chunk_id in (mention_row.get("chunk_ids") or []):
            key = (mention_run_id, chunk_id)
            mentions_by_run_chunk.setdefault(key, []).append(mention_row)

    edge_rows: list[dict[str, Any]] = []

    edges_by_method: dict[str, int] = defaultdict(int)
    edges_by_role: dict[str, int] = defaultdict(int)
    edges_by_role_and_method: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    unmatched_slots = 0
    unmatched_by_role: dict[str, int] = defaultdict(int)
    ambiguous_slots = 0
    ambiguous_by_role: dict[str, int] = defaultdict(int)
    list_split_suppressed = 0
    list_split_suppressed_by_role: dict[str, int] = defaultdict(int)
    claims_with_edge_set: set[str] = set()
    slots_processed = 0

    list_split_full_success = 0
    list_split_partial_success = 0
    list_split_no_success = 0
    list_split_total_parts = 0
    list_split_matched_parts = 0
    list_split_unmatched_parts = 0

    sample_list_split: list[str] = []
    sample_list_split_seen: set[str] = set()
    sample_list_split_partial: list[str] = []
    sample_list_split_partial_seen: set[str] = set()
    residual_list_split_partial: list[dict[str, Any]] = []
    sample_unmatched: list[str] = []
    sample_unmatched_seen: set[str] = set()
    sample_ambiguous: list[str] = []
    sample_ambiguous_seen: set[str] = set()

    def add_sample(bucket: list[str], seen: set[str], claim_id: str) -> None:
        if len(bucket) < _METRICS_SAMPLE_SIZE and claim_id not in seen:
            seen.add(claim_id)
            bucket.append(claim_id)

    for claim_row in claim_rows:
        claim_chunk_ids: list[str] = claim_row.get("chunk_ids") or []
        if not claim_chunk_ids:
            continue

        claim_id: str = claim_row.get("claim_id", "")
        run_id: str = claim_row.get("run_id", "")
        source_uri: str | None = claim_row.get("source_uri")
        properties: dict[str, Any] = claim_row.get("properties", {})

        seen_mention_ids: set[str] = set()
        candidate_mentions: list[dict[str, Any]] = []
        for chunk_id in claim_chunk_ids:
            for mention in mentions_by_run_chunk.get((run_id, chunk_id), []):
                mention_id = mention.get("mention_id", "")
                if mention_id not in seen_mention_ids:
                    seen_mention_ids.add(mention_id)
                    candidate_mentions.append(mention)

        if not candidate_mentions:
            continue

        flat_mentions = [
            {
                "mention_id": mention.get("mention_id", ""),
                "name": mention.get("properties", {}).get("name", ""),
            }
            for mention in candidate_mentions
        ]

        edges_before_claim = len(edge_rows)

        for slot in ("subject", "object"):
            slot_text = properties.get(slot)
            if not slot_text:
                continue

            slot_str = str(slot_text).strip()
            if not slot_str:
                continue
            seen_for_slot: set[str] = set()
            role = _SLOT_ROLE[slot]
            slots_processed += 1

            matched, method = match_slot_to_mention(slot_str, flat_mentions)
            if matched is not None:
                edge_rows.append(
                    {
                        "claim_id": claim_id,
                        "mention_id": matched["mention_id"],
                        "run_id": run_id,
                        "source_uri": source_uri,
                        "slot": slot,
                        "role": role,
                        "match_method": method,
                        "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
                    }
                )
                assert method is not None
                edges_by_method[method] += 1
                edges_by_role[role] += 1
                edges_by_role_and_method[role][method] += 1
                continue

            if method is not None:
                ambiguous_slots += 1
                ambiguous_by_role[role] += 1
                list_split_suppressed += 1
                list_split_suppressed_by_role[role] += 1
                add_sample(sample_ambiguous, sample_ambiguous_seen, claim_id)
                continue

            list_split_parts = split_slot_text(slot_str)
            slot_part_total = len(list_split_parts)
            slot_part_matched = 0
            matched_part_texts: list[str] = []
            unmatched_part_texts: list[str] = []
            for part in list_split_parts:
                part_matched, _part_method = match_slot_to_mention(part, flat_mentions)
                if part_matched is None:
                    unmatched_part_texts.append(part)
                    continue
                matched_part_texts.append(part)
                slot_part_matched += 1
                mention_id = part_matched["mention_id"]
                if mention_id in seen_for_slot:
                    continue
                seen_for_slot.add(mention_id)
                edge_rows.append(
                    {
                        "claim_id": claim_id,
                        "mention_id": mention_id,
                        "run_id": run_id,
                        "source_uri": source_uri,
                        "slot": slot,
                        "role": role,
                        "match_method": MATCH_METHOD_LIST_SPLIT,
                        "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
                    }
                )
                edges_by_method[MATCH_METHOD_LIST_SPLIT] += 1
                edges_by_role[role] += 1
                edges_by_role_and_method[role][MATCH_METHOD_LIST_SPLIT] += 1
                add_sample(sample_list_split, sample_list_split_seen, claim_id)

            list_split_total_parts += slot_part_total
            list_split_matched_parts += slot_part_matched
            list_split_unmatched_parts += slot_part_total - slot_part_matched

            if slot_part_total >= 2:
                if slot_part_matched == slot_part_total:
                    list_split_full_success += 1
                elif slot_part_matched > 0:
                    list_split_partial_success += 1
                    add_sample(
                        sample_list_split_partial,
                        sample_list_split_partial_seen,
                        claim_id,
                    )
                    if len(residual_list_split_partial) < _METRICS_SAMPLE_SIZE:
                        residual_list_split_partial.append(
                            {
                                "claim_id": claim_id,
                                "slot": slot,
                                "slot_text": slot_str,
                                "parts": list(list_split_parts),
                                "matched_parts": matched_part_texts,
                                "unmatched_parts": unmatched_part_texts,
                            }
                        )
                else:
                    list_split_no_success += 1

            if slot_part_matched == 0:
                unmatched_slots += 1
                unmatched_by_role[role] += 1
                add_sample(sample_unmatched, sample_unmatched_seen, claim_id)

        if len(edge_rows) > edges_before_claim:
            claims_with_edge_set.add(claim_id)

    claims_processed = len(claim_rows)
    claims_with_any_edge = len(claims_with_edge_set)

    metrics = ParticipationMatchMetrics(
        claims_processed=claims_processed,
        slots_processed=slots_processed,
        edges_by_method=dict(edges_by_method),
        edges_by_role=dict(edges_by_role),
        edges_by_role_and_method={role: dict(methods) for role, methods in edges_by_role_and_method.items()},
        unmatched_slots=unmatched_slots,
        unmatched_by_role=dict(unmatched_by_role),
        ambiguous_slots=ambiguous_slots,
        ambiguous_by_role=dict(ambiguous_by_role),
        list_split_suppressed=list_split_suppressed,
        list_split_suppressed_by_role=dict(list_split_suppressed_by_role),
        list_split_full_success=list_split_full_success,
        list_split_partial_success=list_split_partial_success,
        list_split_no_success=list_split_no_success,
        list_split_total_parts=list_split_total_parts,
        list_split_matched_parts=list_split_matched_parts,
        list_split_unmatched_parts=list_split_unmatched_parts,
        claims_with_any_edge=claims_with_any_edge,
        claims_with_no_edges=claims_processed - claims_with_any_edge,
        sample_list_split_claim_ids=sample_list_split,
        sample_list_split_partial_claim_ids=sample_list_split_partial,
        residual_list_split_partial=residual_list_split_partial,
        sample_unmatched_claim_ids=sample_unmatched,
        sample_ambiguous_claim_ids=sample_ambiguous,
    )
    return edge_rows, metrics


__all__ = [
    "MATCH_METHOD_RAW_EXACT",
    "MATCH_METHOD_CASEFOLD_EXACT",
    "MATCH_METHOD_NORMALIZED_EXACT",
    "MATCH_METHOD_LIST_SPLIT",
    "MATCH_OUTCOME_AMBIGUOUS",
    "EDGE_TYPE_HAS_PARTICIPANT",
    "ROLE_SUBJECT",
    "ROLE_OBJECT",
    "ParticipationMatchMetrics",
    "split_slot_text",
    "match_slot_to_mention",
    "build_participation_edges",
    "build_participation_edges_with_metrics",
]
