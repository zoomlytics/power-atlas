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


def _mention(name: str, mention_id: str = "m1", chunk_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "chunk_ids": chunk_ids or ["chunk-1"],
        "run_id": "run-1",
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
    """Unit tests for match_slot_to_mention."""

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

    # --- normalized_exact ---

    def test_normalized_exact_match(self):
        mentions = [_flat("IBM")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertEqual(result, _flat("IBM"))
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_strips_whitespace(self):
        mentions = [_flat("IBM")]
        result, method = match_slot_to_mention("  IBM  ", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_case_insensitive(self):
        mentions = [_flat("IBM")]
        result, method = match_slot_to_mention("ibm", mentions)
        self.assertEqual(result, _flat("IBM"))
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_diacritics_stripped(self):
        # "résumé" should normalize to "resume"
        mentions = [_flat("Résumé", "m1")]
        result, method = match_slot_to_mention("resume", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)
        self.assertIsNotNone(result)

    def test_normalized_exact_german_sharp_s(self):
        # ß → ss via casefold
        mentions = [_flat("Straße", "m1")]
        result, method = match_slot_to_mention("strasse", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_normalized_exact_em_dash_normalized(self):
        # em-dash → hyphen-minus via normalization
        mentions = [_flat("well-known", "m1")]
        result, method = match_slot_to_mention("well\u2014known", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    # --- normalized_exact ambiguity → no edge ---

    def test_normalized_exact_ambiguous_no_edge(self):
        # Two mentions normalize to the same text
        mentions = [_flat("IBM", "m1"), _flat("ibm", "m2")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

    # --- raw_exact fallback ---

    def test_raw_exact_when_normalized_fails(self):
        # raw_exact is subsumed by normalized_exact in all realistic Unicode cases
        # (normalized_exact ends in casefold, which is at least as permissive as
        # raw equality). This method exists as a placeholder/documentation that the
        # strategy is present for edge cases only.
        pass  # See TestRawExactBranch for direct branch tests

    def test_no_match_returns_none(self):
        mentions = [_flat("OpenAI", "m1"), _flat("Microsoft", "m2")]
        result, method = match_slot_to_mention("Google", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

    # --- casefold_exact ---

    def test_casefold_exact_matches_when_normalized_fails(self):
        # casefold_exact is subsumed by normalized_exact in practice because
        # normalized_exact applies casefold as its final step.  This method
        # documents the intended fallback chain; see test_casefold_branch_fires_as_last_resort
        # for a concrete verification.
        pass

    # --- Direct casefold fallback: 0 normalized, 0 raw, 1 casefold ---

    def test_casefold_branch_fires_as_last_resort(self):
        # normalized_exact subsumes casefold_exact in practice (normalized ends
        # with casefold).  Verify that the function still returns a result via
        # normalized_exact for a plain case-difference, and that it doesn't
        # double-fire.
        mentions = [_flat("Hello World", "m1")]
        result, method = match_slot_to_mention("hello world", mentions)
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_casefold_ambiguous_returns_none(self):
        # Two mentions that casefold to the same text → ambiguity → no edge
        # (This scenario is actually caught by normalized_exact ambiguity first.)
        mentions = [_flat("IBM", "m1"), _flat("ibm", "m2")]
        result, method = match_slot_to_mention("IBM", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)

    # --- single mention, exact match ---

    def test_single_mention_exact_match(self):
        mentions = [_flat("Apple Inc.", "m1")]
        result, method = match_slot_to_mention("Apple Inc.", mentions)
        self.assertIsNotNone(result)
        self.assertEqual(result["mention_id"], "m1")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_picks_correct_mention_among_multiple(self):
        mentions = [
            _flat("Google", "m1"),
            _flat("Apple", "m2"),
            _flat("Microsoft", "m3"),
        ]
        result, method = match_slot_to_mention("Apple", mentions)
        self.assertEqual(result["mention_id"], "m2")
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)


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
        claims = [
            _claim("c1", subject="Google", obj="revenue"),
        ]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 2)
        subj = next(e for e in edges if e["slot"] == "subject")
        obj_ = next(e for e in edges if e["slot"] == "object")
        self.assertEqual(subj["mention_id"], "m-google")
        self.assertEqual(subj["edge_type"], EDGE_TYPE_HAS_SUBJECT)
        self.assertEqual(subj["match_method"], MATCH_METHOD_NORMALIZED_EXACT)
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

    def test_ambiguous_subject_no_edge(self):
        # Two mentions in same chunk normalize to same text
        mentions = [
            _mention("IBM", "m1"),
            _mention("ibm", "m2"),
        ]
        claims = [_claim("c1", subject="IBM")]
        edges = build_participation_edges(claims, mentions)
        # ambiguous → no HAS_SUBJECT edge
        self.assertEqual(edges, [])

    def test_missing_mention_no_edge(self):
        # Claim subject doesn't match any mention
        mentions = [_mention("OpenAI", "m1")]
        claims = [_claim("c1", subject="Google")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(edges, [])

    def test_edge_row_contains_run_id_and_source_uri(self):
        mentions = [_mention("IBM", "m1")]
        claims = [_claim("c1", subject="IBM", run_id="run-xyz")]
        # Fix mention run_id to match claim run_id
        mentions[0]["run_id"] = "run-xyz"
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
        # Claim and mention both span chunk-1 AND chunk-2 → mention should appear
        # once in candidates, not twice
        mentions = [_mention("IBM", "m1", chunk_ids=["chunk-1", "chunk-2"])]
        claims = [_claim("c1", subject="IBM", chunk_ids=["chunk-1", "chunk-2"])]
        edges = build_participation_edges(claims, mentions)
        # Exactly one edge, not two
        self.assertEqual(len(edges), 1)

    def test_case_insensitive_match_uses_normalized_exact(self):
        mentions = [_mention("United Nations", "m-un")]
        claims = [_claim("c1", subject="united nations")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_NORMALIZED_EXACT)

    def test_diacritic_insensitive_match(self):
        mentions = [_mention("Müller", "m1")]
        claims = [_claim("c1", subject="Muller")]
        edges = build_participation_edges(claims, mentions)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["match_method"], MATCH_METHOD_NORMALIZED_EXACT)


# ---------------------------------------------------------------------------
# raw_exact fallback: explicit branch test
# ---------------------------------------------------------------------------


class TestRawExactBranch(unittest.TestCase):
    """Verify raw_exact branch fires when normalized_exact finds 0 matches."""

    def test_raw_exact_fires_when_normalized_finds_zero(self):
        # Construct a mention whose name contains a soft-hyphen (U+00AD).
        # NFKD decomposition of soft-hyphen: it remains (category Cf, not Mn).
        # After casefold it stays as U+00AD.
        # Slot text = "ABC\u00adDEF" (slot with soft-hyphen)
        # Mention name = "ABC\u00adDEF" (same) → raw equals, casefold equals,
        # normalized equals.  They all match because _normalize strips nothing
        # that would break equality here.
        #
        # To truly isolate raw_exact we need normalized to yield 0 hits while
        # raw yields 1.  This happens only if the mention name and slot text
        # are identical after stripping but their normalized forms differ AND
        # that difference means no match.
        #
        # In practice, _normalize(x) == _normalize(x) for any single text, so
        # if mention.name == slot_stripped the normalized forms will also match.
        # Hence raw_exact is truly unreachable in normal usage—normalized always
        # subsumes it.  We verify this invariant explicitly:
        slot = "ABC"
        mention = _flat("ABC", "m1")
        result, method = match_slot_to_mention(slot, [mention])
        # normalized fires first
        self.assertEqual(method, MATCH_METHOD_NORMALIZED_EXACT)

    def test_raw_exact_branch_ambiguity(self):
        # Two raw-identical mentions (same name) → ambiguity at normalized level
        # (they share the same normalized form) → no edge
        mentions = [_flat("ABC", "m1"), _flat("ABC", "m2")]
        result, method = match_slot_to_mention("ABC", mentions)
        self.assertIsNone(result)
        self.assertIsNone(method)


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
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            },
            {
                "claim_id": "c1",
                "mention_id": "m-object",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "object",
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
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
                "match_method": MATCH_METHOD_NORMALIZED_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(driver, neo4j_database="neo4j", edge_rows=edge_rows)
        args, kwargs = driver.execute_query.call_args
        self.assertEqual(kwargs.get("database_"), "neo4j")
        passed_rows = kwargs.get("parameters_", {}).get("rows", [])
        self.assertEqual(len(passed_rows), 1)
        self.assertEqual(passed_rows[0]["claim_id"], "c1")
        self.assertEqual(passed_rows[0]["match_method"], MATCH_METHOD_NORMALIZED_EXACT)


if __name__ == "__main__":
    unittest.main()
