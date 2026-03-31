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

_ALLOWED_CASE_TYPES = {
    "single_entity",
    "pairwise_entity",
    "fragmented_entity",
    "composite_claim",
    "canonical_vs_cluster",
}


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
) -> BenchmarkCaseResult:
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
        )
        self.assertEqual(result.lower_layer_rows, ll_rows)

    def test_to_dict_json_serialisable(self) -> None:
        result = build_benchmark_case_result(
            case_def=_make_case_def(),
            canonical_rows=_make_canonical_rows(2),
            cluster_rows=_make_cluster_rows(2),
            lower_layer_rows=_make_lower_layer_rows(2),
            fragmentation_check_rows=_make_frag_rows(1),
        )
        d = result.to_dict()
        serialised = json.dumps(d)
        self.assertIn("canonical_claim_count", serialised)


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
    """Four empty row lists for one non-pairwise benchmark case."""
    return [[], [], [], []]


def _minimal_live_rows(
    cases: list[BenchmarkCaseDefinition],
) -> list[list[dict[str, Any]]]:
    """Return a list of empty row lists for each query that will be executed.

    For each non-pairwise case: 4 queries (canonical, cluster, lower_layer, frag).
    For each pairwise case: 1 query (pairwise).
    """
    rows: list[list[dict[str, Any]]] = []
    for c in cases:
        if c.case_type == "pairwise_entity":
            rows.append([])  # pairwise query
        else:
            rows.extend([[], [], [], []])  # 4 queries per non-pairwise case
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

    def test_live_four_queries_per_non_pairwise_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1"), _make_case_def("c2")]
            rows = _empty_case_rows() + _empty_case_rows()
            mock_driver = _make_mock_driver(rows)
            config = _make_config(Path(tmp), dry_run=False)
            with patch("demo.stages.retrieval_benchmark.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                run_retrieval_benchmark(config, run_id="run-q", benchmark_cases=cases)
            # 2 non-pairwise cases × 4 queries each = 8
            self.assertEqual(mock_driver.execute_query.call_count, 8)

    def test_live_fragmentation_detected_when_frag_rows_exceed_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("frag_test", "fragmented_entity")]
            canonical_rows = _make_canonical_rows(n_claims=3, n_clusters=1)
            cluster_rows = _make_cluster_rows(n_claims=3, n_clusters=3)
            lower_rows = _make_lower_layer_rows(3)
            frag_rows = _make_frag_rows(n_clusters=3)
            rows = [canonical_rows, cluster_rows, lower_rows, frag_rows]
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
            rows = [canonical_rows, cluster_rows, lower_rows, frag_rows]
            result = self._run_with_mock(Path(tmp), cases, rows)
            cr = result["artifact"]["case_results"][0]
            self.assertFalse(cr["fragmentation_detected"])

    def test_live_summary_reflects_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = [_make_case_def("c1"), _make_case_def("c2")]
            # c1: 5 canonical claims; c2: 0
            rows = [
                _make_canonical_rows(5),  # c1 canonical
                _make_cluster_rows(5),    # c1 cluster
                _make_lower_layer_rows(5),
                _make_frag_rows(1),
                [],  # c2 canonical (empty)
                [],  # c2 cluster (empty)
                [],  # c2 lower_layer
                [],  # c2 frag
            ]
            result = self._run_with_mock(Path(tmp), cases, rows)
            s = result["artifact"]["benchmark_summary"]
            self.assertEqual(s["total_cases"], 2)
            self.assertEqual(s["total_canonical_claims"], 5)
            self.assertEqual(s["entities_with_claims_canonical"], 1)


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
