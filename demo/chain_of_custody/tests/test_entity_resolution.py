"""Tests for the entity resolution stage."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from demo.chain_of_custody.contracts.runtime import DemoConfig
from demo.chain_of_custody.stages.entity_resolution import (
    _build_lookup_tables,
    _normalize,
    _resolve_mention,
    _split_aliases,
    run_entity_resolution,
)


def _dry_run_config(tmp_path: Path) -> DemoConfig:
    return DemoConfig(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


def _live_config(tmp_path: Path) -> DemoConfig:
    return DemoConfig(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


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

    def test_qid_pattern_match_no_canonical_falls_through_to_unresolved(self):
        mention = {"mention_id": "m2", "name": "Q999"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["resolution_method"], "unresolved")

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

    def test_unresolved(self):
        mention = {"mention_id": "m5", "name": "Unknown Entity XYZ"}
        result = _resolve_mention(mention, self.by_qid, self.by_label, self.by_alias)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["resolution_method"], "unresolved")
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
            self.assertEqual(result["resolution_breakdown"].get("unresolved"), 1)

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
            config = module.DemoConfig(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            env_backup = os.environ.get("CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID")
            try:
                os.environ["CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID"] = "test-unstructured-run-001"
                manifest_path = module.run_independent_demo(config, "resolve-entities")
            finally:
                if env_backup is None:
                    os.environ.pop("CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID", None)
                else:
                    os.environ["CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID"] = env_backup

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
            config = module.DemoConfig(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="bolt://example.invalid",
                neo4j_username="neo4j",
                neo4j_password="not-used",
                neo4j_database="neo4j",
                openai_model="test-model",
            )
            env_backup = os.environ.get("CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID")
            try:
                os.environ.pop("CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID", None)
                with self.assertRaises(ValueError) as ctx:
                    module.run_independent_demo(config, "resolve-entities")
                self.assertIn("CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID", str(ctx.exception))
            finally:
                if env_backup is not None:
                    os.environ["CHAIN_OF_CUSTODY_UNSTRUCTURED_RUN_ID"] = env_backup


class TestBatchManifestEntityResolution(unittest.TestCase):
    """Verify build_batch_manifest includes entity_resolution when provided."""

    def test_entity_resolution_stage_included_when_provided(self):
        from demo.chain_of_custody.contracts.manifest import build_batch_manifest
        from demo.chain_of_custody.contracts.runtime import DemoConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = DemoConfig(
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
                resolution_run_id="resolution-3",
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
        from demo.chain_of_custody.contracts.manifest import build_batch_manifest
        from demo.chain_of_custody.contracts.runtime import DemoConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = DemoConfig(
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
                resolution_run_id="resolution-3",
                structured_stage={"status": "dry_run"},
                pdf_stage={"status": "dry_run"},
                claim_stage={"status": "dry_run"},
                retrieval_stage={"status": "dry_run"},
            )
            self.assertNotIn("entity_resolution", manifest["stages"])


if __name__ == "__main__":
    unittest.main()
