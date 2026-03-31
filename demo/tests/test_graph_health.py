"""Tests for the graph-health diagnostics stage."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

from demo.stages.graph_health import (
    GraphHealthArtifact,
    _compute_alignment_summary,
    _compute_mention_summary,
    _compute_participation_summary,
    _records_to_dicts,
    build_graph_health_artifact,
    run_graph_health_diagnostics,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _role_dist(rows: list[tuple[str, int]]) -> list[dict[str, Any]]:
    return [{"role": r, "total": t} for r, t in rows]


def _edge_coverage(rows: list[tuple[int, int]]) -> list[dict[str, Any]]:
    return [{"participant_edges": e, "claim_count": c} for e, c in rows]


def _clustering(clustered: int, unclustered: int) -> list[dict[str, Any]]:
    result = []
    if clustered:
        result.append({"is_clustered": True, "mention_count": clustered})
    if unclustered:
        result.append({"is_clustered": False, "mention_count": unclustered})
    return result


def _alignment(aligned: int, unaligned: int) -> list[dict[str, Any]]:
    result = []
    if aligned:
        result.append({"is_aligned": True, "cluster_count": aligned})
    if unaligned:
        result.append({"is_aligned": False, "cluster_count": unaligned})
    return result


def _minimal_artifact(**overrides: Any) -> GraphHealthArtifact:
    """Return a minimal valid artifact with sensible defaults."""
    defaults: dict[str, Any] = dict(
        run_id="run-test",
        alignment_version="v1.0",
        participation_role_distribution=_role_dist([("subject", 10), ("object", 8)]),
        claim_edge_coverage_distribution=_edge_coverage([(0, 2), (1, 6), (2, 4)]),
        match_method_distribution=[{"match_method": "raw_exact", "total": 14}],
        mention_clustering=_clustering(20, 3),
        cluster_size_distribution=[{"member_count": 1, "cluster_count": 5}, {"member_count": 2, "cluster_count": 3}],
        cluster_type_fragmentation=[{"distinct_types_in_cluster": 1, "cluster_count": 7}, {"distinct_types_in_cluster": 2, "cluster_count": 1}],
        alignment_coverage=_alignment(6, 2),
        per_canonical_alignment=[
            {
                "canonical_entity": "Acme Corp",
                "entity_id": "Q1",
                "entity_type": "Organization",
                "aligned_cluster_count": 2,
                "bridged_mention_count": 5,
                "sample_methods": ["label_exact"],
            }
        ],
        canonical_chain_health=[
            {
                "canonical_entity": "Acme Corp",
                "entity_type": "Organization",
                "mention_count": 5,
                "claim_count": 3,
                "status": "active",
            }
        ],
        generated_at="2024-01-01T00:00:00Z",
    )
    defaults.update(overrides)
    return build_graph_health_artifact(**defaults)


# ---------------------------------------------------------------------------
# _records_to_dicts
# ---------------------------------------------------------------------------


class TestRecordsToDicts(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(_records_to_dicts([]), [])

    def test_converts_plain_dicts_unchanged(self) -> None:
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        self.assertEqual(_records_to_dicts(rows), rows)

    def test_converts_mapping_like_objects(self) -> None:
        """Neo4j Record objects expose a dict-like interface; dict() should work."""

        class FakeRecord(dict):
            pass

        rows = [FakeRecord({"role": "subject", "total": 5})]
        result = _records_to_dicts(rows)
        self.assertEqual(result, [{"role": "subject", "total": 5}])


# ---------------------------------------------------------------------------
# _compute_participation_summary
# ---------------------------------------------------------------------------


class TestComputeParticipationSummary(unittest.TestCase):
    def test_basic(self) -> None:
        role_dist = _role_dist([("subject", 10), ("object", 8)])
        edge_cov = _edge_coverage([(0, 2), (1, 6), (2, 4)])
        result = _compute_participation_summary(role_dist, edge_cov)
        self.assertEqual(result["total_edges"], 18)
        self.assertEqual(result["edges_by_role"], {"subject": 10, "object": 8})
        self.assertEqual(result["total_claims"], 12)
        self.assertEqual(result["claims_with_zero_edges"], 2)
        # coverage = 10/12 = 83.33%
        self.assertAlmostEqual(result["claim_coverage_pct"], 83.33, places=1)

    def test_all_claims_covered(self) -> None:
        role_dist = _role_dist([("subject", 5)])
        edge_cov = _edge_coverage([(1, 5)])
        result = _compute_participation_summary(role_dist, edge_cov)
        self.assertEqual(result["claims_with_zero_edges"], 0)
        self.assertEqual(result["claim_coverage_pct"], 100.0)

    def test_no_claims(self) -> None:
        result = _compute_participation_summary([], [])
        self.assertEqual(result["total_edges"], 0)
        self.assertIsNone(result["claim_coverage_pct"])

    def test_all_claims_zero_edges(self) -> None:
        role_dist = _role_dist([])
        edge_cov = _edge_coverage([(0, 10)])
        result = _compute_participation_summary(role_dist, edge_cov)
        self.assertEqual(result["claims_with_zero_edges"], 10)
        self.assertEqual(result["claim_coverage_pct"], 0.0)


# ---------------------------------------------------------------------------
# _compute_mention_summary
# ---------------------------------------------------------------------------


class TestComputeMentionSummary(unittest.TestCase):
    def test_basic(self) -> None:
        rows = _clustering(20, 5)
        result = _compute_mention_summary(rows)
        self.assertEqual(result["total_mentions"], 25)
        self.assertEqual(result["clustered_mentions"], 20)
        self.assertEqual(result["unclustered_mentions"], 5)
        self.assertAlmostEqual(result["unresolved_rate_pct"], 20.0)

    def test_all_clustered(self) -> None:
        rows = _clustering(10, 0)
        result = _compute_mention_summary(rows)
        self.assertEqual(result["unclustered_mentions"], 0)
        self.assertEqual(result["unresolved_rate_pct"], 0.0)

    def test_no_mentions(self) -> None:
        result = _compute_mention_summary([])
        self.assertEqual(result["total_mentions"], 0)
        self.assertIsNone(result["unresolved_rate_pct"])

    def test_only_unclustered(self) -> None:
        rows = _clustering(0, 8)
        result = _compute_mention_summary(rows)
        self.assertEqual(result["clustered_mentions"], 0)
        self.assertEqual(result["unresolved_rate_pct"], 100.0)


# ---------------------------------------------------------------------------
# _compute_alignment_summary
# ---------------------------------------------------------------------------


class TestComputeAlignmentSummary(unittest.TestCase):
    def test_basic(self) -> None:
        rows = _alignment(6, 2)
        result = _compute_alignment_summary(rows)
        self.assertEqual(result["total_clusters"], 8)
        self.assertEqual(result["aligned_clusters"], 6)
        self.assertEqual(result["unaligned_clusters"], 2)
        self.assertEqual(result["alignment_coverage_pct"], 75.0)

    def test_fully_aligned(self) -> None:
        rows = _alignment(10, 0)
        result = _compute_alignment_summary(rows)
        self.assertEqual(result["alignment_coverage_pct"], 100.0)

    def test_no_clusters(self) -> None:
        result = _compute_alignment_summary([])
        self.assertIsNone(result["alignment_coverage_pct"])

    def test_no_aligned(self) -> None:
        rows = _alignment(0, 5)
        result = _compute_alignment_summary(rows)
        self.assertEqual(result["aligned_clusters"], 0)
        self.assertEqual(result["alignment_coverage_pct"], 0.0)


# ---------------------------------------------------------------------------
# build_graph_health_artifact
# ---------------------------------------------------------------------------


class TestBuildGraphHealthArtifact(unittest.TestCase):
    def test_returns_artifact_instance(self) -> None:
        artifact = _minimal_artifact()
        self.assertIsInstance(artifact, GraphHealthArtifact)

    def test_run_id_and_alignment_version_preserved(self) -> None:
        artifact = _minimal_artifact(run_id="my-run", alignment_version="v2.0")
        self.assertEqual(artifact.run_id, "my-run")
        self.assertEqual(artifact.alignment_version, "v2.0")

    def test_none_run_id(self) -> None:
        artifact = _minimal_artifact(run_id=None, alignment_version=None)
        self.assertIsNone(artifact.run_id)
        self.assertIsNone(artifact.alignment_version)

    def test_generated_at_used_when_provided(self) -> None:
        artifact = _minimal_artifact(generated_at="2030-06-15T12:00:00Z")
        self.assertEqual(artifact.generated_at, "2030-06-15T12:00:00Z")

    def test_generated_at_defaults_to_now(self) -> None:
        # When not provided, generated_at should be a non-empty ISO string.
        artifact = build_graph_health_artifact(
            run_id=None,
            alignment_version=None,
            participation_role_distribution=[],
            claim_edge_coverage_distribution=[],
            match_method_distribution=[],
            mention_clustering=[],
            cluster_size_distribution=[],
            cluster_type_fragmentation=[],
            alignment_coverage=[],
            per_canonical_alignment=[],
            canonical_chain_health=[],
        )
        self.assertTrue(artifact.generated_at)
        self.assertIn("T", artifact.generated_at)

    def test_summaries_are_derived(self) -> None:
        artifact = _minimal_artifact(
            participation_role_distribution=_role_dist([("subject", 4)]),
            claim_edge_coverage_distribution=_edge_coverage([(0, 1), (1, 3)]),
            mention_clustering=_clustering(10, 2),
            alignment_coverage=_alignment(5, 5),
        )
        self.assertEqual(artifact.participation_summary["total_edges"], 4)
        self.assertEqual(artifact.mention_summary["total_mentions"], 12)
        self.assertEqual(artifact.alignment_summary["total_clusters"], 10)

    def test_raw_rows_preserved(self) -> None:
        size_dist = [{"member_count": 1, "cluster_count": 3}]
        artifact = _minimal_artifact(cluster_size_distribution=size_dist)
        self.assertEqual(artifact.cluster_size_distribution, size_dist)

    def test_to_dict_is_json_serialisable(self) -> None:
        artifact = _minimal_artifact()
        d = artifact.to_dict()
        # Should not raise.
        serialised = json.dumps(d)
        self.assertIn("participation_summary", serialised)

    def test_to_json_round_trips(self) -> None:
        artifact = _minimal_artifact()
        json_str = artifact.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["run_id"], artifact.run_id)
        self.assertEqual(parsed["alignment_version"], artifact.alignment_version)
        self.assertEqual(
            parsed["participation_summary"]["total_edges"],
            artifact.participation_summary["total_edges"],
        )


# ---------------------------------------------------------------------------
# run_graph_health_diagnostics — dry_run mode
# ---------------------------------------------------------------------------


class TestRunGraphHealthDiagnosticsDryRun(unittest.TestCase):
    def _config(self, tmp_path: Path) -> MagicMock:
        cfg = MagicMock()
        cfg.dry_run = True
        cfg.output_dir = tmp_path
        cfg.neo4j_uri = "bolt://localhost:7687"
        cfg.neo4j_username = "neo4j"
        cfg.neo4j_password = "test"
        cfg.neo4j_database = "neo4j"
        return cfg

    def test_dry_run_returns_status_dry_run(self, tmp_path: Path = Path("/tmp/gh_test_dry")) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        config = self._config(tmp_path)
        result = run_graph_health_diagnostics(config, run_id="run-dry", alignment_version="v1.0")
        self.assertEqual(result["status"], "dry_run")
        self.assertIsNone(result["artifact"])

    def test_dry_run_writes_artifact_file(self, tmp_path: Path = Path("/tmp/gh_test_dry2")) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        config = self._config(tmp_path)
        run_graph_health_diagnostics(config, run_id="run-dry2", alignment_version=None)
        path = tmp_path / "runs" / "run-dry2" / "graph_health" / "graph_health_diagnostics.json"
        self.assertTrue(path.exists(), f"Expected artifact at {path}")

    def test_dry_run_no_run_id_uses_graph_health_dir(
        self, tmp_path: Path = Path("/tmp/gh_test_dry3")
    ) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        config = self._config(tmp_path)
        run_graph_health_diagnostics(config, run_id=None)
        path = tmp_path / "graph_health" / "graph_health_diagnostics.json"
        self.assertTrue(path.exists(), f"Expected artifact at {path}")


# ---------------------------------------------------------------------------
# run_graph_health_diagnostics — live mode (mocked driver)
# ---------------------------------------------------------------------------


def _make_mock_driver(rows_by_query_index: list[list[dict[str, Any]]]) -> MagicMock:
    """Return a mock neo4j.Driver whose execute_query returns successive row lists."""
    driver = MagicMock()
    driver.__enter__ = MagicMock(return_value=driver)
    driver.__exit__ = MagicMock(return_value=False)
    # Each call to execute_query returns the next row list in order.
    driver.execute_query.side_effect = [
        (rows, None, None) for rows in rows_by_query_index
    ]
    return driver


class TestRunGraphHealthDiagnosticsLive(unittest.TestCase):
    def _config(self, tmp_path: Path) -> MagicMock:
        cfg = MagicMock()
        cfg.dry_run = False
        cfg.output_dir = tmp_path
        cfg.neo4j_uri = "bolt://localhost:7687"
        cfg.neo4j_username = "neo4j"
        cfg.neo4j_password = "secret"
        cfg.neo4j_database = "neo4j"
        return cfg

    def _make_rows(self) -> list[list[dict[str, Any]]]:
        """Return the 9 successive query result lists expected by the stage."""
        return [
            _role_dist([("subject", 10), ("object", 8)]),   # role distribution
            _edge_coverage([(0, 1), (1, 4)]),               # claim edge coverage
            [{"match_method": "raw_exact", "total": 14}],   # match method dist
            _clustering(20, 3),                             # mention clustering
            [{"member_count": 1, "cluster_count": 5}],      # cluster size dist
            [{"distinct_types_in_cluster": 1, "cluster_count": 5}],  # type frag
            _alignment(6, 2),                               # alignment coverage
            [{"canonical_entity": "Acme", "entity_id": "Q1", "entity_type": "Org",
              "aligned_cluster_count": 2, "bridged_mention_count": 5,
              "sample_methods": ["label_exact"]}],          # per-canonical
            [{"canonical_entity": "Acme", "entity_type": "Org",
              "mention_count": 5, "claim_count": 3, "status": "active"}],  # chain health
        ]

    def test_live_run_writes_artifact(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = self._config(tmp_path)
            rows = self._make_rows()
            mock_driver = _make_mock_driver(rows)

            with patch("demo.stages.graph_health.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                result = run_graph_health_diagnostics(
                    config,
                    run_id="run-live-001",
                    alignment_version="v1.0",
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["run_id"], "run-live-001")
            artifact_path = Path(result["artifact_path"])
            self.assertTrue(artifact_path.exists())
            artifact_json = json.loads(artifact_path.read_text())
            self.assertEqual(artifact_json["run_id"], "run-live-001")

    def test_live_run_summaries_correct(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = self._config(tmp_path)
            rows = self._make_rows()
            mock_driver = _make_mock_driver(rows)

            with patch("demo.stages.graph_health.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                result = run_graph_health_diagnostics(
                    config, run_id="run-live-002", alignment_version=None
                )

            artifact = result["artifact"]
            ps = artifact["participation_summary"]
            self.assertEqual(ps["total_edges"], 18)
            self.assertEqual(ps["claims_with_zero_edges"], 1)

            ms = artifact["mention_summary"]
            self.assertEqual(ms["total_mentions"], 23)
            self.assertEqual(ms["unclustered_mentions"], 3)

            als = artifact["alignment_summary"]
            self.assertEqual(als["total_clusters"], 8)
            self.assertEqual(als["aligned_clusters"], 6)

    def test_execute_query_called_nine_times(self) -> None:
        """Exactly 9 Cypher queries should be run per invocation."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = self._config(tmp_path)
            rows = self._make_rows()
            mock_driver = _make_mock_driver(rows)

            with patch("demo.stages.graph_health.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                run_graph_health_diagnostics(
                    config, run_id="run-live-003", alignment_version="v1.0"
                )

            self.assertEqual(mock_driver.execute_query.call_count, 9)

    def test_artifact_path_uses_run_id(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = self._config(tmp_path)
            rows = self._make_rows()
            mock_driver = _make_mock_driver(rows)

            with patch("demo.stages.graph_health.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                result = run_graph_health_diagnostics(
                    config, run_id="my-special-run", alignment_version=None
                )

            self.assertIn("my-special-run", result["artifact_path"])
            self.assertIn("graph_health", result["artifact_path"])

    def test_no_run_id_uses_global_path(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = self._config(tmp_path)
            rows = self._make_rows()
            mock_driver = _make_mock_driver(rows)

            with patch("demo.stages.graph_health.neo4j") as mock_neo4j:
                mock_neo4j.GraphDatabase.driver.return_value = mock_driver
                mock_neo4j.RoutingControl.READ = "READ"
                result = run_graph_health_diagnostics(
                    config, run_id=None, alignment_version=None
                )

            # Should not contain "runs/" in path when run_id is None
            self.assertNotIn("/runs/", result["artifact_path"])


if __name__ == "__main__":
    unittest.main()
