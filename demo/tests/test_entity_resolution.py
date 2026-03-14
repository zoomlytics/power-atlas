"""Tests for the entity resolution stage."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from demo.contracts.runtime import Config
from demo.stages.entity_resolution import (
    _CLUSTER_VERSION,
    _RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    _build_lookup_tables,
    _cluster_mentions_unstructured_only,
    _fuzzy_ratio,
    _is_abbreviation,
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
                result = run_entity_resolution(config, run_id="run-live-001", source_uri="file:///doc.pdf")

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
                result = run_entity_resolution(config, run_id="run-live-002", source_uri=None)

            self.assertEqual(result["resolved"], 1)
            self.assertEqual(result["resolution_breakdown"].get("label_exact"), 1)

    def test_live_resolves_alias_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _live_config(Path(tmpdir))
            mentions = [{"mention_id": "m3", "name": "D. Adams", "entity_type": "person"}]
            canonicals = [{"entity_id": "Q42", "run_id": "run-s1", "name": "Douglas Adams", "aliases": "D. Adams|Adams"}]
            driver = self._make_driver(mentions, canonicals)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                result = run_entity_resolution(config, run_id="run-live-003", source_uri=None)

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
                run_entity_resolution(config, run_id="run-live-006", source_uri="file:///a.pdf")

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
                result = run_entity_resolution(config, run_id="run-cluster-002", source_uri=None)

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

            unresolved_path = (
                Path(tmpdir) / "runs" / "run-cluster-004" / "entity_resolution" / "unresolved_mentions.json"
            )
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
            self.assertEqual(len(unresolved), 1)
            self.assertIn("cluster_id", unresolved[0])
            self.assertEqual(unresolved[0]["cluster_id"], "cluster::widget inc")

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
        """unstructured_only should NOT query CanonicalEntity nodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._live_config(Path(tmpdir))
            mentions = [{"mention_id": "m1", "name": "Alice", "entity_type": "person"}]
            driver = self._make_driver(mentions)

            with patch("neo4j.GraphDatabase.driver", return_value=driver):
                run_entity_resolution(config, run_id="run-uo-001", source_uri=None)

            all_calls = [str(c) for c in driver.execute_query.call_args_list]
            self.assertFalse(
                any("CanonicalEntity" in call and "RETURN" in call for call in all_calls),
                "unstructured_only mode must not query CanonicalEntity nodes",
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


if __name__ == "__main__":
    unittest.main()
