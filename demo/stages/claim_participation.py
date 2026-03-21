"""Claim participation edge matching.

Matches :ExtractedClaim subject/object text to :EntityMention nodes
from the same chunk/run and writes :HAS_SUBJECT_MENTION / :HAS_OBJECT_MENTION edges.

Matching strategy (tried in priority order for each slot — most restrictive
first so that the recorded ``match_method`` reflects the minimum transformation
needed to find a unique match):

1. **raw_exact** — compare slot text and mention name after stripping
   leading/trailing whitespace only (no other transformation).  This is the
   highest-confidence match: the strings are textually identical as written.
2. **casefold_exact** — apply only ``str.casefold()`` after stripping to both
   sides; match on equality.  Catches purely case-different variants (e.g.
   ``"IBM"`` vs ``"ibm"``) without any Unicode normalization.
3. **normalized_exact** — apply full Unicode normalization (NFKD, diacritics
   removal, apostrophe/hyphen collapse, whitespace collapse, case-fold) to
   both the slot text and each mention name; match on equality.  Catches
   Unicode variant forms such as diacritics (``"Müller"`` → ``"muller"``) and
   typographic substitutions (``ß`` → ``ss``, em-dash → hyphen-minus).

For each slot, the first strategy that yields **exactly one** matching mention
is used and an edge row is emitted with ``match_method`` set to the strategy
name.  If a strategy yields zero matches the next strategy is tried.  If a
strategy yields **two or more** matches no edge is created for that slot
(ambiguity rule).  If no strategy finds a unique match no edge is created
(missing-mention rule).

Candidates are scoped strictly by ``(run_id, chunk_id)`` overlap — mentions
from a different run can never match a claim even if they share a ``chunk_id``
string, because ``chunk_id`` values are only unique within a run.

This keeps edge creation deterministic and auditable: every emitted edge
records *how* its mention was found, and no guesses are made when the
evidence is absent or contradictory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import neo4j

from demo.text_utils import normalize_mention_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Matching method labels written onto participation edges.
MATCH_METHOD_RAW_EXACT = "raw_exact"
MATCH_METHOD_CASEFOLD_EXACT = "casefold_exact"
MATCH_METHOD_NORMALIZED_EXACT = "normalized_exact"

#: Neo4j relationship type for subject slot edges.
EDGE_TYPE_HAS_SUBJECT = "HAS_SUBJECT_MENTION"
#: Neo4j relationship type for object slot edges.
EDGE_TYPE_HAS_OBJECT = "HAS_OBJECT_MENTION"

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

    Strategies are tried in priority order from most restrictive to least
    restrictive.  The first strategy that yields **exactly one** match is used.
    A strategy that yields two or more matches is treated as ambiguous and
    causes an immediate ``(None, None)`` return (no edge created).

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

    # Build (mention, stripped_name) pairs once; used by all three strategies.
    # None names are treated as empty string to avoid surprising "None" string matches.
    raw_forms: list[tuple[dict[str, Any], str]] = []
    for m in mentions:
        name = m.get("name")
        raw_forms.append((m, "" if name is None else str(name).strip()))

    # Strategy 1: raw_exact — most restrictive, highest confidence.
    # Only strip whitespace; no other transformation.
    raw_matches = [m for m, raw in raw_forms if raw == slot_stripped]
    if len(raw_matches) == 1:
        return raw_matches[0], MATCH_METHOD_RAW_EXACT
    if len(raw_matches) > 1:
        # Ambiguous — do not create an edge
        return None, None

    # Strategy 2: casefold_exact — computed lazily only when raw_exact finds 0 matches.
    slot_cf = slot_stripped.casefold()
    cf_matches = [m for m, raw in raw_forms if raw.casefold() == slot_cf]
    if len(cf_matches) == 1:
        return cf_matches[0], MATCH_METHOD_CASEFOLD_EXACT
    if len(cf_matches) > 1:
        return None, None

    # Strategy 3: normalized_exact — normalize_mention_text called lazily only when both
    # raw_exact and casefold_exact find 0 matches.  Pre-compute all mention normal forms
    # here (rather than inside the list comprehension) so the function is called once per
    # mention rather than once per mention per iteration.
    slot_norm = normalize_mention_text(slot_stripped)
    norm_forms = [(m, normalize_mention_text(raw)) for m, raw in raw_forms]
    norm_matches = [m for m, norm in norm_forms if norm == slot_norm]
    if len(norm_matches) == 1:
        return norm_matches[0], MATCH_METHOD_NORMALIZED_EXACT
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
    that share at least one ``chunk_id`` **and** the same ``run_id``, then
    attempts to match the claim's ``subject`` and ``object`` property texts.
    Edges are emitted only when matching is unambiguous.

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
    # Index mentions by (run_id, chunk_id) for O(1) scoped lookup.
    # Scoping by run_id prevents cross-run contamination: chunk_id values are
    # only unique within a single run (see extraction_utils.py write logic).
    mentions_by_run_chunk: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for mention_row in mention_rows:
        m_run_id = mention_row.get("run_id", "")
        for cid in (mention_row.get("chunk_ids") or []):
            key = (m_run_id, cid)
            mentions_by_run_chunk.setdefault(key, []).append(mention_row)

    edge_rows: list[dict[str, Any]] = []

    for claim_row in claim_rows:
        claim_chunk_ids: list[str] = claim_row.get("chunk_ids") or []
        if not claim_chunk_ids:
            continue

        claim_id: str = claim_row.get("claim_id", "")
        run_id: str = claim_row.get("run_id", "")
        source_uri: str | None = claim_row.get("source_uri")
        props: dict[str, Any] = claim_row.get("properties", {})

        # Collect candidate mentions: any mention sharing at least one
        # (run_id, chunk_id) pair with this claim.  Deduplicate by mention_id.
        seen_mention_ids: set[str] = set()
        candidate_mentions: list[dict[str, Any]] = []
        for cid in claim_chunk_ids:
            for m in mentions_by_run_chunk.get((run_id, cid), []):
                mid = m.get("mention_id", "")
                if mid not in seen_mention_ids:
                    seen_mention_ids.add(mid)
                    candidate_mentions.append(m)

        if not candidate_mentions:
            continue

        # Flatten candidate mentions into dicts with a "name" key for the
        # matching function, carrying mention_id for result identification.
        # Computed once per claim (shared across subject and object slots).
        flat_mentions = [
            {
                "mention_id": m.get("mention_id", ""),
                "name": m.get("properties", {}).get("name", ""),
            }
            for m in candidate_mentions
        ]

        for slot in ("subject", "object"):
            slot_text = props.get(slot)
            if not slot_text:
                continue

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
    """Write :HAS_SUBJECT_MENTION and :HAS_OBJECT_MENTION edges to Neo4j.

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
            MERGE (claim)-[r:HAS_SUBJECT_MENTION]->(mention)
            SET r.run_id = row.run_id,
                r.source_uri = coalesce(row.source_uri, r.source_uri),
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
            MERGE (claim)-[r:HAS_OBJECT_MENTION]->(mention)
            SET r.run_id = row.run_id,
                r.source_uri = coalesce(row.source_uri, r.source_uri),
                r.match_method = row.match_method
            """,
            parameters_={"rows": object_rows},
            database_=neo4j_database,
        )


__all__ = [
    "MATCH_METHOD_RAW_EXACT",
    "MATCH_METHOD_CASEFOLD_EXACT",
    "MATCH_METHOD_NORMALIZED_EXACT",
    "EDGE_TYPE_HAS_SUBJECT",
    "EDGE_TYPE_HAS_OBJECT",
    "match_slot_to_mention",
    "build_participation_edges",
    "write_participation_edges",
    "run_claim_participation",
]


# ---------------------------------------------------------------------------
# Pipeline stage entry point
# ---------------------------------------------------------------------------


def run_claim_participation(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
) -> dict[str, Any]:
    """Build and persist :HAS_SUBJECT_MENTION / :HAS_OBJECT_MENTION edges for a claim extraction run.

    Reads :ExtractedClaim and :EntityMention nodes for *run_id* from Neo4j,
    runs the slot→mention matching logic, and writes the resulting participation
    edges back to the graph via MERGE (idempotent).

    Parameters
    ----------
    config:
        :class:`~demo.contracts.runtime.Config` instance with ``neo4j_uri``,
        ``neo4j_username``, ``neo4j_password``, ``neo4j_database``,
        ``output_dir``, and ``dry_run`` attributes.
    run_id:
        The run whose claims and mentions should be linked.  Must match the
        ``run_id`` used during the preceding claim extraction stage.
    source_uri:
        Provenance URI for the source document.

    Returns
    -------
    A summary dict with ``status``, ``run_id``, ``edges_written``,
    ``subject_edges``, ``object_edges``, and ``warnings``.
    """
    # Validate run_id to prevent path traversal outside the runs directory.
    # Mirrors the same check used in run_entity_resolution.
    runs_root = (config.output_dir / "runs").resolve()
    run_id_path = Path(run_id)
    if run_id_path.is_absolute() or ".." in run_id_path.parts or run_id_path.name != run_id:
        raise ValueError(
            f"Invalid run_id {run_id!r}: must be a simple relative name without path separators or '..'."
        )
    run_root = (runs_root / run_id_path).resolve()
    if run_root == runs_root or runs_root not in run_root.parents:
        raise ValueError(
            f"Invalid run_id {run_id!r}: must resolve to a subdirectory of the runs directory."
        )

    participation_dir = run_root / "claim_participation"
    participation_dir.mkdir(parents=True, exist_ok=True)
    summary_path = participation_dir / "claim_participation_summary.json"

    if config.dry_run:
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "edges_written": 0,
            "subject_edges": 0,
            "object_edges": 0,
            "warnings": ["claim participation skipped in dry_run mode"],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    driver = neo4j.GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_username, config.neo4j_password),
    )
    with driver:
        # 1. Read ExtractedClaim rows for this run.
        claim_result, _, _ = driver.execute_query(
            """
            MATCH (claim:ExtractedClaim {run_id: $run_id})
            OPTIONAL MATCH (claim)-[supported_by:SUPPORTED_BY]->()
            RETURN claim.claim_id AS claim_id,
                   claim.subject   AS subject,
                   claim.object    AS object,
                   claim.source_uri AS source_uri,
                   collect(DISTINCT supported_by.chunk_id) AS chunk_ids
            ORDER BY claim.claim_id
            """,
            parameters_={"run_id": run_id},
            database_=config.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        claim_rows = [
            {
                "claim_id": r["claim_id"],
                "chunk_ids": [cid for cid in (r["chunk_ids"] or []) if cid is not None],
                "run_id": run_id,
                "source_uri": r["source_uri"] if r["source_uri"] not in (None, "") else source_uri,
                "properties": {
                    k: v
                    for k, v in (("subject", r["subject"]), ("object", r["object"]))
                    if v is not None
                },
            }
            for r in claim_result
        ]

        # 2. Read EntityMention rows for this run.
        mention_result, _, _ = driver.execute_query(
            """
            MATCH (mention:EntityMention {run_id: $run_id})
            OPTIONAL MATCH (mention)-[mentioned_in:MENTIONED_IN]->()
            RETURN mention.mention_id AS mention_id,
                   mention.name       AS name,
                   mention.source_uri AS source_uri,
                   collect(DISTINCT mentioned_in.chunk_id) AS chunk_ids
            ORDER BY mention.mention_id
            """,
            parameters_={"run_id": run_id},
            database_=config.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        mention_rows = [
            {
                "mention_id": r["mention_id"],
                "chunk_ids": [cid for cid in (r["chunk_ids"] or []) if cid is not None],
                "run_id": run_id,
                "source_uri": r["source_uri"] if r["source_uri"] not in (None, "") else source_uri,
                "properties": {"name": r["name"] or ""},
            }
            for r in mention_result
        ]

        # 3. Build and persist participation edges.
        edge_rows = build_participation_edges(claim_rows, mention_rows)
        write_participation_edges(driver, neo4j_database=config.neo4j_database, edge_rows=edge_rows)

    subject_edges = sum(1 for e in edge_rows if e["edge_type"] == EDGE_TYPE_HAS_SUBJECT)
    object_edges = sum(1 for e in edge_rows if e["edge_type"] == EDGE_TYPE_HAS_OBJECT)
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "claims_read": len(claim_rows),
        "mentions_read": len(mention_rows),
        "edges_written": len(edge_rows),
        "subject_edges": subject_edges,
        "object_edges": object_edges,
        "warnings": [],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

