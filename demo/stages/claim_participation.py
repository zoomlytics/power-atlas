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

import dataclasses
import json
import re
from collections import defaultdict
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
MATCH_METHOD_LIST_SPLIT = "list_split"

# Sentinel returned by match_slot_to_mention (as the method value) when
# two or more candidates match at any strategy level.  Callers that only check
# ``matched is None`` are unaffected; callers that need to distinguish "no
# candidates found" from "ambiguous" inspect ``method == MATCH_OUTCOME_AMBIGUOUS``.
MATCH_OUTCOME_AMBIGUOUS = "ambiguous"
# Private alias kept for backwards compatibility.
_MATCH_OUTCOME_AMBIGUOUS = MATCH_OUTCOME_AMBIGUOUS

#: v0.3 Neo4j relationship type for all claim argument edges.
#: Role is stored as the ``role`` property on the edge.
EDGE_TYPE_HAS_PARTICIPANT = "HAS_PARTICIPANT"

#: Role label for the subject argument slot.
ROLE_SUBJECT = "subject"
#: Role label for the object argument slot.
ROLE_OBJECT = "object"

# Slot name → role label (used to populate the ``role`` property on participation edges).
_SLOT_ROLE: dict[str, str] = {
    "subject": ROLE_SUBJECT,
    "object": ROLE_OBJECT,
}

# Matches conjunction/list separators used to split composite slot values.
# Conjunctions (and/or/&) require surrounding whitespace so that words
# containing these strings (e.g. "Anderson", "border") are not split.
# The optional leading comma (,?) in the first alternative handles Oxford-comma
# lists such as "A, B, and C": the ", and " is consumed as a single separator
# so the last token is correctly "C" rather than "and C".
# Plain comma-only separators (", ") are handled by the second alternative.
# Slash separators (" / ") require whitespace on both sides to avoid splitting
# URL paths or numeric ratios (e.g. "Q1/Q2").
# Semicolon separators ("; ") require at least one trailing space to avoid
# splitting abbreviations (e.g. "U.S.;").
_LIST_SPLIT_RE = re.compile(r",?\s+(?:and|or|&)\s+|,\s+|\s+/\s+|;\s+", re.IGNORECASE)

# ---------------------------------------------------------------------------
# List-splitting helper
# ---------------------------------------------------------------------------


def split_slot_text(slot_text: str) -> list[str]:
    """Split *slot_text* on conjunction and list separators.

    Splits on: ``" and "``, ``" or "``, ``" & "`` (surrounded by whitespace),
    ``", "`` (comma followed by at least one space),
    ``" / "`` (slash with at least one space on each side), and
    ``"; "`` (semicolon followed by at least one space).
    Oxford-comma lists such as ``"A, B, and C"`` are also handled — the
    ``", and "`` separator is consumed as a single token so the result is
    ``["A", "B", "C"]`` rather than ``["A", "B", "and C"]``.  The split is
    case-insensitive so ``"Amazon AND eBay"`` is handled the same as
    ``"Amazon and eBay"``.

    **Qualified composite forms with no special parsing** — splitting is still
    applied, but no qualifier stripping or interpretation is performed.  All
    resulting parts are tried for matching; qualifier-bearing phrases typically
    fail to match:

    - *Parenthetical qualifiers* — ``"Amazon (AWS) and Google"``: the part
      ``"Amazon (AWS)"`` is not reduced to ``"Amazon"``, so matching typically
      fails for that part.
    - *Grouped qualifiers* — ``"Amazon and eBay subsidiaries"``: the part
      ``"eBay subsidiaries"`` is not simplified to ``"eBay"``.
    - *Appositives* — ``"Xapo, a digital-assets company"``: only ``"Xapo"``
      recovers a mention; the appositive descriptor is tried and typically fails.
    - *Bare slash (no spaces)* — ``"Amazon/eBay"`` is **not** split (avoids
      URL paths and numeric ratios).
    - *Bare semicolon (no trailing space)* — ``"Inc.;Ltd."`` is **not** split.

    Parameters
    ----------
    slot_text:
        The raw text of a claim's subject or object slot.

    Returns
    -------
    A list of stripped, non-empty part strings when the split yields at least
    two non-empty parts; an empty list otherwise (signals "no actionable
    split").
    """
    parts = _LIST_SPLIT_RE.split(slot_text.strip())
    stripped = [s for p in parts if (s := p.strip())]
    return stripped if len(stripped) >= 2 else []

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
    causes an immediate return with ``(None, MATCH_OUTCOME_AMBIGUOUS)``
    (no edge created).

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
    ``(mention_row, match_method)`` when exactly one candidate matches.

    ``(None, None)`` when *no* candidate matches at any strategy level (zero
    matches throughout — safe to attempt a list-split fallback).

    ``(None, MATCH_OUTCOME_AMBIGUOUS)`` when two or more candidates match at
    some strategy level (ambiguity — do **not** attempt a list-split fallback).
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
        # Ambiguous — do not create an edge, and do not attempt list-split.
        return None, MATCH_OUTCOME_AMBIGUOUS

    # Strategy 2: casefold_exact — computed lazily only when raw_exact finds 0 matches.
    slot_cf = slot_stripped.casefold()
    cf_matches = [m for m, raw in raw_forms if raw.casefold() == slot_cf]
    if len(cf_matches) == 1:
        return cf_matches[0], MATCH_METHOD_CASEFOLD_EXACT
    if len(cf_matches) > 1:
        return None, MATCH_OUTCOME_AMBIGUOUS

    # Strategy 3: normalized_exact — normalize_mention_text called lazily only when both
    # raw_exact and casefold_exact find 0 matches.  Pre-compute all mention normal forms
    # here (rather than inside the list comprehension) so the function is called once per
    # mention rather than once per mention per iteration.
    slot_norm = normalize_mention_text(slot_stripped)
    norm_forms = [(m, normalize_mention_text(raw)) for m, raw in raw_forms]
    norm_matches = [m for m, norm in norm_forms if norm == slot_norm]
    if len(norm_matches) == 1:
        return norm_matches[0], MATCH_METHOD_NORMALIZED_EXACT
    if len(norm_matches) > 1:
        return None, MATCH_OUTCOME_AMBIGUOUS
    # Zero matches across all strategies — no edge, but list-split may be tried.
    return None, None


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------

#: Maximum number of representative claim IDs collected per outcome class in
#: :class:`ParticipationMatchMetrics` samples.  Kept small to bound artifact
#: size while still providing concrete examples for auditing.
_METRICS_SAMPLE_SIZE = 20


@dataclasses.dataclass
class ParticipationMatchMetrics:
    """Per-run instrumentation for participation edge matching outcomes.

    Produced by :func:`build_participation_edges_with_metrics` and written as
    ``participation_metrics.json`` by :func:`run_claim_participation`.

    All counts are for a single call (i.e. a single pipeline run).

    Attributes
    ----------
    claims_processed:
        Number of claim rows supplied to the matcher (includes rows with no
        candidate mentions — those never enter the slot loop).
    slots_processed:
        Total (claim, slot) pairs where the slot text was non-empty and at
        least one candidate mention was available.
    edges_by_method:
        Edge count keyed by ``match_method``
        (``raw_exact`` / ``casefold_exact`` / ``normalized_exact`` /
        ``list_split``).  Each emitted edge is counted once.
    edges_by_role:
        Edge count keyed by role (``"subject"`` / ``"object"``).
    edges_by_role_and_method:
        Two-level breakdown: ``{role: {match_method: count}}``.
    unmatched_slots:
        Slots that produced no edge and whose whole-slot attempt returned zero
        candidates (``method is None``).  Includes slots where
        :func:`split_slot_text` found no separator *and* slots where all
        list-split parts also failed to match.
    unmatched_by_role:
        ``unmatched_slots`` broken down by role.
    ambiguous_slots:
        Slots whose whole-slot attempt returned
        :data:`MATCH_OUTCOME_AMBIGUOUS` (two or more candidates matched).
        List-split is suppressed for these slots.
    ambiguous_by_role:
        ``ambiguous_slots`` broken down by role.
    list_split_suppressed:
        Slots where list-split was *not* attempted because the whole-slot
        match was ambiguous.  This is always equal to ``ambiguous_slots``;
        it is provided as a separate field so the suppression decision is
        legible in the artifact without requiring the reader to cross-reference
        the ambiguity count.
    list_split_suppressed_by_role:
        ``list_split_suppressed`` broken down by role.
    list_split_full_success:
        Slots where :func:`split_slot_text` yielded at least two parts **and**
        every part found a matching mention (full composite recovery).  A slot
        like ``"Amazon and eBay"`` where both ``"Amazon"`` and ``"eBay"`` match
        counts here.
    list_split_partial_success:
        Slots where :func:`split_slot_text` yielded at least two parts, at
        least one part matched, but at least one part also failed to match
        (partial composite recovery).  A slot like ``"Amazon and UnknownCo"``
        where only ``"Amazon"`` matches counts here.
    list_split_no_success:
        Slots where :func:`split_slot_text` yielded at least two parts but
        **no** part found a matching mention (zero recovery after split).
        These slots are also counted in ``unmatched_slots``.
    list_split_total_parts:
        Total number of individual parts examined across all split-eligible
        slots (those where :func:`split_slot_text` returned ≥ 2 parts).
    list_split_matched_parts:
        Total number of parts (across all split-eligible slots) that found a
        matching mention.  Always satisfies
        ``list_split_matched_parts + list_split_unmatched_parts == list_split_total_parts``.
    list_split_unmatched_parts:
        Total number of parts (across all split-eligible slots) that failed to
        find a matching mention.
    claims_with_any_edge:
        Number of distinct claims for which at least one participation edge was
        emitted (regardless of slot or method).
    claims_with_no_edges:
        ``claims_processed`` minus ``claims_with_any_edge``.
    sample_list_split_claim_ids:
        Up to :data:`_METRICS_SAMPLE_SIZE` claim IDs that contributed at least
        one ``list_split`` edge — useful for auditing composite/list-valued
        argument spans.
    sample_list_split_partial_claim_ids:
        Up to :data:`_METRICS_SAMPLE_SIZE` claim IDs with at least one
        partial-success ``list_split`` slot (some parts matched, some did not)
        — useful for identifying residual unmatched spans in composite
        arguments.
    residual_list_split_partial:
        Up to :data:`_METRICS_SAMPLE_SIZE` per-slot residual diagnostics for
        partial-success ``list_split`` cases.  Each entry is a dict with keys:

        ``claim_id``
            The claim that owns the slot.
        ``slot``
            The slot name (``"subject"`` or ``"object"``).
        ``slot_text``
            The normalized/trimmed slot text (``slot_str``) used for splitting
            — i.e. the value passed to :func:`split_slot_text`.  Leading and
            trailing whitespace is stripped; the value is always a plain string.
        ``parts``
            All constituent parts produced by :func:`split_slot_text`.
        ``matched_parts``
            The subset of *parts* for which a matching mention was found.
        ``unmatched_parts``
            The subset of *parts* for which no matching mention was found,
            including parts whose match was ambiguous (two or more candidates).
            Ambiguous parts produce no edge and are treated as unmatched for
            residual purposes to keep entries self-consistent.

        These diagnostics allow reviewers to inspect *which* split
        constituents failed without reconstructing them from claim text alone.
        The list is populated **only** for partial-success slots (i.e. those
        where at least one part matched *and* at least one part did not).
        Entries are bounded by :data:`_METRICS_SAMPLE_SIZE` to keep the
        artifact size small.  This field is purely observational and does not
        affect any matching behaviour.
    sample_unmatched_claim_ids:
        Up to :data:`_METRICS_SAMPLE_SIZE` claim IDs with at least one
        unmatched slot — useful for identifying extraction gaps.
    sample_ambiguous_claim_ids:
        Up to :data:`_METRICS_SAMPLE_SIZE` claim IDs with at least one
        ambiguous whole-slot match — useful for auditing mention-name collisions.
    """

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
        """Return a JSON-serialisable dict representation of the metrics."""
        return dataclasses.asdict(self)


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

    The resulting rows use the v0.3 :HAS_PARTICIPANT model: every edge row
    has ``edge_type = EDGE_TYPE_HAS_PARTICIPANT`` and a ``role`` field
    (``"subject"`` or ``"object"``).  See
    ``docs/architecture/claim-argument-model-v0.3.md`` for the decision record.

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
    ``role``, ``match_method``, and ``edge_type``
    (always ``EDGE_TYPE_HAS_PARTICIPANT``).

    .. tip::

        Use :func:`build_participation_edges_with_metrics` when you also need
        per-run matching instrumentation (counts by method, unmatched/ambiguous
        slot diagnostics, and representative sample IDs).
    """
    edge_rows, _ = build_participation_edges_with_metrics(claim_rows, mention_rows)
    return edge_rows


def build_participation_edges_with_metrics(
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], ParticipationMatchMetrics]:
    """Build participation edge rows **and** collect per-run matching metrics.

    This is the instrumented counterpart of :func:`build_participation_edges`.
    It applies the same matching logic and emits the same edge rows, while
    additionally counting outcomes by match method, role, and failure mode.

    Matching rules are identical to :func:`build_participation_edges`:

    - Whole-slot match (raw_exact → casefold_exact → normalized_exact) takes
      precedence over list-split.
    - Ambiguous whole-slot matches (:data:`MATCH_OUTCOME_AMBIGUOUS`) suppress
      list-split entirely and are counted separately.
    - Zero-match slots (``method is None``) are eligible for list-split;
      all remaining zero-match slots (including those where no split is
      possible or all split parts failed) are counted as unmatched.

    Parameters
    ----------
    claim_rows:
        Same as :func:`build_participation_edges`.
    mention_rows:
        Same as :func:`build_participation_edges`.

    Returns
    -------
    A tuple ``(edge_rows, metrics)`` where *edge_rows* is the same list
    returned by :func:`build_participation_edges` and *metrics* is a
    :class:`ParticipationMatchMetrics` instance capturing outcome counts and
    representative sample IDs.
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

    # Metrics accumulators.
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

    # Sample collectors — bounded by _METRICS_SAMPLE_SIZE to keep artifact small.
    # Each list has a companion set for O(1) duplicate detection (the linear
    # scan over the list would also work given the tiny cap, but the set is
    # cleaner and avoids any ordering-dependent behaviour).
    sample_list_split: list[str] = []
    _sample_list_split_seen: set[str] = set()
    sample_list_split_partial: list[str] = []
    _sample_list_split_partial_seen: set[str] = set()
    residual_list_split_partial: list[dict[str, Any]] = []
    sample_unmatched: list[str] = []
    _sample_unmatched_seen: set[str] = set()
    sample_ambiguous: list[str] = []
    _sample_ambiguous_seen: set[str] = set()

    def _add_sample(bucket: list[str], seen: set[str], claim_id: str) -> None:
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

        edges_before_claim = len(edge_rows)

        for slot in ("subject", "object"):
            slot_text = props.get(slot)
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
                # Record metrics for the successful whole-slot match.
                assert method is not None  # narrowing; always true when matched is not None
                edges_by_method[method] += 1
                edges_by_role[role] += 1
                edges_by_role_and_method[role][method] += 1
                continue

            # Whole-slot match failed; try splitting on conjunctions/list
            # separators and match each part independently — but ONLY when the
            # whole-slot attempt found zero candidates (method is None).  When
            # method is MATCH_OUTCOME_AMBIGUOUS (the public ambiguous-outcome
            # marker) the whole-slot text matched two or more mentions; splitting
            # it into parts would silently override that ambiguity signal and
            # could emit misleading edges.
            if method is not None:
                # Ambiguous whole-slot match — skip list-split entirely.
                ambiguous_slots += 1
                ambiguous_by_role[role] += 1
                list_split_suppressed += 1
                list_split_suppressed_by_role[role] += 1
                _add_sample(sample_ambiguous, _sample_ambiguous_seen, claim_id)
                continue

            # method is None — zero candidates from whole-slot, try list-split.
            list_split_parts = split_slot_text(slot_str)
            slot_part_total = len(list_split_parts)
            slot_part_matched = 0
            matched_part_texts: list[str] = []
            unmatched_part_texts: list[str] = []
            for part in list_split_parts:
                part_matched, part_method = match_slot_to_mention(part, flat_mentions)
                # Ambiguous part-level matches (MATCH_OUTCOME_AMBIGUOUS) produce no
                # edge — treat them as unmatched for both residual diagnostics and
                # part-level totals.  This keeps residual entries self-consistent
                # (unmatched_parts is never empty when matched_parts is non-empty)
                # and avoids surfacing separate ambiguous-part bookkeeping that
                # would complicate residual interpretation.
                if part_matched is None:
                    unmatched_part_texts.append(part)
                    continue
                matched_part_texts.append(part)
                slot_part_matched += 1
                mid = part_matched["mention_id"]
                if mid in seen_for_slot:
                    continue  # deduplicate: same mention already linked for this slot
                seen_for_slot.add(mid)
                edge_rows.append(
                    {
                        "claim_id": claim_id,
                        "mention_id": mid,
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
                _add_sample(sample_list_split, _sample_list_split_seen, claim_id)

            # Accumulate part-level totals for split-eligible slots.
            list_split_total_parts += slot_part_total
            list_split_matched_parts += slot_part_matched
            list_split_unmatched_parts += slot_part_total - slot_part_matched

            # Slot-level list-split outcome (only when split yielded ≥ 2 parts).
            if slot_part_total >= 2:
                if slot_part_matched == slot_part_total:
                    list_split_full_success += 1
                elif slot_part_matched > 0:
                    list_split_partial_success += 1
                    _add_sample(
                        sample_list_split_partial,
                        _sample_list_split_partial_seen,
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
                # No edge was produced for this slot: either no splittable
                # separator was found or all split parts failed to match.
                unmatched_slots += 1
                unmatched_by_role[role] += 1
                _add_sample(sample_unmatched, _sample_unmatched_seen, claim_id)

        if len(edge_rows) > edges_before_claim:
            claims_with_edge_set.add(claim_id)

    claims_processed = len(claim_rows)
    claims_with_any_edge = len(claims_with_edge_set)

    metrics = ParticipationMatchMetrics(
        claims_processed=claims_processed,
        slots_processed=slots_processed,
        edges_by_method=dict(edges_by_method),
        edges_by_role=dict(edges_by_role),
        edges_by_role_and_method={r: dict(m) for r, m in edges_by_role_and_method.items()},
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
    if not edge_rows:
        return

    invalid = [i for i, r in enumerate(edge_rows) if not str(r.get("role") or "").strip()]
    if invalid:
        raise ValueError(
            f"write_participation_edges: {len(invalid)} row(s) have a missing or empty "
            f"'role' field (row indices: {invalid}).  Each row must carry a non-empty "
            f"role (e.g. ROLE_SUBJECT or ROLE_OBJECT) before the MERGE is executed."
        )

    invalid_type = [
        i
        for i, r in enumerate(edge_rows)
        if "edge_type" in r and r["edge_type"] != EDGE_TYPE_HAS_PARTICIPANT
    ]
    if invalid_type:
        raise ValueError(
            f"write_participation_edges: {len(invalid_type)} row(s) have an unexpected "
            f"'edge_type' value; expected {EDGE_TYPE_HAS_PARTICIPANT!r} "
            f"(row indices: {invalid_type})."
        )

    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
        MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})
        MERGE (claim)-[r:HAS_PARTICIPANT {role: row.role}]->(mention)
        SET r.run_id = row.run_id,
            r.source_uri = coalesce(row.source_uri, r.source_uri),
            r.match_method = row.match_method
        """,
        parameters_={"rows": edge_rows},
        database_=neo4j_database,
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
    """Build and persist :HAS_PARTICIPANT edges for a claim extraction run (v0.3 model).

    Reads :ExtractedClaim and :EntityMention nodes for *run_id* from Neo4j,
    runs the slot→mention matching logic, and writes the resulting participation
    edges back to the graph via MERGE (idempotent).  Each edge carries a
    ``role`` property (``"subject"``, ``"object"``, etc.) identifying the
    argument slot.

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
    ``subject_edges``, ``object_edges``, ``match_metrics``, and ``warnings``.
    The ``match_metrics`` key contains a serialised :class:`ParticipationMatchMetrics`
    dict.  A separate ``participation_metrics.json`` file is also written to
    ``<output_dir>/runs/<run_id>/claim_participation/`` for offline inspection.
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
    metrics_path = participation_dir / "participation_metrics.json"

    if config.dry_run:
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "edges_written": 0,
            "subject_edges": 0,
            "object_edges": 0,
            "match_metrics": None,
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
        edge_rows, match_metrics = build_participation_edges_with_metrics(claim_rows, mention_rows)
        write_participation_edges(driver, neo4j_database=config.neo4j_database, edge_rows=edge_rows)

    subject_edges = sum(1 for e in edge_rows if e["role"] == ROLE_SUBJECT)
    object_edges = sum(1 for e in edge_rows if e["role"] == ROLE_OBJECT)
    metrics_dict = match_metrics.to_dict()
    metrics_path.write_text(json.dumps(metrics_dict, indent=2), encoding="utf-8")
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "claims_read": len(claim_rows),
        "mentions_read": len(mention_rows),
        "edges_written": len(edge_rows),
        "subject_edges": subject_edges,
        "object_edges": object_edges,
        "match_metrics": metrics_dict,
        "warnings": [],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

