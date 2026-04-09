"""Tests for the retrieval benchmark stage.

Structure
---------
``TestRecordsToDicts``
    Verify that Neo4j-Record-like objects are coerced to plain dicts.

``TestCountHelpers``
    Unit tests for ``_count_distinct``, ``_count_distinct_claims``,
    ``_count_distinct_clusters``, and ``_detect_fragmentation``.

``TestComputeBenchmarkSummary``
    Unit tests for the ``_compute_benchmark_summary`` helper.

``TestBuildBenchmarkCaseResult``
    Unit tests for ``build_benchmark_case_result``, verifying that derived
    metrics are computed correctly from pre-fetched rows.

``TestBuildBenchmarkArtifact``
    Unit tests for ``build_benchmark_artifact``, verifying that the artifact
    is constructed correctly from case results and that it is JSON-serialisable.

``TestRunRetrievalBenchmarkDryRun``
    Tests that drive ``run_retrieval_benchmark`` in dry_run mode (no Neo4j
    connection required).

``TestRunRetrievalBenchmarkLive``
    Tests that drive ``run_retrieval_benchmark`` in live mode with a mocked
    Neo4j driver.

``TestBenchmarkCasesContract``
    Tests that verify the static :data:`BENCHMARK_CASES` constant meets its
    documented contracts (all required fields non-empty, case_type values
    from the allowed set, entity_names non-empty, pairwise cases have two
    names, etc.).

``TestCypherQueryHygiene``
    Asserts that Cypher query constants do not use deprecated Neo4j functions
    (e.g. ``id()``).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from demo.stages.retrieval_benchmark import (
    BENCHMARK_CASES,
    BenchmarkCaseDefinition,
    BenchmarkCaseResult,
    PairwiseCaseResult,
    RetrievalBenchmarkArtifact,
    _Q_CANONICAL_SINGLE,
    _Q_CATALOG_EXISTENCE_CHECK,
    _Q_LOWER_LAYER_CHAIN,
    _Q_PAIRWISE_CANONICAL,
    _classify_fragmentation_type,
    _compute_benchmark_summary,
    _count_distinct,
    _count_distinct_claims,
    _count_distinct_clusters,
    _detect_fragmentation,
    _records_to_dicts,
    build_benchmark_artifact,
    build_benchmark_case_result,
    run_retrieval_benchmark,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_canonical_rows(n_claims: int, n_clusters: int = 1) -> list[dict[str, Any]]:
    """Return *n_claims* synthetic canonical traversal rows."""
    rows = []
    for i in range(n_claims):
        cluster_idx = i % n_clusters
        rows.append(
            {
                "canonical_entity": "TestEntity",
                "cluster_id": f"cluster-id-{cluster_idx}",
                "cluster": f"TestEntity Cluster {cluster_idx}",
                "mention": f"mention_{i}",
                "role": "subject",
                "claim_text": f"claim {i}",
                "predicate": "did",
                "match_method": "raw_exact",
                "claim_id": f"claim-{i:03d}",
            }
        )
    return rows


def _make_cluster_rows(n_claims: int, n_clusters: int = 1) -> list[dict[str, Any]]:
    """Return *n_claims* synthetic cluster-name traversal rows."""
    rows = []
    for i in range(n_claims):
        cluster_idx = i % n_clusters
        rows.append(
            {
                "cluster_id": f"cluster-id-{cluster_idx}",
                "cluster": f"TestEntity Cluster {cluster_idx}",
                "cluster_type": "Organization",
                "mention": f"mention_{i}",
                "role": "subject",
                "claim_text": f"claim {i}",
                "predicate": "did",
                "match_method": "raw_exact",
                "claim_id": f"claim-{i:03d}",
            }
        )
    return rows


def _make_frag_rows(n_clusters: int) -> list[dict[str, Any]]:
    """Return *n_clusters* synthetic fragmentation check rows."""
    return [
        {
            "cluster_id": f"cluster-{i}",
            "canonical_name": "TestEntity",
            "entity_type": "Organization" if i == 0 else "Person",
        }
        for i in range(n_clusters)
    ]


def _make_catalog_check_rows(present: bool) -> list[dict[str, Any]]:
    """Return synthetic catalog existence check rows.

    Parameters
    ----------
    present:
        When ``True``, return a single row simulating a found ``CanonicalEntity``.
        When ``False``, return an empty list simulating a catalog-absent result.
    """
    if present:
        return [{"canonical_entity_name": "TestEntity"}]
    return []


def _make_lower_layer_rows(n: int) -> list[dict[str, Any]]:
    """Return *n* synthetic lower-layer chain rows."""
    return [
        {
            "canonical_entity": "TestEntity",
            "cluster": "TestEntity Cluster 0",
            "cluster_type": "Organization",
            "mention": f"mention_{i}",
            "mention_type": "Organization",
            "role": "subject",
            "claim_id": f"claim-{i:03d}",
            "claim_text": f"claim {i}",
        }
        for i in range(n)
    ]


def _make_case_def(
    case_id: str = "test_case",
    case_type: str = "single_entity",
    entity_names: list[str] | None = None,
) -> BenchmarkCaseDefinition:
    return BenchmarkCaseDefinition(
        case_id=case_id,
        case_type=case_type,
        entity_names=entity_names or ["testentity"],
        description="A test case.",
        expected_shape="Some rows.",
        failure_modes=["no rows"],
        lower_layer_checks=["inspect chain"],
    )


def _make_case_result(
    case_id: str = "test_case",
    canonical_claim_count: int = 3,
    cluster_claim_count: int = 3,
    canonical_cluster_count: int = 1,
    cluster_name_cluster_count: int = 1,
    fragmentation_detected: bool = False,
    canonical_empty_cluster_populated: bool = False,
    fragmentation_type_hints: list[str] | None = None,
    catalog_check_rows: list[dict[str, Any]] | None = None,
) -> BenchmarkCaseResult:
    resolved_catalog_rows = catalog_check_rows if catalog_check_rows is not None else []
    return BenchmarkCaseResult(
        case_id=case_id,
        case_type="single_entity",
        entity_names=["testentity"],
        description="A test case.",
        expected_shape="Some rows.",
        failure_modes=["no rows"],
        canonical_rows=[],
        cluster_rows=[],
        lower_layer_rows=[],
        fragmentation_check_rows=[],
        canonical_claim_count=canonical_claim_count,
        cluster_claim_count=cluster_claim_count,
        canonical_cluster_count=canonical_cluster_count,
        cluster_name_cluster_count=cluster_name_cluster_count,
        fragmentation_detected=fragmentation_detected,
        canonical_empty_cluster_populated=canonical_empty_cluster_populated,
        fragmentation_type_hints=fragmentation_type_hints if fragmentation_type_hints is not None else [],
        catalog_check_rows=resolved_catalog_rows,
        canonical_catalog_present=bool(resolved_catalog_rows),
    )


def _make_pairwise_result(
    case_id: str = "pairwise_case",
    pairwise_claim_count: int = 2,
) -> PairwiseCaseResult:
    return PairwiseCaseResult(
        case_id=case_id,
        entity_names=["entity_a", "entity_b"],
        description="A pairwise test case.",
        expected_shape="Some rows.",
        failure_modes=["no rows"],
        pairwise_rows=[],
        pairwise_claim_count=pairwise_claim_count,
    )


def _make_config(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.dry_run = dry_run
    cfg.output_dir = tmp_path
    cfg.neo4j_uri = "bolt://localhost:7687"
    cfg.neo4j_username = "neo4j"
    cfg.neo4j_password = "secret"
    cfg.neo4j_database = "neo4j"
    return cfg


# ---------------------------------------------------------------------------
# TestRecordsToDicts
# ---------------------------------------------------------------------------


class TestRecordsToDicts(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(_records_to_dicts([]), [])

    def test_plain_dicts_unchanged(self) -> None:
        rows = [{"a": 1}, {"a": 2}]
        self.assertEqual(_records_to_dicts(rows), rows)

    def test_mapping_like_objects_converted(self) -> None:
        class FakeRecord(dict):
            pass

        rows = [FakeRecord({"role": "subject", "total": 5})]
        self.assertEqual(_records_to_dicts(rows), [{"role": "subject", "total": 5}])


# ---------------------------------------------------------------------------
# TestCountHelpers
# ---------------------------------------------------------------------------


class TestCountHelpers(unittest.TestCase):
    def test_count_distinct_empty(self) -> None:
        self.assertEqual(_count_distinct([], "claim_id"), 0)

    def test_count_distinct_basic(self) -> None:
        rows = [{"claim_id": "c1"}, {"claim_id": "c2"}, {"claim_id": "c1"}]
        self.assertEqual(_count_distinct(rows, "claim_id"), 2)

    def test_count_distinct_ignores_none(self) -> None:
        rows = [{"claim_id": "c1"}, {"claim_id": None}]
        self.assertEqual(_count_distinct(rows, "claim_id"), 1)

    def test_count_distinct_claims(self) -> None:
        rows = _make_canonical_rows(n_claims=5, n_clusters=2)
        self.assertEqual(_count_distinct_claims(rows), 5)

    def test_count_distinct_clusters(self) -> None:
        rows = _make_canonical_rows(n_claims=6, n_clusters=3)
        self.assertEqual(_count_distinct_clusters(rows), 3)

    def test_detect_fragmentation_false(self) -> None:
        self.assertFalse(_detect_fragmentation(2, 2))

    def test_detect_fragmentation_true(self) -> None:
        self.assertTrue(_detect_fragmentation(1, 3))

    def test_detect_fragmentation_canonical_more_clusters(self) -> None:
        # Canonical may aggregate multiple clusters; that is not fragmentation.
        self.assertFalse(_detect_fragmentation(3, 2))


# ---------------------------------------------------------------------------
# TestClassifyFragmentationType
# ---------------------------------------------------------------------------


class TestClassifyFragmentationType(unittest.TestCase):
    """Unit tests for _classify_fragmentation_type."""

    def test_empty_returns_no_hints(self) -> None:
        hints = _classify_fragmentation_type([], [], [])
        self.assertEqual(hints, [])

    def test_entity_type_case_split_detected(self) -> None:
        # "Organization" and "organization" differ only by case.
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "organization"},
        ]
        hints = _classify_fragmentation_type(frag_rows, [], [])
        self.assertIn("entity_type_case_split", hints)

    def test_entity_type_case_split_not_detected_when_types_genuinely_differ(self) -> None:
        # "Organization" and "Person" do not share a common lowercased form.
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "Person"},
        ]
        hints = _classify_fragmentation_type(frag_rows, [], [])
        self.assertNotIn("entity_type_case_split", hints)

    def test_entity_type_case_split_not_detected_when_single_type(self) -> None:
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
        ]
        hints = _classify_fragmentation_type(frag_rows, [], [])
        self.assertNotIn("entity_type_case_split", hints)

    # ------------------------------------------------------------------
    # catalog_absent_or_alignment_gap (backwards-compat: catalog_check_rows=None)
    # ------------------------------------------------------------------

    def test_catalog_absent_or_alignment_gap_detected_when_no_catalog_check(self) -> None:
        # canonical empty, cluster non-empty, catalog_check_rows=None (not provided)
        # → ambiguous combined token for backwards compatibility
        canonical_rows: list[dict] = []
        cluster_rows = _make_cluster_rows(n_claims=3)
        hints = _classify_fragmentation_type([], canonical_rows, cluster_rows)
        self.assertIn("catalog_absent_or_alignment_gap", hints)

    def test_catalog_absent_or_alignment_gap_not_detected_when_canonical_present(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=2)
        cluster_rows = _make_cluster_rows(n_claims=3)
        hints = _classify_fragmentation_type([], canonical_rows, cluster_rows)
        self.assertNotIn("catalog_absent_or_alignment_gap", hints)

    def test_catalog_absent_or_alignment_gap_not_detected_when_both_empty(self) -> None:
        hints = _classify_fragmentation_type([], [], [])
        self.assertNotIn("catalog_absent_or_alignment_gap", hints)

    def test_multiple_hints_when_both_conditions_present_no_catalog_check(self) -> None:
        # Case-split AND canonical empty with cluster populated, no catalog check.
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "organization"},
        ]
        cluster_rows = _make_cluster_rows(n_claims=2)
        hints = _classify_fragmentation_type(frag_rows, [], cluster_rows)
        self.assertIn("entity_type_case_split", hints)
        self.assertIn("catalog_absent_or_alignment_gap", hints)

    # ------------------------------------------------------------------
    # catalog_absent (catalog_check_rows provided and empty)
    # ------------------------------------------------------------------

    def test_catalog_absent_emitted_when_no_canonical_entity_found(self) -> None:
        # canonical empty, cluster non-empty, catalog_check_rows empty → catalog_absent
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=False)
        hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
        self.assertIn("catalog_absent", hints)

    def test_catalog_absent_not_emitted_when_canonical_entity_found(self) -> None:
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=True)
        hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
        self.assertNotIn("catalog_absent", hints)

    def test_catalog_absent_not_emitted_when_canonical_rows_present(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=2)
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=False)
        hints = _classify_fragmentation_type([], canonical_rows, cluster_rows, catalog_check_rows)
        self.assertNotIn("catalog_absent", hints)

    def test_catalog_absent_not_emitted_when_both_empty(self) -> None:
        catalog_check_rows = _make_catalog_check_rows(present=False)
        hints = _classify_fragmentation_type([], [], [], catalog_check_rows)
        self.assertNotIn("catalog_absent", hints)

    # ------------------------------------------------------------------
    # catalog_present_canonical_empty (catalog_check_rows provided and non-empty)
    # ------------------------------------------------------------------

    def test_catalog_present_canonical_empty_emitted_when_canonical_entity_exists_but_no_canonical_rows(self) -> None:
        # canonical empty, cluster non-empty, catalog_check_rows non-empty → catalog_present_canonical_empty
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=True)
        hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
        self.assertIn("catalog_present_canonical_empty", hints)

    def test_catalog_present_canonical_empty_not_emitted_when_canonical_rows_present(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=2)
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=True)
        hints = _classify_fragmentation_type([], canonical_rows, cluster_rows, catalog_check_rows)
        self.assertNotIn("catalog_present_canonical_empty", hints)

    def test_catalog_present_canonical_empty_not_emitted_when_no_canonical_entity(self) -> None:
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_check_rows = _make_catalog_check_rows(present=False)
        hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
        self.assertNotIn("catalog_present_canonical_empty", hints)

    def test_catalog_present_canonical_empty_not_emitted_when_both_empty(self) -> None:
        catalog_check_rows = _make_catalog_check_rows(present=True)
        hints = _classify_fragmentation_type([], [], [], catalog_check_rows)
        self.assertNotIn("catalog_present_canonical_empty", hints)

    # ------------------------------------------------------------------
    # mutual exclusivity: catalog_absent vs catalog_present_canonical_empty
    # ------------------------------------------------------------------

    def test_catalog_absent_and_catalog_present_canonical_empty_are_mutually_exclusive(self) -> None:
        cluster_rows = _make_cluster_rows(n_claims=2)
        for present in (True, False):
            catalog_check_rows = _make_catalog_check_rows(present=present)
            hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
            both = "catalog_absent" in hints and "catalog_present_canonical_empty" in hints
            self.assertFalse(both, f"Both tokens present when catalog present={present}")

    def test_catalog_absent_or_alignment_gap_not_emitted_when_catalog_check_provided(self) -> None:
        # When catalog_check_rows is provided, the ambiguous combined token
        # must not appear — the specific token replaces it.
        cluster_rows = _make_cluster_rows(n_claims=2)
        for present in (True, False):
            catalog_check_rows = _make_catalog_check_rows(present=present)
            hints = _classify_fragmentation_type([], [], cluster_rows, catalog_check_rows)
            self.assertNotIn(
                "catalog_absent_or_alignment_gap",
                hints,
                f"Ambiguous token present when catalog_check_rows provided (present={present})",
            )

    # ------------------------------------------------------------------
    # entity_type_case_split combined with catalog_absent / catalog_present_canonical_empty
    # ------------------------------------------------------------------

    def test_case_split_and_catalog_absent_both_present(self) -> None:
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "organization"},
        ]
        cluster_rows = _make_cluster_rows(n_claims=2)
        catalog_check_rows = _make_catalog_check_rows(present=False)
        hints = _classify_fragmentation_type(frag_rows, [], cluster_rows, catalog_check_rows)
        self.assertIn("entity_type_case_split", hints)
        self.assertIn("catalog_absent", hints)

    def test_case_split_and_catalog_present_canonical_empty_both_present(self) -> None:
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "organization"},
        ]
        cluster_rows = _make_cluster_rows(n_claims=2)
        catalog_check_rows = _make_catalog_check_rows(present=True)
        hints = _classify_fragmentation_type(frag_rows, [], cluster_rows, catalog_check_rows)
        self.assertIn("entity_type_case_split", hints)
        self.assertIn("catalog_present_canonical_empty", hints)

    # ------------------------------------------------------------------
    # null / mixed entity_type handling (unchanged)
    # ------------------------------------------------------------------

    def test_null_entity_type_ignored(self) -> None:
        # Rows with null entity_type should not trigger a false case-split detection.
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": None},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": None},
        ]
        hints = _classify_fragmentation_type(frag_rows, [], [])
        self.assertNotIn("entity_type_case_split", hints)

    def test_mixed_null_and_case_variant_still_detected(self) -> None:
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "Acme", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "Acme", "entity_type": "organization"},
            {"cluster_id": "c3", "canonical_name": "Acme", "entity_type": None},
        ]
        hints = _classify_fragmentation_type(frag_rows, [], [])
        self.assertIn("entity_type_case_split", hints)


# ---------------------------------------------------------------------------
# TestComputeBenchmarkSummary
# ---------------------------------------------------------------------------


class TestComputeBenchmarkSummary(unittest.TestCase):
    def test_empty(self) -> None:
        s = _compute_benchmark_summary([], [])
        self.assertEqual(s["total_cases"], 0)
        self.assertEqual(s["fragmentation_detected_count"], 0)
        self.assertEqual(s["total_canonical_claims"], 0)
        self.assertEqual(s["total_pairwise_claims"], 0)

    def test_counts_fragmentation(self) -> None:
        cases = [
            _make_case_result("a", fragmentation_detected=True),
            _make_case_result("b", fragmentation_detected=False),
            _make_case_result("c", fragmentation_detected=True),
        ]
        s = _compute_benchmark_summary(cases, [])
        self.assertEqual(s["fragmentation_detected_count"], 2)

    def test_counts_entities_with_claims(self) -> None:
        cases = [
            _make_case_result("a", canonical_claim_count=5, cluster_claim_count=3),
            _make_case_result("b", canonical_claim_count=0, cluster_claim_count=2),
        ]
        s = _compute_benchmark_summary(cases, [])
        self.assertEqual(s["entities_with_claims_canonical"], 1)
        self.assertEqual(s["entities_with_claims_cluster"], 2)

    def test_sums_claim_counts(self) -> None:
        cases = [
            _make_case_result("a", canonical_claim_count=4, cluster_claim_count=5),
            _make_case_result("b", canonical_claim_count=2, cluster_claim_count=2),
        ]
        pairwise = [_make_pairwise_result("p", pairwise_claim_count=3)]
        s = _compute_benchmark_summary(cases, pairwise)
        self.assertEqual(s["total_canonical_claims"], 6)
        self.assertEqual(s["total_cluster_claims"], 7)
        self.assertEqual(s["total_pairwise_claims"], 3)

    def test_total_cases_includes_pairwise(self) -> None:
        cases = [_make_case_result("a"), _make_case_result("b")]
        pairwise = [_make_pairwise_result("p1"), _make_pairwise_result("p2")]
        s = _compute_benchmark_summary(cases, pairwise)
        self.assertEqual(s["total_cases"], 4)
        self.assertEqual(s["single_and_comparison_cases"], 2)
        self.assertEqual(s["pairwise_cases"], 2)

    def test_canonical_empty_cluster_populated_count_zero_by_default(self) -> None:
        cases = [
            _make_case_result("a", canonical_claim_count=3, cluster_claim_count=3),
            _make_case_result("b", canonical_claim_count=0, cluster_claim_count=0),
        ]
        s = _compute_benchmark_summary(cases, [])
        self.assertEqual(s["canonical_empty_cluster_populated_count"], 0)

    def test_canonical_empty_cluster_populated_count_nonzero(self) -> None:
        cases = [
            _make_case_result(
                "a",
                canonical_claim_count=0,
                cluster_claim_count=8,
                canonical_empty_cluster_populated=True,
            ),
            _make_case_result(
                "b",
                canonical_claim_count=3,
                cluster_claim_count=3,
                canonical_empty_cluster_populated=False,
            ),
        ]
        s = _compute_benchmark_summary(cases, [])
        self.assertEqual(s["canonical_empty_cluster_populated_count"], 1)

    def test_canonical_empty_cluster_populated_count_in_summary_keys(self) -> None:
        s = _compute_benchmark_summary([], [])
        self.assertIn("canonical_empty_cluster_populated_count", s)


# ---------------------------------------------------------------------------
# TestBuildBenchmarkCaseResult
# ---------------------------------------------------------------------------


class TestBuildBenchmarkCaseResult(unittest.TestCase):
    def test_returns_instance(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertIsInstance(result, BenchmarkCaseResult)

    def test_canonical_claim_count_derived(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=5)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=canonical_rows,
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertEqual(result.canonical_claim_count, 5)

    def test_cluster_claim_count_derived(self) -> None:
        cluster_rows = _make_cluster_rows(n_claims=7)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=cluster_rows,
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertEqual(result.cluster_claim_count, 7)

    def test_fragmentation_not_detected_when_equal_clusters(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=4, n_clusters=2)
        frag_rows = _make_frag_rows(n_clusters=2)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=canonical_rows,
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=frag_rows,
            catalog_check_rows=[],
        )
        self.assertFalse(result.fragmentation_detected)
        self.assertEqual(result.cluster_name_cluster_count, 2)

    def test_fragmentation_detected_when_cluster_name_has_more(self) -> None:
        # canonical path sees 1 cluster; cluster-name path sees 3 (fragmentation)
        canonical_rows = _make_canonical_rows(n_claims=4, n_clusters=1)
        frag_rows = _make_frag_rows(n_clusters=3)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=canonical_rows,
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=frag_rows,
            catalog_check_rows=[],
        )
        self.assertTrue(result.fragmentation_detected)
        self.assertEqual(result.canonical_cluster_count, 1)
        self.assertEqual(result.cluster_name_cluster_count, 3)

    def test_static_fields_copied_from_case_def(self) -> None:
        case_def = _make_case_def(case_id="my_case", case_type="composite_claim")
        result = build_benchmark_case_result(
            case_def=case_def,
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertEqual(result.case_id, "my_case")
        self.assertEqual(result.case_type, "composite_claim")
        self.assertEqual(result.description, case_def.description)
        self.assertEqual(result.expected_shape, case_def.expected_shape)
        self.assertEqual(result.failure_modes, list(case_def.failure_modes))

    def test_rows_preserved(self) -> None:
        ll_rows = _make_lower_layer_rows(3)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=ll_rows,
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertEqual(result.lower_layer_rows, ll_rows)

    def test_to_dict_json_serialisable(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=_make_canonical_rows(2),
            cluster_rows=_make_cluster_rows(2),
            lower_layer_rows=_make_lower_layer_rows(2),
            fragmentation_check_rows=_make_frag_rows(1),
            catalog_check_rows=[],
        )
        d = result.to_dict()
        serialised = json.dumps(d)
        self.assertIn("canonical_claim_count", serialised)

    def test_canonical_empty_cluster_populated_true_when_canonical_empty(self) -> None:
        # canonical_rows empty but cluster_rows populated → flag set
        cluster_rows = _make_cluster_rows(n_claims=4)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=cluster_rows,
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertTrue(result.canonical_empty_cluster_populated)

    def test_canonical_empty_cluster_populated_false_when_canonical_present(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=3)
        cluster_rows = _make_cluster_rows(n_claims=3)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=canonical_rows,
            cluster_rows=cluster_rows,
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertFalse(result.canonical_empty_cluster_populated)

    def test_canonical_empty_cluster_populated_false_when_both_empty(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertFalse(result.canonical_empty_cluster_populated)

    def test_fragmentation_type_hints_entity_type_case_split(self) -> None:
        # Organization vs organization → case-split hint expected.
        # catalog_check_rows=[] (catalog absent) → catalog_absent hint also expected.
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "ML", "entity_type": "Organization"},
            {"cluster_id": "c2", "canonical_name": "ML", "entity_type": "organization"},
        ]
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=_make_cluster_rows(2),
            lower_layer_rows=[],
            fragmentation_check_rows=frag_rows,
            catalog_check_rows=[],
        )
        self.assertIn("entity_type_case_split", result.fragmentation_type_hints)
        self.assertIn("catalog_absent", result.fragmentation_type_hints)

    def test_fragmentation_type_hints_empty_when_healthy(self) -> None:
        canonical_rows = _make_canonical_rows(n_claims=3)
        frag_rows = [
            {"cluster_id": "c1", "canonical_name": "TestEntity", "entity_type": "Organization"},
        ]
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=canonical_rows,
            cluster_rows=_make_cluster_rows(3),
            lower_layer_rows=[],
            fragmentation_check_rows=frag_rows,
            catalog_check_rows=_make_catalog_check_rows(present=True),
        )
        self.assertEqual(result.fragmentation_type_hints, [])

    def test_fragmentation_type_hints_in_to_dict(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        d = result.to_dict()
        self.assertIn("fragmentation_type_hints", d)
        self.assertIn("canonical_empty_cluster_populated", d)
        self.assertIn("catalog_check_rows", d)
        self.assertIn("canonical_catalog_present", d)

    # ------------------------------------------------------------------
    # canonical_catalog_present
    # ------------------------------------------------------------------

    def test_canonical_catalog_present_false_when_catalog_check_rows_empty(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=[],
        )
        self.assertFalse(result.canonical_catalog_present)

    def test_canonical_catalog_present_true_when_catalog_check_rows_non_empty(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=_make_catalog_check_rows(present=True),
        )
        self.assertTrue(result.canonical_catalog_present)

    def test_catalog_check_rows_stored_in_result(self) -> None:
        catalog_rows = _make_catalog_check_rows(present=True)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=[],
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=catalog_rows,
        )
        self.assertEqual(result.catalog_check_rows, catalog_rows)

    def test_catalog_present_canonical_empty_hint_when_catalog_present_and_canonical_empty(self) -> None:
        # canonical empty, cluster populated, catalog present → catalog_present_canonical_empty
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_rows = _make_catalog_check_rows(present=True)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=cluster_rows,
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=catalog_rows,
        )
        self.assertIn("catalog_present_canonical_empty", result.fragmentation_type_hints)
        self.assertTrue(result.canonical_catalog_present)

    def test_catalog_absent_hint_when_no_catalog_entity_and_canonical_empty(self) -> None:
        # canonical empty, cluster populated, catalog absent → catalog_absent
        cluster_rows = _make_cluster_rows(n_claims=3)
        catalog_rows = _make_catalog_check_rows(present=False)
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=[],
            cluster_rows=cluster_rows,
            lower_layer_rows=[],
            fragmentation_check_rows=[],
            catalog_check_rows=catalog_rows,
        )
        self.assertIn("catalog_absent", result.fragmentation_type_hints)
        self.assertFalse(result.canonical_catalog_present)


# ---------------------------------------------------------------------------
# TestBuildBenchmarkArtifact
# ---------------------------------------------------------------------------


class TestBuildBenchmarkArtifact(unittest.TestCase):
    def test_returns_instance(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            alignment_version="v1.0",
            case_results=[],
            pairwise_results=[],
        )
        self.assertIsInstance(artifact, RetrievalBenchmarkArtifact)

    def test_run_id_and_alignment_version_preserved(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="my-run",
            alignment_version="v2.0",
            case_results=[],
            pairwise_results=[],
        )
        self.assertEqual(artifact.run_id, "my-run")
        self.assertEqual(artifact.alignment_version, "v2.0")

    def test_none_run_id(self) -> None:
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
        )
        self.assertIsNone(artifact.run_id)
        self.assertIsNone(artifact.alignment_version)

    def test_generated_at_used_when_provided(self) -> None:
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
            generated_at="2030-01-01T00:00:00Z",
        )
        self.assertEqual(artifact.generated_at, "2030-01-01T00:00:00Z")

    def test_generated_at_defaults_to_now(self) -> None:
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
        )
        self.assertTrue(artifact.generated_at)
        self.assertIn("T", artifact.generated_at)

    def test_case_results_serialised_as_dicts(self) -> None:
        cr = _make_case_result("a")
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=[cr],
            pairwise_results=[],
        )
        self.assertEqual(len(artifact.case_results), 1)
        self.assertIsInstance(artifact.case_results[0], dict)
        self.assertEqual(artifact.case_results[0]["case_id"], "a")

    def test_pairwise_results_serialised_as_dicts(self) -> None:
        pr = _make_pairwise_result("p")
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[pr],
        )
        self.assertEqual(len(artifact.pairwise_results), 1)
        self.assertIsInstance(artifact.pairwise_results[0], dict)
        self.assertEqual(artifact.pairwise_results[0]["case_id"], "p")

    def test_benchmark_summary_derived(self) -> None:
        cases = [
            _make_case_result("a", canonical_claim_count=5),
            _make_case_result("b", canonical_claim_count=3, fragmentation_detected=True),
        ]
        artifact = build_benchmark_artifact(
            run_id=None,
            alignment_version=None,
            case_results=cases,
            pairwise_results=[],
        )
        s = artifact.benchmark_summary
        self.assertEqual(s["total_cases"], 2)
        self.assertEqual(s["fragmentation_detected_count"], 1)
        self.assertEqual(s["total_canonical_claims"], 8)

    def test_to_json_round_trips(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            alignment_version="v1.0",
            case_results=[_make_case_result("a")],
            pairwise_results=[_make_pairwise_result("p")],
        )
        parsed = json.loads(artifact.to_json())
        self.assertEqual(parsed["run_id"], "r1")
        self.assertEqual(parsed["alignment_version"], "v1.0")
        self.assertEqual(len(parsed["case_results"]), 1)
        self.assertEqual(len(parsed["pairwise_results"]), 1)
        self.assertIn("benchmark_summary", parsed)


# ---------------------------------------------------------------------------
# TestRunRetrievalBenchmarkDryRun
# ---------------------------------------------------------------------------


class TestRunRetrievalBenchmarkDryRun(unittest.TestCase):
    def test_returns_dry_run_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            result = run_retrieval_benchmark(config, run_id="run-dry", alignment_version="v1.0")
            self.assertEqual(result["status"], "dry_run")
            self.assertIsNone(result["artifact"])

    def test_writes_artifact_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(config, run_id="run-dry2", alignment_version=None)
            path = (
                Path(tmp)
                / "runs"
                / "run-dry2"
                / "retrieval_benchmark"
                / "retrieval_benchmark.json"
            )
            self.assertTrue(path.exists(), f"Expected artifact at {path}")

    def test_dry_run_no_run_id_uses_runs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(config, run_id=None)
            path = Path(tmp) / "runs" / "retrieval_benchmark" / "retrieval_benchmark.json"
            self.assertTrue(path.exists(), f"Expected artifact at {path}")

    def test_dry_run_artifact_schema_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(config, run_id="run-schema", alignment_version="v1.0")
            path = (
                Path(tmp)
                / "runs"
                / "run-schema"
                / "retrieval_benchmark"
                / "retrieval_benchmark.json"
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("generated_at", data)
            self.assertIn("run_id", data)
            self.assertIn("alignment_version", data)
            self.assertIn("case_results", data)
            self.assertIn("pairwise_results", data)
            self.assertIn("benchmark_summary", data)
            s = data["benchmark_summary"]
            self.assertIn("total_cases", s)
            self.assertIn("fragmentation_detected_count", s)
            self.assertIn("canonical_empty_cluster_populated_count", s)
            self.assertIn("total_canonical_claims", s)
            self.assertIn("total_pairwise_claims", s)

    def test_invalid_run_id_absolute_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            with self.assertRaises(ValueError):
                run_retrieval_benchmark(config, run_id="/etc/passwd")

    def test_invalid_run_id_dotdot_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            with self.assertRaises(ValueError):
                run_retrieval_benchmark(config, run_id="../escape")

    def test_empty_run_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            with self.assertRaises(ValueError):
                run_retrieval_benchmark(config, run_id="")


# ---------------------------------------------------------------------------
# TestRunRetrievalBenchmarkLive
# ---------------------------------------------------------------------------


def _make_mock_driver(rows_by_call: list[list[dict[str, Any]]]) -> MagicMock:
    """Return a mock neo4j.Driver whose execute_query returns successive row lists."""
    driver = MagicMock()
    driver.__enter__ = MagicMock(return_value=driver)
    driver.__exit__ = MagicMock(return_value=False)
    driver.execute_query.side_effect = [(rows, None, None) for rows in rows_by_call]
    return driver


def _empty_case_rows() -> list[list[dict[str, Any]]]:
    """Five empty row lists for one non-pairwise benchmark case.

    Matches the five queries executed per non-pairwise case:
    canonical, cluster, lower_layer, fragmentation_check, catalog_check.
    """
    return [[], [], [], [], []]


def _minimal_live_rows(
    cases: list[BenchmarkCaseDefinition],
) -> list[list[dict[str, Any]]]:
    """Return a list of empty row lists for each query that will be executed.

    For each non-pairwise case: 5 queries (canonical, cluster, lower_layer,
    fragmentation_check, catalog_check).
    For each pairwise case: 1 query (pairwise).
    """
    rows: list[list[dict[str, Any]]] = []
    for c in cases:
        if c.case_type == "pairwise_entity":
            rows.append([])  # pairwise query
        else:
            rows.extend([[], [], [], [], []])  # 5 queries per non-pairwise case
    return rows


class TestRunRetrievalBenchmarkLive(unittest.TestCase):
    def _run_with_mock(
        self,
        tmp_path: Path,
        cases: list[BenchmarkCaseDefinition],
        rows: list[list[dict[str, Any]]],
        run_id: str | None = "run-live-001",
        alignment_version: str | None = "v1.0",
    ) -> dict[str, Any]:
        config = _make_config(tmp_path, dry_run=False)
        mock_driver = _make_mock_driver(rows)
        with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
            mock_neo4j.GraphDatabase.driver.return_value = mock_driver
            mock_neo4j.RoutingControl.READ = "READ"
            return run_retrieval_benchmark(
                config,
                run_id=run_id,
                alignment_version=alignment_version,
                benchmark_cases=cases,
            )

    def test_live_returns_live_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            result = self._run_with_mock(Path(tmp), cases, rows)
            self.assertEqual(result["status"], "live")

    def test_live_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            result = self._run_with_mock(Path(tmp), cases, rows)
            artifact_path = Path(result["artifact_path"])
            self.assertTrue(artifact_path.exists())

    def test_live_artifact_json_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            result = self._run_with_mock(Path(tmp), cases, rows)
            parsed = json.loads(Path(result["artifact_path"]).read_text())
            self.assertEqual(parsed["run_id"], "run-live-001")
            self.assertIn("benchmark_summary", parsed)

    def test_live_case_results_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1"), _make_case_def("c2")]
            rows = _empty_case_rows() + _empty_case_rows()
            result = self._run_with_mock(Path(tmp), cases, rows)
            artifact = result["artifact"]
            self.assertEqual(len(artifact["case_results"]), 2)

    def test_live_pairwise_case_uses_one_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pairwise_def = _make_case_def(
                "pair1", "pairwise_entity", ["entity_a", "entity_b"]
            )
            cases = [pairwise_def]
            rows = [[]]  # one pairwise query
            mock_driver = _make_mock_driver(rows)
            config = _make_config(Path(tmp), dry_run=False)
            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                result = run_retrieval_benchmark(
                    config,
                    run_id="run-p",
                    benchmark_cases=cases,
                )
            self.assertEqual(mock_driver.execute_query.call_count, 1)
            artifact = result["artifact"]
            self.assertEqual(len(artifact["pairwise_results"]), 1)
            self.assertEqual(len(artifact["case_results"]), 0)

    def test_live_five_queries_per_non_pairwise_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1"), _make_case_def("c2")]
            rows = _empty_case_rows() + _empty_case_rows()
            mock_driver = _make_mock_driver(rows)
            config = _make_config(Path(tmp), dry_run=False)
            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                run_retrieval_benchmark(config, run_id="run-q", benchmark_cases=cases)
            # 2 non-pairwise cases × 5 queries each = 10
            self.assertEqual(mock_driver.execute_query.call_count, 10)

    def test_live_fragmentation_detected_when_frag_rows_exceed_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("frag_test", "fragmented_entity")]
            canonical_rows = _make_canonical_rows(n_claims=3, n_clusters=1)
            cluster_rows = _make_cluster_rows(n_claims=3, n_clusters=3)
            lower_rows = _make_lower_layer_rows(3)
            frag_rows = _make_frag_rows(n_clusters=3)
            catalog_rows = _make_catalog_check_rows(present=False)
            rows = [canonical_rows, cluster_rows, lower_rows, frag_rows, catalog_rows]
            result = self._run_with_mock(Path(tmp), cases, rows)
            cr = result["artifact"]["case_results"][0]
            self.assertTrue(cr["fragmentation_detected"])
            self.assertEqual(cr["canonical_cluster_count"], 1)
            self.assertEqual(cr["cluster_name_cluster_count"], 3)

    def test_live_no_fragmentation_when_cluster_counts_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            canonical_rows = _make_canonical_rows(n_claims=4, n_clusters=2)
            cluster_rows = _make_cluster_rows(n_claims=4, n_clusters=2)
            lower_rows = _make_lower_layer_rows(4)
            frag_rows = _make_frag_rows(n_clusters=2)
            catalog_rows = _make_catalog_check_rows(present=True)
            rows = [canonical_rows, cluster_rows, lower_rows, frag_rows, catalog_rows]
            result = self._run_with_mock(Path(tmp), cases, rows)
            cr = result["artifact"]["case_results"][0]
            self.assertFalse(cr["fragmentation_detected"])

    def test_live_summary_reflects_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1"), _make_case_def("c2")]
            # c1: 5 canonical claims; c2: 0
            rows = [
                _make_canonical_rows(5),         # c1 canonical
                _make_cluster_rows(5),            # c1 cluster
                _make_lower_layer_rows(5),        # c1 lower_layer
                _make_frag_rows(1),               # c1 frag
                _make_catalog_check_rows(True),   # c1 catalog_check
                [],  # c2 canonical (empty)
                [],  # c2 cluster (empty)
                [],  # c2 lower_layer
                [],  # c2 frag
                [],  # c2 catalog_check
            ]
            result = self._run_with_mock(Path(tmp), cases, rows)
            s = result["artifact"]["benchmark_summary"]
            self.assertEqual(s["total_cases"], 2)
            self.assertEqual(s["total_canonical_claims"], 5)
            self.assertEqual(s["entities_with_claims_canonical"], 1)

    def test_live_catalog_check_rows_stored_in_case_result(self) -> None:
        # Verify that catalog_check_rows and canonical_catalog_present
        # are present in the serialised case result.
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1")]
            canonical_rows: list[dict] = []
            cluster_rows = _make_cluster_rows(n_claims=2)
            catalog_rows = _make_catalog_check_rows(present=True)
            rows = [canonical_rows, cluster_rows, [], [], catalog_rows]
            result = self._run_with_mock(Path(tmp), cases, rows)
            cr = result["artifact"]["case_results"][0]
            self.assertIn("catalog_check_rows", cr)
            self.assertIn("canonical_catalog_present", cr)
            self.assertTrue(cr["canonical_catalog_present"])
            self.assertIn("catalog_present_canonical_empty", cr["fragmentation_type_hints"])

    def test_live_catalog_absent_hint_when_no_canonical_entity(self) -> None:
        # canonical empty, cluster populated, catalog_check empty → catalog_absent hint
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1")]
            canonical_rows: list[dict] = []
            cluster_rows = _make_cluster_rows(n_claims=2)
            catalog_rows = _make_catalog_check_rows(present=False)
            rows = [canonical_rows, cluster_rows, [], [], catalog_rows]
            result = self._run_with_mock(Path(tmp), cases, rows)
            cr = result["artifact"]["case_results"][0]
            self.assertFalse(cr["canonical_catalog_present"])
            self.assertIn("catalog_absent", cr["fragmentation_type_hints"])


# ---------------------------------------------------------------------------
# TestBenchmarkCasesContract
# ---------------------------------------------------------------------------

_ALLOWED_CASE_TYPES_MODULE = {
    "single_entity",
    "pairwise_entity",
    "fragmented_entity",
    "composite_claim",
    "canonical_vs_cluster",
}


class TestBenchmarkCasesContract(unittest.TestCase):
    """Verify that the static BENCHMARK_CASES constant meets its contract."""

    def test_non_empty(self) -> None:
        self.assertGreater(len(BENCHMARK_CASES), 0)

    def test_all_case_ids_unique(self) -> None:
        ids = [c.case_id for c in BENCHMARK_CASES]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate case_id values found")

    def test_all_case_types_valid(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertIn(
                c.case_type,
                _ALLOWED_CASE_TYPES_MODULE,
                f"Case {c.case_id!r} has invalid case_type {c.case_type!r}",
            )

    def test_all_entity_names_non_empty(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertGreater(
                len(c.entity_names),
                0,
                f"Case {c.case_id!r} has no entity names",
            )
            for name in c.entity_names:
                self.assertIsInstance(name, str)
                self.assertTrue(name.strip(), f"Case {c.case_id!r} has empty entity name")

    def test_pairwise_cases_have_two_entity_names(self) -> None:
        for c in BENCHMARK_CASES:
            if c.case_type == "pairwise_entity":
                self.assertEqual(
                    len(c.entity_names),
                    2,
                    f"Pairwise case {c.case_id!r} must have exactly 2 entity names",
                )

    def test_all_descriptions_non_empty(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertTrue(
                c.description.strip(),
                f"Case {c.case_id!r} has empty description",
            )

    def test_all_expected_shapes_non_empty(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertTrue(
                c.expected_shape.strip(),
                f"Case {c.case_id!r} has empty expected_shape",
            )

    def test_all_failure_modes_non_empty_lists(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertGreater(
                len(c.failure_modes),
                0,
                f"Case {c.case_id!r} has no failure modes",
            )

    def test_all_lower_layer_checks_non_empty_lists(self) -> None:
        for c in BENCHMARK_CASES:
            self.assertGreater(
                len(c.lower_layer_checks),
                0,
                f"Case {c.case_id!r} has no lower_layer_checks",
            )

    def test_benchmark_includes_single_entity_cases(self) -> None:
        types = {c.case_type for c in BENCHMARK_CASES}
        self.assertIn("single_entity", types)

    def test_benchmark_includes_pairwise_case(self) -> None:
        types = {c.case_type for c in BENCHMARK_CASES}
        self.assertIn("pairwise_entity", types)

    def test_benchmark_includes_fragmented_entity_case(self) -> None:
        types = {c.case_type for c in BENCHMARK_CASES}
        self.assertIn("fragmented_entity", types)

    def test_benchmark_includes_composite_claim_case(self) -> None:
        types = {c.case_type for c in BENCHMARK_CASES}
        self.assertIn("composite_claim", types)

    def test_benchmark_includes_canonical_vs_cluster_case(self) -> None:
        types = {c.case_type for c in BENCHMARK_CASES}
        self.assertIn("canonical_vs_cluster", types)

    def test_benchmark_covers_expected_entities(self) -> None:
        all_names = {n.lower() for c in BENCHMARK_CASES for n in c.entity_names}
        for expected in ["mercadolibre", "xapo", "endeavor", "linda rottenberg"]:
            self.assertTrue(
                any(expected in n for n in all_names),
                f"Expected entity {expected!r} not covered by any benchmark case",
            )

    def test_case_definition_is_frozen(self) -> None:
        case = BENCHMARK_CASES[0]
        with self.assertRaises((AttributeError, TypeError)):
            case.case_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cypher query hygiene — no deprecated Neo4j id() usage
# ---------------------------------------------------------------------------

class TestCypherQueryHygiene(unittest.TestCase):
    """Verify that retrieval benchmark Cypher queries do not use deprecated functions."""

    def test_pairwise_canonical_query_does_not_use_deprecated_id(self) -> None:
        import re

        # Match the standalone id() Neo4j function call (case-insensitive).
        # This must not appear in the pairwise query.
        pattern = re.compile(r"\bid\s*\(", re.IGNORECASE)
        self.assertIsNone(
            pattern.search(_Q_PAIRWISE_CANONICAL),
            "Deprecated Neo4j id() function found in _Q_PAIRWISE_CANONICAL; "
            "use direct node comparison (canonObj <> canonSub) instead.",
        )

    def test_catalog_existence_check_query_does_not_use_deprecated_id(self) -> None:
        import re

        pattern = re.compile(r"\bid\s*\(", re.IGNORECASE)
        self.assertIsNone(
            pattern.search(_Q_CATALOG_EXISTENCE_CHECK),
            "Deprecated Neo4j id() function found in _Q_CATALOG_EXISTENCE_CHECK.",
        )

    def test_catalog_existence_check_query_matches_canonical_entity_label(self) -> None:
        # Ensure the query targets CanonicalEntity nodes.
        self.assertIn("CanonicalEntity", _Q_CATALOG_EXISTENCE_CHECK)

    def test_catalog_existence_check_query_uses_entity_name_param(self) -> None:
        # The query must accept $entity_name as its filter parameter.
        self.assertIn("$entity_name", _Q_CATALOG_EXISTENCE_CHECK)

    def test_catalog_existence_check_query_returns_canonical_entity_name(self) -> None:
        # The RETURN column must be canonical_entity_name.
        self.assertIn("canonical_entity_name", _Q_CATALOG_EXISTENCE_CHECK)


# ---------------------------------------------------------------------------
# TestDatasetIdScoping
# ---------------------------------------------------------------------------


class TestDatasetIdScoping(unittest.TestCase):
    """Tests that verify dataset_id is propagated through the benchmark pipeline.

    These tests cover:
    - dataset_id is stamped as a top-level field in the artifact
    - dataset_id=None is preserved correctly (all-datasets mode)
    - Cypher queries contain $dataset_id filter clauses for CanonicalEntity nodes
    - dataset_id is included in the query parameters passed to Neo4j
    - Dry-run artifact includes dataset_id
    - Multi-dataset scenario: benchmark scoped to v1 does not see v2 entities
    """

    # ------------------------------------------------------------------
    # Artifact-level dataset_id tests (pure / no I/O)
    # ------------------------------------------------------------------

    def test_build_artifact_stamps_dataset_id(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            dataset_id="demo_dataset_v1",
            alignment_version="v1.0",
            case_results=[],
            pairwise_results=[],
        )
        self.assertEqual(artifact.dataset_id, "demo_dataset_v1")

    def test_build_artifact_none_dataset_id(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            dataset_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
        )
        self.assertIsNone(artifact.dataset_id)

    def test_artifact_dataset_id_serialised_in_to_dict(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            dataset_id="demo_dataset_v2",
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
        )
        d = artifact.to_dict()
        self.assertIn("dataset_id", d)
        self.assertEqual(d["dataset_id"], "demo_dataset_v2")

    def test_artifact_none_dataset_id_serialised_in_to_dict(self) -> None:
        artifact = build_benchmark_artifact(
            run_id=None,
            dataset_id=None,
            alignment_version=None,
            case_results=[],
            pairwise_results=[],
        )
        d = artifact.to_dict()
        self.assertIn("dataset_id", d)
        self.assertIsNone(d["dataset_id"])

    def test_to_json_round_trips_dataset_id(self) -> None:
        artifact = build_benchmark_artifact(
            run_id="r1",
            dataset_id="demo_dataset_v1",
            alignment_version="v1.0",
            case_results=[],
            pairwise_results=[],
        )
        parsed = json.loads(artifact.to_json())
        self.assertIn("dataset_id", parsed)
        self.assertEqual(parsed["dataset_id"], "demo_dataset_v1")

    # ------------------------------------------------------------------
    # Cypher query filter tests
    # ------------------------------------------------------------------

    def test_canonical_single_query_has_dataset_id_filter(self) -> None:
        self.assertIn("$dataset_id", _Q_CANONICAL_SINGLE)
        self.assertIn("canonical.dataset_id", _Q_CANONICAL_SINGLE)

    def test_lower_layer_chain_query_has_dataset_id_filter(self) -> None:
        self.assertIn("$dataset_id", _Q_LOWER_LAYER_CHAIN)
        self.assertIn("canonical.dataset_id", _Q_LOWER_LAYER_CHAIN)

    def test_catalog_existence_check_query_has_dataset_id_filter(self) -> None:
        self.assertIn("$dataset_id", _Q_CATALOG_EXISTENCE_CHECK)
        self.assertIn("ce.dataset_id", _Q_CATALOG_EXISTENCE_CHECK)

    def test_pairwise_canonical_query_has_dataset_id_filter(self) -> None:
        self.assertIn("$dataset_id", _Q_PAIRWISE_CANONICAL)
        self.assertIn("canonSub.dataset_id", _Q_PAIRWISE_CANONICAL)
        self.assertIn("canonObj.dataset_id", _Q_PAIRWISE_CANONICAL)

    # ------------------------------------------------------------------
    # Dry-run artifact includes dataset_id
    # ------------------------------------------------------------------

    def test_dry_run_artifact_includes_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(
                config,
                run_id="run-ds",
                dataset_id="demo_dataset_v1",
            )
            path = (
                Path(tmp)
                / "runs"
                / "run-ds"
                / "retrieval_benchmark"
                / "retrieval_benchmark.json"
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("dataset_id", data)
            self.assertEqual(data["dataset_id"], "demo_dataset_v1")

    def test_dry_run_artifact_dataset_id_none_when_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(config, run_id="run-nods")
            path = (
                Path(tmp)
                / "runs"
                / "run-nods"
                / "retrieval_benchmark"
                / "retrieval_benchmark.json"
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("dataset_id", data)
            self.assertIsNone(data["dataset_id"])

    def test_dry_run_result_dict_includes_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(Path(tmp), dry_run=True)
            result = run_retrieval_benchmark(
                config, run_id="run-rd", dataset_id="demo_dataset_v2"
            )
            self.assertIn("dataset_id", result)
            self.assertEqual(result["dataset_id"], "demo_dataset_v2")

    # ------------------------------------------------------------------
    # Live mode: dataset_id in query params and result dict
    # ------------------------------------------------------------------

    def _run_live_with_dataset_id(
        self,
        tmp_path: Path,
        dataset_id: str | None,
        cases: list[BenchmarkCaseDefinition],
        rows: list[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        config = _make_config(tmp_path, dry_run=False)
        driver = MagicMock()
        driver.__enter__ = MagicMock(return_value=driver)
        driver.__exit__ = MagicMock(return_value=False)
        driver.execute_query.side_effect = [(r, None, None) for r in rows]
        with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
            mock_neo4j.GraphDatabase.driver.return_value = driver
            mock_neo4j.RoutingControl.READ = "READ"
            result = run_retrieval_benchmark(
                config,
                run_id="run-live",
                dataset_id=dataset_id,
                benchmark_cases=cases,
            )
        return result

    def test_live_result_dict_includes_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            result = self._run_live_with_dataset_id(Path(tmp), "demo_dataset_v1", cases, rows)
            self.assertIn("dataset_id", result)
            self.assertEqual(result["dataset_id"], "demo_dataset_v1")

    def test_live_artifact_json_includes_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            result = self._run_live_with_dataset_id(Path(tmp), "demo_dataset_v1", cases, rows)
            parsed = json.loads(Path(result["artifact_path"]).read_text())
            self.assertIn("dataset_id", parsed)
            self.assertEqual(parsed["dataset_id"], "demo_dataset_v1")

    def test_live_query_receives_dataset_id_param(self) -> None:
        """Verify that $dataset_id is passed in the parameters to each query."""
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            config = _make_config(Path(tmp), dry_run=False)
            driver = MagicMock()
            driver.__enter__ = MagicMock(return_value=driver)
            driver.__exit__ = MagicMock(return_value=False)
            driver.execute_query.side_effect = [(r, None, None) for r in rows]
            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = driver
                mock_neo4j.RoutingControl.READ = "READ"
                run_retrieval_benchmark(
                    config,
                    run_id="run-param",
                    dataset_id="demo_dataset_v1",
                    benchmark_cases=cases,
                )
            # Every query call should include dataset_id in parameters_.
            for call in driver.execute_query.call_args_list:
                params = call.kwargs.get("parameters_", call.args[1] if len(call.args) > 1 else {})
                self.assertIn("dataset_id", params, f"dataset_id missing from query params: {call}")
                self.assertEqual(params["dataset_id"], "demo_dataset_v1")

    def test_live_query_receives_none_dataset_id_when_not_scoped(self) -> None:
        """When dataset_id is None, $dataset_id=None is passed so the IS NULL branch fires."""
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def()]
            rows = _empty_case_rows()
            config = _make_config(Path(tmp), dry_run=False)
            driver = MagicMock()
            driver.__enter__ = MagicMock(return_value=driver)
            driver.__exit__ = MagicMock(return_value=False)
            driver.execute_query.side_effect = [(r, None, None) for r in rows]
            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = driver
                mock_neo4j.RoutingControl.READ = "READ"
                run_retrieval_benchmark(
                    config,
                    run_id="run-noparam",
                    dataset_id=None,
                    benchmark_cases=cases,
                )
            for call in driver.execute_query.call_args_list:
                params = call.kwargs.get("parameters_", call.args[1] if len(call.args) > 1 else {})
                self.assertIn("dataset_id", params)
                self.assertIsNone(params["dataset_id"])

    # ------------------------------------------------------------------
    # Multi-dataset isolation: v1 and v2 scoped runs
    # ------------------------------------------------------------------

    def test_multidataset_v1_and_v2_produce_distinct_dataset_ids_in_artifacts(self) -> None:
        """Simulate running the benchmark twice — once scoped to v1, once to v2.

        Verifies that each artifact records its own dataset_id and that the two
        artifacts are independently auditable.  In a real multi-dataset graph the
        Cypher $dataset_id filter would prevent v2 CanonicalEntity nodes from
        appearing in the v1 benchmark run (and vice versa).
        """
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("ent")]
            rows = _empty_case_rows()

            # v1 benchmark
            config = _make_config(Path(tmp), dry_run=True)
            run_retrieval_benchmark(
                config,
                run_id="run-v1",
                dataset_id="demo_dataset_v1",
                benchmark_cases=cases,
            )
            # v2 benchmark
            run_retrieval_benchmark(
                config,
                run_id="run-v2",
                dataset_id="demo_dataset_v2",
                benchmark_cases=cases,
            )

            v1_data = json.loads(
                (Path(tmp) / "runs" / "run-v1" / "retrieval_benchmark" / "retrieval_benchmark.json")
                .read_text(encoding="utf-8")
            )
            v2_data = json.loads(
                (Path(tmp) / "runs" / "run-v2" / "retrieval_benchmark" / "retrieval_benchmark.json")
                .read_text(encoding="utf-8")
            )

            self.assertEqual(v1_data["dataset_id"], "demo_dataset_v1")
            self.assertEqual(v2_data["dataset_id"], "demo_dataset_v2")
            self.assertNotEqual(v1_data["dataset_id"], v2_data["dataset_id"])

    def test_multidataset_shared_entity_not_double_counted_when_dataset_scoped(self) -> None:
        """In a multi-dataset graph a shared entity (e.g. MercadoLibre) that has
        CanonicalEntity nodes in both v1 and v2 should NOT double-count when the
        benchmark is scoped to a single dataset_id.

        This test simulates the scenario by:
        1. Running a v1-scoped benchmark — the mock driver returns only v1 rows (3
           claims), demonstrating correct isolation.
        2. Running an unscoped benchmark — the mock driver returns combined v1+v2 rows
           (3+2=5 claims), demonstrating the double-counting risk that the dataset_id
           filter is designed to prevent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("shared_entity")]

            # Rows that would be returned by a v1-scoped query (3 claims).
            v1_canonical_rows = _make_canonical_rows(n_claims=3, n_clusters=1)
            # Rows that would be returned for v2 (2 more claims for the same entity name).
            # Use distinct claim IDs to simulate a different dataset's nodes.
            # In the real graph, the $dataset_id filter prevents these from appearing in a v1 run.
            v2_canonical_rows = [
                {
                    **row,
                    "claim_id": f"v2-claim-{i:03d}",
                    "cluster_id": f"v2-cluster-id-0",
                }
                for i, row in enumerate(_make_canonical_rows(n_claims=2, n_clusters=1))
            ]

            # --- Scoped run: only v1 rows returned by the filter ---
            v1_rows = [v1_canonical_rows, [], [], [], []]  # canonical, cluster, lower, frag, catalog

            config = _make_config(Path(tmp), dry_run=False)
            driver_v1 = MagicMock()
            driver_v1.__enter__ = MagicMock(return_value=driver_v1)
            driver_v1.__exit__ = MagicMock(return_value=False)
            driver_v1.execute_query.side_effect = [(r, None, None) for r in v1_rows]

            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = driver_v1
                mock_neo4j.RoutingControl.READ = "READ"
                result_v1 = run_retrieval_benchmark(
                    config,
                    run_id="run-v1-shared",
                    dataset_id="demo_dataset_v1",
                    benchmark_cases=cases,
                )

            cr_v1 = result_v1["artifact"]["case_results"][0]
            # Only 3 v1 claims — no double-counting of v2 claims.
            self.assertEqual(cr_v1["canonical_claim_count"], 3)
            self.assertEqual(result_v1["dataset_id"], "demo_dataset_v1")

            # --- Unscoped run: combined v1+v2 rows — demonstrates double-counting risk ---
            # Simulate what a db query without a dataset_id filter would return: both
            # v1 and v2 CanonicalEntity nodes for the same entity name.
            combined_canonical_rows = v1_canonical_rows + v2_canonical_rows
            unscoped_rows = [combined_canonical_rows, [], [], [], []]

            driver_all = MagicMock()
            driver_all.__enter__ = MagicMock(return_value=driver_all)
            driver_all.__exit__ = MagicMock(return_value=False)
            driver_all.execute_query.side_effect = [(r, None, None) for r in unscoped_rows]

            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = driver_all
                mock_neo4j.RoutingControl.READ = "READ"
                result_all = run_retrieval_benchmark(
                    config,
                    run_id="run-all-shared",
                    dataset_id=None,  # unscoped — aggregates across all datasets
                    benchmark_cases=cases,
                )

            cr_all = result_all["artifact"]["case_results"][0]
            # Unscoped run sees 5 claims (3 v1 + 2 v2) — the double-counting scenario.
            self.assertEqual(cr_all["canonical_claim_count"], 5)
            self.assertIsNone(result_all["dataset_id"])

            # Confirm the scoped count is less than the unscoped count.
            self.assertLess(cr_v1["canonical_claim_count"], cr_all["canonical_claim_count"])
