"""Claim participation edge matching.

Matches :ExtractedClaim subject/object text to :EntityMention nodes
from the same chunk and writes :HAS_SUBJECT / :HAS_OBJECT edges.

Matching strategy (tried in priority order for each slot):

1. **normalized_exact** — apply full Unicode normalization (NFKD, diacritics
   removal, apostrophe/hyphen collapse, whitespace collapse, case-fold) to
   both the slot text and each mention name; match on equality.
2. **raw_exact** — compare slot text and mention name after stripping
   leading/trailing whitespace only (no other transformation).
3. **casefold_exact** — apply only ``str.casefold()`` after stripping to both
   sides; match on equality.

For each slot, the first strategy that yields **exactly one** matching mention
is used and an edge row is emitted with ``match_method`` set to the strategy
name.  If a strategy yields zero matches the next strategy is tried.  If a
strategy yields **two or more** matches no edge is created for that slot
(ambiguity rule).  If no strategy finds a unique match no edge is created
(missing-mention rule).

This keeps edge creation deterministic and auditable: every emitted edge
records *how* its mention was found, and no guesses are made when the
evidence is absent or contradictory.
"""
from __future__ import annotations

from typing import Any

import neo4j

from demo.stages.entity_resolution import _normalize

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Matching method labels written onto participation edges.
MATCH_METHOD_NORMALIZED_EXACT = "normalized_exact"
MATCH_METHOD_RAW_EXACT = "raw_exact"
MATCH_METHOD_CASEFOLD_EXACT = "casefold_exact"

#: Neo4j relationship type for subject slot edges.
EDGE_TYPE_HAS_SUBJECT = "HAS_SUBJECT"
#: Neo4j relationship type for object slot edges.
EDGE_TYPE_HAS_OBJECT = "HAS_OBJECT"

# Slot name → edge type
_SLOT_EDGE_TYPE: dict[str, str] = {
    "subject": EDGE_TYPE_HAS_SUBJECT,
    "object": EDGE_TYPE_HAS_OBJECT,
}

# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------


def match_slot_to_mention(
    slot_text: str,
    mentions: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Match *slot_text* to at most one mention from *mentions*.

    Parameters
    ----------
    slot_text:
        The raw text of a claim's subject or object slot.
    mentions:
        Mention rows (each having at minimum a ``"name"`` key) that are
        eligible candidates — typically all mentions from the same chunk as
        the claim.

    Returns
    -------
    ``(mention_row, match_method)`` when exactly one candidate matches, or
    ``(None, None)`` when there is no match or when two or more candidates
    match (ambiguity).
    """
    if not slot_text or not mentions:
        return None, None

    slot_stripped = slot_text.strip()
    if not slot_stripped:
        return None, None

    # Pre-compute all derived forms for each mention once to avoid redundant work
    # across the three matching strategies.
    mention_forms: list[tuple[dict[str, Any], str, str, str]] = []
    for m in mentions:
        raw = str(m.get("name", "")).strip()
        mention_forms.append((m, raw, _normalize(raw), raw.casefold()))

    # Strategy 1: normalized_exact
    slot_norm = _normalize(slot_stripped)
    norm_matches = [m for m, _raw, norm, _cf in mention_forms if norm == slot_norm]
    if len(norm_matches) == 1:
        return norm_matches[0], MATCH_METHOD_NORMALIZED_EXACT
    if len(norm_matches) > 1:
        # Ambiguous — do not create an edge
        return None, None

    # Strategy 2: raw_exact
    raw_matches = [m for m, raw, _norm, _cf in mention_forms if raw == slot_stripped]
    if len(raw_matches) == 1:
        return raw_matches[0], MATCH_METHOD_RAW_EXACT
    if len(raw_matches) > 1:
        return None, None

    # Strategy 3: casefold_exact
    slot_cf = slot_stripped.casefold()
    cf_matches = [m for m, _raw, _norm, cf in mention_forms if cf == slot_cf]
    if len(cf_matches) == 1:
        return cf_matches[0], MATCH_METHOD_CASEFOLD_EXACT
    # Zero or >1 matches — no edge
    return None, None


# ---------------------------------------------------------------------------
# Edge row construction
# ---------------------------------------------------------------------------


def build_participation_edges(
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build participation edge rows for subject and object slots.

    For each :ExtractedClaim row the function looks up :EntityMention rows
    that share at least one ``chunk_id``, then attempts to match the claim's
    ``subject`` and ``object`` property texts.  Edges are emitted only when
    matching is unambiguous.

    Parameters
    ----------
    claim_rows:
        Rows produced by :func:`demo.extraction_utils.prepare_extracted_rows`
        for ``ExtractedClaim`` nodes.  Each row must have ``claim_id``,
        ``chunk_ids``, ``run_id``, ``source_uri``, and a ``properties``
        dict that may contain ``"subject"`` and/or ``"object"`` keys.
    mention_rows:
        Rows produced by :func:`demo.extraction_utils.prepare_extracted_rows`
        for ``EntityMention`` nodes.  Each row must have ``mention_id``,
        ``chunk_ids``, ``run_id``, and a ``properties`` dict with a
        ``"name"`` key.

    Returns
    -------
    A list of edge row dicts, each with keys:
    ``claim_id``, ``mention_id``, ``run_id``, ``source_uri``, ``slot``,
    ``match_method``, and ``edge_type``.
    """
    # Index mentions by each of their chunk_ids for O(1) lookup per chunk.
    mentions_by_chunk: dict[str, list[dict[str, Any]]] = {}
    for mention_row in mention_rows:
        for cid in mention_row.get("chunk_ids", []):
            mentions_by_chunk.setdefault(cid, []).append(mention_row)

    edge_rows: list[dict[str, Any]] = []

    for claim_row in claim_rows:
        claim_chunk_ids: list[str] = claim_row.get("chunk_ids", [])
        if not claim_chunk_ids:
            continue

        # Collect candidate mentions: any mention sharing at least one chunk_id
        # with this claim.  Deduplicate by mention_id to avoid double-counting
        # mentions that appear in multiple matching chunks.
        seen_mention_ids: set[str] = set()
        candidate_mentions: list[dict[str, Any]] = []
        for cid in claim_chunk_ids:
            for m in mentions_by_chunk.get(cid, []):
                mid = m.get("mention_id", "")
                if mid not in seen_mention_ids:
                    seen_mention_ids.add(mid)
                    candidate_mentions.append(m)

        if not candidate_mentions:
            continue

        claim_id: str = claim_row.get("claim_id", "")
        run_id: str = claim_row.get("run_id", "")
        source_uri: str | None = claim_row.get("source_uri")
        props: dict[str, Any] = claim_row.get("properties", {})

        for slot in ("subject", "object"):
            slot_text = props.get(slot)
            if not slot_text:
                continue

            # Flatten candidate mentions into dicts with a "name" key for the
            # matching function, carrying mention_id for result identification.
            flat_mentions = [
                {
                    "mention_id": m.get("mention_id", ""),
                    "name": m.get("properties", {}).get("name", ""),
                }
                for m in candidate_mentions
            ]

            matched, method = match_slot_to_mention(str(slot_text), flat_mentions)
            if matched is None:
                continue

            edge_rows.append(
                {
                    "claim_id": claim_id,
                    "mention_id": matched["mention_id"],
                    "run_id": run_id,
                    "source_uri": source_uri,
                    "slot": slot,
                    "match_method": method,
                    "edge_type": _SLOT_EDGE_TYPE[slot],
                }
            )

    return edge_rows


# ---------------------------------------------------------------------------
# Neo4j writer
# ---------------------------------------------------------------------------


def write_participation_edges(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    edge_rows: list[dict[str, Any]],
) -> None:
    """Write :HAS_SUBJECT and :HAS_OBJECT edges to Neo4j.

    Uses MERGE so that re-running the stage is idempotent.  Only edges that
    already have ``claim_id``/``mention_id`` nodes in the graph will be
    written (the MATCH clauses ensure this without raising an error for
    missing nodes).

    Parameters
    ----------
    driver:
        An open :class:`neo4j.Driver` instance.
    neo4j_database:
        Neo4j database name (e.g. ``"neo4j"``).
    edge_rows:
        Edge rows returned by :func:`build_participation_edges`.
    """
    subject_rows = [r for r in edge_rows if r["edge_type"] == EDGE_TYPE_HAS_SUBJECT]
    object_rows = [r for r in edge_rows if r["edge_type"] == EDGE_TYPE_HAS_OBJECT]

    if subject_rows:
        driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})
            MERGE (claim)-[r:HAS_SUBJECT]->(mention)
            SET r.run_id = row.run_id,
                r.source_uri = row.source_uri,
                r.match_method = row.match_method
            """,
            parameters_={"rows": subject_rows},
            database_=neo4j_database,
        )

    if object_rows:
        driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})
            MERGE (claim)-[r:HAS_OBJECT]->(mention)
            SET r.run_id = row.run_id,
                r.source_uri = row.source_uri,
                r.match_method = row.match_method
            """,
            parameters_={"rows": object_rows},
            database_=neo4j_database,
        )


__all__ = [
    "MATCH_METHOD_NORMALIZED_EXACT",
    "MATCH_METHOD_RAW_EXACT",
    "MATCH_METHOD_CASEFOLD_EXACT",
    "EDGE_TYPE_HAS_SUBJECT",
    "EDGE_TYPE_HAS_OBJECT",
    "match_slot_to_mention",
    "build_participation_edges",
    "write_participation_edges",
]
