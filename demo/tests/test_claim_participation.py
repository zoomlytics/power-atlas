"""Tests for the claim participation edge matching stage."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

import neo4j

from demo.stages.claim_participation import (
    EDGE_TYPE_HAS_PARTICIPANT,
    MATCH_METHOD_CASEFOLD_EXACT,
    MATCH_METHOD_LIST_SPLIT,
    MATCH_METHOD_NORMALIZED_EXACT,
    MATCH_METHOD_RAW_EXACT,
    MATCH_OUTCOME_AMBIGUOUS,
    ROLE_OBJECT,
    ROLE_SUBJECT,
    ParticipationMatchMetrics,
    build_participation_edges,
    build_participation_edges_with_metrics,
    match_slot_to_mention,
    split_slot_text,
    write_participation_edges,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mention(name: str, mention_id: str = "m1", chunk_ids: list[str] | None = None, run_id: str = "run-1") -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "chunk_ids": chunk_ids or ["chunk-1"],
        "run_id": run_id,
        "source_uri": "uri://test",
        "properties": {"name": name, "entity_type": "ORG"},
    }


def _flat(name: str, mention_id: str = "m1") -> dict[str, Any]:
    """Flat mention dict as expected by match_slot_to_mention."""
    return {"mention_id": mention_id, "name": name}


def _claim(
    claim_id: str = "c1",
    subject: str | None = None,
    obj: str | None = None,
    chunk_ids: list[str] | None = None,
    run_id: str = "run-1",
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "run_id": run_id,
        "source_uri": "uri://test",
        "claim_text": "some claim",
    }
    if subject is not None:
        props["subject"] = subject
    if obj is not None:
        props["object"] = obj
    return {
        "claim_id": claim_id,
        "chunk_ids": chunk_ids or ["chunk-1"],
        "run_id": run_id,
        "source_uri": "uri://test",
        "properties": props,
    }


def _make_driver() -> MagicMock:
    """Return a MagicMock neo4j.Driver with a pre-configured execute_query stub."""
    driver = MagicMock(spec=neo4j.Driver)
    driver.execute_query = MagicMock(return_value=MagicMock())
    return driver


# ---------------------------------------------------------------------------
# Tests for match_slot_to_mention
# ---------------------------------------------------------------------------


class TestMatchSlotToMention(unittest.TestCase):
    """Unit tests for match_slot_to_mention.

    Strategy priority order: raw_exact → casefold_exact → normalized_exact.
    The most restrictive strategy wins, so match_method tells you the minimum
    transformation needed to find a unique match.
    """

    # --- empty / missing inputs ---

    def test_empty_slot_text_returns_none(self):
        mentions = [_flat("IBM")]
        result, method = match_slot_to_mention("", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

    def test_whitespace_only_slot_text_returns_none(self):
        result, method = match_slot_to_mention("   ", [_flat("IBM")])
        self.assertIsNone(result)
        self.assertIsNone(method)

    def test_empty_mentions_list_returns_none(self):
        result, method = match_slot_to_mention("IBM", [])
        self.assertIsNone(result)
        self.assertIsNone(method)

    # --- raw_exact: identical strings after strip ---

    def test_raw_exact_identical_strings(self):
        # Slot and mention are textually identical — raw_exact fires.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_strips_surrounding_whitespace(self):
        # Surrounding whitespace is stripped before comparison.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("  IBM  ", mentions)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_picks_correct_mention_among_multiple(self):
        mentions = [_flat("Google", "m1"), _flat("Apple", "m2"), _flat("Microsoft", "m3")]
        result, method = match_slot_to_mention("Apple", mentions)
        self.assertEqual(result["mention_id"], "m2")
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_with_punctuation(self):
        mentions = [_flat("Apple Inc.", "m1")]
        result, method = match_slot_to_mention("Apple Inc.", mentions)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_ambiguous_returns_none(self):
        # Two mentions with the same name — ambiguous at raw level.
        # match returns (None, MATCH_OUTCOME_AMBIGUOUS) to signal ambiguity
        # (distinct from the zero-match case which returns (None, None)).
        mentions = [_flat("ABC", "m1"), _flat("ABC", "m2")]
        result, method = match_slot_to_mention("ABC", mentions)
        self.assertIsNone(result)
        self.assertEqual(method, MATCH_OUTCOME_AMBIGUOUS)

    # --- casefold_exact: only case differs ---

    def test_casefold_exact_slot_lowercase_mention_uppercase(self):
        # "ibm" vs mention "IBM": raw fails, casefold succeeds.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("ibm", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_CASEFOLD_EXACT)

    def test_casefold_exact_mixed_case(self):
        # "United Nations" vs "united nations"
        mentions = [_flat("United Nations", "m-un")]
        result, method = match_slot_to_mention("united nations", mentions)
        self.assertEqual(result["mention_id"], "m-un")
        self.assertEqual(method, MATCH_METHOD_CASEFOLD_EXACT)

    def test_casefold_exact_not_triggered_when_raw_matches(self):
        # Raw match fires first; casefold should not be used.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_casefold_exact_ambiguous_returns_none(self):
        # Two mentions with different raw names that casefold to the same text
        # — ambiguous at casefold level (raw_exact already found 0 matches).
        # "Hello" and "HELLO" differ in raw form, but both casefold to "hello".
        # Returns (None, MATCH_OUTCOME_AMBIGUOUS) to distinguish from zero-match.
        mentions = [_flat("Hello", "m1"), _flat("HELLO", "m2")]
        result, method = match_slot_to_mention("hello", mentions)
        self.assertIsNone(result)
        self.assertEqual(method, MATCH_OUTCOME_AMBIGUOUS)

    # --- normalized_exact: Unicode normalization needed ---

    def test_normalized_exact_diacritics_stripped(self):
        # "Résumé" → "resume" via normalization; "resume" matches.
        mentions = [_flat("Résumé", "m1")]
        result, method = match_slot_to_mention("resume", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_umlaut_stripped(self):
        # Both "Müller" and slot "Muller" normalize to "muller" via NFKD+diacritics+casefold.
        mentions = [_flat("Müller", "m1")]
        result, method = match_slot_to_mention("Muller", mentions)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_casefold_exact_german_sharp_s(self):
        # ß casefolds to "ss", so "Straße".casefold() == "strasse".
        # casefold_exact fires before normalized_exact.
        mentions = [_flat("Straße", "m1")]
        result, method = match_slot_to_mention("strasse", mentions)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_CASEFOLD_EXACT)

    def test_normalized_exact_em_dash_normalized(self):
        # em-dash → hyphen-minus via normalization.
        mentions = [_flat("well-known", "m1")]
        result, method = match_slot_to_mention("well\u2014known", mentions)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_not_triggered_when_casefold_matches(self):
        # Pure case difference → casefold fires, not normalized.
        mentions = [_flat("Hello World", "m1")]
        result, method = match_slot_to_mention("hello world", mentions)
        self.assertEqual(method, MATCH_METHOD_CASEFOLD_EXACT)

    def test_normalized_exact_not_triggered_when_raw_matches(self):
        # Identical strings → raw fires, not normalized.
        mentions = [_flat("Apple Inc.", "m1")]
        result, method = match_slot_to_mention("Apple Inc.", mentions)
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_normalized_exact_ambiguous_returns_none(self):
        # Two mentions with different diacritic forms that normalize identically,
        # but neither matches via raw or casefold.
        # "Café" and "CAFÉ" both casefold to "café" (not "cafe") but both
        # normalize to "cafe" — so normalized_exact sees 2 matches → ambiguous.
        # Returns (None, MATCH_OUTCOME_AMBIGUOUS) to distinguish from zero-match.
        mentions = [_flat("Café", "m1"), _flat("CAFÉ", "m2")]
        result, method = match_slot_to_mention("cafe", mentions)
        self.assertIsNone(result)
        self.assertEqual(method, MATCH_OUTCOME_AMBIGUOUS)

    # --- no match ---

    def test_no_match_returns_none(self):
        mentions = [_flat("OpenAI", "m1"), _flat("Microsoft", "m2")]
        result, method = match_slot_to_mention("Google", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)


# ---------------------------------------------------------------------------
# Tests for the strategy priority order
# ---------------------------------------------------------------------------


class TestStrategyPriorityOrder(unittest.TestCase):
    """Verify the raw_exact → casefold_exact → normalized_exact ordering."""

    def test_raw_exact_takes_precedence_over_casefold(self):
        # Slot and mention are identical — raw_exact fires before casefold.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_takes_precedence_over_normalized(self):
        # Slot and mention are identical — raw_exact fires before normalized.
        mentions = [_flat("Café", "m1")]
        result, method = match_slot_to_mention("Café", mentions)
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_casefold_exact_takes_precedence_over_normalized(self):
        # "ibm" vs "IBM": no diacritics or Unicode variants — casefold fires first.
        mentions = [_flat("IBM", "m1")]
        result, method = match_slot_to_mention("ibm", mentions)
        self.assertEqual(method, MATCH_METHOD_CASEFOLD_EXACT)

    def test_normalized_exact_used_when_casefold_finds_zero(self):
        # "Muller" vs "Müller": casefold doesn't help (müller ≠ muller after strip),
        # but full normalization removes the umlaut.
        mentions = [_flat("Müller", "m1")]
        result, method = match_slot_to_mention("Muller", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_raw_ambiguity_stops_search(self):
        # Two identical-name mentions → ambiguous at raw level; no edge.
        # Returns (None, MATCH_OUTCOME_AMBIGUOUS) rather than (None, None)
        # so callers can distinguish "ambiguous" from "no candidates found".
        mentions = [_flat("ABC", "m1"), _flat("ABC", "m2")]
        result, method = match_slot_to_mention("ABC", mentions)
        self.assertIsNone(result)
        self.assertEqual(method, MATCH_OUTCOME_AMBIGUOUS)

    def test_casefold_ambiguity_stops_search(self):
        # Two mentions with different raw names that casefold identically
        # — ambiguous at casefold level; no edge created.
        # Returns (None, MATCH_OUTCOME_AMBIGUOUS) rather than (None, None).
        mentions = [_flat("Hello", "m1"), _flat("HELLO", "m2")]
        result, method = match_slot_to_mention("hello", mentions)
        self.assertIsNone(result)
        self.assertEqual(method, MATCH_OUTCOME_AMBIGUOUS)


# ---------------------------------------------------------------------------
# Tests for build_participation_edges
# ---------------------------------------------------------------------------


class TestBuildParticipationEdges(unittest.TestCase):
    """Unit tests for build_participation_edges."""

    def test_basic_subject_and_object_matched(self):
        mentions = [
            _mention("Google", "m-google"),
            _mention("revenue", "m-revenue"),
        ]
        claims = [_claim("c1", subject="Google", obj="revenue")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        subj = next(e for e in edges if e["slot"] == "subject")
        obj_ = next(e for e in edges if e["slot"] == "object")
        self.assertEqual(subj["mention_id"], "m-google")
        self.assertEqual(subj["edge_type"], EDGE_TYPE_HAS_PARTICIPANT)
        self.assertEqual(subj["role"], ROLE_SUBJECT)
        self.assertEqual(subj["match_method"], MATCH_METHOD_RAW_EXACT)
        self.assertEqual(obj_["mention_id"], "m-revenue")
        self.assertEqual(obj_["edge_type"], EDGE_TYPE_HAS_PARTICIPANT)
        self.assertEqual(obj_["role"], ROLE_OBJECT)

    def test_no_subject_or_object_slot(self):
        mentions = [_mention("Google", "m1")]
        claims = [_claim("c1")]  # no subject/object
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_only_subject_slot(self):
        mentions = [_mention("Tesla", "m-tesla")]
        claims = [_claim("c1", subject="Tesla")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["slot"], "subject")
        self.assertEqual(edges[0]["mention_id"], "m-tesla")

    def test_only_object_slot(self):
        mentions = [_mention("profit", "m-profit")]
        claims = [_claim("c1", obj="profit")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["slot"], "object")
        self.assertEqual(edges[0]["mention_id"], "m-profit")

    def test_mentions_from_different_chunk_not_matched(self):
        # Mention is in chunk-2 but claim is in chunk-1 → no overlap
        mentions = [_mention("Google", "m1", chunk_ids=["chunk-2"])]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"])]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_cross_chunk_mention_matched_when_overlap(self):
        # Mention spans chunk-1 and chunk-2; claim is in chunk-1 → overlap
        mentions = [_mention("Google", "m1", chunk_ids=["chunk-1", "chunk-2"])]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"])]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)

    def test_mentions_from_different_run_not_matched(self):
        # Mention shares a chunk_id but belongs to a different run — must not match.
        mentions = [_mention("Google", "m1", chunk_ids=["chunk-1"], run_id="run-B")]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"], run_id="run-A")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_run_id_scoping_same_chunk_id_different_runs(self):
        # Two mentions with the same chunk_id but different run_ids.
        # Only the one matching the claim's run_id should be a candidate.
        mentions = [
            _mention("Google", "m-a", chunk_ids=["chunk-1"], run_id="run-A"),
            _mention("Google", "m-b", chunk_ids=["chunk-1"], run_id="run-B"),
        ]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"], run_id="run-A")]
        edges = build_participation_edges(claims, mentions)
        # Only m-a is in run-A; exactly 1 candidate → unique match
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-a")

    def test_ambiguous_subject_no_edge(self):
        # Two mentions in same chunk/run that casefold to the same text but
        # have different raw names (so raw_exact doesn't fire on either).
        mentions = [
            _mention("Hello", "m1"),
            _mention("HELLO", "m2"),
        ]
        claims = [_claim("c1", subject="hello")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_missing_mention_no_edge(self):
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c1", subject="Google")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_edge_row_contains_run_id_and_source_uri(self):
        mentions = [_mention("IBM", "m1", run_id="run-xyz")]
        claims = [_claim("c1", subject="IBM", run_id="run-xyz")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["run_id"], "run-xyz")
        self.assertIn("source_uri", edges[0])

    def test_multiple_claims_in_same_chunk(self):
        mentions = [
            _mention("Google", "m-google"),
            _mention("Apple", "m-apple"),
        ]
        claims = [
            _claim("c1", subject="Google"),
            _claim("c2", subject="Apple"),
        ]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        ids = {e["mention_id"] for e in edges}
        self.assertEqual(ids, {"m-google", "m-apple"})

    def test_no_mentions_returns_empty(self):
        claims = [_claim("c1", subject="Google")]
        edges = build_participation_edges(claims, [])
        self.assertEqual(edges, [])

    def test_no_claims_returns_empty(self):
        mentions = [_mention("Google", "m1")]
        edges = build_participation_edges([], mentions)
        self.assertEqual(edges, [])

    def test_claim_missing_chunk_ids_skipped(self):
        mentions = [_mention("IBM", "m1")]
        claim = _claim("c1", subject="IBM")
        claim["chunk_ids"] = []
        edges = build_participation_edges([claim], mentions)
        self.assertEqual(edges, [])

    def test_mention_deduped_when_spans_multiple_matching_chunks(self):
        # Claim and mention both span chunk-1 AND chunk-2 → mention appears once
        mentions = [_mention("IBM", "m1", chunk_ids=["chunk-1", "chunk-2"])]
        claims = [_claim("c1", subject="IBM", chunk_ids=["chunk-1", "chunk-2"])]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)

    def test_casefold_match_uses_casefold_exact(self):
        mentions = [_mention("United Nations", "m-un")]
        claims = [_claim("c1", subject="united nations")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_CASEFOLD_EXACT)

    def test_diacritic_match_uses_normalized_exact(self):
        # "Muller" matches "Müller" only after full normalization.
        mentions = [_mention("Müller", "m1")]
        claims = [_claim("c1", subject="Muller")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_NORMALIZED_EXACT)

    def test_exact_match_uses_raw_exact(self):
        mentions = [_mention("Apple Inc.", "m1")]
        claims = [_claim("c1", subject="Apple Inc.")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_RAW_EXACT)


# ---------------------------------------------------------------------------
# Tests for write_participation_edges
# ---------------------------------------------------------------------------


class TestWriteParticipationEdges(unittest.TestCase):
    """Unit tests for write_participation_edges (Neo4j interaction mocked)."""

    def test_write_subject_and_object_edges(self):
        driver = _make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m-subject",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "subject",
                "role": ROLE_SUBJECT,
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
            },
            {
                "claim_id": "c1",
                "mention_id": "m-object",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "object",
                "role": ROLE_OBJECT,
                "match_method": MATCH_METHOD_CASEFOLD_EXACT,
                "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
            },
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        # v0.3 model: single execute_query call for all rows regardless of role.
        self.assertEqual(driver.execute_query.call_count, 1)

    def test_write_only_subject_edges(self):
        driver = _make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": None,
                "slot": "subject",
                "role": ROLE_SUBJECT,
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 1)

    def test_write_only_object_edges(self):
        driver = _make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": None,
                "slot": "object",
                "role": ROLE_OBJECT,
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 1)

    def test_write_empty_edge_rows_no_queries(self):
        driver = _make_driver()
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=[])
        driver.execute_query.assert_not_called()

    def test_parameters_passed_to_driver(self):
        driver = _make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": "uri://x",
                "slot": "subject",
                "role": ROLE_SUBJECT,
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        _args, kwargs = driver.execute_query.call_args
        self.assertEqual(kwargs.get("database_"), "neo4j")
        passed_rows = kwargs.get("parameters_", {}).get("rows", [])
        self.assertEqual(len(passed_rows), 1)
        self.assertEqual(passed_rows[0]["claim_id"], "c1")
        self.assertEqual(passed_rows[0]["match_method"], MATCH_METHOD_RAW_EXACT)


# ---------------------------------------------------------------------------
# Normalization edge cases for match_slot_to_mention
# ---------------------------------------------------------------------------


class TestMatchSlotNormalizationEdgeCases(unittest.TestCase):
    """Additional normalization edge cases — spacing, apostrophes, dashes."""

    def test_multiple_internal_spaces_collapsed_by_normalized_exact(self):
        # Extra whitespace in slot text is collapsed to a single space by
        # normalize_mention_text, so "Apple  Inc" matches mention "Apple Inc".
        mentions = [_flat("Apple Inc", "m1")]
        result, method = match_slot_to_mention("Apple  Inc", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_curly_right_apostrophe_normalized_to_ascii(self):
        # RIGHT SINGLE QUOTATION MARK (U+2019) in slot text → ASCII apostrophe
        # via normalize_mention_text; mention uses plain apostrophe.
        mentions = [_flat("O'Brien", "m1")]
        result, method = match_slot_to_mention("O\u2019Brien", mentions)  # curly '
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_curly_left_apostrophe_normalized_to_ascii(self):
        # LEFT SINGLE QUOTATION MARK (U+2018) in mention → ASCII apostrophe in slot
        mentions = [_flat("O\u2018Brien", "m1")]  # curly ' in mention
        result, method = match_slot_to_mention("O'Brien", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_en_dash_in_slot_normalizes_to_hyphen(self):
        # EN DASH (U+2013) in slot text is normalized to hyphen-minus.
        mentions = [_flat("well-known", "m1")]
        result, method = match_slot_to_mention("well\u2013known", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_em_dash_in_mention_normalizes_to_hyphen(self):
        # EM DASH (U+2014) in mention; slot uses hyphen-minus.
        mentions = [_flat("well\u2014known", "m1")]
        result, method = match_slot_to_mention("well-known", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_non_breaking_space_in_slot_normalized(self):
        # NO-BREAK SPACE (U+00A0) in slot text is collapsed to regular space.
        mentions = [_flat("New York", "m1")]
        result, method = match_slot_to_mention("New\u00A0York", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_non_breaking_space_in_mention_normalized(self):
        # NO-BREAK SPACE in mention name; slot uses regular space.
        mentions = [_flat("New\u00A0York", "m1")]
        result, method = match_slot_to_mention("New York", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_whitespace_does_not_fire_on_raw_match(self):
        # Slot and mention are identical including a double space → raw_exact wins.
        mentions = [_flat("Apple  Inc", "m1")]
        result, method = match_slot_to_mention("Apple  Inc", mentions)
        self.assertEqual(method, MATCH_METHOD_RAW_EXACT)

    def test_no_match_when_normalization_still_differs(self):
        # Even after full normalization the strings do not match.
        mentions = [_flat("Google", "m1")]
        result, method = match_slot_to_mention("Alphabet", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)


# ---------------------------------------------------------------------------
# Multiple similar mentions in the same chunk
# ---------------------------------------------------------------------------


class TestMultipleSimilarMentions(unittest.TestCase):
    """Tests involving multiple similar mentions within the same chunk."""

    def test_two_identical_raw_names_ambiguous(self):
        # Two mentions with the same exact name → ambiguous at raw_exact.
        mentions = [_mention("Apple", "m1"), _mention("Apple", "m2")]
        claims = [_claim("c1", subject="Apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_two_case_variants_slot_lowercase_casefold_ambiguous(self):
        # "Apple" and "APPLE" in same chunk, slot "apple" →
        # raw_exact: no match; casefold: both match → ambiguous, no edge.
        mentions = [_mention("Apple", "m1"), _mention("APPLE", "m2")]
        claims = [_claim("c1", subject="apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_two_case_variants_slot_matches_one_raw(self):
        # "Apple" (m1) and "APPLE" (m2) in same chunk, slot "Apple" →
        # raw_exact finds exactly "Apple" → unique match, no ambiguity.
        mentions = [_mention("Apple", "m1"), _mention("APPLE", "m2")]
        claims = [_claim("c1", subject="Apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m1")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_RAW_EXACT)

    def test_raw_exact_match_among_casefold_duplicates(self):
        # Mentions: "apple" (m1) and "Apple" (m2); slot "apple" →
        # raw_exact finds exactly "apple" → m1 matched, not ambiguous.
        mentions = [_mention("apple", "m1"), _mention("Apple", "m2")]
        claims = [_claim("c1", subject="apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m1")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_RAW_EXACT)

    def test_prefix_mention_does_not_match_longer_slot(self):
        # Mention "App" in chunk, slot "Apple" → strings differ → no match.
        mentions = [_mention("App", "m1")]
        claims = [_claim("c1", subject="Apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_multiple_mentions_only_one_matches_slot(self):
        # Three mentions; slot uniquely matches one via raw_exact.
        mentions = [
            _mention("Google", "m-google"),
            _mention("Apple", "m-apple"),
            _mention("Microsoft", "m-ms"),
        ]
        claims = [_claim("c1", subject="Apple")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-apple")

    def test_two_normalized_duplicates_ambiguous(self):
        # "Café" and "CAFÉ" both normalize to "cafe";
        # slot "cafe" → normalized_exact sees 2 → ambiguous.
        mentions = [_mention("Café", "m1"), _mention("CAFÉ", "m2")]
        claims = [_claim("c1", subject="cafe")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_subject_ambiguous_object_unique(self):
        # Subject slot is ambiguous → no subject edge;
        # object slot is uniquely matched → one object edge.
        mentions = [
            _mention("Hello", "m1"),
            _mention("HELLO", "m2"),
            _mention("profit", "m-profit"),
        ]
        claims = [_claim("c1", subject="hello", obj="profit")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["slot"], "object")
        self.assertEqual(edges[0]["mention_id"], "m-profit")


# ---------------------------------------------------------------------------
# Idempotency of build_participation_edges (repeated calls)
# ---------------------------------------------------------------------------


class TestBuildParticipationEdgesIdempotency(unittest.TestCase):
    """Repeated calls to build_participation_edges with the same data
    must always return equal, deterministic results."""

    def test_raw_exact_match_idempotent(self):
        mentions = [_mention("Google", "m-google"), _mention("revenue", "m-revenue")]
        claims = [_claim("c1", subject="Google", obj="revenue")]
        self.assertEqual(
            build_participation_edges(claims, mentions),
            build_participation_edges(claims, mentions),
        )

    def test_casefold_match_idempotent(self):
        mentions = [_mention("United Nations", "m-un")]
        claims = [_claim("c1", subject="united nations")]
        self.assertEqual(
            build_participation_edges(claims, mentions),
            build_participation_edges(claims, mentions),
        )

    def test_normalized_match_idempotent(self):
        mentions = [_mention("Müller", "m1")]
        claims = [_claim("c1", subject="Muller")]
        self.assertEqual(
            build_participation_edges(claims, mentions),
            build_participation_edges(claims, mentions),
        )

    def test_no_match_idempotent(self):
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c1", subject="Google")]
        result = build_participation_edges(claims, mentions)
        self.assertEqual(result, [])
        self.assertEqual(result, build_participation_edges(claims, mentions))

    def test_ambiguous_no_edge_idempotent(self):
        mentions = [_mention("Hello", "m1"), _mention("HELLO", "m2")]
        claims = [_claim("c1", subject="hello")]
        result = build_participation_edges(claims, mentions)
        self.assertEqual(result, [])
        self.assertEqual(result, build_participation_edges(claims, mentions))

    def test_empty_inputs_idempotent(self):
        self.assertEqual(build_participation_edges([], []), [])
        self.assertEqual(build_participation_edges([], []), build_participation_edges([], []))


# ---------------------------------------------------------------------------
# Orphan edge prevention
# ---------------------------------------------------------------------------


class TestOrphanEdgePrevention(unittest.TestCase):
    """No edges are emitted when the evidence is absent, ambiguous, or mismatched."""

    def test_no_edge_when_claim_has_no_candidates_in_its_chunk(self):
        mentions = [_mention("Google", "m1", chunk_ids=["chunk-99"])]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"])]
        self.assertEqual(build_participation_edges(claims, mentions), [])

    def test_no_edge_when_mention_belongs_to_different_run(self):
        mentions = [_mention("Apple", "m1", run_id="run-2")]
        claims = [_claim("c1", subject="Apple", run_id="run-1")]
        self.assertEqual(build_participation_edges(claims, mentions), [])

    def test_subject_edge_not_created_when_subject_absent_from_chunk(self):
        # Mention in chunk-2 only; claim in chunk-1 only → no edge
        mentions = [_mention("Tesla", "m1", chunk_ids=["chunk-2"])]
        claims = [_claim("c1", subject="Tesla", chunk_ids=["chunk-1"])]
        self.assertEqual(build_participation_edges(claims, mentions), [])

    def test_object_match_but_subject_absent_produces_one_edge(self):
        # Subject slot text is not in any mention; object slot matches uniquely.
        mentions = [_mention("revenue", "m-revenue")]
        claims = [_claim("c1", subject="Totally-Absent", obj="revenue")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["slot"], "object")
        self.assertEqual(edges[0]["mention_id"], "m-revenue")

    def test_no_edge_when_both_slots_absent_from_mentions(self):
        mentions = [_mention("Irrelevant", "m1")]
        claims = [_claim("c1", subject="Nobody", obj="Nothing")]
        self.assertEqual(build_participation_edges(claims, mentions), [])

    def test_no_cross_run_contamination_with_shared_chunk_id(self):
        # Two runs share the same chunk_id string, but edges must never cross runs.
        mentions = [
            _mention("Tesla", "m-a", chunk_ids=["chunk-1"], run_id="run-A"),
            _mention("Tesla", "m-b", chunk_ids=["chunk-1"], run_id="run-B"),
        ]
        claims = [
            _claim("c-a", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-A"),
            _claim("c-b", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-B"),
        ]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        edges_by_claim = {e["claim_id"]: e for e in edges}
        self.assertEqual(edges_by_claim["c-a"]["mention_id"], "m-a")
        self.assertEqual(edges_by_claim["c-b"]["mention_id"], "m-b")


# ---------------------------------------------------------------------------
# Demo-reset + rerun cycle
# ---------------------------------------------------------------------------


class TestDemoResetRerunCycle(unittest.TestCase):
    """Simulate a demo-reset followed by a re-extraction run.

    Since build_participation_edges is a pure function, the same inputs always
    produce the same outputs.  These tests verify that:
    - a second call to build_participation_edges is deterministic,
    - fresh run_id data is fully isolated from old run_id data,
    - no stale edges from a previous run bleed into the new run.
    """

    def test_rerun_with_same_data_produces_identical_edges(self):
        mentions = [_mention("Google", "m-google"), _mention("revenue", "m-revenue")]
        claims = [_claim("c1", subject="Google", obj="revenue")]
        edges_first = build_participation_edges(claims, mentions)
        edges_second = build_participation_edges(claims, mentions)
        self.assertEqual(edges_first, edges_second)
        self.assertEqual(len(edges_first), 2)

    def test_new_run_id_isolated_from_old_run_id(self):
        # "run-v1" mentions must not link to "run-v2" claims.
        mentions_v1 = [_mention("Tesla", "m-v1", run_id="run-v1")]
        claims_v2 = [_claim("c1", subject="Tesla", run_id="run-v2")]
        edges = build_participation_edges(claims_v2, mentions_v1)
        self.assertEqual(edges, [])

    def test_fresh_run_produces_clean_edges_without_stale_data(self):
        # Old mentions (run-v1) and new mentions (run-v2) both present;
        # new claims (run-v2) must only link to run-v2 mentions.
        old_mentions = [_mention("Apple", "m-old", run_id="run-v1")]
        new_mentions = [_mention("Apple", "m-new", run_id="run-v2")]
        new_claims = [_claim("c1", subject="Apple", run_id="run-v2")]

        all_mentions = old_mentions + new_mentions
        edges = build_participation_edges(new_claims, all_mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-new")
        self.assertEqual(edges[0]["run_id"], "run-v2")

    def test_reset_then_rerun_same_run_id_returns_same_edges(self):
        # Simulate: run stage → reset memory → run stage again with same run_id.
        # Both calls are isolated pure-function calls; results must be equal.
        mentions = [_mention("IBM", "m-ibm", run_id="run-demo")]
        claims = [_claim("claim-1", subject="IBM", run_id="run-demo")]

        edges_before_reset = build_participation_edges(claims, mentions)
        # "Reset": rebuild from scratch (pure function, no side effects)
        edges_after_reset = build_participation_edges(claims, mentions)

        self.assertEqual(edges_before_reset, edges_after_reset)
        self.assertEqual(len(edges_before_reset), 1)
        self.assertEqual(edges_before_reset[0]["mention_id"], "m-ibm")

    def test_casefold_match_stable_across_reruns(self):
        mentions = [_mention("United Nations", "m-un", run_id="run-demo")]
        claims = [_claim("c1", subject="united nations", run_id="run-demo")]
        first = build_participation_edges(claims, mentions)
        second = build_participation_edges(claims, mentions)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["match_method"], MATCH_METHOD_CASEFOLD_EXACT)

    def test_normalized_match_stable_across_reruns(self):
        mentions = [_mention("Müller", "m1", run_id="run-demo")]
        claims = [_claim("c1", subject="Muller", run_id="run-demo")]
        first = build_participation_edges(claims, mentions)
        second = build_participation_edges(claims, mentions)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["match_method"], MATCH_METHOD_NORMALIZED_EXACT)


# ---------------------------------------------------------------------------
# Idempotency of write_participation_edges (MERGE semantics)
# ---------------------------------------------------------------------------


class TestWriteParticipationEdgesIdempotency(unittest.TestCase):
    """write_participation_edges uses MERGE, so calling it twice with the same
    data must issue the same number of queries with identical parameters."""

    def _subject_row(self, claim_id: str = "c1", mention_id: str = "m1") -> dict:
        return {
            "claim_id": claim_id,
            "mention_id": mention_id,
            "run_id": "run-1",
            "source_uri": "uri://test",
            "slot": "subject",
            "role": ROLE_SUBJECT,
            "match_method": MATCH_METHOD_RAW_EXACT,
            "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
        }

    def _object_row(self, claim_id: str = "c1", mention_id: str = "m2") -> dict:
        return {
            "claim_id": claim_id,
            "mention_id": mention_id,
            "run_id": "run-1",
            "source_uri": "uri://test",
            "slot": "object",
            "role": ROLE_OBJECT,
            "match_method": MATCH_METHOD_CASEFOLD_EXACT,
            "edge_type": EDGE_TYPE_HAS_PARTICIPANT,
        }

    def test_calling_twice_issues_same_number_of_queries(self):
        # Each call with [subject] issues 1 query; two calls → 2 total.
        driver = _make_driver()
        edge_rows = [self._subject_row()]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        first_count = driver.execute_query.call_count
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, first_count * 2)

    def test_calling_twice_passes_identical_rows_to_driver(self):
        # MERGE semantics: both calls must supply the same row payloads.
        driver = _make_driver()
        edge_rows = [self._object_row()]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        first_rows = driver.execute_query.call_args_list[0][1].get("parameters_", {}).get("rows")
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        second_rows = driver.execute_query.call_args_list[1][1].get("parameters_", {}).get("rows")
        self.assertEqual(first_rows, second_rows)

    def test_subject_and_object_idempotent_together(self):
        # v0.3 model: a single execute_query call covers all rows.
        # Two calls → 2 total execute_query calls.
        driver = _make_driver()
        edge_rows = [self._subject_row(), self._object_row()]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 1)
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 2)

    def test_empty_edge_rows_no_queries_on_rerun(self):
        driver = _make_driver()
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=[])
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=[])
        driver.execute_query.assert_not_called()

    def test_database_name_unchanged_across_reruns(self):
        driver = _make_driver()
        edge_rows = [self._subject_row()]
        write_participation_edges(driver, neo4j_database="mydb", edge_rows=edge_rows)
        write_participation_edges(driver, neo4j_database="mydb", edge_rows=edge_rows)
        for call in driver.execute_query.call_args_list:
            self.assertEqual(call[1].get("database_"), "mydb")


# ---------------------------------------------------------------------------
# Tests for split_slot_text
# ---------------------------------------------------------------------------


class TestSplitSlotText(unittest.TestCase):
    """Unit tests for split_slot_text — the conjunction/list splitter."""

    # --- conjunction separators ---

    def test_and_separator_splits_two_entities(self):
        parts = split_slot_text("Amazon and eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_or_separator_splits_two_entities(self):
        parts = split_slot_text("Amazon or eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_ampersand_separator_splits_two_entities(self):
        parts = split_slot_text("Amazon & eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_and_separator_case_insensitive(self):
        # "AND" in uppercase should also split.
        parts = split_slot_text("Google AND Microsoft")
        self.assertEqual(parts, ["Google", "Microsoft"])

    def test_or_separator_case_insensitive(self):
        parts = split_slot_text("Tesla OR Ford")
        self.assertEqual(parts, ["Tesla", "Ford"])

    # --- comma separators ---

    def test_comma_space_separator_splits_two_parts(self):
        # "Xapo, Company" → ["Xapo", "Company"]
        parts = split_slot_text("Xapo, Company")
        self.assertEqual(parts, ["Xapo", "Company"])

    def test_comma_multiple_spaces_separator(self):
        parts = split_slot_text("Xapo,  Organization")
        self.assertEqual(parts, ["Xapo", "Organization"])

    def test_comma_no_space_does_not_split(self):
        # Comma without a following space is NOT a list separator.
        parts = split_slot_text("Inc.,Ltd.")
        self.assertEqual(parts, [])

    # --- three-way splits ---

    def test_three_part_and_split(self):
        parts = split_slot_text("Google and Apple and Microsoft")
        self.assertEqual(parts, ["Google", "Apple", "Microsoft"])

    def test_three_part_comma_split(self):
        parts = split_slot_text("Google, Apple, Microsoft")
        self.assertEqual(parts, ["Google", "Apple", "Microsoft"])

    def test_oxford_comma_and(self):
        # "A, B, and C" — the ", and " separator is consumed as a unit so the
        # last token is "C", not "and C".
        parts = split_slot_text("Amazon, eBay, and Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    def test_oxford_comma_or(self):
        parts = split_slot_text("Amazon, eBay, or Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    def test_oxford_comma_ampersand(self):
        parts = split_slot_text("Amazon, eBay, & Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    def test_oxford_comma_case_insensitive(self):
        parts = split_slot_text("Amazon, eBay, AND Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    # --- no split cases ---

    def test_single_entity_returns_empty_list(self):
        # Single entity with no separator → no split → empty list.
        self.assertEqual(split_slot_text("Amazon"), [])

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(split_slot_text(""), [])

    def test_whitespace_only_returns_empty_list(self):
        self.assertEqual(split_slot_text("   "), [])

    def test_word_containing_and_not_split(self):
        # "Anderson" contains "and" but as part of a word, not as a separator.
        # The regex requires whitespace on both sides of "and".
        self.assertEqual(split_slot_text("Anderson"), [])

    # --- whitespace handling ---

    def test_surrounding_whitespace_stripped_from_parts(self):
        parts = split_slot_text("  Amazon  and  eBay  ")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_parts_with_internal_spaces_preserved(self):
        parts = split_slot_text("New York and Los Angeles")
        self.assertEqual(parts, ["New York", "Los Angeles"])

    # --- slash separators (new: supported with surrounding whitespace) ---

    def test_slash_with_spaces_splits_two_entities(self):
        # "Amazon / eBay" → ["Amazon", "eBay"]
        parts = split_slot_text("Amazon / eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_slash_with_spaces_splits_three_entities(self):
        # "Amazon / eBay / Google" → ["Amazon", "eBay", "Google"]
        parts = split_slot_text("Amazon / eBay / Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    def test_slash_no_spaces_does_not_split(self):
        # "Amazon/eBay" — bare slash without spaces is NOT a list separator
        # (avoids splitting URL paths, numeric ratios, etc.).
        self.assertEqual(split_slot_text("Amazon/eBay"), [])

    def test_slash_only_leading_space_does_not_split(self):
        # " /eBay" — requires space on BOTH sides; asymmetric space does not split.
        self.assertEqual(split_slot_text("Amazon /eBay"), [])

    def test_slash_only_trailing_space_does_not_split(self):
        # "Amazon/ eBay" — requires space on BOTH sides.
        self.assertEqual(split_slot_text("Amazon/ eBay"), [])

    def test_slash_multiple_spaces_splits(self):
        # Multiple spaces around slash are also acceptable.
        parts = split_slot_text("Amazon  /  eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    # --- semicolon separators (new: supported with trailing whitespace) ---

    def test_semicolon_space_splits_two_entities(self):
        # "Amazon; eBay" → ["Amazon", "eBay"]
        parts = split_slot_text("Amazon; eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    def test_semicolon_space_splits_three_entities(self):
        # "Amazon; eBay; Google" → ["Amazon", "eBay", "Google"]
        parts = split_slot_text("Amazon; eBay; Google")
        self.assertEqual(parts, ["Amazon", "eBay", "Google"])

    def test_semicolon_no_space_does_not_split(self):
        # "Amazon;eBay" — bare semicolon without trailing space is NOT a separator
        # (avoids splitting abbreviations such as "U.S.;").
        self.assertEqual(split_slot_text("Amazon;eBay"), [])

    def test_semicolon_multiple_spaces_splits(self):
        parts = split_slot_text("Amazon;  eBay")
        self.assertEqual(parts, ["Amazon", "eBay"])

    # --- explicitly unsupported forms (documented non-support) ---

    def test_parenthetical_qualifier_splits_but_qualifier_retained(self):
        # "Amazon (AWS) and Google" splits into ["Amazon (AWS)", "Google"].
        # The parenthetical form is not stripped; "Amazon (AWS)" will fail
        # to match a plain "Amazon" mention.  This is intentional: we do not
        # attempt to recover the base name from parenthetical qualifiers.
        parts = split_slot_text("Amazon (AWS) and Google")
        self.assertEqual(parts, ["Amazon (AWS)", "Google"])

    def test_grouped_qualifier_splits_but_qualifier_retained(self):
        # "Amazon and eBay subsidiaries" splits into ["Amazon", "eBay subsidiaries"].
        # "eBay subsidiaries" will not match a plain "eBay" mention.
        parts = split_slot_text("Amazon and eBay subsidiaries")
        self.assertEqual(parts, ["Amazon", "eBay subsidiaries"])

    def test_appositive_comma_splits_entity_and_descriptor(self):
        # "Xapo, a digital-assets company" splits via comma into
        # ["Xapo", "a digital-assets company"].  "Xapo" can match a mention;
        # the appositive descriptor phrase will typically fail to match.
        parts = split_slot_text("Xapo, a digital-assets company")
        self.assertEqual(parts, ["Xapo", "a digital-assets company"])

    def test_nested_qualifier_splits_into_parts(self):
        # "Amazon, eBay, and Google subsidiaries" splits into
        # ["Amazon", "eBay", "Google subsidiaries"].
        # "Google subsidiaries" is intentionally not resolved.
        parts = split_slot_text("Amazon, eBay, and Google subsidiaries")
        self.assertEqual(parts, ["Amazon", "eBay", "Google subsidiaries"])


# ---------------------------------------------------------------------------
# Tests for list-split matching in build_participation_edges
# ---------------------------------------------------------------------------


class TestBuildParticipationEdgesListSplit(unittest.TestCase):
    """Regression tests for conjunction/list splitting in build_participation_edges.

    These cover grouped, enumerative, and composite argument spans that do not
    match as a whole but do match when split on conjunctions or commas.
    """

    # --- "and" conjunction ---

    def test_object_and_conjunction_yields_two_edges(self):
        # "Amazon and eBay" as object slot with both entities as mentions
        # → two list_split edges (one per entity).
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay"})
        for e in edges:
            self.assertEqual(e["slot"], "object")
            self.assertEqual(e["role"], ROLE_OBJECT)
            self.assertEqual(e["match_method"], MATCH_METHOD_LIST_SPLIT)
            self.assertEqual(e["edge_type"], EDGE_TYPE_HAS_PARTICIPANT)

    def test_subject_and_conjunction_yields_two_edges(self):
        # "Google and Facebook" as subject slot.
        mentions = [
            _mention("Google", "m-g"),
            _mention("Facebook", "m-fb"),
        ]
        claims = [_claim("c1", subject="Google and Facebook")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e["slot"] == "subject" for e in edges))
        self.assertTrue(all(e["role"] == ROLE_SUBJECT for e in edges))
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    # --- "or" conjunction ---

    def test_object_or_conjunction_yields_two_edges(self):
        mentions = [
            _mention("Tesla", "m-tesla"),
            _mention("Ford", "m-ford"),
        ]
        claims = [_claim("c1", obj="Tesla or Ford")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-tesla", "m-ford"})

    # --- comma separator ---

    def test_subject_comma_list_yields_two_edges(self):
        # "Xapo, Company" as subject — Xapo matches as an entity,
        # Company also has a mention.
        mentions = [
            _mention("Xapo", "m-xapo"),
            _mention("Company", "m-company"),
        ]
        claims = [_claim("c1", subject="Xapo, Company")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-xapo", "m-company"})
        for e in edges:
            self.assertEqual(e["match_method"], MATCH_METHOD_LIST_SPLIT)

    # --- partial match (one part matches, other does not) ---

    def test_partial_match_yields_one_edge(self):
        # "Amazon and UnknownCo": Amazon matches, UnknownCo has no mention.
        mentions = [_mention("Amazon", "m-amazon")]
        claims = [_claim("c1", obj="Amazon and UnknownCo")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-amazon")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_no_parts_match_yields_no_edges(self):
        # Neither "X" nor "Y" has a mention in the chunk.
        mentions = [_mention("Amazon", "m-amazon")]
        claims = [_claim("c1", obj="X and Y")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- deduplication within a slot ---

    def test_list_parts_resolving_to_same_mention_deduplicated(self):
        # "IBM and ibm" splits into ["IBM", "ibm"]; both casefold to "ibm"
        # and match the single mention "IBM" → only one edge emitted.
        mentions = [_mention("IBM", "m-ibm")]
        claims = [_claim("c1", subject="IBM and ibm")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-ibm")

    # --- whole-slot match takes priority over list splitting ---

    def test_whole_slot_match_prevents_list_split(self):
        # "Amazon and eBay" is also a mention name itself — whole-slot raw_exact
        # fires first; list_split must NOT be attempted.
        mentions = [
            _mention("Amazon and eBay", "m-combined"),
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay")]
        edges = build_participation_edges(claims, mentions)
        # raw_exact match on "Amazon and eBay" → one edge, not three.
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-combined")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_RAW_EXACT)

    def test_ambiguous_whole_slot_does_not_trigger_list_split(self):
        # Two mentions named "Amazon and eBay" → whole-slot match is ambiguous
        # (MATCH_OUTCOME_AMBIGUOUS).  list_split must NOT be attempted, so no
        # individual "Amazon" / "eBay" edges should be created either.
        mentions = [
            _mention("Amazon and eBay", "m-combined-1"),
            _mention("Amazon and eBay", "m-combined-2"),
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay")]
        edges = build_participation_edges(claims, mentions)
        # Whole-slot is ambiguous — list-split must NOT fire.
        self.assertEqual(edges, [])

    def test_ambiguous_whole_slot_casefold_does_not_trigger_list_split(self):
        # "google and facebook" casefolds to match two mentions ("Google and Facebook"
        # and "GOOGLE AND FACEBOOK") — whole-slot is casefold-ambiguous.
        # list_split must NOT be attempted.
        mentions = [
            _mention("Google and Facebook", "m-1"),
            _mention("GOOGLE AND FACEBOOK", "m-2"),
            _mention("Google", "m-google"),
            _mention("Facebook", "m-fb"),
        ]
        claims = [_claim("c1", subject="google and facebook")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- list-split with casefold/normalized sub-matching ---

    def test_list_split_parts_matched_via_casefold(self):
        # "google and FACEBOOK": parts are "google" and "FACEBOOK";
        # both match via casefold.
        mentions = [
            _mention("Google", "m-g"),
            _mention("Facebook", "m-fb"),
        ]
        claims = [_claim("c1", subject="google and FACEBOOK")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-g", "m-fb"})
        # All via list_split, not individual strategies.
        for e in edges:
            self.assertEqual(e["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_list_split_parts_matched_via_normalized(self):
        # "Müller and Café": parts match mentions after normalization.
        mentions = [
            _mention("Müller", "m-muller"),
            _mention("Café", "m-cafe"),
        ]
        claims = [_claim("c1", subject="Muller and Cafe")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-muller", "m-cafe"})

    # --- run-id scoping still enforced for list-split ---

    def test_list_split_respects_run_id_scoping(self):
        # Mentions are in a different run; no edges should be created even
        # for correctly split parts.
        mentions = [
            _mention("Amazon", "m-amazon", run_id="run-B"),
            _mention("eBay", "m-ebay", run_id="run-B"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay", run_id="run-A")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- mixed subject/object with list split ---

    def test_subject_list_split_and_object_direct_match(self):
        # Subject: "Google and Apple" (list split); Object: "revenue" (raw_exact).
        mentions = [
            _mention("Google", "m-g"),
            _mention("Apple", "m-apple"),
            _mention("revenue", "m-revenue"),
        ]
        claims = [_claim("c1", subject="Google and Apple", obj="revenue")]
        edges = build_participation_edges(claims, mentions)
        subj_edges = [e for e in edges if e["slot"] == "subject"]
        obj_edges = [e for e in edges if e["slot"] == "object"]
        self.assertEqual(len(subj_edges), 2)
        self.assertEqual(len(obj_edges), 1)
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in subj_edges))
        self.assertEqual(obj_edges[0]["match_method"], MATCH_METHOD_RAW_EXACT)

    # --- idempotency for list-split results ---

    def test_list_split_result_idempotent(self):
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay")]
        self.assertEqual(
            build_participation_edges(claims, mentions),
            build_participation_edges(claims, mentions),
        )

    # --- no fallback to chunk co-location ---

    def test_no_edge_when_slot_text_has_no_matching_parts(self):
        # When none of the split parts (or the whole text) matches any mention
        # in the chunk, no edge is created — there is no chunk co-location fallback.
        mentions = [_mention("OpenAI", "m-openai")]
        claims = [_claim("c1", obj="Amazon and eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- three-way conjunction ---

    def test_three_part_and_yields_three_edges(self):
        mentions = [
            _mention("Google", "m-g"),
            _mention("Apple", "m-apple"),
            _mention("Microsoft", "m-ms"),
        ]
        claims = [_claim("c1", subject="Google and Apple and Microsoft")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 3)
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    # --- Oxford-comma lists ---

    def test_oxford_comma_and_yields_three_edges(self):
        # "Amazon, eBay, and Google" — the ", and " separator must be consumed
        # as a unit so the last part is "Google", not "and Google".
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
            _mention("Google", "m-google"),
        ]
        claims = [_claim("c1", obj="Amazon, eBay, and Google")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 3)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay", "m-google"})
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    def test_oxford_comma_or_yields_three_edges(self):
        mentions = [
            _mention("Tesla", "m-tesla"),
            _mention("Ford", "m-ford"),
            _mention("GM", "m-gm"),
        ]
        claims = [_claim("c1", obj="Tesla, Ford, or GM")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 3)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-tesla", "m-ford", "m-gm"})

    # --- slash-delimited lists (new: supported with surrounding whitespace) ---

    def test_slash_delimited_two_entities_yields_two_edges(self):
        # "Amazon / eBay" → two list_split edges.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon / eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay"})
        for e in edges:
            self.assertEqual(e["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_slash_delimited_three_entities_yields_three_edges(self):
        # "Amazon / eBay / Google" → three list_split edges.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
            _mention("Google", "m-google"),
        ]
        claims = [_claim("c1", obj="Amazon / eBay / Google")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 3)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay", "m-google"})
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    def test_slash_without_spaces_does_not_split(self):
        # "Amazon/eBay" — no spaces around slash → treated as a single slot text;
        # no edge created because "Amazon/eBay" has no matching mention.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon/eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- semicolon-delimited lists (new: supported with trailing whitespace) ---

    def test_semicolon_delimited_two_entities_yields_two_edges(self):
        # "Amazon; eBay" → two list_split edges.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon; eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay"})
        for e in edges:
            self.assertEqual(e["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_semicolon_delimited_three_entities_yields_three_edges(self):
        # "Amazon; eBay; Google" → three list_split edges.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
            _mention("Google", "m-google"),
        ]
        claims = [_claim("c1", subject="Amazon; eBay; Google")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 3)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay", "m-google"})
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    def test_semicolon_without_space_does_not_split(self):
        # "Amazon;eBay" — no trailing space → not a list separator.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon;eBay")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])


# ---------------------------------------------------------------------------
# Tests for explicitly unsupported composite argument forms
# ---------------------------------------------------------------------------


class TestBuildParticipationEdgesUnsupportedForms(unittest.TestCase):
    """Documents explicitly unsupported composite argument patterns.

    These tests verify that the matching pipeline does not silently invent
    matches for argument patterns that require deeper linguistic analysis
    (parenthetical qualifiers, grouped qualifiers, appositives, nested
    qualifiers).  Where partial recovery is the documented behavior (i.e.
    the entity name is extracted while the qualifying phrase is discarded),
    the test confirms exactly how many edges are created and which mentions
    they point to.

    No new matching behavior is added for these forms.  Tests in this class
    serve as precision regression guards and as machine-readable documentation
    of the boundary between supported and unsupported patterns.
    """

    # --- parenthetical qualifiers ---

    def test_parenthetical_qualifier_not_resolved_to_base_mention(self):
        # "Amazon (AWS) and Google": splits into ["Amazon (AWS)", "Google"].
        # "Amazon (AWS)" does NOT match mention "Amazon" — parenthetical
        # qualifier stripping is intentionally unsupported.
        # "Google" DOES match normally → one edge for Google only.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("Google", "m-google"),
        ]
        claims = [_claim("c1", obj="Amazon (AWS) and Google")]
        edges = build_participation_edges(claims, mentions)
        # Only Google is recovered; Amazon (AWS) is not resolved.
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-google")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_parenthetical_only_slot_yields_no_edge(self):
        # "Amazon (AWS)" as the whole slot — no match because the parenthetical
        # suffix prevents raw/casefold/normalized match against mention "Amazon".
        mentions = [_mention("Amazon", "m-amazon")]
        claims = [_claim("c1", obj="Amazon (AWS)")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    # --- grouped qualifiers ---

    def test_grouped_qualifier_partial_recovery(self):
        # "Amazon and eBay subsidiaries": splits into ["Amazon", "eBay subsidiaries"].
        # "Amazon" matches; "eBay subsidiaries" does NOT match mention "eBay".
        # Recovering "eBay" from "eBay subsidiaries" is intentionally unsupported.
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay subsidiaries")]
        edges = build_participation_edges(claims, mentions)
        # Only Amazon is recovered; "eBay subsidiaries" is not resolved.
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-amazon")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_grouped_qualifier_both_sides_qualified_yields_no_edge(self):
        # "U.S. and European regulators" — neither part matches any mention.
        mentions = [
            _mention("U.S.", "m-us"),
            _mention("European", "m-eu"),
        ]
        claims = [_claim("c1", subject="U.S. and European regulators")]
        edges = build_participation_edges(claims, mentions)
        # "U.S." matches its mention; "European regulators" does not match "European".
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-us")

    # --- appositives ---

    def test_appositive_entity_recovered_descriptor_discarded(self):
        # "Xapo, a digital-assets company": splits via comma into
        # ["Xapo", "a digital-assets company"].
        # "Xapo" matches → one edge.  The appositive descriptor does not match
        # any mention and is silently skipped (partial-match behavior).
        mentions = [_mention("Xapo", "m-xapo")]
        claims = [_claim("c1", subject="Xapo, a digital-assets company")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-xapo")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_LIST_SPLIT)

    def test_appositive_mercadolibre_descriptor_discarded(self):
        # "MercadoLibre, the ecommerce giant": same pattern as above.
        mentions = [_mention("MercadoLibre", "m-ml")]
        claims = [_claim("c1", subject="MercadoLibre, the ecommerce giant")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-ml")
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_LIST_SPLIT)

    # --- nested/mixed constructions ---

    def test_nested_qualifier_entities_recovered_qualified_part_not(self):
        # "Amazon, eBay, and Google subsidiaries": splits into
        # ["Amazon", "eBay", "Google subsidiaries"].
        # "Amazon" and "eBay" match; "Google subsidiaries" does NOT match "Google".
        mentions = [
            _mention("Amazon", "m-amazon"),
            _mention("eBay", "m-ebay"),
            _mention("Google", "m-google"),
        ]
        claims = [_claim("c1", obj="Amazon, eBay, and Google subsidiaries")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        mention_ids = {e["mention_id"] for e in edges}
        self.assertEqual(mention_ids, {"m-amazon", "m-ebay"})
        self.assertTrue(all(e["match_method"] == MATCH_METHOD_LIST_SPLIT for e in edges))

    def test_mixed_conjunction_multiple_qualifiers(self):
        # "MercadoLibre and Nubank investors and advisors":
        # splits into ["MercadoLibre", "Nubank investors", "advisors"].
        # "MercadoLibre" matches; "Nubank investors" does NOT match "Nubank";
        # "advisors" does not match any entity mention.
        mentions = [
            _mention("MercadoLibre", "m-ml"),
            _mention("Nubank", "m-nubank"),
        ]
        claims = [_claim("c1", subject="MercadoLibre and Nubank investors and advisors")]
        edges = build_participation_edges(claims, mentions)
        # Only MercadoLibre is recovered.
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["mention_id"], "m-ml")


# ---------------------------------------------------------------------------
# Tests for build_participation_edges_with_metrics and ParticipationMatchMetrics
# ---------------------------------------------------------------------------


class TestBuildParticipationEdgesWithMetrics(unittest.TestCase):
    """Unit tests for build_participation_edges_with_metrics.

    Verifies that the edge rows returned are identical to build_participation_edges
    and that the ParticipationMatchMetrics fields correctly reflect matching outcomes.
    """

    # --- return type and parity with build_participation_edges ---

    def test_returns_tuple_of_edges_and_metrics(self):
        mentions = [_mention("Google", "m-google")]
        claims = [_claim("c1", subject="Google")]
        result = build_participation_edges_with_metrics(claims, mentions)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        edge_rows, metrics = result
        self.assertIsInstance(edge_rows, list)
        self.assertIsInstance(metrics, ParticipationMatchMetrics)

    def test_edge_rows_identical_to_build_participation_edges(self):
        # The edge rows returned by the instrumented version must be exactly
        # the same as those returned by the non-instrumented version.
        mentions = [
            _mention("Google", "m-google"),
            _mention("Apple", "m-apple"),
        ]
        claims = [
            _claim("c1", subject="Google", obj="Apple"),
            _claim("c2", subject="nobody"),
        ]
        plain_rows = build_participation_edges(claims, mentions)
        instrumented_rows, _ = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(plain_rows, instrumented_rows)

    def test_empty_inputs_return_empty_edges_and_zero_metrics(self):
        edge_rows, metrics = build_participation_edges_with_metrics([], [])
        self.assertEqual(edge_rows, [])
        self.assertEqual(metrics.claims_processed, 0)
        self.assertEqual(metrics.slots_processed, 0)
        self.assertEqual(metrics.edges_by_method, {})
        self.assertEqual(metrics.unmatched_slots, 0)
        self.assertEqual(metrics.ambiguous_slots, 0)
        self.assertEqual(metrics.list_split_suppressed, 0)
        self.assertEqual(metrics.claims_with_any_edge, 0)
        self.assertEqual(metrics.claims_with_no_edges, 0)

    # --- claims_processed and claims_with_any_edge ---

    def test_claims_processed_counts_all_supplied_claim_rows(self):
        # Two claims; one has a matching mention, the other does not.
        mentions = [_mention("Google", "m-g")]
        claims = [
            _claim("c1", subject="Google"),
            _claim("c2", subject="nobody"),
        ]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.claims_processed, 2)

    def test_claims_with_any_edge_and_no_edges(self):
        mentions = [_mention("Google", "m-g")]
        claims = [
            _claim("c1", subject="Google"),   # will get an edge
            _claim("c2", subject="nobody"),   # no matching mention
        ]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.claims_with_any_edge, 1)
        self.assertEqual(metrics.claims_with_no_edges, 1)

    def test_claims_with_no_edges_equals_processed_minus_any_edge(self):
        mentions = [_mention("IBM", "m-ibm"), _mention("Apple", "m-apple")]
        claims = [
            _claim("c1", subject="IBM"),
            _claim("c2", subject="Apple"),
            _claim("c3", subject="Absent"),
        ]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(
            metrics.claims_with_no_edges,
            metrics.claims_processed - metrics.claims_with_any_edge,
        )

    # --- slots_processed ---

    def test_slots_processed_counts_non_empty_slots_with_candidates(self):
        # One claim with both subject and object → 2 slots; only claims with
        # candidate mentions enter the slot loop.
        mentions = [_mention("Google", "m-g"), _mention("revenue", "m-r")]
        claims = [_claim("c1", subject="Google", obj="revenue")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.slots_processed, 2)

    def test_claim_with_no_candidate_mentions_contributes_zero_slots(self):
        # Mention is in chunk-99; claim is in chunk-1 → no candidates.
        mentions = [_mention("Google", "m-g", chunk_ids=["chunk-99"])]
        claims = [_claim("c1", subject="Google", chunk_ids=["chunk-1"])]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.slots_processed, 0)

    # --- edges_by_method ---

    def test_edges_by_method_raw_exact(self):
        mentions = [_mention("IBM", "m-ibm")]
        claims = [_claim("c1", subject="IBM")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_RAW_EXACT, 0), 1)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_CASEFOLD_EXACT, 0), 0)

    def test_edges_by_method_casefold_exact(self):
        mentions = [_mention("IBM", "m-ibm")]
        claims = [_claim("c1", subject="ibm")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_CASEFOLD_EXACT, 0), 1)

    def test_edges_by_method_normalized_exact(self):
        mentions = [_mention("Müller", "m1")]
        claims = [_claim("c1", subject="Muller")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_NORMALIZED_EXACT, 0), 1)

    def test_edges_by_method_list_split(self):
        mentions = [_mention("Amazon", "m-a"), _mention("eBay", "m-e")]
        claims = [_claim("c1", obj="Amazon and eBay")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_LIST_SPLIT, 0), 2)

    def test_edges_by_method_mixed_methods(self):
        # Subject: raw_exact; Object: list_split (2 edges).
        mentions = [
            _mention("Google", "m-g"),
            _mention("Amazon", "m-a"),
            _mention("eBay", "m-e"),
        ]
        claims = [_claim("c1", subject="Google", obj="Amazon and eBay")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_RAW_EXACT, 0), 1)
        self.assertEqual(metrics.edges_by_method.get(MATCH_METHOD_LIST_SPLIT, 0), 2)

    # --- edges_by_role ---

    def test_edges_by_role_subject_only(self):
        mentions = [_mention("Google", "m-g")]
        claims = [_claim("c1", subject="Google")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_role.get(ROLE_SUBJECT, 0), 1)
        self.assertEqual(metrics.edges_by_role.get(ROLE_OBJECT, 0), 0)

    def test_edges_by_role_object_only(self):
        mentions = [_mention("revenue", "m-r")]
        claims = [_claim("c1", obj="revenue")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_role.get(ROLE_OBJECT, 0), 1)
        self.assertEqual(metrics.edges_by_role.get(ROLE_SUBJECT, 0), 0)

    def test_edges_by_role_subject_and_object(self):
        mentions = [_mention("Google", "m-g"), _mention("Apple", "m-a")]
        claims = [_claim("c1", subject="Google", obj="Apple")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.edges_by_role.get(ROLE_SUBJECT, 0), 1)
        self.assertEqual(metrics.edges_by_role.get(ROLE_OBJECT, 0), 1)

    # --- edges_by_role_and_method ---

    def test_edges_by_role_and_method_structure(self):
        mentions = [_mention("IBM", "m-ibm"), _mention("revenue", "m-r")]
        claims = [_claim("c1", subject="IBM", obj="revenue")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertIn(ROLE_SUBJECT, metrics.edges_by_role_and_method)
        self.assertIn(ROLE_OBJECT, metrics.edges_by_role_and_method)
        self.assertEqual(
            metrics.edges_by_role_and_method[ROLE_SUBJECT].get(MATCH_METHOD_RAW_EXACT, 0), 1
        )
        self.assertEqual(
            metrics.edges_by_role_and_method[ROLE_OBJECT].get(MATCH_METHOD_RAW_EXACT, 0), 1
        )

    def test_edges_by_role_and_method_list_split_subject(self):
        mentions = [_mention("Google", "m-g"), _mention("Apple", "m-a")]
        claims = [_claim("c1", subject="Google and Apple")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(
            metrics.edges_by_role_and_method.get(ROLE_SUBJECT, {}).get(MATCH_METHOD_LIST_SPLIT, 0),
            2,
        )

    # --- unmatched_slots ---

    def test_unmatched_slots_when_no_mention_found(self):
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c1", subject="Google")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.unmatched_slots, 1)
        self.assertEqual(metrics.unmatched_by_role.get(ROLE_SUBJECT, 0), 1)

    def test_unmatched_by_role_object(self):
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c1", obj="unknown entity")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.unmatched_slots, 1)
        self.assertEqual(metrics.unmatched_by_role.get(ROLE_OBJECT, 0), 1)

    def test_no_unmatched_when_all_slots_matched(self):
        mentions = [_mention("Google", "m-g"), _mention("Apple", "m-a")]
        claims = [_claim("c1", subject="Google", obj="Apple")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.unmatched_slots, 0)
        self.assertEqual(metrics.unmatched_by_role, {})

    def test_unmatched_after_list_split_parts_all_fail(self):
        # "X and Y" — no parts match → unmatched
        mentions = [_mention("Amazon", "m-a")]
        claims = [_claim("c1", obj="X and Y")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.unmatched_slots, 1)
        self.assertEqual(metrics.unmatched_by_role.get(ROLE_OBJECT, 0), 1)

    def test_partial_list_split_success_not_counted_as_unmatched(self):
        # "Amazon and UnknownCo": Amazon matches → slot has at least one edge
        # → not counted as unmatched.
        mentions = [_mention("Amazon", "m-a")]
        claims = [_claim("c1", obj="Amazon and UnknownCo")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.unmatched_slots, 0)

    # --- ambiguous_slots and list_split_suppressed ---

    def test_ambiguous_slot_counted(self):
        # Two mentions named identically → raw_exact ambiguous
        mentions = [_mention("ABC", "m1"), _mention("ABC", "m2")]
        claims = [_claim("c1", subject="ABC")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.ambiguous_slots, 1)
        self.assertEqual(metrics.ambiguous_by_role.get(ROLE_SUBJECT, 0), 1)

    def test_ambiguous_slot_suppresses_list_split(self):
        # Ambiguous whole-slot → list_split_suppressed incremented, not unmatched.
        mentions = [
            _mention("Amazon and eBay", "m-comb-1"),
            _mention("Amazon and eBay", "m-comb-2"),
            _mention("Amazon", "m-a"),
            _mention("eBay", "m-e"),
        ]
        claims = [_claim("c1", obj="Amazon and eBay")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.ambiguous_slots, 1)
        self.assertEqual(metrics.list_split_suppressed, 1)
        self.assertEqual(metrics.list_split_suppressed_by_role.get(ROLE_OBJECT, 0), 1)
        # Ambiguous slot must NOT be counted as unmatched.
        self.assertEqual(metrics.unmatched_slots, 0)

    def test_list_split_suppressed_equals_ambiguous_slots(self):
        # By definition: every ambiguous slot suppresses a list-split attempt.
        mentions = [
            _mention("Hello", "m1"),
            _mention("HELLO", "m2"),
            _mention("profit", "m-p"),
        ]
        claims = [_claim("c1", subject="hello", obj="profit")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        # Subject is ambiguous; object matches uniquely.
        self.assertEqual(metrics.ambiguous_slots, metrics.list_split_suppressed)

    def test_no_ambiguity_when_all_slots_uniquely_matched(self):
        mentions = [_mention("IBM", "m-ibm")]
        claims = [_claim("c1", subject="IBM")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(metrics.ambiguous_slots, 0)
        self.assertEqual(metrics.list_split_suppressed, 0)

    # --- sample IDs ---

    def test_sample_list_split_claim_ids_populated(self):
        mentions = [_mention("Amazon", "m-a"), _mention("eBay", "m-e")]
        claims = [_claim("c1", obj="Amazon and eBay")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertIn("c1", metrics.sample_list_split_claim_ids)

    def test_sample_unmatched_claim_ids_populated(self):
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c-unmatched", subject="Google")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertIn("c-unmatched", metrics.sample_unmatched_claim_ids)

    def test_sample_ambiguous_claim_ids_populated(self):
        mentions = [_mention("ABC", "m1"), _mention("ABC", "m2")]
        claims = [_claim("c-amb", subject="ABC")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertIn("c-amb", metrics.sample_ambiguous_claim_ids)

    def test_sample_ids_not_duplicated(self):
        # Same claim contributes two list_split slots; its ID must appear once
        # in the sample list (no duplicates).
        mentions = [
            _mention("Google", "m-g"),
            _mention("Apple", "m-a"),
            _mention("Amazon", "m-amz"),
            _mention("eBay", "m-e"),
        ]
        claims = [_claim("c1", subject="Google and Apple", obj="Amazon and eBay")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(
            len(metrics.sample_list_split_claim_ids),
            len(set(metrics.sample_list_split_claim_ids)),
        )

    # --- to_dict ---

    def test_to_dict_returns_json_serialisable_dict(self):
        import json
        mentions = [_mention("IBM", "m-ibm")]
        claims = [_claim("c1", subject="IBM")]
        _, metrics = build_participation_edges_with_metrics(claims, mentions)
        d = metrics.to_dict()
        self.assertIsInstance(d, dict)
        # Must be serialisable without raising.
        serialised = json.dumps(d)
        self.assertIn("edges_by_method", serialised)

    def test_to_dict_includes_all_expected_keys(self):
        _, metrics = build_participation_edges_with_metrics([], [])
        d = metrics.to_dict()
        expected_keys = {
            "claims_processed",
            "slots_processed",
            "edges_by_method",
            "edges_by_role",
            "edges_by_role_and_method",
            "unmatched_slots",
            "unmatched_by_role",
            "ambiguous_slots",
            "ambiguous_by_role",
            "list_split_suppressed",
            "list_split_suppressed_by_role",
            "claims_with_any_edge",
            "claims_with_no_edges",
            "sample_list_split_claim_ids",
            "sample_unmatched_claim_ids",
            "sample_ambiguous_claim_ids",
        }
        self.assertTrue(expected_keys.issubset(d.keys()))

    # --- idempotency ---

    def test_metrics_idempotent_across_repeated_calls(self):
        mentions = [_mention("Google", "m-g"), _mention("revenue", "m-r")]
        claims = [_claim("c1", subject="Google", obj="revenue")]
        _, m1 = build_participation_edges_with_metrics(claims, mentions)
        _, m2 = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(m1.to_dict(), m2.to_dict())

    # --- run_id scoping preserved ---

    def test_metrics_respect_run_id_scoping(self):
        # Mention in run-B must not match claim in run-A.
        mentions = [_mention("Google", "m-g", run_id="run-B")]
        claims = [_claim("c1", subject="Google", run_id="run-A")]
        edges, metrics = build_participation_edges_with_metrics(claims, mentions)
        self.assertEqual(edges, [])
        self.assertEqual(metrics.edges_by_method, {})
        # The claim had no candidate mentions → slots_processed == 0
        self.assertEqual(metrics.slots_processed, 0)
