"""Tests for the claim participation edge matching stage."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

import neo4j

from demo.stages.claim_participation import (
    EDGE_TYPE_HAS_OBJECT,
    EDGE_TYPE_HAS_SUBJECT,
    MATCH_METHOD_CASEFOLD_EXACT,
    MATCH_METHOD_NORMALIZED_EXACT,
    MATCH_METHOD_RAW_EXACT,
    build_participation_edges,
    match_slot_to_mention,
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
        mentions = [_flat("ABC", "m1"), _flat("ABC", "m2")]
        result, method = match_slot_to_mention("ABC", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

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
        mentions = [_flat("Hello", "m1"), _flat("HELLO", "m2")]
        result, method = match_slot_to_mention("hello", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

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
        mentions = [_flat("Café", "m1"), _flat("CAFÉ", "m2")]
        result, method = match_slot_to_mention("cafe", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

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
        mentions = [_flat("ABC", "m1"), _flat("ABC", "m2")]
        result, method = match_slot_to_mention("ABC", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

    def test_casefold_ambiguity_stops_search(self):
        # Two mentions with different raw names that casefold identically
        # — ambiguous at casefold level; no edge created.
        mentions = [_flat("Hello", "m1"), _flat("HELLO", "m2")]
        result, method = match_slot_to_mention("hello", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)


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
        self.assertEqual(subj["edge_type"], EDGE_TYPE_HAS_SUBJECT)
        self.assertEqual(subj["match_method"], MATCH_METHOD_RAW_EXACT)
        self.assertEqual(obj_["mention_id"], "m-revenue")
        self.assertEqual(obj_["edge_type"], EDGE_TYPE_HAS_OBJECT)

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

    def _make_driver(self) -> MagicMock:
        driver = MagicMock(spec=neo4j.Driver)
        driver.execute_query = MagicMock(return_value=MagicMock())
        return driver

    def test_write_subject_and_object_edges(self):
        driver = self._make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m-subject",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            },
            {
                "claim_id": "c1",
                "mention_id": "m-object",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "object",
                "match_method": MATCH_METHOD_CASEFOLD_EXACT,
                "edge_type": EDGE_TYPE_HAS_OBJECT,
            },
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 2)

    def test_write_only_subject_edges(self):
        driver = self._make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": None,
                "slot": "subject",
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 1)

    def test_write_only_object_edges(self):
        driver = self._make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": None,
                "slot": "object",
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_OBJECT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(driver.execute_query.call_count, 1)

    def test_write_empty_edge_rows_no_queries(self):
        driver = self._make_driver()
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=[])
        driver.execute_query.assert_not_called()

    def test_parameters_passed_to_driver(self):
        driver = self._make_driver()
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": "uri://x",
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        _args, kwargs = driver.execute_query.call_args
        self.assertEqual(kwargs.get("database_"), "neo4j")
        passed_rows = kwargs.get("parameters_", {}).get("rows", [])
        self.assertEqual(len(passed_rows), 1)
        self.assertEqual(passed_rows[0]["claim_id"], "c1")
        self.assertEqual(passed_rows[0]["match_method"], MATCH_METHOD_RAW_EXACT)


if __name__ == "__main__":
    unittest.main()
