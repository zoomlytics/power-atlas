"""Tests for the entity resolution stage."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
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
    _build_lookup_tables,
    _cluster_mentions_unstructured_only,
    _fuzzy_ratio,
    _is_abbreviation,
    _make_cluster_id,
    _normalize,
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
        _Record(mention_id=m["mention_id"], name=m["name"], entity_type=m.get("entity_type"))
        for m in mentions
    ]
    canonical_records = [
        _Record(entity_id=c["entity_id"], run_id=c.get("run_id", ""), name=c["name"], aliases=c.get("aliases"))
        for c in canonical_nodes
    ]

    def execute_query(query, parameters_=None, database_=None, routing_=None):
        if "EntityMention" in query and "RETURN" in query:
            return (mention_records, None, None)
        if "CanonicalEntity" in query and "RETURN" in query:
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
        """Unresolved rows (label_cluster) must include entity_type for cluster scoping."""
        mention = {"mention_id": "m7", "name": "Nobody Known", "entity_type": "ORG"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertIn("entity_type", result)
        self.assertEqual(result["entity_type"], "ORG")

    def test_unresolved_qid_row_carries_entity_type(self):
        """Unresolved QID-pattern rows (no canonical match) must include entity_type."""
        mention = {"mention_id": "m8", "name": "Q99999", "entity_type": "concept"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertIn("entity_type", result)
        self.assertEqual(result["entity_type"], "concept")


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
            self.assertEqual(unresolved[0]["entity_type"], "ORG")

    def test_cross_run_same_text_produces_distinct_cluster_ids(self):
        """Same normalized text in two different runs must yield different cluster_ids."""
        cid_run1 = _make_cluster_id("run-A", None, "ibm")
        cid_run2 = _make_cluster_id("run-B", None, "ibm")
        self.assertNotEqual(cid_run1, cid_run2)

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


class TestIsAbbreviation(unittest.TestCase):
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

class TestFuzzyRatio(unittest.TestCase):
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
        """Every output row must carry the entity_type from the input mention."""
        mentions = [
            {"mention_id": "m1", "name": "Acme", "entity_type": "ORG"},
            {"mention_id": "m2", "name": "Acme", "entity_type": "PRODUCT"},
            {"mention_id": "m3", "name": "Widget"},  # no entity_type key
        ]
        result = _cluster_mentions_unstructured_only(mentions)
        by_mid = {r["mention_id"]: r for r in result}
        self.assertIn("entity_type", by_mid["m1"])
        self.assertEqual(by_mid["m1"]["entity_type"], "ORG")
        self.assertEqual(by_mid["m2"]["entity_type"], "PRODUCT")
        self.assertIsNone(by_mid["m3"]["entity_type"])

class TestRunEntityResolutionUnstructuredOnly(unittest.TestCase):
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
        """fuzzy cluster assignments must write status='provisional'."""
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

    def test_abbreviation_method_writes_provisional_status(self):
        """abbreviation cluster assignments must write status='provisional'."""
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
                    r["status"], "provisional",
                    f"abbreviation row must write status='provisional', got {r['status']!r}",
                )

class TestAlignClustersToCanonical(unittest.TestCase):
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
            # ALIGNED_WITH must NOT appear in Cypher calls when no canonicals exist
            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(any("ALIGNED_WITH" in c for c in all_calls))

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


if __name__ == "__main__":
    unittest.main()
