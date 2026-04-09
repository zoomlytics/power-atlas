"""Tests for the entity resolution stage."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from demo.contracts.runtime import Config
from demo.stages.entity_resolution import (
    _ALIGNMENT_VERSION,
    _CLUSTER_VERSION,
    _RESOLUTION_MODE_HYBRID,
    _RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    _align_clusters_to_canonical,
    _build_entity_type_report,
    _build_lookup_tables,
    _cluster_mentions_unstructured_only,
    _fuzzy_ratio,
    _is_abbreviation,
    _make_cluster_id,
    _normalize,
    _normalize_entity_type,
    _resolve_mention,
    _split_aliases,
    run_entity_resolution,
)


def _dry_run_config(tmp_path: Path) -> Config:
    return Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


def _live_config(tmp_path: Path) -> Config:
    return Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


def _make_neo4j_test_driver(
    mentions: list[dict[str, Any]],
    canonical_nodes: list[dict[str, Any]],
) -> MagicMock:
    """Build a mock neo4j.Driver that returns the given data."""

    # Records returned by execute_query must support subscript access (record["key"]).
    # Using a plain dict subclass is the simplest way to simulate Neo4j record behaviour
    # without pulling in the real driver.
    class _Record(dict):
        pass

    mention_records = [
        _Record(mention_id=m["mention_id"], name=m["name"], entity_type=m.get("entity_type"), source_uri=m.get("source_uri"))
        for m in mentions
    ]
    canonical_records = [
        _Record(entity_id=c["entity_id"], run_id=c.get("run_id", ""), name=c["name"],
                aliases=c.get("aliases"), dataset_id=c.get("dataset_id"))
        for c in canonical_nodes
    ]

    # Pre-compute alignment results to simulate graph-backed post-write queries.
    # This mirrors what run_entity_resolution does internally so that the mock
    # returns realistic counts rather than hard-coded zeros.
    _cluster_rows = _cluster_mentions_unstructured_only([
        {"mention_id": m["mention_id"], "name": m["name"],
         "entity_type": m.get("entity_type"), "source_uri": m.get("source_uri")}
        for m in mentions
    ])
    _cluster_entries: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _cluster_rows:
        # Use a placeholder run_id consistent with what the live path would use.
        # The cluster_id is computed in the real code with the actual run_id, but
        # for counting purposes we just need a stable key per unique cluster.
        _key = (row.get("entity_type") or "", row["normalized_text"])
        if _key not in _cluster_entries:
            _cluster_entries[_key] = {
                "cluster_id": _key,   # synthetic key only used for set comparisons
                "normalized_text": row["normalized_text"],
            }
    _unique_clusters = list(_cluster_entries.values())
    _total_cluster_count = len(_unique_clusters)
    _, _by_label, _by_alias = _build_lookup_tables([
        {"entity_id": c["entity_id"], "run_id": c.get("run_id", ""),
         "name": c["name"], "aliases": c.get("aliases")}
        for c in canonical_nodes
    ])
    _alignment_rows = _align_clusters_to_canonical(_unique_clusters, _by_label, _by_alias)
    _aligned_cluster_keys = {r["cluster_id"] for r in _alignment_rows}
    _aligned_cluster_count = len(_aligned_cluster_keys)
    _distinct_canonical_count = len(
        {(r["canonical_entity_id"], r["canonical_run_id"]) for r in _alignment_rows}
    )
    _mentions_in_aligned = sum(
        1 for row in _cluster_rows
        if (row.get("entity_type") or "", row["normalized_text"]) in _aligned_cluster_keys
    )
    # Compute breakdown from in-memory alignment rows (mirrors how the real graph
    # would aggregate alignment_method on ALIGNED_WITH edges per cluster).
    _alignment_breakdown: dict[str, int] = {}
    for _arow in _alignment_rows:
        _method = _arow.get("alignment_method") or "unknown"
        _alignment_breakdown[_method] = _alignment_breakdown.get(_method, 0) + 1

    # Track whether the expected write queries have actually been executed.
    member_of_written = False
    aligned_with_written = False

    def execute_query(query, parameters_=None, database_=None, routing_=None):
        nonlocal member_of_written, aligned_with_written

        # Detect MERGE write queries that create MEMBER_OF or ALIGNED_WITH relationships.
        if "MERGE" in query and "MEMBER_OF" in query:
            member_of_written = True
        if "MERGE" in query and "ALIGNED_WITH" in query:
            aligned_with_written = True

        # Post-write MEMBER_OF coverage count query (distinguished by the
        # "mentions_clustered" alias in the RETURN clause).
        if "mentions_clustered" in query:
            if member_of_written:
                return (
                    [_Record(mentions_clustered=len(mention_records), mentions_unclustered=0)],
                    None,
                    None,
                )
            # If no MEMBER_OF writes have occurred, report zero clustered mentions.
            return (
                [_Record(mentions_clustered=0, mentions_unclustered=len(mention_records))],
                None,
                None,
            )
        # Post-write total cluster count query.
        if "total_clusters" in query:
            if member_of_written:
                return (
                    [_Record(total_clusters=_total_cluster_count)],
                    None,
                    None,
                )
            return (
                [_Record(total_clusters=0)],
                None,
                None,
            )
        # Post-write ALIGNED_WITH cluster/canonical count query.
        if "aligned_clusters" in query:
            if aligned_with_written:
                return (
                    [_Record(
                        aligned_clusters=_aligned_cluster_count,
                        distinct_canonical_entities_aligned=_distinct_canonical_count,
                    )],
                    None,
                    None,
                )
            return (
                [_Record(
                    aligned_clusters=0,
                    distinct_canonical_entities_aligned=0,
                )],
                None,
                None,
            )
        # Post-write alignment_method breakdown query on ALIGNED_WITH edges.
        if "alignment_method" in query and "ALIGNED_WITH" in query:
            if aligned_with_written:
                return (
                    [
                        _Record(alignment_method=method, method_count=count)
                        for method, count in _alignment_breakdown.items()
                    ],
                    None,
                    None,
                )
            # No aligned edges written: no breakdown to report.
            return ([], None, None)
        # Post-write mentions-in-aligned-clusters count query.
        if "mentions_in_aligned" in query:
            if aligned_with_written:
                return (
                    [_Record(mentions_in_aligned=_mentions_in_aligned)],
                    None,
                    None,
                )
            return (
                [_Record(mentions_in_aligned=0)],
                None,
                None,
            )
        if "EntityMention" in query and "RETURN" in query:
            return (mention_records, None, None)
        if "CanonicalEntity" in query and "RETURN" in query:
            params = parameters_ or {}
            req_dataset = params.get("dataset_id")
            if req_dataset is not None:
                # Filter canonical records by dataset_id.  Records without a
                # dataset_id (i.e. dataset_id is None) are treated as dataset-agnostic
                # and match any dataset — this preserves backward compatibility for
                # existing tests that do not set dataset_id on canonical nodes.
                filtered = [
                    r for r in canonical_records
                    if r.get("dataset_id") is None or r.get("dataset_id") == req_dataset
                ]
                return (filtered, None, None)
            return (canonical_records, None, None)
        # write queries — return empty
        return ([], None, None)

    driver = MagicMock()
    driver.execute_query.side_effect = execute_query
    driver.__enter__ = lambda s: s
    driver.__exit__ = MagicMock(return_value=False)
    return driver


class TestNormalize(unittest.TestCase):
    def test_strips_and_lowercases(self):
        self.assertEqual(_normalize("  Hello World  "), "hello world")

    def test_empty_string(self):
        self.assertEqual(_normalize(""), "")

    # ------------------------------------------------------------------ #
    # Diacritic / accent removal
    # ------------------------------------------------------------------ #

    def test_strips_acute_accents(self):
        self.assertEqual(_normalize("résumé"), "resume")

    def test_strips_umlaut(self):
        self.assertEqual(_normalize("Müller"), "muller")

    def test_strips_mixed_accents(self):
        self.assertEqual(_normalize("naïve café"), "naive cafe")

    def test_accented_and_plain_normalize_equal(self):
        self.assertEqual(_normalize("Resumé"), _normalize("Resume"))

    # ------------------------------------------------------------------ #
    # NFKD / compatibility decomposition
    # ------------------------------------------------------------------ #

    def test_fi_ligature_becomes_fi(self):
        # U+FB01 LATIN SMALL LIGATURE FI → "fi"
        self.assertEqual(_normalize("\uFB01le"), "file")

    def test_fullwidth_latin_folds_to_ascii(self):
        # U+FF21 FULLWIDTH LATIN CAPITAL LETTER A → "a"
        self.assertEqual(_normalize("\uFF21BC"), "abc")

    # ------------------------------------------------------------------ #
    # Apostrophe / quote variants
    # ------------------------------------------------------------------ #

    def test_left_single_quotation_mark_normalised(self):
        # U+2018 LEFT SINGLE QUOTATION MARK
        self.assertEqual(_normalize("it\u2018s"), "it's")

    def test_right_single_quotation_mark_normalised(self):
        # U+2019 RIGHT SINGLE QUOTATION MARK
        self.assertEqual(_normalize("it\u2019s"), "it's")

    def test_modifier_letter_apostrophe_normalised(self):
        # U+02BC MODIFIER LETTER APOSTROPHE
        self.assertEqual(_normalize("it\u02BCs"), "it's")

    def test_grave_accent_apostrophe_normalised(self):
        # U+0060 GRAVE ACCENT used as apostrophe
        self.assertEqual(_normalize("it\u0060s"), "it's")

    # ------------------------------------------------------------------ #
    # Hyphen / dash variants
    # ------------------------------------------------------------------ #

    def test_en_dash_normalised_to_hyphen(self):
        # U+2013 EN DASH
        self.assertEqual(_normalize("state\u2013of\u2013the\u2013art"), "state-of-the-art")

    def test_em_dash_normalised_to_hyphen(self):
        # U+2014 EM DASH
        self.assertEqual(_normalize("well\u2014known"), "well-known")

    def test_minus_sign_normalised_to_hyphen(self):
        # U+2212 MINUS SIGN
        self.assertEqual(_normalize("t\u2212shirt"), "t-shirt")

    def test_non_breaking_hyphen_normalised(self):
        # U+2011 NON-BREAKING HYPHEN
        self.assertEqual(_normalize("non\u2011breaking"), "non-breaking")

    # ------------------------------------------------------------------ #
    # Whitespace collapse
    # ------------------------------------------------------------------ #

    def test_multiple_spaces_collapsed(self):
        self.assertEqual(_normalize("hello   world"), "hello world")

    def test_tab_collapsed_to_space(self):
        self.assertEqual(_normalize("hello\tworld"), "hello world")

    def test_newline_collapsed_to_space(self):
        self.assertEqual(_normalize("hello\nworld"), "hello world")

    def test_non_breaking_space_collapsed(self):
        # U+00A0 NO-BREAK SPACE
        self.assertEqual(_normalize("hello\u00A0world"), "hello world")

    def test_mixed_whitespace_collapsed(self):
        self.assertEqual(_normalize("  hello \t\n world  "), "hello world")

    # ------------------------------------------------------------------ #
    # Case-folding (casefold rather than lower)
    # ------------------------------------------------------------------ #

    def test_eszett_casefolded(self):
        # German ß should casefold to "ss"
        self.assertEqual(_normalize("Straße"), "strasse")

    def test_latin_extended_lowercase(self):
        # Basic non-ASCII lowercase still works
        self.assertEqual(_normalize("Ñoño"), "nono")


class TestSplitAliases(unittest.TestCase):
    def test_pipe_separated(self):
        result = _split_aliases("Foo|Bar|Baz")
        self.assertEqual(result, ["foo", "bar", "baz"])

    def test_comma_separated(self):
        result = _split_aliases("Foo,Bar,Baz")
        self.assertEqual(result, ["foo", "bar", "baz"])

    def test_none_returns_empty(self):
        self.assertEqual(_split_aliases(None), [])

    def test_empty_string_returns_empty(self):
        self.assertEqual(_split_aliases(""), [])

    def test_whitespace_stripped(self):
        result = _split_aliases(" Foo | Bar ")
        self.assertEqual(result, ["foo", "bar"])


class TestBuildLookupTables(unittest.TestCase):
    def setUp(self):
        self.canonical_nodes = [
            {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": "Ali|Alicia"},
            {"entity_id": "Q2", "run_id": "run-s1", "name": "Bob Corp", "aliases": "BC,Bobby Corp"},
            {"entity_id": "Q3", "run_id": "run-s1", "name": "Charlie", "aliases": None},
        ]

    def test_by_qid_keys(self):
        by_qid, _, _ = _build_lookup_tables(self.canonical_nodes)
        self.assertIn("Q1", by_qid)
        self.assertIn("Q2", by_qid)
        self.assertIn("Q3", by_qid)

    def test_by_label_normalized(self):
        _, by_label, _ = _build_lookup_tables(self.canonical_nodes)
        self.assertIn("alice", by_label)
        self.assertIn("bob corp", by_label)
        self.assertIn("charlie", by_label)

    def test_by_alias(self):
        _, _, by_alias = _build_lookup_tables(self.canonical_nodes)
        self.assertIn("ali", by_alias)
        self.assertIn("alicia", by_alias)
        self.assertIn("bc", by_alias)
        self.assertIn("bobby corp", by_alias)

    def test_empty_list(self):
        by_qid, by_label, by_alias = _build_lookup_tables([])
        self.assertEqual(by_qid, {})
        self.assertEqual(by_label, {})
        self.assertEqual(by_alias, {})

    def test_first_match_wins_for_label_duplicates(self):
        nodes = [
            {"entity_id": "Q10", "run_id": "run-s1", "name": "Duplicate", "aliases": None},
            {"entity_id": "Q11", "run_id": "run-s1", "name": "Duplicate", "aliases": None},
        ]
        _, by_label, _ = _build_lookup_tables(nodes)
        self.assertEqual(by_label["duplicate"]["entity_id"], "Q10")

    def test_first_match_wins_for_qid_duplicates(self):
        nodes = [
            {"entity_id": "Q10", "run_id": "run-a", "name": "Duplicate QID A", "aliases": None},
            {"entity_id": "Q10", "run_id": "run-b", "name": "Duplicate QID B", "aliases": None},
        ]
        by_qid, _, _ = _build_lookup_tables(nodes)
        # Expect the first occurrence of the duplicated entity_id to win.
        self.assertEqual(by_qid["Q10"]["run_id"], "run-a")
        self.assertEqual(by_qid["Q10"]["name"], "Duplicate QID A")

    def test_accented_alias_normalised(self):
        """Aliases with diacritics are stored under their normalised (diacritic-free) key."""
        nodes = [
            {"entity_id": "Q99", "run_id": "run-s1", "name": "Muller GmbH", "aliases": "Müller|Müller AG"},
        ]
        _, _, by_alias = _build_lookup_tables(nodes)
        # "Müller" → "muller" and "Müller AG" → "muller ag" after _normalize
        self.assertIn("muller", by_alias)
        self.assertIn("muller ag", by_alias)
        # The raw accented form should NOT be a key
        self.assertNotIn("müller", by_alias)
        self.assertNotIn("müller ag", by_alias)


class TestResolveMention(unittest.TestCase):
    def setUp(self):
        canonical_nodes = [
            {"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": "D. Adams|Adams"},
            {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
        ]
        self.by_qid, self.by_label, self.by_alias = _build_lookup_tables(canonical_nodes)

    def test_qid_exact_match(self):
        mention = {"mention_id": "m1", "name": "Q42"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_method"], "qid_exact")
        self.assertEqual(result["canonical_entity_id"], "Q42")
        self.assertEqual(result["canonical_run_id"], "run-s1")
        self.assertEqual(result["resolution_confidence"], 1.0)

    def test_qid_pattern_match_no_canonical_falls_through_to_label_cluster(self):
        mention = {"mention_id": "m2", "name": "Q999"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["resolution_method"], "label_cluster")

    def test_label_exact_case_insensitive(self):
        mention = {"mention_id": "m3", "name": "douglas adams"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_method"], "label_exact")
        self.assertEqual(result["canonical_entity_id"], "Q42")
        self.assertEqual(result["canonical_run_id"], "run-s1")
        self.assertEqual(result["resolution_confidence"], 0.9)

    def test_alias_exact_match(self):
        mention = {"mention_id": "m4", "name": "Adams"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_method"], "alias_exact")
        self.assertEqual(result["canonical_entity_id"], "Q42")
        self.assertEqual(result["canonical_run_id"], "run-s1")
        self.assertEqual(result["resolution_confidence"], 0.8)

    def test_unresolved_falls_to_label_cluster(self):
        mention = {"mention_id": "m5", "name": "Unknown Entity XYZ"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["resolution_method"], "label_cluster")
        self.assertEqual(result["resolution_confidence"], 0.0)
        self.assertEqual(result["candidate_ids"], [])
        self.assertEqual(result["normalized_text"], "unknown entity xyz")

    def test_empty_name_is_unresolved(self):
        mention = {"mention_id": "m6", "name": ""}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])

    def test_unresolved_row_carries_entity_type(self):
        """Unresolved rows (label_cluster) must include normalized entity_type."""
        mention = {"mention_id": "m7", "name": "Nobody Known", "entity_type": "ORG"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertIn("entity_type", result)
        # "ORG" is normalized to "Organization"
        self.assertEqual(result["entity_type"], "Organization")

    def test_unresolved_qid_row_carries_entity_type(self):
        """Unresolved QID-pattern rows (no canonical match) must include entity_type."""
        mention = {"mention_id": "m8", "name": "Q99999", "entity_type": "concept"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertIn("entity_type", result)
        self.assertEqual(result["entity_type"], "concept")

    def test_alias_exact_accented_variant(self):
        """A mention with diacritics should resolve via alias_exact when the canonical
        entity lists the same accented form as an alias — both normalize to the same
        diacritic-free key."""
        canonical_nodes = [
            {"entity_id": "Q99", "run_id": "run-s1", "name": "Muller GmbH", "aliases": "Müller|Müller AG"},
        ]
        by_qid, by_label, by_alias = _build_lookup_tables(canonical_nodes)
        # Mention "Müller AG" (accented) should resolve to Q99 via alias_exact
        mention = {"mention_id": "m9", "name": "Müller AG"}
        result = _resolve_mention(mention, by_qid, by_label, by_alias)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_method"], "alias_exact")
        self.assertEqual(result["canonical_entity_id"], "Q99")
        self.assertEqual(result["resolution_confidence"], 0.8)

    def test_alias_exact_compatibility_variant(self):
        """Full-width/compatibility Unicode characters in an alias normalize to the
        same ASCII form and resolve via alias_exact."""
        canonical_nodes = [
            # "\uff2f\uff2d\uff27" is full-width "OMG"; use a distinct canonical name
            # so the mention does not match via label_exact first.
            {"entity_id": "Q50", "run_id": "run-s1", "name": "OMG Corporation", "aliases": "\uff2f\uff2d\uff27 Corp"},
        ]
        by_qid, by_label, by_alias = _build_lookup_tables(canonical_nodes)
        # "omg corp" matches the normalised alias ("\uff2f\uff2d\uff27 Corp" → "omg corp")
        mention = {"mention_id": "m10", "name": "omg corp"}
        result = _resolve_mention(mention, by_qid, by_label, by_alias)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_method"], "alias_exact")
        self.assertEqual(result["canonical_entity_id"], "Q50")


class TestRunEntityResolutionDryRun(unittest.TestCase):
    def test_dry_run_returns_summary_with_zeros(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _dry_run_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="test-run-001", source_uri=None)
            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(result["run_id"], "test-run-001")
            self.assertEqual(result["mentions_total"], 0)
            self.assertEqual(result["resolved"], 0)
            self.assertEqual(result["unresolved"], 0)
            self.assertIn("entity resolution skipped in dry_run mode", result["warnings"])

    def test_dry_run_writes_summary_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _dry_run_config(Path(tmpdir))
            run_entity_resolution(config, run_id="test-run-002", source_uri="file:///test.pdf")
            summary_path = Path(tmpdir) / "runs" / "test-run-002" / "entity_resolution" / "entity_resolution_summary.json"
            self.assertTrue(summary_path.exists())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "dry_run")
            self.assertEqual(summary["source_uri"], "file:///test.pdf")

    def test_dry_run_writes_empty_unresolved_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _dry_run_config(Path(tmpdir))
            run_entity_resolution(config, run_id="test-run-003", source_uri=None)
            unresolved_path = (
                Path(tmpdir) / "runs" / "test-run-003" / "entity_resolution" / "unresolved_mentions.json"
            )
            self.assertTrue(unresolved_path.exists())
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
            self.assertEqual(unresolved, [])

    def test_dry_run_carries_resolver_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _dry_run_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="test-run-004", source_uri=None)
            self.assertIn("resolver_version", result)
            self.assertTrue(result["resolver_version"])


class TestRunEntityResolutionLive(unittest.TestCase):
    """Tests for the live path using a mock Neo4j driver."""

    def _make_driver(
        self,
        mentions: list[dict[str, Any]],
        canonical_nodes: list[dict[str, Any]],
    ) -> MagicMock:
        """Build a mock neo4j.Driver that returns the given data."""
        return _make_neo4j_test_driver(mentions, canonical_nodes)

    def test_live_resolves_qid_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Q42", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-001", source_uri="file:///doc.pdf", resolution_mode="structured_anchor")

            self.assertEqual(result["status"], "live")
            self.assertEqual(result["mentions_total"], 1)
            self.assertEqual(result["resolved"], 1)
            self.assertEqual(result["unresolved"], 0)
            self.assertEqual(result["resolution_breakdown"].get("qid_exact"), 1)

    def test_live_resolves_label_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m2", "name": "Douglas Adams", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-002", source_uri=None, resolution_mode="structured_anchor")

            self.assertEqual(result["resolved"], 1)
            self.assertEqual(result["resolution_breakdown"].get("label_exact"), 1)

    def test_live_resolves_alias_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m3", "name": "D. Adams", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": "D. Adams|Adams"}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-003", source_uri=None, resolution_mode="structured_anchor")

            self.assertEqual(result["resolved"], 1)
            self.assertEqual(result["resolution_breakdown"].get("alias_exact"), 1)

    def test_live_unresolved_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m4", "name": "Nobody Known", "entity_type": None}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-004", source_uri=None)

            self.assertEqual(result["resolved"], 0)
            self.assertEqual(result["unresolved"], 1)
            self.assertEqual(result["resolution_breakdown"].get("label_cluster"), 1)

    def test_live_writes_unresolved_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m5", "name": "Mystery Person", "entity_type": None}]
            canonicals: list[dict[str, Any]] = []
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-live-005", source_uri=None)

            unresolved_path = (
                Path(tmpdir) / "runs" / "run-live-005" / "entity_resolution" / "unresolved_mentions.json"
            )
            self.assertTrue(unresolved_path.exists())
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
            self.assertEqual(len(unresolved), 1)
            self.assertEqual(unresolved[0]["mention_name"], "Mystery Person")
            self.assertEqual(unresolved[0]["normalized_text"], "mystery person")

    def test_live_writes_summary_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m6", "name": "Q1", "entity_type": None},
                {"mention_id": "m7", "name": "Unknown", "entity_type": None},
            ]
            canonicals = [{"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-live-006", source_uri="file:///a.pdf", resolution_mode="structured_anchor")

            summary_path = (
                Path(tmpdir) / "runs" / "run-live-006" / "entity_resolution" / "entity_resolution_summary.json"
            )
            self.assertTrue(summary_path.exists())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "live")
            self.assertEqual(summary["mentions_total"], 2)
            self.assertEqual(summary["resolved"], 1)
            self.assertEqual(summary["unresolved"], 1)

    def test_live_empty_mentions_returns_zero_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            driver = self._make_driver([], [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-007", source_uri=None)

            self.assertEqual(result["mentions_total"], 0)
            self.assertEqual(result["resolved"], 0)
            self.assertEqual(result["unresolved"], 0)
            self.assertEqual(result["resolution_breakdown"], {})


class TestRunEntityResolutionOrchestratorIntegration(unittest.TestCase):
    """Integration smoke test: resolve-entities in the full orchestrator flow."""

    def test_resolve_entities_in_independent_stage_mode(self):
        """run_independent_demo accepts 'resolve-entities' with env var set."""
        import importlib.util
        import os
        import sys

        run_demo_path = Path(__file__).resolve().parents[1] / "run_demo.py"
        spec = importlib.util.spec_from_file_location("_run_demo_test", run_demo_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        try:
            sys.modules["_run_demo_test"] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        finally:
            sys.modules.pop("_run_demo_test", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                dataset_name="demo_dataset_v1",
            )
            env_backup = os.environ.get("UNSTRUCTURED_RUN_ID")
            try:
                os.environ["UNSTRUCTURED_RUN_ID"] = "test-unstructured-run-001"
                manifest_path = module.run_independent_demo(config, "resolve-entities")
            finally:
                if env_backup is None:
                    os.environ.pop("UNSTRUCTURED_RUN_ID", None)
                else:
                    os.environ["UNSTRUCTURED_RUN_ID"] = env_backup

            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("entity_resolution", manifest["stages"])
            self.assertEqual(manifest["run_scopes"]["batch_mode"], "single_independent_run")

    def test_resolve_entities_requires_env_var(self):
        """resolve-entities raises ValueError when env var is missing."""
        import importlib.util
        import os
        import sys

        run_demo_path = Path(__file__).resolve().parents[1] / "run_demo.py"
        spec = importlib.util.spec_from_file_location("_run_demo_test2", run_demo_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        try:
            sys.modules["_run_demo_test2"] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        finally:
            sys.modules.pop("_run_demo_test2", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                dataset_name="demo_dataset_v1",
            )
            env_backup = os.environ.get("UNSTRUCTURED_RUN_ID")
            try:
                os.environ.pop("UNSTRUCTURED_RUN_ID", None)
                with self.assertRaises(ValueError) as ctx:
                    module.run_independent_demo(config, "resolve-entities")
                self.assertIn("UNSTRUCTURED_RUN_ID", str(ctx.exception))
            finally:
                if env_backup is not None:
                    os.environ["UNSTRUCTURED_RUN_ID"] = env_backup


class TestBatchManifestEntityResolution(unittest.TestCase):
    """Verify build_batch_manifest includes entity_resolution when provided."""

    def test_entity_resolution_stage_included_when_provided(self):
        from demo.contracts.manifest import build_batch_manifest
        from demo.contracts.runtime import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            manifest = build_batch_manifest(
                config=config,
                structured_run_id="structured-1",
                unstructured_run_id="unstructured-2",
                structured_stage={"status": "dry_run"},
                pdf_stage={"status": "dry_run"},
                claim_stage={"status": "dry_run"},
                retrieval_stage={"status": "dry_run"},
                entity_resolution_stage={"status": "dry_run", "resolved": 0},
            )
            self.assertIn("entity_resolution", manifest["stages"])
            self.assertEqual(manifest["stages"]["entity_resolution"]["run_id"], "unstructured-2")
            self.assertEqual(manifest["stages"]["entity_resolution"]["status"], "dry_run")

    def test_entity_resolution_stage_absent_by_default(self):
        from demo.contracts.manifest import build_batch_manifest
        from demo.contracts.runtime import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            manifest = build_batch_manifest(
                config=config,
                structured_run_id="structured-1",
                unstructured_run_id="unstructured-2",
                structured_stage={"status": "dry_run"},
                pdf_stage={"status": "dry_run"},
                claim_stage={"status": "dry_run"},
                retrieval_stage={"status": "dry_run"},
            )
            self.assertNotIn("entity_resolution", manifest["stages"])


class TestResolvedEntityCluster(unittest.TestCase):
    """Tests for the ResolvedEntityCluster (provisional cluster) layer."""

    @staticmethod
    def _load_unresolved_json(output_dir: Path, run_id: str, artifact_subdir: str = "entity_resolution") -> list:
        """Load the unresolved_mentions.json artifact for *run_id*."""
        path = output_dir / "runs" / run_id / artifact_subdir / "unresolved_mentions.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Resolution method for non-canonical mentions
    # ------------------------------------------------------------------

    def test_unresolved_mention_gets_label_cluster_method(self):
        by_qid, by_label, by_alias = _build_lookup_tables([])
        mention = {"mention_id": "m1", "name": "Mystery Corp"}
        result = _resolve_mention(mention, by_qid, by_label, by_alias)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["resolution_method"], "label_cluster")

    def test_unresolved_mention_carries_normalized_text(self):
        by_qid, by_label, by_alias = _build_lookup_tables([])
        mention = {"mention_id": "m1", "name": "  Mystery Corp  "}
        result = _resolve_mention(mention, by_qid, by_label, by_alias)
        self.assertEqual(result["normalized_text"], "mystery corp")
        self.assertEqual(result["mention_name"], "  Mystery Corp  ".strip())

    # ------------------------------------------------------------------
    # Dry-run summary includes cluster fields
    # ------------------------------------------------------------------

    def test_dry_run_summary_includes_clusters_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            result = run_entity_resolution(config, run_id="test-cluster-001", source_uri=None)
            self.assertIn("clusters_created", result)
            self.assertEqual(result["clusters_created"], 0)

    def test_dry_run_summary_includes_cluster_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            result = run_entity_resolution(config, run_id="test-cluster-002", source_uri=None)
            self.assertIn("cluster_version", result)
            self.assertEqual(result["cluster_version"], _CLUSTER_VERSION)

    # ------------------------------------------------------------------
    # Live path: clusters_created count
    # ------------------------------------------------------------------

    def _make_driver(
        self,
        mentions: list[dict[str, Any]],
        canonical_nodes: list[dict[str, Any]],
    ) -> MagicMock:
        """Build a mock neo4j.Driver that returns the given data."""
        return _make_neo4j_test_driver(mentions, canonical_nodes)

    def test_live_clusters_created_equals_unique_normalized_texts(self):
        """Two mentions with the same normalized text map to ONE cluster."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [
                {"mention_id": "m1", "name": "Mystery Corp", "entity_type": None},
                {"mention_id": "m2", "name": "mystery corp", "entity_type": None},  # same normalized
                {"mention_id": "m3", "name": "Other Entity", "entity_type": None},
            ]
            driver = self._make_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-cluster-001", source_uri=None)

            # "mystery corp" (normalized) → 1 cluster; "other entity" → 1 cluster
            self.assertEqual(result["unresolved"], 3)
            self.assertEqual(result["clusters_created"], 2)

    def test_live_clusters_created_is_zero_when_all_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Q42", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-cluster-002", source_uri=None, resolution_mode="structured_anchor")

            self.assertEqual(result["resolved"], 1)
            self.assertEqual(result["clusters_created"], 0)

    def test_live_summary_carries_cluster_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            driver = self._make_driver([], [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-cluster-003", source_uri=None)

            self.assertIn("cluster_version", result)
            self.assertEqual(result["cluster_version"], _CLUSTER_VERSION)

    # ------------------------------------------------------------------
    # Live path: cluster_id in unresolved artifact
    # ------------------------------------------------------------------

    def test_live_unresolved_artifact_includes_cluster_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Widget Inc", "entity_type": None}]
            driver = self._make_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cluster-004", source_uri=None)

            unresolved = self._load_unresolved_json(Path(tmpdir), "run-cluster-004")
            self.assertEqual(len(unresolved), 1)
            self.assertIn("cluster_id", unresolved[0])
            expected_cluster_id = _make_cluster_id("run-cluster-004", None, "widget inc")
            self.assertEqual(unresolved[0]["cluster_id"], expected_cluster_id)

    # ------------------------------------------------------------------
    # Cypher: MEMBER_OF edge written for unresolved mentions
    # ------------------------------------------------------------------

    def test_live_member_of_edge_written_for_unresolved(self):
        """Verify the MEMBER_OF Cypher is invoked for unresolved mentions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Nobody Known", "entity_type": None}]
            driver = self._make_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cluster-005", source_uri=None)

            # At least one call should contain MEMBER_OF
            all_calls = driver.execute_query.call_args_list
            cypher_calls = [str(c) for c in all_calls]
            self.assertTrue(
                any("MEMBER_OF" in call for call in cypher_calls),
                "Expected a Cypher call containing MEMBER_OF for unresolved mentions",
            )

    def test_live_resolved_entity_cluster_node_merged(self):
        """Verify ResolvedEntityCluster label appears in the Cypher for unresolved mentions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Widget Co", "entity_type": None}]
            driver = self._make_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cluster-006", source_uri=None)

            all_calls = driver.execute_query.call_args_list
            cypher_calls = [str(c) for c in all_calls]
            self.assertTrue(
                any("ResolvedEntityCluster" in call for call in cypher_calls),
                "Expected a Cypher call containing ResolvedEntityCluster for unresolved mentions",
            )

    # ------------------------------------------------------------------
    # Cluster identity scoping: _make_cluster_id and isolation guarantees
    # ------------------------------------------------------------------

    def test_unresolved_artifact_includes_entity_type(self):
        """Unresolved artifact rows expose entity_type for downstream consumers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Acme Corp", "entity_type": "ORG"}]
            driver = _make_neo4j_test_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-scope-001", source_uri=None)

            unresolved_path = (
                Path(tmpdir) / "runs" / "run-scope-001" / "entity_resolution" / "unresolved_mentions.json"
            )
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
            self.assertEqual(len(unresolved), 1)
            self.assertIn("entity_type", unresolved[0])
            # "ORG" is normalized to "Organization"
            self.assertEqual(unresolved[0]["entity_type"], "Organization")

    def test_cross_run_same_text_produces_distinct_cluster_ids(self):
        """Same normalized text in two different runs must yield different cluster_ids."""
        cid_run1 = _make_cluster_id("run-A", None, "ibm")
        cid_run2 = _make_cluster_id("run-B", None, "ibm")
        self.assertNotEqual(cid_run1, cid_run2)

    def test_cross_source_same_text_produces_same_cluster_id(self):
        """Mentions from different source_uris in the same run must yield the SAME cluster_id.

        source_uri is NOT part of cluster identity; it is provenance-only on edges.
        Cross-document clustering within a run is intentional.
        """
        cid_src1 = _make_cluster_id("run-A", "ORG", "ibm")
        cid_src2 = _make_cluster_id("run-A", "ORG", "ibm")
        self.assertEqual(cid_src1, cid_src2)

    def test_per_mention_source_uri_produces_same_cluster_id_in_artifact(self):
        """Mentions from different sources within the same run_id produce the SAME cluster_id
        in the unresolved artifact — source_uri is provenance on edges, not cluster identity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            # Two mentions with identical text and entity_type, but different source_uri
            # stored on the EntityMention node in the DB.
            mentions = [
                {"mention_id": "m1", "name": "IBM", "entity_type": "ORG", "source_uri": "https://example.com/doc1.pdf"},
                {"mention_id": "m2", "name": "IBM", "entity_type": "ORG", "source_uri": "https://example.com/doc2.pdf"},
            ]
            driver = _make_neo4j_test_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="run-src-scope-001", source_uri=None,
                    resolution_mode="unstructured_only",
                )

            unresolved_path = (
                Path(tmpdir) / "runs" / "run-src-scope-001" / "entity_resolution" / "unresolved_mentions.json"
            )
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
            self.assertEqual(len(unresolved), 2)
            # Both mentions must map to the SAME cluster_id since source_uri is not identity.
            cid_m1 = unresolved[0]["cluster_id"]
            cid_m2 = unresolved[1]["cluster_id"]
            expected_cid = _make_cluster_id("run-src-scope-001", "ORG", "ibm")
            self.assertEqual(cid_m1, expected_cid)
            self.assertEqual(cid_m2, expected_cid)
            # clusters_created must be 1 — both mentions belong to the same cluster.
            self.assertEqual(result["clusters_created"], 1)

    def test_per_mention_source_uri_retained_on_member_of_edges(self):
        """Per-mention source_uri from different source documents is preserved as provenance
        on MEMBER_OF edge rows even when both mentions map to the same cluster_id.

        This verifies the provenance retention guarantee: source_uri is NOT part of
        cluster identity but IS carried per-mention on MEMBER_OF edges so that origin
        tracking is preserved without forcing source-partitioned cluster identity.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [
                {"mention_id": "m1", "name": "IBM", "entity_type": "ORG", "source_uri": "https://example.com/doc1.pdf"},
                {"mention_id": "m2", "name": "IBM", "entity_type": "ORG", "source_uri": "https://example.com/doc2.pdf"},
            ]
            driver = _make_neo4j_test_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(
                    config, run_id="run-provenance-001", source_uri=None,
                    resolution_mode="unstructured_only",
                )

            # Extract the rows written to the MEMBER_OF Cypher call.
            member_of_rows = []
            for call in driver.execute_query.call_args_list:
                query = call.args[0] if call.args else ""
                params = call.kwargs.get("parameters_", {})
                if "MEMBER_OF" in query and "rows" in params:
                    member_of_rows = params["rows"]
                    break

            self.assertEqual(len(member_of_rows), 2, "Expected two MEMBER_OF rows")

            # Both rows must target the same cluster_id (source_uri is NOT identity).
            cluster_ids = {r["cluster_id"] for r in member_of_rows}
            self.assertEqual(len(cluster_ids), 1, "Both mentions must map to the same cluster_id")

            # Per-mention source_uri must be retained as provenance on each edge row.
            source_uris_by_mention = {r["mention_id"]: r.get("source_uri") for r in member_of_rows}
            self.assertEqual(
                source_uris_by_mention.get("m1"), "https://example.com/doc1.pdf",
                "m1 MEMBER_OF edge must carry its source_uri as provenance",
            )
            self.assertEqual(
                source_uris_by_mention.get("m2"), "https://example.com/doc2.pdf",
                "m2 MEMBER_OF edge must carry its source_uri as provenance",
            )

    def test_cross_type_same_text_produces_distinct_cluster_ids(self):
        """Same normalized text with different entity types must yield different cluster_ids."""
        cid_org = _make_cluster_id("run-A", "ORG", "ibm")
        cid_product = _make_cluster_id("run-A", "PRODUCT", "ibm")
        self.assertNotEqual(cid_org, cid_product)

    def test_same_run_same_type_same_text_produces_same_cluster_id(self):
        """Identical (run_id, entity_type, normalized_text) must yield the same cluster_id."""
        cid_a = _make_cluster_id("run-A", "ORG", "ibm")
        cid_b = _make_cluster_id("run-A", "ORG", "ibm")
        self.assertEqual(cid_a, cid_b)

    def test_none_entity_type_and_empty_string_handled_consistently(self):
        """None entity_type is treated as empty string so cluster_id is stable."""
        cid_none = _make_cluster_id("run-A", None, "ibm")
        cid_empty = _make_cluster_id("run-A", "", "ibm")
        self.assertEqual(cid_none, cid_empty)

    def test_make_cluster_id_raises_on_empty_run_id(self):
        """_make_cluster_id must raise ValueError when run_id is empty."""
        with self.assertRaises(ValueError):
            _make_cluster_id("", None, "ibm")
        with self.assertRaises(ValueError):
            _make_cluster_id("", "ORG", "ibm")

    def test_make_cluster_id_delimiter_in_run_id_does_not_collide(self):
        """run_id containing '::' must not produce an ID identical to a different tuple."""
        # run_id="a::b", entity_type="", text="c"  vs  run_id="a", entity_type="b", text="c"
        cid_combined = _make_cluster_id("a::b", None, "c")
        cid_split = _make_cluster_id("a", "b", "c")
        self.assertNotEqual(cid_combined, cid_split)

    def test_make_cluster_id_delimiter_in_entity_type_does_not_collide(self):
        """entity_type containing '::' must not produce an ID identical to a different tuple."""
        # run_id="a", entity_type="b::c", text=""  vs  run_id="a", entity_type="b", text="c"
        cid_combined = _make_cluster_id("a", "b::c", "")
        cid_split = _make_cluster_id("a", "b", "c")
        self.assertNotEqual(cid_combined, cid_split)

    def test_make_cluster_id_percent_in_component_does_not_collide(self):
        """A '%' literal in a component must be encoded and not decode to a collision."""
        # run_id containing a literal % — e.g. "run%3A" would encode as "run%253A",
        # which is distinct from encoding "run:" → "run%3A".
        cid_literal_pct = _make_cluster_id("run%3A", None, "ibm")
        cid_colon = _make_cluster_id("run:", None, "ibm")
        self.assertNotEqual(cid_literal_pct, cid_colon)

    def test_make_cluster_id_space_in_text_does_not_collide(self):
        """Spaces in normalized_text are encoded and don't collapse with other representations."""
        cid_with_space = _make_cluster_id("run-A", "ORG", "new york")
        cid_no_space = _make_cluster_id("run-A", "ORG", "newyork")
        self.assertNotEqual(cid_with_space, cid_no_space)

    def test_clusters_created_counts_unique_entity_type_and_text_pairs(self):
        """clusters_created treats same text with different entity types as separate clusters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            # "IBM" appears as both ORG and PRODUCT — should create 2 distinct clusters.
            mentions = [
                {"mention_id": "m1", "name": "IBM", "entity_type": "ORG"},
                {"mention_id": "m2", "name": "IBM", "entity_type": "PRODUCT"},
            ]
            driver = _make_neo4j_test_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="run-scope-002", source_uri=None,
                    resolution_mode="unstructured_only",
                )

            self.assertEqual(result["clusters_created"], 2)

    def test_clusters_created_none_and_empty_entity_type_counted_as_one(self):
        """None and empty-string entity_type must be treated as the same cluster scope."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            # Both mentions have the same normalized text; one has entity_type=None,
            # the other has entity_type="".  They must map to the same cluster_id
            # and clusters_created must be 1, not 2.
            mentions = [
                {"mention_id": "m1", "name": "Acme", "entity_type": None},
                {"mention_id": "m2", "name": "Acme", "entity_type": ""},
            ]
            driver = _make_neo4j_test_driver(mentions, [])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="run-scope-003", source_uri=None,
                    resolution_mode="unstructured_only",
                )

            self.assertEqual(result["clusters_created"], 1)

    def test_cross_run_clusters_created_are_isolated(self):
        """Two separate runs with the same mentions produce independent clusters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            mentions = [{"mention_id": "m1", "name": "Acme Corp", "entity_type": "ORG"}]

            with patch("neo4j.GraphDatabase.driver", return_value=_make_neo4j_test_driver(mentions, [])):
                result_run1 = run_entity_resolution(
                    config, run_id="run-iso-001", source_uri=None,
                    resolution_mode="unstructured_only",
                )
            with patch("neo4j.GraphDatabase.driver", return_value=_make_neo4j_test_driver(mentions, [])):
                result_run2 = run_entity_resolution(
                    config, run_id="run-iso-002", source_uri=None,
                    resolution_mode="unstructured_only",
                )

            # Each run sees 1 cluster, and those cluster_ids must differ.
            self.assertEqual(result_run1["clusters_created"], 1)
            self.assertEqual(result_run2["clusters_created"], 1)
            unresolved_run1 = self._load_unresolved_json(Path(tmpdir), "run-iso-001")
            unresolved_run2 = self._load_unresolved_json(Path(tmpdir), "run-iso-002")
            self.assertNotEqual(unresolved_run1[0]["cluster_id"], unresolved_run2[0]["cluster_id"])

    def test_ORG_and_Organization_produce_same_cluster_id(self):
        """'ORG' and 'Organization' must produce the same cluster_id after normalization."""
        cid_org = _make_cluster_id("run-A", "ORG", "mercadolibre")
        cid_organization = _make_cluster_id("run-A", "Organization", "mercadolibre")
        self.assertEqual(cid_org, cid_organization)

    def test_Company_and_Organization_produce_same_cluster_id(self):
        """'Company' is a synonym for 'Organization' and must produce the same cluster_id.

        Companies are organizations; mapping 'Company' → 'Organization' prevents
        upstream labeling variance from splitting what should be a single cluster.
        """
        cid_company = _make_cluster_id("run-A", "Company", "xapo")
        cid_organization = _make_cluster_id("run-A", "Organization", "xapo")
        self.assertEqual(cid_company, cid_organization)

    def test_PERSON_and_Person_produce_same_cluster_id(self):
        """'PERSON' and 'Person' must produce the same cluster_id after normalization."""
        cid_person_upper = _make_cluster_id("run-A", "PERSON", "linda rottenberg")
        cid_person_title = _make_cluster_id("run-A", "Person", "linda rottenberg")
        self.assertEqual(cid_person_upper, cid_person_title)

    def test_ORG_Organization_Company_all_produce_same_cluster_id(self):
        """All three organization-type synonyms must converge to the same cluster_id."""
        cid_org = _make_cluster_id("run-A", "ORG", "endeavor")
        cid_organization = _make_cluster_id("run-A", "Organization", "endeavor")
        cid_company = _make_cluster_id("run-A", "Company", "endeavor")
        self.assertEqual(cid_org, cid_organization)
        self.assertEqual(cid_org, cid_company)

    def test_organization_type_still_distinct_from_person_type(self):
        """After normalization, organization and person clusters must still be distinct."""
        cid_org = _make_cluster_id("run-A", "ORG", "apple")
        cid_person = _make_cluster_id("run-A", "PERSON", "apple")
        self.assertNotEqual(cid_org, cid_person)


class TestNormalizeEntityType(unittest.TestCase):
    """Tests for _normalize_entity_type."""

    def test_ORG_maps_to_Organization(self):
        self.assertEqual(_normalize_entity_type("ORG"), "Organization")

    def test_Organization_unchanged(self):
        self.assertEqual(_normalize_entity_type("Organization"), "Organization")

    def test_Company_maps_to_Organization(self):
        """Company is treated as a synonym for Organization."""
        self.assertEqual(_normalize_entity_type("Company"), "Organization")

    def test_PERSON_maps_to_Person(self):
        self.assertEqual(_normalize_entity_type("PERSON"), "Person")

    def test_Person_unchanged(self):
        self.assertEqual(_normalize_entity_type("Person"), "Person")

    def test_unknown_label_returned_unchanged(self):
        """Labels not in the synonym table are returned as-is."""
        self.assertEqual(_normalize_entity_type("PRODUCT"), "PRODUCT")
        self.assertEqual(_normalize_entity_type("Place"), "Place")
        self.assertEqual(_normalize_entity_type("EVENT"), "EVENT")

    def test_none_returns_none(self):
        self.assertIsNone(_normalize_entity_type(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_normalize_entity_type(""))

    def test_whitespace_only_returns_none(self):
        """Whitespace-only strings are treated as absent (same as None / '')."""
        self.assertIsNone(_normalize_entity_type("   "))
        self.assertIsNone(_normalize_entity_type("\t"))

    def test_whitespace_stripped_before_lookup(self):
        """Leading/trailing whitespace is stripped before the synonym lookup."""
        self.assertEqual(_normalize_entity_type(" Organization "), "Organization")
        self.assertEqual(_normalize_entity_type("  ORG  "), "Organization")
        self.assertEqual(_normalize_entity_type(" Person "), "Person")

    def test_lowercase_org_is_not_mapped(self):
        """'org' is an abbreviation, not a casing variant; it is NOT mapped."""
        self.assertEqual(_normalize_entity_type("org"), "org")

    def test_lowercase_organization_maps_to_Organization(self):
        """'organization' (all-lowercase) is a casing variant of 'Organization'."""
        self.assertEqual(_normalize_entity_type("organization"), "Organization")

    def test_lowercase_person_maps_to_Person(self):
        """'person' (all-lowercase) is a casing variant of 'Person'."""
        self.assertEqual(_normalize_entity_type("person"), "Person")


    def test_initialism_match(self):
        self.assertTrue(_is_abbreviation("fbi", "federal bureau of investigation"))

    def test_initialism_mismatch(self):
        self.assertFalse(_is_abbreviation("cia", "federal bureau of investigation"))

    def test_single_word_long_form_returns_false(self):
        self.assertFalse(_is_abbreviation("f", "fbi"))

    def test_empty_short_returns_false(self):
        self.assertFalse(_is_abbreviation("", "federal bureau of investigation"))

    def test_reverse_direction_long_form_is_not_initialism_of_short(self):
        # The long form is NOT an initialism of the abbreviation.
        self.assertFalse(_is_abbreviation("federal bureau of investigation", "fbi"))

    def test_dotted_abbreviation_matches(self):
        # "f.b.i." should normalize to "fbi" and match the long form.
        self.assertTrue(_is_abbreviation("f.b.i.", "federal bureau of investigation"))

    def test_trailing_punctuation_abbreviation_matches(self):
        # "fbi," (common in extracted text) should still match.
        self.assertTrue(_is_abbreviation("fbi,", "federal bureau of investigation"))

    def test_dotted_abbreviation_without_trailing_dot_matches(self):
        # "f.b.i" (no trailing dot) — same initialism as "fbi".
        self.assertTrue(_is_abbreviation("f.b.i", "federal bureau of investigation"))

    def test_long_form_trailing_punctuation_on_token(self):
        # Punctuation attached to a long_form token must be stripped before
        # building initials; "investigation," → "investigation".
        self.assertTrue(_is_abbreviation("fbi", "federal bureau of investigation,"))

    def test_long_form_mid_punctuation_on_token(self):
        # Mid-sentence punctuation on a long_form word must also be stripped.
        self.assertTrue(_is_abbreviation("fbi", "federal bureau, of investigation"))


class TestEntityTypeDriftReport(unittest.TestCase):
    """Tests for _build_entity_type_report."""

    def test_empty_mentions_returns_empty_report(self):
        report = _build_entity_type_report([])
        self.assertEqual(report["raw_counts"], {})
        self.assertEqual(report["normalized_counts"], {})
        self.assertEqual(report["mapped_variants"], {})
        self.assertEqual(report["passthrough_labels"], [])
        self.assertEqual(report["null_or_empty_count"], 0)
        self.assertEqual(report["sentinel_label_warnings"], [])

    def test_none_entity_type_counted_as_null(self):
        mentions = [{"mention_id": "m1", "name": "Acme"}]  # no entity_type key
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["raw_counts"].get("__null__"), 1)
        self.assertEqual(report["null_or_empty_count"], 1)
        self.assertEqual(report["normalized_counts"].get("__null__"), 1)

    def test_explicit_none_entity_type_counted_as_null(self):
        mentions = [{"mention_id": "m1", "name": "Acme", "entity_type": None}]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["raw_counts"].get("__null__"), 1)
        self.assertEqual(report["null_or_empty_count"], 1)

    def test_empty_string_entity_type_counted_as_null(self):
        mentions = [{"mention_id": "m1", "name": "Acme", "entity_type": ""}]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["raw_counts"].get("__null__"), 1)
        self.assertEqual(report["null_or_empty_count"], 1)

    def test_whitespace_only_entity_type_counted_as_null(self):
        """Whitespace-only entity_type is treated as absent (null_or_empty bucket).

        Regression test: _normalize_entity_type now strips whitespace and returns
        None for whitespace-only inputs, so _build_entity_type_report must normalize
        whitespace-only raw values to None before calling it to avoid a failed assert.
        """
        for ws in ("   ", "\t", " \t "):
            with self.subTest(entity_type=repr(ws)):
                mentions = [{"mention_id": "m1", "name": "Acme", "entity_type": ws}]
                report = _build_entity_type_report(mentions)
                self.assertEqual(report["raw_counts"].get("__null__"), 1,
                                 msg=f"raw_counts should use __null__ sentinel for {ws!r}")
                self.assertEqual(report["null_or_empty_count"], 1,
                                 msg=f"null_or_empty_count should be 1 for {ws!r}")
                self.assertEqual(report["normalized_counts"].get("__null__"), 1,
                                 msg=f"normalized_counts should use __null__ sentinel for {ws!r}")

    def test_mapped_synonym_ORG_appears_in_mapped_variants(self):
        mentions = [{"mention_id": "m1", "name": "IBM", "entity_type": "ORG"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("ORG", report["mapped_variants"])
        self.assertEqual(report["mapped_variants"]["ORG"], "Organization")
        self.assertNotIn("ORG", report["passthrough_labels"])

    def test_mapped_synonym_Company_appears_in_mapped_variants(self):
        mentions = [{"mention_id": "m1", "name": "Acme", "entity_type": "Company"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("Company", report["mapped_variants"])
        self.assertEqual(report["mapped_variants"]["Company"], "Organization")

    def test_mapped_synonym_PERSON_appears_in_mapped_variants(self):
        mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "PERSON"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("PERSON", report["mapped_variants"])
        self.assertEqual(report["mapped_variants"]["PERSON"], "Person")

    def test_canonical_label_Organization_is_passthrough(self):
        """The canonical label 'Organization' is not a synonym and must be passthrough."""
        mentions = [{"mention_id": "m1", "name": "IBM", "entity_type": "Organization"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("Organization", report["passthrough_labels"])
        self.assertNotIn("Organization", report["mapped_variants"])

    def test_canonical_label_Person_is_passthrough(self):
        mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "Person"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("Person", report["passthrough_labels"])
        self.assertNotIn("Person", report["mapped_variants"])

    def test_unknown_label_is_passthrough(self):
        """Unrecognised labels not in the synonym table must appear in passthrough_labels."""
        mentions = [{"mention_id": "m1", "name": "Widget", "entity_type": "PRODUCT"}]
        report = _build_entity_type_report(mentions)
        self.assertIn("PRODUCT", report["passthrough_labels"])
        self.assertNotIn("PRODUCT", report["mapped_variants"])

    def test_raw_counts_reflect_actual_input_frequencies(self):
        mentions = [
            {"mention_id": "m1", "name": "IBM", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Apple", "entity_type": "ORG"},
            {"mention_id": "m3", "name": "Alice", "entity_type": "Person"},
        ]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["raw_counts"]["ORG"], 2)
        self.assertEqual(report["raw_counts"]["Person"], 1)

    def test_normalized_counts_merge_synonyms(self):
        """ORG and Organization must both contribute to the 'Organization' bucket."""
        mentions = [
            {"mention_id": "m1", "name": "IBM", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Apple", "entity_type": "Organization"},
            {"mention_id": "m3", "name": "Acme", "entity_type": "Company"},
        ]
        report = _build_entity_type_report(mentions)
        # All three map to "Organization" after normalization
        self.assertEqual(report["normalized_counts"].get("Organization"), 3)
        # ORG and Company are synonyms; Organization is passthrough
        self.assertEqual(set(report["mapped_variants"].keys()), {"ORG", "Company"})
        self.assertIn("Organization", report["passthrough_labels"])

    def test_normalized_counts_person_synonyms_merged(self):
        """PERSON and Person must both contribute to the 'Person' bucket."""
        mentions = [
            {"mention_id": "m1", "name": "Alice", "entity_type": "PERSON"},
            {"mention_id": "m2", "name": "Bob", "entity_type": "Person"},
        ]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["normalized_counts"].get("Person"), 2)

    def test_mixed_mentions_passthrough_and_mapped_and_null(self):
        """A realistic mix of all three categories is tracked correctly."""
        mentions = [
            {"mention_id": "m1", "name": "IBM", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Alice", "entity_type": "Person"},
            {"mention_id": "m3", "name": "Widget", "entity_type": "PRODUCT"},
            {"mention_id": "m4", "name": "Unknown"},
        ]
        report = _build_entity_type_report(mentions)
        # mapped
        self.assertIn("ORG", report["mapped_variants"])
        # passthrough
        self.assertIn("Person", report["passthrough_labels"])
        self.assertIn("PRODUCT", report["passthrough_labels"])
        # null
        self.assertEqual(report["null_or_empty_count"], 1)

    def test_passthrough_labels_sorted(self):
        """passthrough_labels must be returned in sorted order for stable output."""
        mentions = [
            {"mention_id": "m1", "name": "x", "entity_type": "PRODUCT"},
            {"mention_id": "m2", "name": "y", "entity_type": "Event"},
            {"mention_id": "m3", "name": "z", "entity_type": "Place"},
        ]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["passthrough_labels"], sorted(report["passthrough_labels"]))

    def test_raw_counts_sorted_by_descending_count_then_label(self):
        """raw_counts must be ordered by descending count, then alphabetically on ties."""
        mentions = [
            {"mention_id": "m1", "name": "a", "entity_type": "Person"},   # count 3
            {"mention_id": "m2", "name": "b", "entity_type": "Person"},
            {"mention_id": "m3", "name": "c", "entity_type": "Person"},
            {"mention_id": "m4", "name": "d", "entity_type": "PRODUCT"},  # count 2
            {"mention_id": "m5", "name": "e", "entity_type": "PRODUCT"},
            {"mention_id": "m6", "name": "f", "entity_type": "Event"},    # count 2 (tie with PRODUCT)
            {"mention_id": "m7", "name": "g", "entity_type": "Event"},
            {"mention_id": "m8", "name": "h", "entity_type": "Zorg"},     # count 1
        ]
        report = _build_entity_type_report(mentions)
        keys = list(report["raw_counts"].keys())
        # Person (3) must come first
        self.assertEqual(keys[0], "Person")
        # Tie between Event (2) and PRODUCT (2): alphabetical → Event before PRODUCT
        self.assertEqual(keys[1], "Event")
        self.assertEqual(keys[2], "PRODUCT")
        # Zorg (1) last
        self.assertEqual(keys[3], "Zorg")

    def test_normalized_counts_sorted_by_descending_count_then_label(self):
        """normalized_counts must be ordered by descending count, then alphabetically on ties."""
        mentions = [
            # ORG and Company both normalize to Organization → combined count 3
            {"mention_id": "m1", "name": "a", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "b", "entity_type": "ORG"},
            {"mention_id": "m3", "name": "c", "entity_type": "Company"},
            # Person passthrough count 2
            {"mention_id": "m4", "name": "d", "entity_type": "Person"},
            {"mention_id": "m5", "name": "e", "entity_type": "Person"},
            # PRODUCT passthrough count 1
            {"mention_id": "m6", "name": "f", "entity_type": "PRODUCT"},
        ]
        report = _build_entity_type_report(mentions)
        keys = list(report["normalized_counts"].keys())
        self.assertEqual(keys[0], "Organization")  # 3
        self.assertEqual(keys[1], "Person")         # 2
        self.assertEqual(keys[2], "PRODUCT")        # 1

    def test_report_is_json_serializable(self):
        """The report dict must be safely JSON-serializable (no None keys)."""
        mentions = [
            {"mention_id": "m1", "name": "Acme", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Nobody"},
        ]
        report = _build_entity_type_report(mentions)
        # This must not raise
        serialized = json.dumps(report)
        parsed = json.loads(serialized)
        self.assertIn("raw_counts", parsed)
        self.assertIn("__null__", parsed["raw_counts"])

    def test_dry_run_summary_includes_entity_type_report(self):
        """dry_run summary must include an entity_type_report key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _dry_run_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="drift-dry-001", source_uri=None)
            self.assertIn("entity_type_report", result)
            rpt = result["entity_type_report"]
            self.assertIn("raw_counts", rpt)
            self.assertIn("normalized_counts", rpt)
            self.assertIn("mapped_variants", rpt)
            self.assertIn("passthrough_labels", rpt)
            self.assertIn("null_or_empty_count", rpt)

    def test_live_summary_includes_entity_type_report(self):
        """live summary must include an entity_type_report that reflects observed mentions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "IBM", "entity_type": "ORG"},
                {"mention_id": "m2", "name": "Alice", "entity_type": "Person"},
                {"mention_id": "m3", "name": "Mystery", "entity_type": None},
            ]
            canonicals: list[dict] = []
            driver = _make_neo4j_test_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config,
                    run_id="drift-live-001",
                    source_uri=None,
                    resolution_mode="structured_anchor",
                )
            self.assertIn("entity_type_report", result)
            rpt = result["entity_type_report"]
            # ORG is a mapped synonym
            self.assertIn("ORG", rpt["mapped_variants"])
            self.assertEqual(rpt["mapped_variants"]["ORG"], "Organization")
            # Person is passthrough
            self.assertIn("Person", rpt["passthrough_labels"])
            # one null
            self.assertEqual(rpt["null_or_empty_count"], 1)
            self.assertEqual(rpt["raw_counts"]["ORG"], 1)

    def test_sentinel_collision_surfaces_warning(self):
        """When extractor emits literal '__null__' and absent types coexist, warn."""
        mentions = [
            {"mention_id": "m1", "name": "Acme"},  # entity_type absent → None
            {"mention_id": "m2", "name": "Weird", "entity_type": "__null__"},  # reserved sentinel
        ]
        report = _build_entity_type_report(mentions)
        # Counts are merged under the sentinel key
        self.assertEqual(report["raw_counts"]["__null__"], 2)
        self.assertEqual(report["normalized_counts"]["__null__"], 2)
        # Warning is surfaced
        self.assertEqual(len(report["sentinel_label_warnings"]), 1)
        self.assertIn("__null__", report["sentinel_label_warnings"][0])

    def test_sentinel_label_without_null_input_no_warning(self):
        """Literal '__null__' label alone (no absent types) produces no warning."""
        mentions = [
            {"mention_id": "m1", "name": "Weird", "entity_type": "__null__"},
        ]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["sentinel_label_warnings"], [])

    def test_padded_sentinel_sets_raw_null_sentinel_seen(self):
        """A padded sentinel like ' __null__ ' collides with the __null__ bucket.

        Regression test: sentinel collision detection must strip the raw value
        before comparing so that padded forms are caught and the warning is
        raised when null/empty mentions also exist.
        """
        mentions = [
            {"mention_id": "m1", "name": "Acme"},  # entity_type absent → None
            {"mention_id": "m2", "name": "Weird", "entity_type": " __null__ "},  # padded sentinel
        ]
        report = _build_entity_type_report(mentions)
        # Padded sentinel merges into __null__ bucket in raw_counts
        self.assertEqual(report["raw_counts"].get("__null__"), 2)
        # Also merges in normalized_counts
        self.assertEqual(report["normalized_counts"].get("__null__"), 2)
        # Warning must be surfaced (collision between extractor-emitted sentinel and absent type)
        self.assertEqual(len(report["sentinel_label_warnings"]), 1)
        self.assertIn("__null__", report["sentinel_label_warnings"][0])

    def test_padded_sentinel_alone_no_warning(self):
        """A padded sentinel with no absent types should not produce a warning."""
        mentions = [
            {"mention_id": "m1", "name": "Weird", "entity_type": " __null__ "},
        ]
        report = _build_entity_type_report(mentions)
        self.assertEqual(report["raw_counts"].get("__null__"), 1)
        self.assertEqual(report["sentinel_label_warnings"], [])


    def test_identical_strings_return_one(self):
        self.assertAlmostEqual(_fuzzy_ratio("alice", "alice"), 1.0)

    def test_completely_different_returns_low(self):
        ratio = _fuzzy_ratio("alice", "xyz")
        self.assertLess(ratio, 0.5)

    def test_similar_strings_return_high(self):
        ratio = _fuzzy_ratio("alice smith", "alice smyth")
        self.assertGreater(ratio, 0.85)


class TestClusterMentionsUnstructuredOnly(unittest.TestCase):
    """Tests for _cluster_mentions_unstructured_only."""

    def test_empty_returns_empty(self):
        result = _cluster_mentions_unstructured_only([])
        self.assertEqual(result, [])

    def test_single_mention_becomes_label_cluster(self):
        mentions = [{"mention_id": "m1", "name": "Alice"}]
        result = _cluster_mentions_unstructured_only(mentions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["resolution_method"], "label_cluster")
        self.assertEqual(result[0]["normalized_text"], "alice")

    def test_same_normalized_text_shares_cluster(self):
        mentions = [
            {"mention_id": "m1", "name": "Alice"},
            {"mention_id": "m2", "name": "alice"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        self.assertEqual(len(result), 2)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Both mentions should share one cluster key")

    def test_normalized_exact_method_for_duplicate(self):
        mentions = [
            {"mention_id": "m1", "name": "Bob Corp"},
            {"mention_id": "m2", "name": "Bob Corp"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        methods = [r["resolution_method"] for r in result]
        self.assertIn("label_cluster", methods)
        self.assertIn("normalized_exact", methods)

    def test_abbreviation_clusters_with_long_form(self):
        mentions = [
            {"mention_id": "m1", "name": "Federal Bureau of Investigation"},
            {"mention_id": "m2", "name": "fbi"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        self.assertEqual(len(result), 2)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Abbreviation should map to long-form cluster")
        abbrev_row = next(r for r in result if r["mention_id"] == "m2")
        self.assertEqual(abbrev_row["resolution_method"], "abbreviation")

    def test_abbreviation_seen_before_long_form_uses_long_form_as_cluster_key(self):
        """Cluster key should be the long form regardless of mention order."""
        mentions = [
            {"mention_id": "m1", "name": "fbi"},
            {"mention_id": "m2", "name": "Federal Bureau of Investigation"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Both mentions should share one cluster key")
        # The long form should be the stable cluster key.
        self.assertIn("federal bureau of investigation", cluster_keys)
        self.assertNotIn("fbi", cluster_keys)
        # The abbreviation (m1, seen first) should be re-labeled "abbreviation"
        # after re-keying; the long form (m2, the introducer) is "label_cluster".
        m1_row = next(r for r in result if r["mention_id"] == "m1")
        m2_row = next(r for r in result if r["mention_id"] == "m2")
        self.assertEqual(m1_row["resolution_method"], "abbreviation")
        self.assertEqual(m2_row["resolution_method"], "label_cluster")

    def test_fuzzy_similar_names_share_cluster(self):
        mentions = [
            {"mention_id": "m1", "name": "Alice Smith"},
            {"mention_id": "m2", "name": "Alice Smyth"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Fuzzy-similar names should share one cluster")
        fuzzy_row = next(r for r in result if r["mention_id"] == "m2")
        self.assertEqual(fuzzy_row["resolution_method"], "fuzzy")

    def test_distinct_names_produce_separate_clusters(self):
        mentions = [
            {"mention_id": "m1", "name": "Alice"},
            {"mention_id": "m2", "name": "Bob"},
            {"mention_id": "m3", "name": "Charlie"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 3)

    def test_all_rows_have_resolved_false(self):
        mentions = [
            {"mention_id": "m1", "name": "Alice"},
            {"mention_id": "m2", "name": "Bob"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        for row in result:
            self.assertFalse(row["resolved"])

    def test_fuzzy_blocked_by_entity_type(self):
        """Fuzzy matching must not cross entity_type boundaries."""
        # "Alice Smith" (person) and "Alice Smyth" (org) are fuzzy-similar, but
        # the entity_type blocking should prevent them from sharing a cluster.
        mentions = [
            {"mention_id": "m1", "name": "Alice Smith", "entity_type": "person"},
            {"mention_id": "m2", "name": "Alice Smyth", "entity_type": "organization"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 2, "Cross-type fuzzy match should be blocked")

    def test_fuzzy_within_same_entity_type(self):
        """Fuzzy matching works when entity_type matches."""
        mentions = [
            {"mention_id": "m1", "name": "Alice Smith", "entity_type": "person"},
            {"mention_id": "m2", "name": "Alice Smyth", "entity_type": "person"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Same-type fuzzy-similar names should cluster")

    def test_rekey_does_not_cross_entity_type_boundary(self):
        """Abbreviation re-key must not remap mentions of a different entity_type.

        A 'person' mention with key "fbi" (introduced via normalized_exact from
        a different type) must stay on that key even when an 'organization' long
        form causes a re-key of 'fbi' → 'federal bureau of investigation' within
        the organization type.
        """
        mentions = [
            # organization: "fbi" arrives first (label_cluster for org type)
            {"mention_id": "m1", "name": "fbi", "entity_type": "organization"},
            # person: "fbi" arrives second — normalized_exact hit, clusters into the
            # shared 'fbi' key (type-agnostic strategy 1)
            {"mention_id": "m2", "name": "fbi", "entity_type": "person"},
            # organization: long form arrives; re-keys 'fbi' → long form for org only
            {"mention_id": "m3", "name": "Federal Bureau of Investigation",
             "entity_type": "organization"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        # org mentions (m1, m3) must share the long-form cluster key
        self.assertEqual(by_mid["m1"]["normalized_text"],
                         by_mid["m3"]["normalized_text"])
        self.assertEqual(by_mid["m1"]["normalized_text"],
                         "federal bureau of investigation")
        # person mention (m2) must NOT be re-keyed — it has a different entity_type
        self.assertEqual(by_mid["m2"]["normalized_text"], "fbi",
                         "Cross-type remap must not affect person mention")

    def test_short_key_stays_in_seen_keys_when_cross_type_mentions_remain(self):
        """After abbreviation re-key, short_key must remain in seen_keys if
        cross-type mentions still reference it, so future same-text mentions of
        those types still hit normalized_exact (Strategy 1) rather than
        creating a duplicate cluster.
        """
        mentions = [
            # organization: "fbi" first
            {"mention_id": "m1", "name": "fbi", "entity_type": "organization"},
            # person: "fbi" second — hits normalized_exact, shares "fbi" key
            {"mention_id": "m2", "name": "fbi", "entity_type": "person"},
            # organization: long form — re-keys "fbi" → long form for org only
            {"mention_id": "m3", "name": "Federal Bureau of Investigation",
             "entity_type": "organization"},
            # person: a fourth mention with identical name must still join the
            # existing "fbi" cluster (not create a new one), because the
            # cross-type short_key must still be in seen_keys.
            {"mention_id": "m4", "name": "fbi", "entity_type": "person"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        # m2 and m4 are both person-type "fbi"; they must be in the same cluster
        self.assertEqual(by_mid["m2"]["normalized_text"],
                         by_mid["m4"]["normalized_text"],
                         "Duplicate person 'fbi' must join existing cluster, not create new one")
        # m4 is a normalized_exact hit (not label_cluster)
        self.assertEqual(by_mid["m4"]["resolution_method"], "normalized_exact")
        # org mentions (m1, m3) share the long-form cluster
        self.assertEqual(by_mid["m1"]["normalized_text"], "federal bureau of investigation")
        self.assertEqual(by_mid["m3"]["normalized_text"], "federal bureau of investigation")

    def test_normalized_exact_registers_cluster_for_same_type_fuzzy_matching(self):
        """After a normalized_exact cross-type hit the cluster must be visible
        in the per-type indices so that a later same-type mention can still
        fuzzy-match against it.
        """
        mentions = [
            # "org" type introduces "federal reserve system" first
            {"mention_id": "m1", "name": "Federal Reserve System", "entity_type": "org"},
            # "agency" type hits normalized_exact — joins the same key
            {"mention_id": "m2", "name": "Federal Reserve System", "entity_type": "agency"},
            # "agency" type: pluralised variant — should fuzzy-match the
            # cluster that "agency" now knows about via the cross-type hit
            {"mention_id": "m3", "name": "Federal Reserve Systems", "entity_type": "agency"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        # m2 and m3 must share the same cluster key (both are "agency" type)
        self.assertEqual(by_mid["m2"]["normalized_text"],
                         by_mid["m3"]["normalized_text"],
                         "Same-type fuzzy match must work after cross-type normalized_exact hit")
        self.assertIn(by_mid["m3"]["resolution_method"], ("fuzzy", "normalized_exact"))

    def test_multiple_abbreviation_variants_all_promoted_to_long_form(self):
        """Both 'fbi' and 'f.b.i.' (same alpha 'fbi') must be promoted to the
        long-form cluster when 'federal bureau of investigation' is seen; no
        abbreviation cluster should remain orphaned.
        """
        mentions = [
            # Two abbreviation variants of the same long form, same type.
            {"mention_id": "m1", "name": "fbi", "entity_type": "organization"},
            {"mention_id": "m2", "name": "f.b.i.", "entity_type": "organization"},
            # Long form seen last — must adopt BOTH prior abbreviation mentions.
            {"mention_id": "m3", "name": "Federal Bureau of Investigation",
             "entity_type": "organization"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        long_key = "federal bureau of investigation"
        self.assertEqual(
            by_mid["m1"]["normalized_text"], long_key,
            "'fbi' mention must be promoted to the long-form cluster",
        )
        self.assertEqual(
            by_mid["m2"]["normalized_text"], long_key,
            "'f.b.i.' mention must be promoted to the long-form cluster",
        )
        self.assertEqual(
            by_mid["m3"]["normalized_text"], long_key,
            "Long-form mention must belong to its own cluster key",
        )

    def test_output_rows_include_entity_type(self):
        """Every output row must carry the normalized entity_type from the input mention."""
        mentions = [
            {"mention_id": "m1", "name": "Acme", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Acme", "entity_type": "PRODUCT"},
            {"mention_id": "m3", "name": "Widget"},  # no entity_type key
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        self.assertIn("entity_type", by_mid["m1"])
        # "ORG" is normalized to "Organization" in the output
        self.assertEqual(by_mid["m1"]["entity_type"], "Organization")
        self.assertEqual(by_mid["m2"]["entity_type"], "PRODUCT")
        self.assertIsNone(by_mid["m3"]["entity_type"])

    # ------------------------------------------------------------------ #
    # Normalization-aware clustering edge cases
    # ------------------------------------------------------------------ #

    def test_accented_and_plain_variants_share_cluster(self):
        """Accented and unaccented forms of the same name must end up in one cluster."""
        mentions = [
            {"mention_id": "m1", "name": "Müller"},
            {"mention_id": "m2", "name": "Muller"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Accented and unaccented should share a cluster")

    def test_naive_naive_accented_share_cluster(self):
        """naïve and naive should end up in the same cluster."""
        mentions = [
            {"mention_id": "m1", "name": "naïve"},
            {"mention_id": "m2", "name": "naive"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1)

    def test_hyphen_dash_variants_share_cluster(self):
        """Em-dash and hyphen variants of the same name must share a cluster."""
        mentions = [
            {"mention_id": "m1", "name": "state\u2013of\u2013the\u2013art"},  # en-dash
            {"mention_id": "m2", "name": "state-of-the-art"},              # ASCII hyphen
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "En-dash and hyphen variants should share a cluster")

    def test_curly_apostrophe_variants_share_cluster(self):
        """Typographic and ASCII apostrophe variants of the same name must share a cluster."""
        mentions = [
            {"mention_id": "m1", "name": "McDonald\u2019s"},   # RIGHT SINGLE QUOTATION MARK
            {"mention_id": "m2", "name": "McDonald's"},         # ASCII apostrophe
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Curly and plain apostrophes should share a cluster")

    def test_whitespace_variants_share_cluster(self):
        """Extra or non-standard whitespace must not create separate clusters."""
        mentions = [
            {"mention_id": "m1", "name": "United  States"},   # double space
            {"mention_id": "m2", "name": "United\u00A0States"},  # non-breaking space
            {"mention_id": "m3", "name": "United States"},    # normal space
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        cluster_keys = {r["normalized_text"] for r in result}
        self.assertEqual(len(cluster_keys), 1, "Whitespace variants should all share a cluster")

    def test_normalized_text_output_is_cleaned(self):
        """normalized_text field in output rows must reflect the cleaned form."""
        mentions = [{"mention_id": "m1", "name": "  Ré sumé  "}]
        result = _cluster_mentions_unstructured_only(mentions)
        self.assertEqual(result[0]["normalized_text"], "re sume")

    def test_ORG_and_Organization_mentions_share_cluster_after_normalization(self):
        """Mentions with entity_type 'ORG' and 'Organization' must share a type-scoped cluster.

        Before normalization, 'ORG' and 'Organization' were treated as distinct
        types, splitting fuzzy/abbreviation clustering across them.  After
        normalization both map to 'Organization', so they use the same type bucket
        and the same cluster_id.
        """
        mentions = [
            {"mention_id": "m1", "name": "MercadoLibre", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "MercadoLibre", "entity_type": "Organization"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        # Both must resolve to the same normalized_text (which drives cluster_id)
        self.assertEqual(by_mid["m1"]["normalized_text"], by_mid["m2"]["normalized_text"])
        # Both must carry the normalized entity_type
        self.assertEqual(by_mid["m1"]["entity_type"], "Organization")
        self.assertEqual(by_mid["m2"]["entity_type"], "Organization")

    def test_Company_mentions_cluster_with_Organization_mentions(self):
        """Mentions with entity_type 'Company' must share a cluster with 'Organization' mentions."""
        mentions = [
            {"mention_id": "m1", "name": "Xapo", "entity_type": "Company"},
            {"mention_id": "m2", "name": "Xapo", "entity_type": "Organization"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        self.assertEqual(by_mid["m1"]["normalized_text"], by_mid["m2"]["normalized_text"])
        self.assertEqual(by_mid["m1"]["entity_type"], "Organization")
        self.assertEqual(by_mid["m2"]["entity_type"], "Organization")

    def test_PERSON_and_Person_mentions_share_cluster_after_normalization(self):
        """Mentions with entity_type 'PERSON' and 'Person' must share a type-scoped cluster."""
        mentions = [
            {"mention_id": "m1", "name": "Linda Rottenberg", "entity_type": "PERSON"},
            {"mention_id": "m2", "name": "Linda Rottenberg", "entity_type": "Person"},
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        self.assertEqual(by_mid["m1"]["normalized_text"], by_mid["m2"]["normalized_text"])
        self.assertEqual(by_mid["m1"]["entity_type"], "Person")
        self.assertEqual(by_mid["m2"]["entity_type"], "Person")


    """Tests for run_entity_resolution with resolution_mode='unstructured_only'."""

    def _live_config(self, tmp_path: Path) -> Config:
        return Config(
            dry_run=False,
            output_dir=tmp_path,
            neo4j_uri="bolt://example.invalid",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            openai_model="test-model",
            resolution_mode=_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
        )

    def _make_driver(self, mentions: list[dict[str, Any]]) -> MagicMock:
        return _make_neo4j_test_driver(mentions, [])

    def test_dry_run_mode_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                resolution_mode=_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
            )
            result = run_entity_resolution(config, run_id="test-uo-dry", source_uri=None)
            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_UNSTRUCTURED_ONLY)

    def test_live_no_canonical_lookup(self):
        """unstructured_only should NOT touch CanonicalEntity nodes at all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-uo-001", source_uri=None)

            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(
                any("CanonicalEntity" in call for call in all_calls),
                "unstructured_only mode must not reference CanonicalEntity in any query",
            )

    def test_live_all_mentions_clustered(self):
        """In unstructured_only mode all mentions end up in clusters (unresolved)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-002", source_uri=None)

            self.assertEqual(result["resolved"], 0)
            self.assertEqual(result["unresolved"], 2)
            self.assertEqual(result["mentions_total"], 2)

    def test_live_mentions_clustered_equals_mentions_total(self):
        """In unstructured_only mode mentions_clustered == mentions_total and mentions_unclustered == 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
                {"mention_id": "m3", "name": "Charlie", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-clustered-001", source_uri=None)

            self.assertEqual(result["mentions_clustered"], result["mentions_total"])
            self.assertEqual(result["mentions_unclustered"], 0)

    def test_live_clustering_invariant(self):
        """mentions_clustered + mentions_unclustered == mentions_total (graph-backed invariant)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
                {"mention_id": "m3", "name": "Charlie", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-invariant-001", source_uri=None)

            self.assertEqual(
                result["mentions_clustered"] + result["mentions_unclustered"],
                result["mentions_total"],
            )

    def test_dry_run_includes_mentions_clustered_zero(self):
        """dry_run summary must include mentions_clustered and mentions_unclustered (both 0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                resolution_mode=_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
            )
            result = run_entity_resolution(config, run_id="run-uo-dry-clustered", source_uri=None)
            self.assertIn("mentions_clustered", result)
            self.assertIn("mentions_unclustered", result)
            self.assertEqual(result["mentions_clustered"], 0)
            self.assertEqual(result["mentions_unclustered"], 0)

    def test_live_normalized_exact_reduces_clusters(self):
        """Two mentions with the same normalized text -> one cluster."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": None},
                {"mention_id": "m2", "name": "ALICE", "entity_type": None},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-003", source_uri=None)

            self.assertEqual(result["clusters_created"], 1)

    def test_live_resolution_mode_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            driver = self._make_driver([])

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-004", source_uri=None)

            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_UNSTRUCTURED_ONLY)

    def test_live_resolution_breakdown_no_structured_methods(self):
        """Resolution breakdown should not contain qid_exact/label_exact/alias_exact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Widget Corp", "entity_type": None},
                {"mention_id": "m2", "name": "Widget Corp.", "entity_type": None},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-uo-005", source_uri=None)

            breakdown = result["resolution_breakdown"]
            self.assertNotIn("qid_exact", breakdown)
            self.assertNotIn("label_exact", breakdown)
            self.assertNotIn("alias_exact", breakdown)

    def test_explicit_arg_overrides_config_mode(self):
        """resolution_mode kwarg overrides config.resolution_mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                resolution_mode="structured_anchor",
            )
            result = run_entity_resolution(
                config,
                run_id="run-uo-override",
                source_uri=None,
                resolution_mode=_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
            )
            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_UNSTRUCTURED_ONLY)

    def test_invalid_resolution_mode_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            with self.assertRaises(ValueError) as ctx:
                run_entity_resolution(
                    config,
                    run_id="run-uo-bad-mode",
                    source_uri=None,
                    resolution_mode="invalid_mode",
                )
            self.assertIn("invalid_mode", str(ctx.exception))

    def _get_member_of_rows(self, driver: MagicMock) -> list[dict]:
        """Extract the 'rows' parameter from the MEMBER_OF Cypher write call."""
        for call in driver.execute_query.call_args_list:
            query = call.args[0] if call.args else ""
            params = call.kwargs.get("parameters_", {})
            if "MEMBER_OF" in query and "rows" in params:
                return params["rows"]
        return []

    def test_deterministic_methods_write_accepted_status(self):
        """label_cluster and normalized_exact must write status='accepted'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                # m1: singleton → label_cluster for "uniquename1"
                {"mention_id": "m1", "name": "UniqueName1", "entity_type": "person"},
                # m2: duplicate of m1 → normalized_exact for "uniquename1"
                {"mention_id": "m2", "name": "UniqueName1", "entity_type": "person"},
                # m3: distinct singleton → label_cluster for "uniquename2"
                {"mention_id": "m3", "name": "UniqueName2", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-status-001", source_uri=None)

            rows = self._get_member_of_rows(driver)
            self.assertTrue(rows, "Expected MEMBER_OF rows in Cypher call")
            by_method = {r["method"]: r["status"] for r in rows}
            self.assertEqual(
                by_method.get("label_cluster"), "accepted",
                "label_cluster must write status='accepted'",
            )
            self.assertEqual(
                by_method.get("normalized_exact"), "accepted",
                "normalized_exact must write status='accepted'",
            )

    def test_fuzzy_method_writes_provisional_status(self):
        """High-confidence fuzzy matches (ratio >= _FUZZY_REVIEW_THRESHOLD) write status='provisional'.

        'Federal Reserve Board' vs 'Federal Reserve Boards' has a SequenceMatcher ratio
        of ~0.977 which is above _FUZZY_REVIEW_THRESHOLD=0.92, so the membership is
        classified as 'provisional' (minor surface-form variant, review optional).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            # Two mentions that fuzzy-match each other (same type, similar text)
            mentions = [
                {"mention_id": "m1", "name": "Federal Reserve Board",
                 "entity_type": "organization"},
                {"mention_id": "m2", "name": "Federal Reserve Boards",
                 "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-status-002", source_uri=None)

            rows = self._get_member_of_rows(driver)
            self.assertTrue(rows, "Expected MEMBER_OF rows in Cypher call")
            fuzzy_rows = [r for r in rows if r["method"] == "fuzzy"]
            self.assertTrue(fuzzy_rows, "Expected at least one fuzzy row")
            for r in fuzzy_rows:
                self.assertEqual(
                    r["status"], "provisional",
                    f"fuzzy row must write status='provisional', got {r['status']!r}",
                )

    def test_abbreviation_method_writes_candidate_status(self):
        """abbreviation cluster assignments must write status='candidate'.

        Abbreviated forms are inherently ambiguous (e.g. 'FBI' could match multiple
        long forms), so they are classified as 'candidate' rather than 'provisional'
        to make the ambiguity explicit for downstream consumers and reviewers.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Federal Bureau of Investigation",
                 "entity_type": "organization"},
                {"mention_id": "m2", "name": "fbi",
                 "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-status-003", source_uri=None)

            rows = self._get_member_of_rows(driver)
            self.assertTrue(rows, "Expected MEMBER_OF rows in Cypher call")
            abbrev_rows = [r for r in rows if r["method"] == "abbreviation"]
            self.assertTrue(abbrev_rows, "Expected at least one abbreviation row")
            for r in abbrev_rows:
                self.assertEqual(
                    r["status"], "candidate",
                    f"abbreviation row must write status='candidate', got {r['status']!r}",
                )

    def test_borderline_fuzzy_writes_review_required_status(self):
        """Borderline fuzzy matches (ratio < _FUZZY_REVIEW_THRESHOLD) must write status='review_required'.

        'European Central Bank' vs 'Euro Central Bank' has a similarity of ~0.895,
        which is above the fuzzy entry threshold (0.85) but below _FUZZY_REVIEW_THRESHOLD
        (0.92), so the membership is classified as 'review_required'.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "European Central Bank",
                 "entity_type": "organization"},
                {"mention_id": "m2", "name": "Euro Central Bank",
                 "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-status-005", source_uri=None)

            rows = self._get_member_of_rows(driver)
            self.assertTrue(rows, "Expected MEMBER_OF rows in Cypher call")
            fuzzy_rows = [r for r in rows if r["method"] == "fuzzy"]
            self.assertTrue(fuzzy_rows, "Expected at least one fuzzy row")
            for r in fuzzy_rows:
                self.assertEqual(
                    r["status"], "review_required",
                    f"borderline fuzzy row must write status='review_required', got {r['status']!r}",
                )

    def _get_candidate_match_rows(self, driver: MagicMock) -> list[dict]:
        """Extract the 'rows' parameter from the CANDIDATE_MATCH Cypher write call."""
        for call in driver.execute_query.call_args_list:
            query = call.args[0] if call.args else ""
            params = call.kwargs.get("parameters_", {})
            if "CANDIDATE_MATCH" in query and "rows" in params:
                return params["rows"]
        return []

    def test_candidate_match_edges_written_for_abbreviation(self):
        """CANDIDATE_MATCH edges must be written for 'candidate' (abbreviation) memberships."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Federal Bureau of Investigation",
                 "entity_type": "organization"},
                {"mention_id": "m2", "name": "fbi",
                 "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cand-001", source_uri=None)

            candidate_rows = self._get_candidate_match_rows(driver)
            self.assertTrue(candidate_rows, "Expected CANDIDATE_MATCH rows for abbreviation memberships")
            for r in candidate_rows:
                self.assertIn(
                    r["status"], ("candidate", "review_required"),
                    f"CANDIDATE_MATCH row must have candidate/review_required status, got {r['status']!r}",
                )

    def test_candidate_match_edges_written_for_borderline_fuzzy(self):
        """CANDIDATE_MATCH edges must be written for 'review_required' (borderline fuzzy) memberships."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "European Central Bank",
                 "entity_type": "organization"},
                {"mention_id": "m2", "name": "Euro Central Bank",
                 "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cand-002", source_uri=None)

            candidate_rows = self._get_candidate_match_rows(driver)
            self.assertTrue(candidate_rows, "Expected CANDIDATE_MATCH rows for borderline fuzzy memberships")
            review_rows = [r for r in candidate_rows if r["status"] == "review_required"]
            self.assertTrue(review_rows, "Expected at least one review_required CANDIDATE_MATCH row")

    def test_no_candidate_match_edges_for_accepted_memberships(self):
        """CANDIDATE_MATCH edges must NOT be written for deterministic ('accepted') memberships."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            # Use names with no textual similarity so they each form singletons via
            # label_cluster (deterministic, status='accepted') and cannot fuzzy-match.
            mentions = [
                {"mention_id": "m1", "name": "Alpha Corp", "entity_type": "organization"},
                {"mention_id": "m2", "name": "Zeta LLC", "entity_type": "organization"},
            ]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-cand-003", source_uri=None)

            candidate_rows = self._get_candidate_match_rows(driver)
            self.assertEqual(
                candidate_rows, [],
                "No CANDIDATE_MATCH edges should be written for purely accepted memberships",
            )


    """Unit tests for _align_clusters_to_canonical."""

    def setUp(self):
        canonical_nodes = [
            {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": "Ali|Alicia"},
            {"entity_id": "Q2", "run_id": "run-s1", "name": "Bob Corp", "aliases": "BC,Bobby Corp"},
        ]
        _, self.by_label, self.by_alias = _build_lookup_tables(canonical_nodes)

    def _cluster(self, run_id: str, entity_type: str | None, normalized_text: str) -> dict:
        """Build a cluster dict matching the _make_cluster_id format used in production."""
        return {
            "cluster_id": _make_cluster_id(run_id, entity_type, normalized_text),
            "normalized_text": normalized_text,
        }

    def test_label_exact_match_returned(self):
        c = self._cluster("run-t1", "person", "alice")
        rows = _align_clusters_to_canonical([c], self.by_label, self.by_alias)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cluster_id"], c["cluster_id"])
        self.assertEqual(rows[0]["canonical_entity_id"], "Q1")
        self.assertEqual(rows[0]["alignment_method"], "label_exact")
        self.assertAlmostEqual(rows[0]["alignment_score"], 0.9)
        self.assertEqual(rows[0]["alignment_status"], "aligned")

    def test_alias_exact_match_returned(self):
        c = self._cluster("run-t1", None, "ali")
        rows = _align_clusters_to_canonical([c], self.by_label, self.by_alias)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["canonical_entity_id"], "Q1")
        self.assertEqual(rows[0]["alignment_method"], "alias_exact")
        self.assertAlmostEqual(rows[0]["alignment_score"], 0.8)

    def test_label_preferred_over_alias(self):
        # "bob corp" should match label_exact, not alias_exact
        c = self._cluster("run-t1", "org", "bob corp")
        rows = _align_clusters_to_canonical([c], self.by_label, self.by_alias)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["alignment_method"], "label_exact")

    def test_no_match_returns_empty(self):
        c = self._cluster("run-t1", None, "unknown entity xyz")
        rows = _align_clusters_to_canonical([c], self.by_label, self.by_alias)
        self.assertEqual(rows, [])

    def test_empty_input_returns_empty(self):
        rows = _align_clusters_to_canonical([], self.by_label, self.by_alias)
        self.assertEqual(rows, [])

    def test_partial_matches_only_matched_returned(self):
        clusters = [
            self._cluster("run-t1", "person", "alice"),
            self._cluster("run-t1", None, "unknown xyz"),
            self._cluster("run-t1", "org", "bc"),
        ]
        rows = _align_clusters_to_canonical(clusters, self.by_label, self.by_alias)
        # "alice" label_exact + "bc" alias_exact; "unknown xyz" has no match
        self.assertEqual(len(rows), 2)
        cluster_ids = {r["cluster_id"] for r in rows}
        self.assertIn(clusters[0]["cluster_id"], cluster_ids)
        self.assertIn(clusters[2]["cluster_id"], cluster_ids)

    def test_empty_lookup_tables_returns_empty(self):
        c = self._cluster("run-t1", None, "alice")
        rows = _align_clusters_to_canonical([c], {}, {})
        self.assertEqual(rows, [])


class TestRunEntityResolutionHybrid(unittest.TestCase):
    """Tests for run_entity_resolution with resolution_mode='hybrid'."""

    def _live_config(self, tmp_path: Path) -> Config:
        return Config(
            dry_run=False,
            output_dir=tmp_path,
            neo4j_uri="bolt://example.invalid",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            openai_model="test-model",
            resolution_mode=_RESOLUTION_MODE_HYBRID,
        )

    def _dry_config(self, tmp_path: Path) -> Config:
        return Config(
            dry_run=True,
            output_dir=tmp_path,
            neo4j_uri="bolt://example.invalid",
            neo4j_username="neo4j",
            neo4j_password="not-used",
            neo4j_database="neo4j",
            openai_model="test-model",
            resolution_mode=_RESOLUTION_MODE_HYBRID,
        )

    def _make_driver(
        self,
        mentions: list[dict[str, Any]],
        canonical_nodes: list[dict[str, Any]],
    ) -> MagicMock:
        return _make_neo4j_test_driver(mentions, canonical_nodes)

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def test_dry_run_returns_hybrid_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-001", source_uri=None)
            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_HYBRID)

    def test_dry_run_includes_alignment_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-002", source_uri=None)
            self.assertIn("alignment_version", result)
            self.assertEqual(result["alignment_version"], _ALIGNMENT_VERSION)

    def test_dry_run_includes_aligned_clusters_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-003", source_uri=None)
            self.assertIn("aligned_clusters", result)
            self.assertEqual(result["aligned_clusters"], 0)

    def test_dry_run_includes_alignment_breakdown_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-004", source_uri=None)
            self.assertIn("alignment_breakdown", result)
            self.assertEqual(result["alignment_breakdown"], {})

    def test_dry_run_resolver_method(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-005", source_uri=None)
            self.assertEqual(
                result["resolver_method"],
                "unstructured_clustering_with_canonical_alignment",
            )

    # ------------------------------------------------------------------
    # Live: unstructured clustering behaves identically to unstructured_only
    # ------------------------------------------------------------------

    def test_live_all_mentions_become_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-001", source_uri=None)
            self.assertEqual(result["resolved"], 0)
            self.assertEqual(result["unresolved"], 2)
            self.assertEqual(result["mentions_total"], 2)

    def test_live_member_of_edge_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Widget Corp", "entity_type": None}]
            driver = self._make_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="hybrid-live-002", source_uri=None)
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertTrue(any("MEMBER_OF" in c for c in all_calls))

    def test_live_no_aligned_clusters_when_no_canonical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            driver = self._make_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-003", source_uri=None)
            self.assertEqual(result["aligned_clusters"], 0)
            # No ALIGNED_WITH *write* (MERGE) should happen when there are no canonical nodes.
            # Post-write read queries do contain ALIGNED_WITH in their text, so we check
            # specifically for write queries (MERGE) rather than all ALIGNED_WITH occurrences.
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(
                any("MERGE" in c and "ALIGNED_WITH" in c for c in all_calls),
                "No ALIGNED_WITH MERGE write should occur when there are no canonical nodes",
            )

    # ------------------------------------------------------------------
    # Live: enrichment alignment when CanonicalEntity nodes exist
    # ------------------------------------------------------------------

    def test_live_aligned_with_edge_written_for_label_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-004", source_uri=None)
            self.assertEqual(result["aligned_clusters"], 1)
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertTrue(any("ALIGNED_WITH" in c for c in all_calls))

    def test_live_aligned_with_written_with_non_null_source_uri(self):
        """ALIGNED_WITH edges must also be written correctly with a non-null source_uri."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)
            source_uri = "file:///test-doc.pdf"
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="hybrid-live-004b", source_uri=source_uri
                )
            self.assertEqual(result["aligned_clusters"], 1)
            # Verify the ALIGNED_WITH write call carries the source_uri in its parameters
            aligned_with_calls = [
                call for call in driver.execute_query.call_args_list
                if "ALIGNED_WITH" in (call.args[0] if call.args else "")
            ]
            self.assertTrue(aligned_with_calls, "Expected an ALIGNED_WITH write call")
            params = aligned_with_calls[0].kwargs.get("parameters_", {})
            self.assertEqual(params.get("source_uri"), source_uri)

    def test_live_aligned_with_written_for_alias_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            # "ali" is an alias for "Alice" (Q1)
            mentions = [{"mention_id": "m1", "name": "Ali", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": "Ali|Alicia"}]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-005", source_uri=None)
            self.assertEqual(result["aligned_clusters"], 1)
            self.assertEqual(result["alignment_breakdown"].get("alias_exact"), 1)

    def test_live_alignment_breakdown_reflects_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "BC", "entity_type": "org"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
                {"entity_id": "Q2", "run_id": "run-s1", "name": "Bob Corp", "aliases": "BC"},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-006", source_uri=None)
            self.assertEqual(result["aligned_clusters"], 2)
            self.assertEqual(result["alignment_breakdown"].get("label_exact"), 1)
            self.assertEqual(result["alignment_breakdown"].get("alias_exact"), 1)

    def test_live_unaligned_clusters_preserved(self):
        """Clusters with no canonical match must still exist (MEMBER_OF written)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Unknown Corp", "entity_type": "org"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-007", source_uri=None)
            # One cluster aligned, one unaligned — both clusters still in unresolved
            self.assertEqual(result["unresolved"], 2)
            self.assertEqual(result["clusters_created"], 2)
            self.assertEqual(result["aligned_clusters"], 1)

    def test_live_mentions_clustered_equals_mentions_total(self):
        """In hybrid mode mentions_clustered == mentions_total and mentions_unclustered == 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-mc-001", source_uri=None)
            self.assertEqual(result["mentions_clustered"], result["mentions_total"])
            self.assertEqual(result["mentions_unclustered"], 0)

    def test_live_clustering_invariant(self):
        """mentions_clustered + mentions_unclustered == mentions_total (graph-backed invariant)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob", "entity_type": "person"},
            ]
            driver = self._make_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-invariant-001", source_uri=None)
            self.assertEqual(
                result["mentions_clustered"] + result["mentions_unclustered"],
                result["mentions_total"],
            )

    def test_live_distinct_canonical_entities_aligned(self):
        """distinct_canonical_entities_aligned counts unique canonical entity IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            # Two mentions both align to the same canonical entity Q1
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Ali", "entity_type": "person"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": "Ali"},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-dce-001", source_uri=None)
            # Both clusters align to the same canonical entity Q1,
            # so distinct_canonical_entities_aligned == 1 regardless of cluster count.
            self.assertGreaterEqual(result["aligned_clusters"], 1)
            self.assertEqual(result["distinct_canonical_entities_aligned"], 1)

    def test_live_distinct_canonical_entities_aligned_multiple(self):
        """distinct_canonical_entities_aligned counts multiple distinct canonical IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob Corp", "entity_type": "org"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
                {"entity_id": "Q2", "run_id": "run-s1", "name": "Bob Corp", "aliases": None},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-dce-002", source_uri=None)
            self.assertEqual(result["distinct_canonical_entities_aligned"], 2)

    def test_live_mentions_in_aligned_clusters(self):
        """mentions_in_aligned_clusters counts mentions in clusters with ALIGNED_WITH edges."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            # "alice" and "ALICE" normalize to the same cluster, aligned to Q1
            # "Unknown" forms a separate unaligned cluster
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "ALICE", "entity_type": "person"},
                {"mention_id": "m3", "name": "Unknown", "entity_type": "person"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-miac-001", source_uri=None)
            # 2 mentions are in the "alice" cluster which aligns to Q1
            self.assertEqual(result["mentions_in_aligned_clusters"], 2)
            # "Unknown" is in an unaligned cluster
            self.assertEqual(result["clusters_pending_alignment"], 1)

    def test_live_clusters_pending_alignment_zero_when_all_align(self):
        """clusters_pending_alignment == 0 when every cluster aligns to a canonical."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": "Alice", "entity_type": "person"},
                {"mention_id": "m2", "name": "Bob Corp", "entity_type": "org"},
            ]
            canonicals = [
                {"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None},
                {"entity_id": "Q2", "run_id": "run-s1", "name": "Bob Corp", "aliases": None},
            ]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-cpa-001", source_uri=None)
            self.assertEqual(result["clusters_pending_alignment"], 0)
            self.assertEqual(result["aligned_clusters"], result["clusters_created"])

    def test_dry_run_includes_clustering_and_alignment_metrics(self):
        """dry_run summary must include all new clustering/alignment metric fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._dry_config(Path(tmpdir))
            result = run_entity_resolution(config, run_id="hybrid-dry-metrics", source_uri=None)
            for field in (
                "mentions_clustered",
                "mentions_unclustered",
                "distinct_canonical_entities_aligned",
                "mentions_in_aligned_clusters",
                "clusters_pending_alignment",
            ):
                self.assertIn(field, result, f"dry_run summary missing field: {field}")
                self.assertEqual(result[field], 0, f"dry_run {field} should be 0")

    def test_live_resolution_mode_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            driver = self._make_driver([], [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-008", source_uri=None)
            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_HYBRID)

    def test_live_resolver_method_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            driver = self._make_driver([], [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-009", source_uri=None)
            self.assertEqual(
                result["resolver_method"],
                "unstructured_clustering_with_canonical_alignment",
            )

    def test_live_alignment_version_in_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            driver = self._make_driver([], [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="hybrid-live-010", source_uri=None)
            self.assertIn("alignment_version", result)
            self.assertEqual(result["alignment_version"], _ALIGNMENT_VERSION)

    def test_explicit_arg_overrides_config_mode(self):
        """resolution_mode kwarg overrides config.resolution_mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
                resolution_mode="structured_anchor",
            )
            result = run_entity_resolution(
                config,
                run_id="hybrid-override",
                source_uri=None,
                resolution_mode=_RESOLUTION_MODE_HYBRID,
            )
            self.assertEqual(result["resolution_mode"], _RESOLUTION_MODE_HYBRID)

    def test_live_does_not_create_resolves_to_edges(self):
        """hybrid mode must not write RESOLVES_TO edges (mentions stay in clusters)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q1", "run_id": "run-s1", "name": "Alice", "aliases": None}]
            driver = self._make_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="hybrid-live-011", source_uri=None)
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(
                any("RESOLVES_TO" in c for c in all_calls),
                "hybrid mode must not write RESOLVES_TO edges",
            )


class TestManifestGraphConsistency(unittest.TestCase):
    """End-to-end consistency checks between manifest summaries and graph state.

    These tests mirror the live-run scenario described in the issue tracker:
      - graph state:  262 mentions, 197 clusters, 262 MEMBER_OF, 23 ALIGNED_WITH
      - manifest bug: alignment metrics (e.g. ``aligned_clusters``) are 0/absent
        despite 23 ALIGNED_WITH edges; ``resolved=0, unresolved=262`` is expected
        in hybrid/unstructured_only modes and is not itself a bug.

    Each assertion message identifies whether the failure is in graph-write
    execution (MERGE queries) or in manifest post-write query capture, so
    reviewers can narrow the root cause without inspecting Neo4j directly.
    """

    def _live_hybrid_config(self, tmp_path: Path) -> Config:
        return dataclass_replace(_live_config(tmp_path), resolution_mode=_RESOLUTION_MODE_HYBRID)

    def _live_unstructured_config(self, tmp_path: Path) -> Config:
        return dataclass_replace(_live_config(tmp_path), resolution_mode=_RESOLUTION_MODE_UNSTRUCTURED_ONLY)

    @staticmethod
    def _make_mentions(count: int, prefix: str = "Entity") -> list[dict[str, Any]]:
        """Generate ``count`` unique mentions with distinct normalized texts."""
        return [
            {"mention_id": f"m{i}", "name": f"{prefix} {i}", "entity_type": "person"}
            for i in range(count)
        ]

    @staticmethod
    def _make_canonicals(
        mentions: list[dict[str, Any]], count: int
    ) -> list[dict[str, Any]]:
        """Return canonical nodes matching the first ``count`` mention names."""
        return [
            {
                "entity_id": f"Q{i}",
                "run_id": "canonical-run",
                "name": m["name"],
                "aliases": None,
            }
            for i, m in enumerate(mentions[:count])
        ]

    # ------------------------------------------------------------------
    # unstructured_only: clustering invariants at scale
    # ------------------------------------------------------------------

    def test_unstructured_only_all_mentions_clustered_at_scale(self):
        """A moderate number of mentions must all appear in MEMBER_OF clusters and partition invariants must hold."""
        n = 64
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_unstructured_config(Path(tmpdir))
            mentions = self._make_mentions(n)
            driver = _make_neo4j_test_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-uo-scale-001", source_uri=None
                )
        # All mentions must be clustered.
        self.assertEqual(
            result["mentions_clustered"],
            n,
            "mentions_clustered must equal mentions_total; "
            "if this fails, MEMBER_OF edges were not written for all mentions "
            "(graph-write failure, not manifest summarization).",
        )
        self.assertEqual(
            result["mentions_unclustered"],
            0,
            "mentions_unclustered must be 0 when all mentions have MEMBER_OF edges; "
            "if this fails, the post-write MEMBER_OF coverage query is incorrect "
            "(manifest summarization failure).",
        )
        # Partition invariant: clustered + unclustered == total.
        self.assertEqual(
            result["mentions_clustered"] + result["mentions_unclustered"],
            result["mentions_total"],
            "mentions_clustered + mentions_unclustered must equal mentions_total; "
            "a mismatch indicates the manifest summarization is inconsistent with graph state.",
        )

    def test_unstructured_only_clusters_created_at_most_mentions_total(self):
        """clusters_created can never exceed mentions_total."""
        n = 262
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_unstructured_config(Path(tmpdir))
            mentions = self._make_mentions(n)
            driver = _make_neo4j_test_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-uo-clusters-001", source_uri=None
                )
        self.assertLessEqual(
            result["clusters_created"],
            result["mentions_total"],
            "clusters_created must not exceed mentions_total; "
            "each cluster needs at least one member mention.",
        )

    # ------------------------------------------------------------------
    # hybrid: alignment invariants — mirrors the live-run evidence
    # ------------------------------------------------------------------

    def test_hybrid_all_mentions_clustered_at_scale(self):
        """In hybrid mode all mentions must be in MEMBER_OF clusters."""
        n = 64
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_hybrid_config(Path(tmpdir))
            mentions = self._make_mentions(n)
            driver = _make_neo4j_test_driver(mentions, [])
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-hybrid-cluster-001", source_uri=None
                )
        self.assertEqual(
            result["mentions_clustered"],
            n,
            "Graph-backed mentions_clustered must equal mentions_total in hybrid mode; "
            "if this fails, MEMBER_OF writes did not cover every mention "
            "(graph-write failure).",
        )
        self.assertEqual(
            result["mentions_unclustered"],
            0,
            "mentions_unclustered must be 0 when all mentions have MEMBER_OF edges; "
            "if this fails, the post-write MEMBER_OF coverage query is returning "
            "a non-zero count (manifest summarization failure).",
        )

    def test_hybrid_aligned_clusters_nonzero_when_alignments_exist(self):
        """Manifest aligned_clusters must be > 0 when ALIGNED_WITH edges exist in the graph.

        This is the primary regression test for the live-run divergence where the
        graph held 23 ALIGNED_WITH edges but the manifest reported resolved=0 /
        unresolved=262 with no alignment metrics.  A failure here means the
        post-write ALIGNED_WITH query result is not being captured in the manifest
        (manifest summarization failure, not a graph-write failure).
        """
        n_mentions = 30
        n_aligned = 23
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_hybrid_config(Path(tmpdir))
            mentions = self._make_mentions(n_mentions)
            canonicals = self._make_canonicals(mentions, n_aligned)
            driver = _make_neo4j_test_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-hybrid-align-001", source_uri=None
                )
                aligned_query_calls = []
                for (_args, kwargs) in driver.execute_query.call_args_list:
                    params = kwargs.get("parameters_")
                    if not params:
                        continue
                    if params.get("run_id") != "consistency-hybrid-align-001":
                        continue
                    if params.get("alignment_version") != _ALIGNMENT_VERSION:
                        continue
                    if not _args or not isinstance(_args[0], str):
                        continue
                    query_text = re.sub(r"\s+", " ", _args[0]).strip()
                    if "ALIGNED_WITH" in query_text and "AS aligned_clusters" in query_text:
                        aligned_query_calls.append(kwargs)
                self.assertTrue(
                    aligned_query_calls,
                    "expected aligned-clusters query to be called with run_id and "
                    "alignment_version parameters to scope post-write alignment metrics.",
                )
        self.assertGreater(
            result["aligned_clusters"],
            0,
            "aligned_clusters must be > 0 when canonical nodes exist and ALIGNED_WITH "
            "edges were written; if this fails, the manifest is not reading post-write "
            "graph state (manifest summarization failure).",
        )
        self.assertGreater(
            result["mentions_in_aligned_clusters"],
            0,
            "mentions_in_aligned_clusters must be > 0 when aligned_clusters > 0; "
            "if this fails, the graph-backed query for aligned mentions is returning 0 "
            "(post-write query failure).",
        )

    def test_hybrid_alignment_bounds_invariant(self):
        """aligned_clusters <= clusters_created and mentions_in_aligned <= mentions_clustered."""
        n_mentions = 50
        n_aligned = 20
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_hybrid_config(Path(tmpdir))
            mentions = self._make_mentions(n_mentions)
            canonicals = self._make_canonicals(mentions, n_aligned)
            driver = _make_neo4j_test_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-hybrid-bounds-001", source_uri=None
                )
        self.assertLessEqual(
            result["aligned_clusters"],
            result["clusters_created"],
            "aligned_clusters cannot exceed clusters_created; "
            "a violation means the manifest is over-counting aligned clusters.",
        )
        self.assertLessEqual(
            result["mentions_in_aligned_clusters"],
            result["mentions_clustered"],
            "mentions_in_aligned_clusters cannot exceed mentions_clustered; "
            "a violation means the manifest is over-counting aligned mentions.",
        )

    def test_hybrid_alignment_partition_invariant(self):
        """aligned_clusters + clusters_pending_alignment == clusters_created."""
        n_mentions = 40
        n_aligned = 15
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_hybrid_config(Path(tmpdir))
            mentions = self._make_mentions(n_mentions)
            canonicals = self._make_canonicals(mentions, n_aligned)
            driver = _make_neo4j_test_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-hybrid-partition-001", source_uri=None
                )
        self.assertEqual(
            result["aligned_clusters"] + result["clusters_pending_alignment"],
            result["clusters_created"],
            "aligned_clusters + clusters_pending_alignment must equal clusters_created; "
            "a mismatch indicates the manifest is deriving clusters_pending_alignment "
            "from stale or incorrect graph totals.",
        )

    def test_hybrid_manifest_reflects_graph_at_live_run_scale(self):
        """End-to-end: manifest must accurately reflect graph state at a realistic live-run scale.

        This test uses a moderately sized synthetic dataset with:
          - all extracted mentions clustered (MEMBER_OF coverage)
          - a non-zero number of ALIGNED_WITH edges via provided canonical nodes

        The unstructured clustering algorithm merges similarly-named mentions via
        fuzzy matching, so the actual number of distinct clusters (and therefore
        aligned clusters) will be smaller than the raw mention count.  The key
        invariant is that the manifest must *not* report zero aligned_clusters when
        ALIGNED_WITH edges exist in the graph — that was the live-run bug.

        Assertion messages identify whether the failure is in graph-write execution
        or in manifest post-write query capture.
        """
        # Use a moderate number of mentions to keep test runtime reasonable while
        # still exercising the clustering and alignment logic at scale.
        n_mentions = 50
        # Provide canonical nodes for the first few mentions.  Due to fuzzy merging
        # some of these will correspond to the same cluster, so the resulting
        # aligned_clusters count will be <= n_canonical.  The critical property under
        # test is that aligned_clusters > 0, not its exact value.
        n_canonical = 5
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_hybrid_config(Path(tmpdir))
            mentions = self._make_mentions(n_mentions)
            canonicals = self._make_canonicals(mentions, n_canonical)
            driver = _make_neo4j_test_driver(mentions, canonicals)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config, run_id="consistency-hybrid-live-scale-001", source_uri=None
                )

        # ---- Extraction counts ----
        self.assertEqual(result["mentions_total"], n_mentions)

        # ---- Clustering counts (MEMBER_OF coverage) ----
        self.assertEqual(
            result["mentions_clustered"],
            n_mentions,
            "mentions_clustered must equal mentions_total; "
            "if this fails, MEMBER_OF edges were not written for every mention "
            "(graph-write failure).",
        )
        self.assertEqual(
            result["mentions_unclustered"],
            0,
            "mentions_unclustered must be 0 when all mentions have MEMBER_OF edges; "
            "if this fails, the post-write MEMBER_OF coverage query returned a "
            "non-zero count (manifest summarization failure).",
        )
        self.assertLessEqual(result["clusters_created"], n_mentions)

        # ---- Alignment counts (ALIGNED_WITH coverage) ----
        # The graph has ALIGNED_WITH edges (canonical nodes were provided); the
        # manifest must not report zero.  This is the regression assertion for the
        # live-run bug where the manifest showed resolved=0 / unresolved=262 while
        # the graph held 23 ALIGNED_WITH edges.
        self.assertGreater(
            result["aligned_clusters"],
            0,
            "Manifest aligned_clusters must be > 0 when canonical nodes exist and "
            "ALIGNED_WITH edges were written to the graph; "
            "if this fails, the manifest is not reading post-write ALIGNED_WITH state "
            "(manifest summarization failure).",
        )
        self.assertGreater(
            result["mentions_in_aligned_clusters"],
            0,
            "mentions_in_aligned_clusters must be > 0 when aligned_clusters > 0; "
            "if this fails, the post-write query for aligned mentions is broken "
            "(manifest summarization failure).",
        )

        # ---- Internal consistency invariants ----
        self.assertEqual(
            result["mentions_clustered"] + result["mentions_unclustered"],
            result["mentions_total"],
        )
        self.assertEqual(
            result["aligned_clusters"] + result["clusters_pending_alignment"],
            result["clusters_created"],
        )
        self.assertLessEqual(result["aligned_clusters"], result["clusters_created"])
        self.assertLessEqual(
            result["mentions_in_aligned_clusters"], result["mentions_clustered"]
        )


class TestArtifactSubdirValidation(unittest.TestCase):
    """Tests for artifact_subdir path safety in run_entity_resolution."""

    def _config(self, tmp_path: Path) -> Config:
        return Config(
            dry_run=True,
            output_dir=tmp_path,
            neo4j_uri="bolt://example.invalid",
            neo4j_username="neo4j",
            neo4j_password="not-used",
            neo4j_database="neo4j",
            openai_model="test-model",
        )

    def test_valid_simple_subdir_writes_artifacts(self):
        """A simple relative subdir name is accepted and artifacts are written there."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            run_entity_resolution(
                config,
                run_id="run-subdir-001",
                source_uri=None,
                artifact_subdir="entity_resolution_custom",
            )
            expected = (
                Path(tmpdir)
                / "runs"
                / "run-subdir-001"
                / "entity_resolution_custom"
                / "entity_resolution_summary.json"
            )
            self.assertTrue(expected.exists())

    def test_valid_nested_subdir_is_accepted(self):
        """A nested relative subdir path such as 'a/b' is accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            run_entity_resolution(
                config,
                run_id="run-subdir-002",
                source_uri=None,
                artifact_subdir="phase1/entity_resolution",
            )

    @unittest.skipIf(not hasattr(os, "symlink"), "os.symlink not supported on this platform")
    def test_symlink_escape_is_rejected(self):
        """
        A symlink under the run directory that points outside must be rejected.

        This ensures that artifact_subdir validation using .resolve() and a parent
        check correctly prevents symlink-based directory escapes.
        """
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside_dir:
            config = self._config(Path(tmpdir))
            run_id = "run-subdir-symlink-escape"
            run_root = Path(tmpdir) / "runs" / run_id
            run_root.mkdir(parents=True, exist_ok=True)

            outside_path = Path(outside_dir)
            evil_link = run_root / "evil_link"

            try:
                # Create a symlink under the run directory pointing outside it.
                evil_link.symlink_to(outside_path, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are not supported or cannot be created on this platform")

            # artifact_subdir refers to the symlink; resolution should detect that the
            # resolved path is outside the run root and reject it.
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id=run_id,
                    source_uri=None,
                    artifact_subdir="evil_link",
                )

    def test_absolute_path_is_rejected(self):
        """An absolute path in artifact_subdir must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id="run-subdir-003",
                    source_uri=None,
                    artifact_subdir="/etc/passwd",
                )

    def test_double_dot_segment_is_rejected(self):
        """A subdir containing '..' must be rejected to prevent directory traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id="run-subdir-004",
                    source_uri=None,
                    artifact_subdir="../escaped_dir",
                )

    def test_double_dot_in_middle_is_rejected(self):
        """A subdir like 'a/../b' also contains '..' and must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id="run-subdir-005",
                    source_uri=None,
                    artifact_subdir="a/../b",
                )

    def test_empty_string_subdir_is_rejected(self):
        """An empty string artifact_subdir resolves to run_root itself and must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id="run-subdir-006",
                    source_uri=None,
                    artifact_subdir="",
                )

    def test_dot_subdir_is_rejected(self):
        """A bare '.' artifact_subdir resolves to run_root itself and must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            with self.assertRaises(ValueError):
                run_entity_resolution(
                    config,
                    run_id="run-subdir-007",
                    source_uri=None,
                    artifact_subdir=".",
                )

    def test_default_subdir_still_writes_to_entity_resolution(self):
        """The default artifact_subdir="entity_resolution" is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(Path(tmpdir))
            run_entity_resolution(config, run_id="run-subdir-008", source_uri=None)
            expected = (
                Path(tmpdir)
                / "runs"
                / "run-subdir-008"
                / "entity_resolution"
                / "entity_resolution_summary.json"
            )
            self.assertTrue(expected.exists())


class TestHybridAlignmentCrossDatasetIsolation(unittest.TestCase):
    """Regression tests for cross-dataset alignment isolation.

    Verifies that hybrid alignment for a dataset (e.g. demo_dataset_v2) attaches
    clusters to CanonicalEntity nodes belonging to that dataset, not to nodes from
    a different dataset (e.g. demo_dataset_v1) that share the same QID.

    Reproduces the issue described in: Make hybrid alignment dataset-local for
    shared canonical entities.
    """

    _V1_DATASET = "demo_dataset_v1"
    _V2_DATASET = "demo_dataset_v2"
    _SHARED_QID = "Q950419"
    _SHARED_NAME = "Mercado Libre"

    def _live_config(self, tmp_path: Path) -> Config:
        return Config(
            dry_run=False,
            output_dir=tmp_path,
            neo4j_uri="bolt://example.invalid",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            openai_model="test-model",
            resolution_mode=_RESOLUTION_MODE_HYBRID,
        )

    def _make_cross_dataset_driver(
        self,
        mentions: list[dict[str, Any]],
        all_canonicals: list[dict[str, Any]],
        target_dataset_id: str,
    ) -> MagicMock:
        """Build a mock driver holding canonical nodes from two datasets.

        The CanonicalEntity query response is filtered by ``dataset_id`` so that
        only canonical nodes from *target_dataset_id* are returned, mirroring the
        new ``WHERE canonical.dataset_id = $dataset_id`` filter in the real query.
        Post-write alignment count queries are pre-computed from *target_dataset_id*
        canonical nodes only.
        """

        class _Record(dict):
            pass

        mention_records = [
            _Record(
                mention_id=m["mention_id"],
                name=m["name"],
                entity_type=m.get("entity_type"),
                source_uri=m.get("source_uri"),
            )
            for m in mentions
        ]

        # All canonical records across all datasets (what would exist in the database).
        all_canonical_records = [
            _Record(
                entity_id=c["entity_id"],
                run_id=c.get("run_id", ""),
                name=c["name"],
                aliases=c.get("aliases"),
                dataset_id=c.get("dataset_id"),
            )
            for c in all_canonicals
        ]

        # Pre-compute alignment counts using only target-dataset canonical nodes.
        target_canonicals = [c for c in all_canonicals if c.get("dataset_id") == target_dataset_id]
        _cluster_rows = _cluster_mentions_unstructured_only([
            {
                "mention_id": m["mention_id"],
                "name": m["name"],
                "entity_type": m.get("entity_type"),
                "source_uri": m.get("source_uri"),
            }
            for m in mentions
        ])
        _cluster_entries: dict[tuple[str, str], dict[str, Any]] = {}
        for row in _cluster_rows:
            _key = (row.get("entity_type") or "", row["normalized_text"])
            if _key not in _cluster_entries:
                _cluster_entries[_key] = {
                    "cluster_id": _key,
                    "normalized_text": row["normalized_text"],
                }
        _unique_clusters = list(_cluster_entries.values())
        _total_cluster_count = len(_unique_clusters)
        _, _by_label, _by_alias = _build_lookup_tables([
            {
                "entity_id": c["entity_id"],
                "run_id": c.get("run_id", ""),
                "name": c["name"],
                "aliases": c.get("aliases"),
            }
            for c in target_canonicals
        ])
        _alignment_rows = _align_clusters_to_canonical(_unique_clusters, _by_label, _by_alias)
        _aligned_cluster_keys = {r["cluster_id"] for r in _alignment_rows}
        _aligned_cluster_count = len(_aligned_cluster_keys)
        _distinct_canonical_count = len(
            {(r["canonical_entity_id"], r["canonical_run_id"]) for r in _alignment_rows}
        )
        _mentions_in_aligned = sum(
            1 for row in _cluster_rows
            if (row.get("entity_type") or "", row["normalized_text"]) in _aligned_cluster_keys
        )
        _alignment_breakdown: dict[str, int] = {}
        for _arow in _alignment_rows:
            _method = _arow.get("alignment_method") or "unknown"
            _alignment_breakdown[_method] = _alignment_breakdown.get(_method, 0) + 1

        member_of_written = False
        aligned_with_written = False

        def execute_query(query, parameters_=None, database_=None, routing_=None):
            nonlocal member_of_written, aligned_with_written

            if "MERGE" in query and "MEMBER_OF" in query:
                member_of_written = True
            if "MERGE" in query and "ALIGNED_WITH" in query:
                aligned_with_written = True

            if "mentions_clustered" in query:
                if member_of_written:
                    return ([_Record(mentions_clustered=len(mention_records), mentions_unclustered=0)], None, None)
                return ([_Record(mentions_clustered=0, mentions_unclustered=len(mention_records))], None, None)
            if "total_clusters" in query:
                if member_of_written:
                    return ([_Record(total_clusters=_total_cluster_count)], None, None)
                return ([_Record(total_clusters=0)], None, None)
            if "aligned_clusters" in query:
                if aligned_with_written:
                    return (
                        [_Record(aligned_clusters=_aligned_cluster_count,
                                 distinct_canonical_entities_aligned=_distinct_canonical_count)],
                        None, None,
                    )
                return ([_Record(aligned_clusters=0, distinct_canonical_entities_aligned=0)], None, None)
            if "alignment_method" in query and "ALIGNED_WITH" in query:
                if aligned_with_written:
                    return (
                        [_Record(alignment_method=method, method_count=count)
                         for method, count in _alignment_breakdown.items()],
                        None, None,
                    )
                return ([], None, None)
            if "mentions_in_aligned" in query:
                if aligned_with_written:
                    return ([_Record(mentions_in_aligned=_mentions_in_aligned)], None, None)
                return ([_Record(mentions_in_aligned=0)], None, None)
            if "EntityMention" in query and "RETURN" in query:
                return (mention_records, None, None)
            if "CanonicalEntity" in query and "RETURN" in query:
                # Return only the target dataset's canonical nodes, matching the
                # WHERE canonical.dataset_id = $dataset_id filter in the real query.
                params = parameters_ or {}
                req_dataset = params.get("dataset_id")
                if req_dataset is not None:
                    filtered = [r for r in all_canonical_records if r.get("dataset_id") == req_dataset]
                    return (filtered, None, None)
                return (all_canonical_records, None, None)
            return ([], None, None)

        driver = MagicMock()
        driver.execute_query.side_effect = execute_query
        driver.__enter__ = lambda s: s
        driver.__exit__ = MagicMock(return_value=False)
        return driver

    def test_v2_hybrid_aligns_to_v2_canonical_not_v1_for_shared_qid(self):
        """v2 hybrid alignment must attach v2 clusters to v2 CanonicalEntity nodes.

        When both demo_dataset_v1 and demo_dataset_v2 contain a CanonicalEntity for
        the same QID (e.g. Q950419 / Mercado Libre), running hybrid resolution for v2
        must align v2 clusters to the v2 canonical entity, not the v1 one.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": self._SHARED_NAME, "entity_type": "organization"},
            ]
            # Both datasets have the same entity but with dataset-local run_ids.
            all_canonicals = [
                {
                    "entity_id": self._SHARED_QID,
                    "run_id": "structured-run-v1",
                    "name": self._SHARED_NAME,
                    "aliases": None,
                    "dataset_id": self._V1_DATASET,
                },
                {
                    "entity_id": self._SHARED_QID,
                    "run_id": "structured-run-v2",
                    "name": self._SHARED_NAME,
                    "aliases": None,
                    "dataset_id": self._V2_DATASET,
                },
            ]
            driver = self._make_cross_dataset_driver(mentions, all_canonicals, self._V2_DATASET)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config,
                    run_id="cross-ds-hybrid-001",
                    source_uri=None,
                    dataset_id=self._V2_DATASET,
                )

            # Alignment should have occurred.
            self.assertGreaterEqual(result["aligned_clusters"], 1, "Expected at least one aligned cluster")

            # Inspect the ALIGNED_WITH MERGE call to confirm it references v2's run_id.
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            aligned_with_merges = [c for c in all_calls if "MERGE" in c and "ALIGNED_WITH" in c]
            self.assertTrue(aligned_with_merges, "Expected at least one ALIGNED_WITH MERGE write")
            self.assertTrue(
                any("structured-run-v2" in c for c in aligned_with_merges),
                "ALIGNED_WITH edge must reference the v2 canonical entity (structured-run-v2); "
                "cross-dataset leakage detected.",
            )
            self.assertFalse(
                any("structured-run-v1" in c for c in aligned_with_merges),
                "ALIGNED_WITH edge must NOT reference the v1 canonical entity (structured-run-v1); "
                "cross-dataset leakage detected.",
            )

    def test_v2_canonical_query_is_scoped_by_dataset_id(self):
        """The CanonicalEntity lookup query must include dataset_id = v2 in its parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": self._SHARED_NAME, "entity_type": "organization"},
            ]
            all_canonicals = [
                {
                    "entity_id": self._SHARED_QID,
                    "run_id": "structured-run-v1",
                    "name": self._SHARED_NAME,
                    "aliases": None,
                    "dataset_id": self._V1_DATASET,
                },
                {
                    "entity_id": self._SHARED_QID,
                    "run_id": "structured-run-v2",
                    "name": self._SHARED_NAME,
                    "aliases": None,
                    "dataset_id": self._V2_DATASET,
                },
            ]
            driver = self._make_cross_dataset_driver(mentions, all_canonicals, self._V2_DATASET)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(
                    config,
                    run_id="cross-ds-hybrid-002",
                    source_uri=None,
                    dataset_id=self._V2_DATASET,
                )

            # Verify that the CanonicalEntity READ query was called with dataset_id=v2.
            # The dataset-scoped lookup query (hybrid enrichment pass) contains both
            # "dataset_id" in the query text and uses WHERE filtering; exclude
            # post-write count queries that also mention CanonicalEntity.
            canonical_read_calls = [
                c for c in driver.execute_query.call_args_list
                if "CanonicalEntity" in str(c) and "RETURN" in str(c)
                and "dataset_id" in str(c) and "ALIGNED_WITH" not in str(c)
            ]
            self.assertTrue(canonical_read_calls, "Expected a CanonicalEntity read query with dataset_id filter")
            for call_obj in canonical_read_calls:
                # call_args_list entries are call(args, kwargs) objects; parameters_ is
                # passed as a keyword argument.
                _, kwargs = call_obj
                params = kwargs.get("parameters_") or {}
                self.assertEqual(
                    params.get("dataset_id"),
                    self._V2_DATASET,
                    "CanonicalEntity read query must be scoped to demo_dataset_v2",
                )

    def test_no_cross_dataset_leakage_when_only_v1_exists(self):
        """When dataset_id=v2 and only v1 canonical entities exist, no alignment occurs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [
                {"mention_id": "m1", "name": self._SHARED_NAME, "entity_type": "organization"},
            ]
            # Only v1 canonical node exists; v2 has none.
            all_canonicals = [
                {
                    "entity_id": self._SHARED_QID,
                    "run_id": "structured-run-v1",
                    "name": self._SHARED_NAME,
                    "aliases": None,
                    "dataset_id": self._V1_DATASET,
                },
            ]
            driver = self._make_cross_dataset_driver(mentions, all_canonicals, self._V2_DATASET)
            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(
                    config,
                    run_id="cross-ds-hybrid-003",
                    source_uri=None,
                    dataset_id=self._V2_DATASET,
                )

            # No alignment should happen because v2 has no canonical entities.
            self.assertEqual(result["aligned_clusters"], 0, "No alignment expected when v2 has no canonical nodes")
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(
                any("MERGE" in c and "ALIGNED_WITH" in c for c in all_calls),
                "No ALIGNED_WITH MERGE should occur when v2 has no canonical entities",
            )


if __name__ == "__main__":
    unittest.main()
