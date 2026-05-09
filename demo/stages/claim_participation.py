"""Claim participation edge matching.

Matches :ExtractedClaim subject/object text to :EntityMention nodes
from the same chunk/run and writes :HAS_PARTICIPANT edges with a ``role``
property (v0.3 model).

**v0.3 edge model** — a single :HAS_PARTICIPANT relationship type replaces
the v0.2 :HAS_SUBJECT_MENTION / :HAS_OBJECT_MENTION dual-edge model.  The
semantic role of each argument is stored as a ``role`` property on the edge
(e.g. ``"subject"``, ``"object"``), allowing future roles (agent, location,
value, etc.) to be introduced without schema changes.  See
``docs/architecture/claim-argument-model-v0.3.md`` for the full decision record.

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
4. **list_split** — when all three strategies above yield no match *and* the
   slot text contains conjunction/list separators such as ``" and "``, ``" or "``,
   ``" & "``, ``", "``, ``" / "`` (slash with surrounding whitespace), or
   ``"; "`` (semicolon followed by whitespace), the slot is split into its
   constituent parts and each part is matched independently using strategies
   1–3.  One :HAS_PARTICIPANT edge is emitted per successfully matched part
   (duplicate mention_ids are deduplicated within the same slot).  This covers
   composite argument spans such as ``"Amazon and eBay"`` (two entities),
   ``"Amazon / eBay / Google"`` (slash-delimited list), or
   ``"Amazon; eBay; Google"`` (semicolon-delimited list).

   **Qualified composite forms with no special parsing** — ``list_split``
   only performs deterministic splitting on separators; it does not attempt
   to strip or interpret qualifiers.  All split parts are still matched
   independently, but qualifier-bearing phrases generally fail to match:

   - *Parenthetical qualifiers* — ``"Amazon (AWS) and Google"``: the part
     ``"Amazon (AWS)"`` is not reduced to a plain ``"Amazon"`` mention, so
     matching is attempted only against the full phrase and typically fails.
     The other parts (e.g. ``"Google"``) are still matched normally.
   - *Grouped qualifiers* — ``"Amazon and eBay subsidiaries"``: ``"eBay
     subsidiaries"`` is not simplified to plain ``"eBay"``; only the
     unqualified part (``"Amazon"``) can be recovered.
   - *Appositives* — ``"Xapo, a digital-assets company"``: the appositive
     phrase ``"a digital-assets company"`` is tried and fails to match; only
     the entity name (``"Xapo"``) creates an edge via comma splitting.
   - *Nested qualifiers* — ``"Amazon, eBay, and Google subsidiaries"``:
     ``"Google subsidiaries"`` is tried and fails to match; ``"Amazon"`` and
     ``"eBay"`` are recovered normally.

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

from typing import Any

import neo4j

from power_atlas.claim_participation_edges import (
    EDGE_TYPE_HAS_PARTICIPANT,
    MATCH_METHOD_CASEFOLD_EXACT,
    MATCH_METHOD_LIST_SPLIT,
    MATCH_METHOD_NORMALIZED_EXACT,
    MATCH_METHOD_RAW_EXACT,
    MATCH_OUTCOME_AMBIGUOUS,
    ROLE_OBJECT,
    ROLE_SUBJECT,
    ParticipationMatchMetrics,
    _METRICS_SAMPLE_SIZE,
    build_participation_edges,
    build_participation_edges_with_metrics,
    match_slot_to_mention,
    split_slot_text,
)
from power_atlas.claim_participation_runner import (
    neo4j_settings_from_config as _neo4j_settings_from_config_impl,
)
from power_atlas.claim_participation_runner import (
    run_claim_participation_request_context as _run_claim_participation_request_context_impl,
)
from power_atlas.claim_participation_runner import (
    write_participation_edges as _write_participation_edges_impl,
)
from power_atlas.context import RequestContext
from power_atlas.settings import Neo4jSettings

# Private alias kept for backwards compatibility.
_MATCH_OUTCOME_AMBIGUOUS = MATCH_OUTCOME_AMBIGUOUS


def _neo4j_settings_from_config(config: object) -> Neo4jSettings:
    return _neo4j_settings_from_config_impl(config)

# The pure matching helpers are package-owned and re-exported from this stage
# to preserve the existing demo import surface for tests and callers.


# ---------------------------------------------------------------------------
# Neo4j writer
# ---------------------------------------------------------------------------


def write_participation_edges(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    edge_rows: list[dict[str, Any]],
) -> None:
    """Write :HAS_PARTICIPANT edges to Neo4j (v0.3 model).

    Uses MERGE so that re-running the stage is idempotent.  The ``role``
    property (``"subject"``, ``"object"``, etc.) is part of the MERGE key,
    so a claim with both a subject and an object argument gets two distinct
    edges.  Only edges whose claim/mention nodes already exist in the graph
    are written (the MATCH clauses ensure this without raising an error for
    missing nodes).

    See ``docs/architecture/claim-argument-model-v0.3.md`` for the decision
    record explaining the migration from v0.2 dual-edge types.

    Parameters
    ----------
    driver:
        An open :class:`neo4j.Driver` instance.
    neo4j_database:
        Neo4j database name (e.g. ``"neo4j"``).
    edge_rows:
        Edge rows returned by :func:`build_participation_edges`.
    """
    _write_participation_edges_impl(
        driver,
        neo4j_database=neo4j_database,
        edge_rows=edge_rows,
    )

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
    "write_participation_edges",
    "run_claim_participation_request_context",
]


# ---------------------------------------------------------------------------
# Pipeline stage entry point
# ---------------------------------------------------------------------------


def run_claim_participation_request_context(request_context: RequestContext) -> dict[str, Any]:
    return _run_claim_participation_request_context_impl(request_context)

