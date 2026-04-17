import csv
import importlib.util
import io
import json
import os
import re
import shutil
import types
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import yaml

from power_atlas.contracts import PROMPT_IDS


DEMO_DIR = Path(__file__).resolve().parents[1]
RUN_DEMO_PATH = DEMO_DIR / "run_demo.py"
SMOKE_TEST_PATH = DEMO_DIR / "smoke_test.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # When multiple fixture datasets exist the auto-discovery raises
        # AmbiguousDatasetError.  Pin to v1 for all tests in this class so
        # that tests don't need individual dataset_name= arguments.
        self._prev_fixture_dataset = os.environ.get("FIXTURE_DATASET")
        os.environ["FIXTURE_DATASET"] = "demo_dataset_v1"

    def tearDown(self):
        if self._prev_fixture_dataset is None:
            os.environ.pop("FIXTURE_DATASET", None)
        else:
            os.environ["FIXTURE_DATASET"] = self._prev_fixture_dataset

    @contextmanager
    def _with_injected_modules(self, injected_modules: dict[str, types.ModuleType]):
        originals = {name: sys.modules.get(name) for name in injected_modules}
        try:
            sys.modules.update(injected_modules)
            yield
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def _build_pdf_ingest_test_modules(
        self,
        *,
        calls: dict[str, object],
        query_payloads: dict[str, dict[str, int]] | None = None,
        pipeline_result: object = None,
    ) -> dict[str, types.ModuleType]:
        query_payloads = query_payloads or {}
        if pipeline_result is None:
            pipeline_result = {"ok": True}

        class _FakeResult:
            def __init__(self, single_payload=None):
                self._single_payload = single_payload or {}

            def consume(self):
                return None

            def single(self):
                return self._single_payload

        class _FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                calls.setdefault("queries", []).append((query, kwargs))
                # Sort by marker length so specific markers (e.g., "missing_page_count")
                # take precedence over substrings like "page_count".
                for marker, payload in sorted(
                    query_payloads.items(), key=lambda item: len(item[0]), reverse=True
                ):
                    if marker in query:
                        calls.setdefault("matched_markers", []).append(marker)
                        return _FakeResult(payload)
                return _FakeResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                calls.setdefault("sessions", []).append(kwargs)
                return _FakeSession()

        class _FakePipeline:
            async def run(self, params):
                calls["run_params"] = params
                if callable(pipeline_result):
                    return pipeline_result(params)
                return pipeline_result

        class _FakePipelineRunner:
            @staticmethod
            def from_config_file(path):
                calls["config_path"] = str(path)
                return _FakePipeline()

        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *_args, **_kwargs: _FakeDriver())
        fake_runner = types.ModuleType("neo4j_graphrag.experimental.pipeline.config.runner")
        fake_runner.PipelineRunner = _FakePipelineRunner

        return {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }

    @contextmanager
    def _with_injected_pdf_ingest_modules(self, injected_modules: dict[str, types.ModuleType]):
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        bootstrap_driver_patch = None
        try:
            fake_neo4j = injected_modules.get("neo4j")
            if fake_neo4j is not None:
                bootstrap_driver_patch = mock.patch(
                    "power_atlas.bootstrap.clients.neo4j.GraphDatabase.driver",
                    new=fake_neo4j.GraphDatabase.driver,
                )
                bootstrap_driver_patch.start()
            sys.modules.update(injected_modules)
            os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
            yield
        finally:
            if bootstrap_driver_patch is not None:
                bootstrap_driver_patch.stop()
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            if had_openai_api_key:
                os.environ["OPENAI_API_KEY"] = original_openai_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_parse_args_supports_expected_subcommands(self):
        module = _load_module(RUN_DEMO_PATH, "run_parse_args_test")
        expected = {
            "lint-structured",
            "ingest-structured",
            "ingest-pdf",
            "extract-claims",
            "resolve-entities",
            "ask",
            "reset",
            "ingest",
        }
        for command in expected:
            args = module.parse_args([command])
            self.assertEqual(args.command, command)
        self.assertEqual(module.parse_args([]).command, "ingest")
        self.assertTrue(module.parse_args(["ingest", "--dry-run"]).dry_run)
        self.assertTrue(module.parse_args(["--dry-run", "ingest"]).dry_run)
        # --live after subcommand must set dry_run=False
        self.assertFalse(module.parse_args(["ingest", "--live"]).dry_run)
        # --live before subcommand must also set dry_run=False (regression for flag-order bug)
        self.assertFalse(module.parse_args(["--live", "ingest"]).dry_run)
        for subcmd in ("extract-claims", "ingest-pdf", "resolve-entities"):
            self.assertFalse(module.parse_args(["--live", subcmd]).dry_run)
        with self.assertRaises(SystemExit):
            module.parse_args(["--dry-run", "ingest", "--live"])
        with self.assertRaises(SystemExit):
            module.parse_args(["--dry-run", "ingest", "--l"])

    def test_parse_args_dataset_default_uses_fixture_dataset_env(self):
        module = _load_module(RUN_DEMO_PATH, "run_parse_args_fixture_dataset_test")
        previous_power_atlas_dataset = os.environ.pop("POWER_ATLAS_DATASET", None)
        previous_fixture_dataset = os.environ.get("FIXTURE_DATASET")
        os.environ["FIXTURE_DATASET"] = "demo_dataset_v1"
        try:
            args = module.parse_args(["ingest"])
        finally:
            if previous_power_atlas_dataset is not None:
                os.environ["POWER_ATLAS_DATASET"] = previous_power_atlas_dataset
            if previous_fixture_dataset is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = previous_fixture_dataset

        self.assertEqual(args.dataset, "demo_dataset_v1")

    def test_parse_args_dataset_default_prefers_power_atlas_dataset_env(self):
        module = _load_module(RUN_DEMO_PATH, "run_parse_args_power_atlas_dataset_test")
        previous_power_atlas_dataset = os.environ.get("POWER_ATLAS_DATASET")
        previous_fixture_dataset = os.environ.get("FIXTURE_DATASET")
        os.environ["POWER_ATLAS_DATASET"] = "demo_dataset_v2"
        os.environ["FIXTURE_DATASET"] = "demo_dataset_v1"
        try:
            args = module.parse_args(["ingest"])
        finally:
            if previous_power_atlas_dataset is None:
                os.environ.pop("POWER_ATLAS_DATASET", None)
            else:
                os.environ["POWER_ATLAS_DATASET"] = previous_power_atlas_dataset
            if previous_fixture_dataset is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = previous_fixture_dataset

        self.assertEqual(args.dataset, "demo_dataset_v2")

    def test_reset_command_skips_password_validation(self):
        module = _load_module(RUN_DEMO_PATH, "run_main_reset_test")
        args = type(
            "Args",
            (),
            {
                "command": "reset",
                "dry_run": False,
                "output_dir": DEMO_DIR / "artifacts",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "CHANGE_ME_BEFORE_USE",
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
                "question": None,
            },
        )()
        original_parse_args = module.parse_args
        try:
            module.parse_args = lambda: args
            with io.StringIO() as buffer, redirect_stdout(buffer):
                module.main()
                self.assertIn("reset_demo_db.py --confirm", buffer.getvalue())
        finally:
            module.parse_args = original_parse_args

    def test_run_demo_dry_run_writes_manifest_with_expected_stages(self):
        module = _load_module(RUN_DEMO_PATH, "run_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = module.run_demo(
                module.Config(
                    dry_run=True,
                    output_dir=Path(tmpdir),
                    neo4j_uri="neo4j://localhost:7687",
                    neo4j_username="neo4j",
                    neo4j_password="testtesttest",
                    neo4j_database="neo4j",
                    openai_model="gpt-4o-mini",
                )
            )

            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["config"]["dry_run"])
            self.assertEqual(manifest["run_scopes"]["batch_mode"], "sequential_independent_runs")
            self.assertIn("structured_ingest_run_id", manifest["run_scopes"])
            self.assertIn("unstructured_ingest_run_id", manifest["run_scopes"])
            self.assertNotIn("resolution_run_id", manifest["run_scopes"])
            # The new unstructured-first sequence emits two entity-resolution passes
            # (unstructured_only, then hybrid) and two Q&A passes (before and after
            # structured ingest) so consumers can see meaningful results at each phase.
            # The retrieval benchmark runs automatically at the end of every orchestrated
            # ingest to produce a regression artifact without a separate manual invocation.
            self.assertEqual(
                set(manifest["stages"].keys()),
                {
                    "pdf_ingest",
                    "claim_and_mention_extraction",
                    "claim_participation",
                    "entity_resolution_unstructured_only",
                    "retrieval_and_qa_unstructured_only",
                    "structured_ingest",
                    "entity_resolution_hybrid",
                    "retrieval_and_qa",
                    "retrieval_benchmark",
                },
            )
            self.assertEqual(
                manifest["stages"]["structured_ingest"]["run_id"],
                manifest["run_scopes"]["structured_ingest_run_id"],
            )
            self.assertEqual(
                manifest["stages"]["pdf_ingest"]["run_id"],
                manifest["run_scopes"]["unstructured_ingest_run_id"],
            )
            self.assertEqual(
                manifest["stages"]["claim_and_mention_extraction"]["run_id"],
                manifest["run_scopes"]["unstructured_ingest_run_id"],
            )
            self.assertEqual(
                manifest["stages"]["entity_resolution_unstructured_only"]["run_id"],
                manifest["run_scopes"]["unstructured_ingest_run_id"],
            )
            self.assertEqual(
                manifest["stages"]["entity_resolution_hybrid"]["run_id"],
                manifest["run_scopes"]["unstructured_ingest_run_id"],
            )
            self.assertEqual(
                manifest["stages"]["claim_and_mention_extraction"]["prompt_version"],
                PROMPT_IDS["claim_extraction"],
            )
            claims_fixture_path = DEMO_DIR / "fixtures" / "structured" / "claims.csv"
            with claims_fixture_path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                expected_claim_count = sum(1 for _ in reader)
            self.assertEqual(
                manifest["stages"]["structured_ingest"]["claims"],
                expected_claim_count,
            )
            self.assertNotEqual(
                manifest["run_scopes"]["structured_ingest_run_id"],
                manifest["run_scopes"]["unstructured_ingest_run_id"],
            )

    def test_orchestrated_unstructured_only_entity_resolution_passes_explicit_dataset_id(self):
        """_run_orchestrated must pass dataset_id explicitly to the unstructured-only
        run_entity_resolution call, not rely on the ambient set_dataset_id() context."""
        from unittest.mock import patch as mock_patch

        module = _load_module(RUN_DEMO_PATH, "run_demo_test_module")

        # Capture every call made to run_entity_resolution as the orchestrator runs.
        captured_calls: list = []
        real_fn = module._run_entity_resolution

        def _fake_run_entity_resolution(*args, **kwargs):
            captured_calls.append(kwargs)
            return real_fn(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock_patch.object(module, "run_entity_resolution", side_effect=_fake_run_entity_resolution):
                module.run_demo(
                    module.Config(
                        dry_run=True,
                        output_dir=Path(tmpdir),
                        neo4j_uri="neo4j://localhost:7687",
                        neo4j_username="neo4j",
                        neo4j_password="testtesttest",
                        neo4j_database="neo4j",
                        openai_model="gpt-4o-mini",
                        dataset_name="demo_dataset_v1",
                    )
                )

        # There must be exactly two entity-resolution calls in the orchestrated flow:
        # one unstructured_only and one hybrid.
        self.assertEqual(len(captured_calls), 2, "Expected exactly two run_entity_resolution calls")

        uo_call = next(
            (c for c in captured_calls if c.get("resolution_mode") == "unstructured_only"), None
        )
        self.assertIsNotNone(uo_call, "No unstructured_only entity-resolution call found")
        self.assertIn(
            "dataset_id",
            uo_call,
            "unstructured_only call must pass dataset_id explicitly",
        )
        self.assertIsNotNone(
            uo_call["dataset_id"],
            "unstructured_only call must not pass dataset_id=None",
        )

    def test_fixture_manifest_tracks_dataset_and_provenance(self):
        fixture_manifest = DEMO_DIR / "fixtures" / "manifest.json"
        data = json.loads(fixture_manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["dataset"], "demo_dataset_v1")
        required_files = set(data["dataset_contract"]["required_files"])
        provenance_paths = {item["path"] for item in data["provenance"]}
        self.assertTrue(required_files.issubset(provenance_paths))

    def test_fixtures_readme_exists_with_required_sections(self):
        fixtures_readme = DEMO_DIR / "fixtures" / "README.md"
        text = fixtures_readme.read_text(encoding="utf-8")
        self.assertIn("## Data provenance", text)
        self.assertIn("## License and attribution", text)
        self.assertIn("## CSV schemas", text)
        self.assertIn("## Claims curation contract", text)
        self.assertIn("## Canonical entity notes", text)
        self.assertIn("## Golden questions for the demo", text)

    def test_cross_dataset_validation_report_exists_with_required_sections(self):
        report_path = DEMO_DIR.parent / "docs" / "cross-dataset-validation-report-v1-v2.md"
        self.assertTrue(report_path.exists(), f"Cross-dataset validation report not found at {report_path}")
        text = report_path.read_text(encoding="utf-8")
        for section in (
            "demo_dataset_v1",
            "demo_dataset_v2",
            "## 3. Fixture summary comparison",
            "## 4. Stage-by-stage comparison",
            "## 5. Successful behaviors",
            "## 6. Degraded behaviors",
            "## 7. Outright failures",
            "## 8. Follow-up items",
        ):
            self.assertIn(section, text, f"Expected section/token missing from report: {section!r}")

    def test_claims_fixture_schema_and_source_linkage(self):
        fixtures_dir = DEMO_DIR / "fixtures" / "structured"
        claims_path = fixtures_dir / "claims.csv"
        facts_path = fixtures_dir / "facts.csv"
        relationships_path = fixtures_dir / "relationships.csv"

        with claims_path.open(encoding="utf-8", newline="") as claims_file:
            claims_reader = csv.DictReader(claims_file)
            self.assertEqual(
                claims_reader.fieldnames,
                [
                    "claim_id",
                    "claim_type",
                    "subject_id",
                    "subject_label",
                    "predicate_pid",
                    "predicate_label",
                    "object_id",
                    "object_label",
                    "value",
                    "value_type",
                    "claim_text",
                    "confidence",
                    "source",
                    "source_url",
                    "retrieved_at",
                    "source_row_id",
                ],
            )
            claims_rows = list(claims_reader)

        self.assertGreaterEqual(len(claims_rows), 20)
        self.assertLessEqual(len(claims_rows), 60)

        with facts_path.open(encoding="utf-8", newline="") as facts_file:
            fact_ids = {row["fact_id"] for row in csv.DictReader(facts_file)}
        with relationships_path.open(encoding="utf-8", newline="") as relationships_file:
            relationship_ids = {row["rel_id"] for row in csv.DictReader(relationships_file)}

        for claim in claims_rows:
            source_row_id = claim["source_row_id"]
            if claim["claim_type"] == "fact":
                self.assertIn(source_row_id, fact_ids)
            elif claim["claim_type"] == "relationship":
                self.assertIn(source_row_id, relationship_ids)
            else:
                self.fail(f"Unexpected claim_type: {claim['claim_type']}")

    def test_structured_ingest_dry_run_emits_clean_run_artifacts(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_clean_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            manifest_path = module.run_independent_demo(config, "ingest-structured")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stage = manifest["stages"]["structured_ingest"]
            self.assertTrue(Path(stage["structured_clean_dir"]).exists())
            self.assertTrue(Path(stage["lint_report_path"]).exists())
            lint_report = json.loads(Path(stage["lint_report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(lint_report["summary"]["status"], "ok")
            self.assertEqual(lint_report["summary"]["issue_count"], 0)
            self.assertEqual(
                lint_report["structured_clean_dir"],
                stage["structured_clean_dir"],
            )
            self.assertTrue(Path(stage["structured_ingest_dir"]).exists())
            self.assertTrue(Path(stage["ingest_summary_path"]).exists())
            self.assertTrue(Path(stage["validation_warnings_path"]).exists())

    def test_structured_ingest_non_dry_run_writes_claim_first_graph_and_artifacts(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_live_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=False,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            calls: dict[str, object] = {}

            class _FakeResult:
                def consume(self):
                    return None

            class _FakeSession:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def run(self, query, **kwargs):
                    calls.setdefault("queries", []).append((query, kwargs))
                    return _FakeResult()

            class _FakeDriver:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def session(self, **kwargs):
                    calls.setdefault("sessions", []).append(kwargs)
                    return _FakeSession()

            fake_neo4j = types.ModuleType("neo4j")
            fake_neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *_args, **_kwargs: _FakeDriver())

            with self._with_injected_modules({"neo4j": fake_neo4j}), mock.patch(
                "power_atlas.bootstrap.clients.neo4j.GraphDatabase.driver",
                new=fake_neo4j.GraphDatabase.driver,
            ):
                result = module._run_structured_ingest(config, run_id="structured_ingest-test")

            self.assertEqual(result["status"], "live")
            self.assertGreater(result["claims"], 0)
            self.assertEqual(result["validation_warning_count"], 0)
            self.assertTrue(Path(result["structured_ingest_dir"]).exists())
            self.assertTrue(Path(result["ingest_summary_path"]).exists())
            self.assertTrue(Path(result["validation_warnings_path"]).exists())
            ingest_summary = json.loads(Path(result["ingest_summary_path"]).read_text(encoding="utf-8"))
            self.assertEqual(ingest_summary["run_id"], "structured_ingest-test")
            self.assertEqual(ingest_summary["warning_count"], 0)
            self.assertIn("counts", ingest_summary)
            self.assertTrue(
                any("MERGE (claim:Claim" in query for query, _ in calls.get("queries", [])),
                "Expected claim ingestion query to run",
            )
            self.assertTrue(
                any("SUPPORTED_BY" in query and "source_row_id" in query for query, _ in calls.get("queries", [])),
                "Expected source_row_id evidence link query to run",
            )
            claim_query = next((query for query, _ in calls["queries"] if "MERGE (claim:Claim" in query), None)
            self.assertIsNotNone(claim_query, "Expected claim ingestion query to run")
            self.assertIn("MERGE (claim:Claim {claim_id: trim(row.claim_id), run_id: $run_id})", claim_query)
            self.assertIn("trim(coalesce(row.object_id, '')) = ''", claim_query)
            self.assertIn("OPTIONAL MATCH (fact:Fact {fact_id: trim(row.source_row_id), run_id: $run_id})", claim_query)
            self.assertIn("trim(row.claim_type) = 'fact'", claim_query)

    def test_structured_lint_deduplicates_duplicate_rows(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_dedup_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_fixtures = Path(tmpdir) / "fixtures"
            shutil.copytree(DEMO_DIR / "fixtures", copied_fixtures)
            entities_path = copied_fixtures / "structured" / "entities.csv"
            with entities_path.open("r", encoding="utf-8", newline="") as entities_file:
                rows = list(csv.DictReader(entities_file))
                headers = [
                    "entity_id",
                    "name",
                    "entity_type",
                    "aliases",
                    "description",
                    "wikidata_url",
                ]
            with entities_path.open("w", encoding="utf-8", newline="") as entities_file:
                writer = csv.DictWriter(entities_file, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows + [rows[0]])

            output_dir = Path(tmpdir) / "output"
            result = module.lint_and_clean_structured_csvs(
                run_id="structured_ingest-test",
                output_dir=output_dir,
                fixtures_dir=copied_fixtures,
            )

            self.assertEqual(result["files"]["entities.csv"]["input_rows"], len(rows) + 1)
            self.assertEqual(result["files"]["entities.csv"]["output_rows"], len(rows))
            self.assertEqual(result["files"]["entities.csv"]["deduplicated_rows"], 1)

    def test_structured_lint_ignores_blank_whitespace_rows(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_blank_rows_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_fixtures = Path(tmpdir) / "fixtures"
            shutil.copytree(DEMO_DIR / "fixtures", copied_fixtures)
            entities_path = copied_fixtures / "structured" / "entities.csv"
            with entities_path.open("r", encoding="utf-8", newline="") as entities_file:
                rows = list(csv.DictReader(entities_file))
            with entities_path.open("a", encoding="utf-8", newline="") as entities_file:
                entities_file.write(",,,,,\n")
                entities_file.write("  ,  ,  ,  ,  ,  \n")

            output_dir = Path(tmpdir) / "output"
            result = module.lint_and_clean_structured_csvs(
                run_id="structured_ingest-test",
                output_dir=output_dir,
                fixtures_dir=copied_fixtures,
            )

            self.assertEqual(result["files"]["entities.csv"]["input_rows"], len(rows))
            self.assertEqual(result["files"]["entities.csv"]["output_rows"], len(rows))
            self.assertGreaterEqual(result["files"]["entities.csv"]["dropped_blank_rows"], 1)

    def test_structured_lint_handles_entities_header_with_extra_column(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_header_mismatch_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_fixtures = Path(tmpdir) / "fixtures"
            shutil.copytree(DEMO_DIR / "fixtures", copied_fixtures)
            entities_path = copied_fixtures / "structured" / "entities.csv"
            with entities_path.open("r", encoding="utf-8", newline="") as entities_file:
                rows = list(csv.DictReader(entities_file))

            mismatch_headers = [
                "entity_id",
                "name",
                "entity_type",
                "aliases",
                "description",
                "wikidata_url",
                "unexpected_col",
            ]
            with entities_path.open("w", encoding="utf-8", newline="") as entities_file:
                writer = csv.DictWriter(entities_file, fieldnames=mismatch_headers)
                writer.writeheader()
                writer.writerows([{**row, "unexpected_col": "extra"} for row in rows])

            output_dir = Path(tmpdir) / "output"
            with self.assertRaises(ValueError):
                module.lint_and_clean_structured_csvs(
                    run_id="structured_ingest-test",
                    output_dir=output_dir,
                    fixtures_dir=copied_fixtures,
                )

            lint_report_path = output_dir / "runs" / "structured_ingest-test" / "lint_report.json"
            self.assertTrue(lint_report_path.exists())
            lint_report = json.loads(lint_report_path.read_text(encoding="utf-8"))
            self.assertGreater(lint_report["summary"]["issue_count"], 0)
            self.assertEqual(lint_report["files"]["entities.csv"]["output_rows"], len(rows))
            self.assertTrue(
                any(issue["code"] == "HEADER_MISMATCH" and issue["file"] == "entities.csv" for issue in lint_report["issues"])
            )

    def test_structured_lint_reports_read_error_and_emits_lint_report(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_missing_file_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_fixtures = Path(tmpdir) / "fixtures"
            shutil.copytree(DEMO_DIR / "fixtures", copied_fixtures)
            missing_file = copied_fixtures / "structured" / "facts.csv"
            missing_file.unlink()

            output_dir = Path(tmpdir) / "output"
            with self.assertRaises(ValueError):
                module.lint_and_clean_structured_csvs(
                    run_id="structured_ingest-test",
                    output_dir=output_dir,
                    fixtures_dir=copied_fixtures,
                )

            lint_report_path = output_dir / "runs" / "structured_ingest-test" / "lint_report.json"
            self.assertTrue(lint_report_path.exists())
            lint_report = json.loads(lint_report_path.read_text(encoding="utf-8"))
            self.assertTrue(
                any(issue["code"] == "READ_ERROR" and issue["file"] == "facts.csv" for issue in lint_report["issues"])
            )
            self.assertFalse(any(issue["code"] == "UNKNOWN_FACT_SOURCE_ROW" for issue in lint_report["issues"]))

    def test_structured_lint_uses_original_row_numbers_after_blank_rows(self):
        module = _load_module(RUN_DEMO_PATH, "run_structured_row_numbers_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_fixtures = Path(tmpdir) / "fixtures"
            shutil.copytree(DEMO_DIR / "fixtures", copied_fixtures)
            claims_path = copied_fixtures / "structured" / "claims.csv"
            with claims_path.open("r", encoding="utf-8", newline="") as claims_file:
                baseline_line_count = sum(1 for _ in claims_file)
            with claims_path.open("r", encoding="utf-8", newline="") as claims_file:
                claims_reader = csv.DictReader(claims_file)
                headers = claims_reader.fieldnames or []
                claims_rows = list(claims_reader)
            with claims_path.open("a", encoding="utf-8", newline="") as claims_file:
                claims_file.write(",,,,,,,,,,,,,\n")
                writer = csv.DictWriter(claims_file, fieldnames=headers)
                writer.writerow({**claims_rows[0], "subject_id": "ent_DOES_NOT_EXIST"})

            expected_row_number = baseline_line_count + 2
            output_dir = Path(tmpdir) / "output"
            with self.assertRaises(ValueError):
                module.lint_and_clean_structured_csvs(
                    run_id="structured_ingest-test",
                    output_dir=output_dir,
                    fixtures_dir=copied_fixtures,
                )

            lint_report_path = output_dir / "runs" / "structured_ingest-test" / "lint_report.json"
            lint_report = json.loads(lint_report_path.read_text(encoding="utf-8"))
            unknown_subject_issues = [
                issue
                for issue in lint_report["issues"]
                if issue["code"] == "UNKNOWN_SUBJECT_ID" and issue["message"].endswith("'ent_DOES_NOT_EXIST'")
            ]
            self.assertEqual(len(unknown_subject_issues), 1)
            self.assertEqual(unknown_subject_issues[0]["row"], expected_row_number)

    def test_run_pdf_ingest_non_dry_run_executes_config_pipeline_and_provenance_flow(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}

        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            query_payloads={
                "document_count": {"document_count": 1, "chunk_count": 2},
                "page_count": {"page_count": 2},
                "missing_chunk_order_count": {"missing_chunk_order_count": 0},
                "missing_embedding_count": {"missing_embedding_count": 0},
                "missing_page_count": {"missing_page_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
        )
        expected_fingerprint = module.sha256_file(
            module.resolve_dataset_root("demo_dataset_v1").pdf_path
        )
        initial_openai_state = ("OPENAI_API_KEY" in os.environ, os.environ.get("OPENAI_API_KEY"))
        initial_bridge_env = {
            key: (key in os.environ, os.environ.get(key))
            for key in (
                "NEO4J_URI",
                "NEO4J_USERNAME",
                "NEO4J_PASSWORD",
                "NEO4J_DATABASE",
                "OPENAI_MODEL",
            )
        }
        with self._with_injected_pdf_ingest_modules(injected_modules):
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

        self.assertEqual(result["status"], "live")
        summary_path = Path(result["ingest_summary_path"])
        self.assertTrue(summary_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["counts"], {"documents": 1, "pages": 2, "chunks": 2})
        self.assertEqual(result["counts"], summary["counts"])
        self.assertEqual(result["pdf_fingerprint_sha256"], expected_fingerprint)
        self.assertEqual(summary["pdf_fingerprint_sha256"], expected_fingerprint)
        self.assertEqual(summary["dataset_id"], "demo_dataset_v1")
        self.assertEqual(
            summary["pipeline_config_sha256"],
            module.sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(
            result["pipeline_config_sha256"],
            module.sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(summary["embedding_model"], module.EMBEDDER_MODEL_NAME)
        self.assertEqual(result["vector_index"]["creation_strategy"], "cypher")
        self.assertEqual(result["pipeline_result"], {"ok": True})
        self.assertEqual(result["provenance"]["dataset_id"], "demo_dataset_v1")
        self.assertTrue(
            any("CREATE VECTOR INDEX `demo_chunk_embedding_index` IF NOT EXISTS" in query for query, _ in calls["queries"]),
            "Expected Cypher vector index creation query",
        )
        self.assertNotIn("vector_index_fallback_reason", result)
        self.assertTrue(
            any(
                session_kwargs.get("database") == config.neo4j_database
                for session_kwargs in calls["sessions"]
            ),
            "Expected Neo4j session to be opened with database=config.neo4j_database",
        )
        self.assertEqual(
            calls["config_path"],
            str(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(
            calls["run_params"]["file_path"],
            str(module.resolve_dataset_root("demo_dataset_v1").pdf_path),
        )
        expected_pdf_uri = module.resolve_dataset_root("demo_dataset_v1").pdf_path.resolve().as_uri()
        self.assertEqual(
            calls["run_params"]["document_metadata"],
            {
                "run_id": "unstructured_ingest-test",
                "dataset_id": "demo_dataset_v1",
                "source_uri": expected_pdf_uri,
            },
        )
        self.assertNotIn("pdf_loader", calls["run_params"])
        self.assertTrue(
            any("SET d.run_id" in query for query, _ in calls.get("queries", [])),
            "Expected post-ingest provenance query to run",
        )
        normalized_query = next(query for query, _ in calls["queries"] if "SET d.run_id" in query)
        self.assertIn("d.run_id IS NULL OR d.run_id = $run_id", normalized_query)
        self.assertNotIn("id(c)", normalized_query)
        normalization_entry = next(
            ((query, kwargs) for query, kwargs in calls["queries"] if "start_char" in query and "chunk_index" in query),
            None,
        )
        self.assertIsNotNone(normalization_entry, "Expected chunk normalization query to run")
        self.assertEqual(
            normalization_entry[1].get("default_chunk_stride"),
            module.CHUNK_FALLBACK_STRIDE,
        )
        self.assertIn("toIntegerOrNull", normalization_entry[0])
        self.assertTrue(
            any(
                "document_count" in query and "chunk_count" in query
                for query, _ in calls["queries"]
            )
        )
        self.assertTrue(
            any("missing_page_count" in query for query, _ in calls["queries"]),
            "Expected missing page validation query",
        )
        self.assertTrue(
            any("missing_char_offset_count" in query for query, _ in calls["queries"]),
            "Expected missing char offset validation query",
        )
        self.assertNotIn("extraction_warnings", result)
        self.assertIn("warnings", result)
        self.assertEqual(
            ("OPENAI_API_KEY" in os.environ, os.environ.get("OPENAI_API_KEY")),
            initial_openai_state,
        )
        for key, expected_state in initial_bridge_env.items():
            self.assertEqual(
                (key in os.environ, os.environ.get(key)),
                expected_state,
                f"Expected {key} to be restored after pdf_ingest vendor bridge",
            )

    def test_pdf_ingest_query_payload_prefers_specific_markers(self):
        module = _load_module(RUN_DEMO_PATH, "run_marker_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}
        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            query_payloads={
                "missing_page_count": {"missing_page_count": 0},
                "page_count": {"page_count": 2},
                "document_count": {"document_count": 1, "chunk_count": 2},
                "missing_chunk_order_count": {"missing_chunk_order_count": 0},
                "missing_embedding_count": {"missing_embedding_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

        self.assertIn("matched_markers", calls)
        # The missing_page_count marker should match the query containing it, not page_count.
        self.assertIn("missing_page_count", calls["matched_markers"])
        self.assertGreaterEqual(calls["matched_markers"].count("missing_page_count"), 1)

    def test_run_pdf_ingest_dry_run_writes_summary_and_fingerprint(self):
        module = _load_module(RUN_DEMO_PATH, "run_pdf_dry_summary_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
            expected_fingerprint = module.sha256_file(
                DEMO_DIR / "fixtures" / "unstructured" / "chain_of_custody.pdf"
            )
            summary_path = Path(result["ingest_summary_path"])
            self.assertTrue(summary_path.exists())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["pdf_fingerprint_sha256"], expected_fingerprint)
            self.assertEqual(summary["counts"], {"documents": 0, "pages": 0, "chunks": 0})
            self.assertEqual(summary["dataset_id"], "demo_dataset_v1")
            self.assertEqual(summary["embedding_model"], module.EMBEDDER_MODEL_NAME)
            self.assertEqual(summary["embedding_dimensions"], module.CHUNK_EMBEDDING_DIMENSIONS)
            self.assertEqual(
                summary["pipeline_config_sha256"],
                module.sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
            )
            self.assertEqual(summary["vector_index"]["creation_strategy"], "dry_run")
            self.assertEqual(result["pdf_fingerprint_sha256"], expected_fingerprint)
            self.assertEqual(
                result["pipeline_config_sha256"],
                module.sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
            )
            self.assertEqual(Path(result["pdf_ingest_dir"]), summary_path.parent)
            self.assertEqual(result["vector_index"]["creation_strategy"], "dry_run")

    def test_run_pdf_ingest_non_dry_run_normalizes_non_json_pipeline_result(self):
        module = _load_module(RUN_DEMO_PATH, "run_result_fallback_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )

        injected_modules = self._build_pdf_ingest_test_modules(
            calls={},
            query_payloads={
                "document_count": {"document_count": 1, "chunk_count": 1},
                "missing_chunk_order_count": {"missing_chunk_order_count": 0},
                "missing_embedding_count": {"missing_embedding_count": 0},
                "missing_page_count": {"missing_page_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
            pipeline_result=lambda _params: object(),
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

        self.assertEqual(result["pipeline_result"]["type"], "object")
        self.assertIn("object object", result["pipeline_result"]["summary"])

    def test_run_pdf_ingest_non_dry_run_always_uses_cypher_index_creation(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_cypher_index_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}

        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            query_payloads={
                "document_count": {"document_count": 1, "chunk_count": 2},
                "missing_chunk_order_count": {"missing_chunk_order_count": 0},
                "missing_embedding_count": {"missing_embedding_count": 0},
                "missing_page_count": {"missing_page_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

        self.assertEqual(result["vector_index"]["creation_strategy"], "cypher")
        self.assertNotIn("vector_index_fallback_reason", result)
        self.assertTrue(
            any("CREATE VECTOR INDEX `demo_chunk_embedding_index` IF NOT EXISTS" in query for query, _ in calls["queries"])
        )

    def test_run_pdf_ingest_non_dry_run_rejects_unsafe_cypher_identifiers(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_unsafe_identifier_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}
        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
        )
        original_identifiers = {
            "CHUNK_EMBEDDING_INDEX_NAME": module.CHUNK_EMBEDDING_INDEX_NAME,
            "CHUNK_EMBEDDING_LABEL": module.CHUNK_EMBEDDING_LABEL,
            "CHUNK_EMBEDDING_PROPERTY": module.CHUNK_EMBEDDING_PROPERTY,
        }
        try:
            with self._with_injected_pdf_ingest_modules(injected_modules):
                for attr_name, value, expected in [
                    ("CHUNK_EMBEDDING_INDEX_NAME", "bad`index", "Unsafe index name for Cypher index creation"),
                    ("CHUNK_EMBEDDING_LABEL", "Chunk:Bad", "Unsafe label for Cypher index creation"),
                    ("CHUNK_EMBEDDING_PROPERTY", "embedding`bad", "Unsafe property for Cypher index creation"),
                ]:
                    for original_attr_name, original_value in original_identifiers.items():
                        setattr(module, original_attr_name, original_value)
                    setattr(module, attr_name, value)
                    with self.assertRaisesRegex(ValueError, expected):
                        module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
                self.assertFalse(calls.get("queries"))
        finally:
            for attr_name, original_value in original_identifiers.items():
                setattr(module, attr_name, original_value)

    def test_run_pdf_ingest_raises_when_contract_index_not_found_after_creation(self):
        """Post-creation validation raises a clear contract violation when the index is absent."""
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_index_contract_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}

        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            query_payloads={
                # Simulate SHOW INDEXES returning zero results for the contract index name.
                "contract_index_count": {"contract_index_count": 0},
            },
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            with self.assertRaisesRegex(
                ValueError,
                "Vector index contract violation",
            ):
                module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

    def test_run_pdf_ingest_non_dry_run_raises_when_no_run_scoped_documents_or_chunks(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_missing_nodes_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )

        injected_modules = self._build_pdf_ingest_test_modules(
            calls={},
            query_payloads={
                "document_count": {"document_count": 0, "chunk_count": 0},
                "missing_page_count": {"missing_page_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            with self.assertRaisesRegex(
                ValueError,
                "expected at least one Document and Chunk for this run",
            ):
                module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

    def test_run_pdf_ingest_non_dry_run_requires_openai_api_key(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_requires_openai_key_test")
        config = module.Config(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            with self.assertRaises(ValueError) as raised:
                module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
            self.assertEqual(str(raised.exception), "Set OPENAI_API_KEY when using --live ingest-pdf")
        finally:
            if had_openai_api_key:
                os.environ["OPENAI_API_KEY"] = original_openai_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_independent_ingest_commands_write_stage_manifests(self):
        module = _load_module(RUN_DEMO_PATH, "run_independent_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            structured_manifest_path = module.run_independent_demo(config, "ingest-structured")
            pdf_manifest_path = module.run_independent_demo(config, "ingest-pdf")
            self.assertTrue(structured_manifest_path.exists())
            self.assertTrue(pdf_manifest_path.exists())

            structured_manifest = json.loads(structured_manifest_path.read_text(encoding="utf-8"))
            pdf_manifest = json.loads(pdf_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(structured_manifest["run_scopes"]["batch_mode"], "single_independent_run")
            self.assertEqual(pdf_manifest["run_scopes"]["batch_mode"], "single_independent_run")
            self.assertEqual(set(structured_manifest["stages"].keys()), {"structured_ingest"})
            self.assertEqual(set(pdf_manifest["stages"].keys()), {"pdf_ingest"})
            self.assertIn("structured_ingest_run_id", structured_manifest["run_scopes"])
            self.assertEqual(
                structured_manifest["run_scopes"]["structured_ingest_run_id"],
                structured_manifest["stages"]["structured_ingest"]["run_id"],
            )
            self.assertIn("unstructured_ingest_run_id", pdf_manifest["run_scopes"])
            self.assertEqual(
                pdf_manifest["run_scopes"]["unstructured_ingest_run_id"],
                pdf_manifest["stages"]["pdf_ingest"]["run_id"],
            )
            self.assertNotEqual(structured_manifest["run_id"], pdf_manifest["run_id"])

    def test_smoke_test_supports_output_dir_override(self):
        sys.path.insert(0, str(DEMO_DIR))
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                smoke_module = _load_module(SMOKE_TEST_PATH, "smoke_test_module")
                output_dir = Path(tmpdir)
                expected_manifest = output_dir / "manifest.json"
                original_parse_args = smoke_module._parse_args
                try:
                    smoke_module._parse_args = lambda: type("Args", (), {"output_dir": output_dir})()
                    smoke_module.main()
                finally:
                    smoke_module._parse_args = original_parse_args
                self.assertTrue(expected_manifest.exists())
        finally:
            sys.path.pop(0)

    def test_run_demo_warns_and_falls_back_when_pipeline_yaml_cannot_be_parsed(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: (_ for _ in ()).throw(yaml.YAMLError("bad yaml"))
            with self.assertLogs("demo.contracts.pipeline", level="WARNING") as captured:
                module = _load_module(RUN_DEMO_PATH, "run_yaml_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("Falling back to default chunk embedding contract" in msg for msg in captured.output),
                "Expected warning when pipeline config cannot be parsed",
            )
        finally:
            yaml.safe_load = original_safe_load

    def test_run_demo_warns_and_falls_back_when_pipeline_yaml_top_level_is_not_mapping(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: []
            with self.assertLogs("demo.contracts.pipeline", level="WARNING") as captured:
                module = _load_module(RUN_DEMO_PATH, "run_yaml_top_level_type_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("expected mapping at top-level" in msg for msg in captured.output),
                "Expected warning when pipeline config top-level is not a mapping",
            )
        finally:
            yaml.safe_load = original_safe_load

    def test_run_demo_uses_live_pipeline_contract_values_without_import_time_snapshot(self):
        module = _load_module(RUN_DEMO_PATH, "run_live_pipeline_contract_test")
        config = module.Config(
            dry_run=True,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )

        import power_atlas.contracts.pipeline as pipeline_contracts

        original_index_name = pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME
        try:
            pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME = "dynamic_contract_index"

            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "dynamic_contract_index")

            summary = module._run_pdf_ingest(config, run_id="dynamic-contract-run")

            self.assertEqual(summary["vector_index"]["index_name"], "dynamic_contract_index")
        finally:
            pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME = original_index_name

    def test_run_demo_warns_and_falls_back_when_chunk_embedding_is_not_mapping(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: {"contract": {"chunk_embedding": []}}
            with self.assertLogs("demo.contracts.pipeline", level="WARNING") as captured:
                module = _load_module(RUN_DEMO_PATH, "run_chunk_contract_type_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("contract.chunk_embedding" in msg for msg in captured.output),
                "Expected warning when chunk embedding contract is not a mapping",
            )
        finally:
            yaml.safe_load = original_safe_load

    def test_run_demo_warns_and_falls_back_when_pipeline_contract_is_not_mapping(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: {"contract": "not-a-dict"}
            with self.assertLogs("demo.contracts.pipeline", level="WARNING") as captured:
                module = _load_module(RUN_DEMO_PATH, "run_pipeline_contract_type_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("expected mapping for contract" in msg for msg in captured.output),
                "Expected warning when pipeline contract is not a mapping",
            )
        finally:
            yaml.safe_load = original_safe_load

    # ── smoke test: _validate_citation_token ───────────────────────────────────

    def _load_smoke_module(self, module_name: str = "smoke_test_unit"):
        sys.path.insert(0, str(DEMO_DIR))
        try:
            return _load_module(SMOKE_TEST_PATH, module_name)
        finally:
            sys.path.pop(0)

    def test_validate_citation_token_accepts_all_fields(self):
        smoke = self._load_smoke_module("smoke_all_fields")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0|page=1|start_char=0|end_char=99]"
        parsed = smoke._validate_citation_token(token)
        self.assertEqual(parsed["chunk_id"], "c1")
        self.assertEqual(parsed["run_id"], "r1")
        self.assertEqual(parsed["chunk_index"], "0")
        self.assertEqual(parsed["page"], "1")

    def test_validate_citation_token_accepts_required_fields_only(self):
        """page, start_char, end_char are optional; token without them must pass."""
        smoke = self._load_smoke_module("smoke_required_only")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=2]"
        parsed = smoke._validate_citation_token(token)
        self.assertNotIn("page", parsed)
        self.assertNotIn("start_char", parsed)
        self.assertNotIn("end_char", parsed)

    def test_validate_citation_token_rejects_missing_required_field(self):
        smoke = self._load_smoke_module("smoke_missing_required")
        token = "[CITATION|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("chunk_id", str(ctx.exception))

    def test_validate_citation_token_rejects_malformed_segment(self):
        smoke = self._load_smoke_module("smoke_malformed")
        token = "[CITATION|chunk_id=c1|run_id|source_uri=file:///doc.pdf|chunk_index=0]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("key=value", str(ctx.exception))

    def test_validate_citation_token_rejects_non_integer_chunk_index(self):
        smoke = self._load_smoke_module("smoke_bad_ci")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=abc]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("chunk_index", str(ctx.exception))

    def test_validate_citation_token_rejects_negative_chunk_index(self):
        smoke = self._load_smoke_module("smoke_neg_ci")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=-1]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("chunk_index", str(ctx.exception))

    def test_validate_citation_token_rejects_invalid_optional_field_when_present(self):
        smoke = self._load_smoke_module("smoke_bad_optional")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0|page=not_a_number]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("page", str(ctx.exception))

    def test_validate_citation_token_rejects_end_char_less_than_start_char(self):
        smoke = self._load_smoke_module("smoke_end_lt_start")
        token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0|start_char=50|end_char=10]"
        with self.assertRaises(SystemExit) as ctx:
            smoke._validate_citation_token(token)
        self.assertIn("end_char", str(ctx.exception))

    def test_validate_citation_token_rejects_not_string(self):
        smoke = self._load_smoke_module("smoke_not_string")
        with self.assertRaises(SystemExit):
            smoke._validate_citation_token(None)

    # ── smoke test: _validate_independent_manifest ─────────────────────────────

    def _make_independent_manifest(
        self,
        stage_name: str,
        run_scope_key: str,
        run_id: str = "structured_ingest-20260101T000000000000Z-aabbccdd",
    ) -> dict:
        return {
            "run_id": run_id,
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "run_scopes": {
                "batch_mode": "single_independent_run",
                run_scope_key: run_id,
            },
            "config": {
                "dry_run": True,
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
            },
            "stages": {
                stage_name: {
                    "run_id": run_id,
                    "status": "ok",
                },
            },
        }

    def test_validate_independent_manifest_accepts_valid_structured_manifest(self):
        smoke = self._load_smoke_module("smoke_valid_indep")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")

    def test_validate_independent_manifest_accepts_valid_pdf_manifest(self):
        smoke = self._load_smoke_module("smoke_valid_pdf_indep")
        run_id = "unstructured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("pdf_ingest", "unstructured_ingest_run_id", run_id)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            smoke._validate_independent_manifest(path, "pdf_ingest", "unstructured_ingest_run_id")

    def test_validate_independent_manifest_rejects_wrong_batch_mode(self):
        smoke = self._load_smoke_module("smoke_wrong_batch_mode")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        manifest["run_scopes"]["batch_mode"] = "sequential_independent_runs"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("single_independent_run", str(ctx.exception))

    def test_validate_independent_manifest_rejects_missing_run_scope_key(self):
        smoke = self._load_smoke_module("smoke_missing_scope_key")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        del manifest["run_scopes"]["structured_ingest_run_id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("structured_ingest_run_id", str(ctx.exception))

    def test_validate_independent_manifest_rejects_mismatched_run_id(self):
        smoke = self._load_smoke_module("smoke_mismatched_run_id")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        manifest["run_id"] = "different_run_id"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("run_id", str(ctx.exception))

    def test_validate_independent_manifest_rejects_missing_stage(self):
        smoke = self._load_smoke_module("smoke_missing_stage")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        del manifest["stages"]["structured_ingest"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("structured_ingest", str(ctx.exception))

    def test_validate_independent_manifest_rejects_stage_run_id_mismatch(self):
        smoke = self._load_smoke_module("smoke_stage_run_id_mismatch")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        # The stage-level run_id disagrees with run_scopes value.
        manifest["stages"]["structured_ingest"]["run_id"] = "structured_ingest-20260101T000000000000Z-deadbeef"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("run_id", str(ctx.exception))

    def test_validate_core_manifest_fields_rejects_missing_top_level_field(self):
        """Deleting a required top-level field must trigger a SystemExit."""
        smoke = self._load_smoke_module("smoke_core_missing_top")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        del manifest["started_at"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("started_at", str(ctx.exception))

    def test_validate_core_manifest_fields_rejects_missing_config_field(self):
        """Deleting a required config sub-field must trigger a SystemExit."""
        smoke = self._load_smoke_module("smoke_core_missing_config")
        run_id = "structured_ingest-20260101T000000000000Z-aabbccdd"
        manifest = self._make_independent_manifest("structured_ingest", "structured_ingest_run_id", run_id)
        del manifest["config"]["openai_model"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_independent_manifest(path, "structured_ingest", "structured_ingest_run_id")
            self.assertIn("openai_model", str(ctx.exception))

    # ── smoke test: _validate_batch_manifest ──────────────────────────────────

    def _make_batch_manifest(
        self,
        structured_run_id: str = "structured-20260101T000000000000Z-aaaabbbb",
        unstructured_run_id: str = "unstructured-20260101T000000000000Z-ccccdddd",
    ) -> dict:
        token = (
            f"[CITATION|chunk_id=c1|run_id={unstructured_run_id}"
            f"|source_uri=file:///doc.pdf|chunk_index=0|page=1|start_char=0|end_char=99]"
        )
        return {
            "run_id": "batch-20260101T000000000000Z-11223344",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:05+00:00",
            "run_scopes": {
                "batch_mode": "sequential_independent_runs",
                "structured_ingest_run_id": structured_run_id,
                "unstructured_ingest_run_id": unstructured_run_id,
            },
            "config": {
                "dry_run": True,
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
            },
            "qa_signals": {
                "all_answers_cited": False,
                "evidence_level": "no_answer",
                "warning_count": 0,
                "warnings": [],
            },
            "stages": {
                "structured_ingest": {"run_id": structured_run_id, "status": "ok"},
                "pdf_ingest": {"run_id": unstructured_run_id, "status": "ok"},
                "claim_and_mention_extraction": {"run_id": unstructured_run_id, "status": "ok"},
                "retrieval_and_qa": {
                    "run_id": unstructured_run_id,
                    "citation_token_example": token,
                    "citation_example": {
                        "chunk_id": "c1",
                        "run_id": unstructured_run_id,
                        "source_uri": "file:///doc.pdf",
                        "chunk_index": 0,
                        "page": 1,
                        "start_char": 0,
                        "end_char": 99,
                    },
                    "citation_quality": {
                        "all_cited": False,
                        "evidence_level": "no_answer",
                        "warning_count": 0,
                        "citation_warnings": [],
                    },
                },
            },
        }

    def test_validate_batch_manifest_accepts_valid_manifest(self):
        smoke = self._load_smoke_module("smoke_valid_batch")
        manifest = self._make_batch_manifest()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            smoke._validate_batch_manifest(path)  # must not raise

    def test_validate_batch_manifest_accepts_citation_token_without_optional_fields(self):
        """Citation token without page/start_char/end_char must be accepted."""
        smoke = self._load_smoke_module("smoke_optional_absent")
        manifest = self._make_batch_manifest()
        # Replace token with one that omits optional fields.
        token_no_offsets = "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0]"
        manifest["stages"]["retrieval_and_qa"]["citation_token_example"] = token_no_offsets
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            smoke._validate_batch_manifest(path)  # must not raise

    def test_validate_batch_manifest_rejects_identical_run_ids(self):
        """Structured and unstructured run_ids must be distinct."""
        smoke = self._load_smoke_module("smoke_identical_run_ids")
        shared_id = "shared-20260101T000000000000Z-aaaabbbb"
        manifest = self._make_batch_manifest(
            structured_run_id=shared_id,
            unstructured_run_id=shared_id,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("distinct", str(ctx.exception))

    def test_validate_batch_manifest_rejects_wrong_batch_mode(self):
        smoke = self._load_smoke_module("smoke_batch_wrong_mode")
        manifest = self._make_batch_manifest()
        manifest["run_scopes"]["batch_mode"] = "single_independent_run"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("sequential_independent_runs", str(ctx.exception))

    def test_validate_batch_manifest_rejects_missing_stage(self):
        smoke = self._load_smoke_module("smoke_missing_batch_stage")
        manifest = self._make_batch_manifest()
        del manifest["stages"]["pdf_ingest"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("pdf_ingest", str(ctx.exception))

    def test_validate_batch_manifest_rejects_missing_qa_signals(self):
        smoke = self._load_smoke_module("smoke_missing_qa_signals")
        manifest = self._make_batch_manifest()
        del manifest["qa_signals"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("qa_signals", str(ctx.exception))

    def test_validate_batch_manifest_rejects_missing_run_scope_key(self):
        smoke = self._load_smoke_module("smoke_batch_missing_scope_key")
        manifest = self._make_batch_manifest()
        del manifest["run_scopes"]["structured_ingest_run_id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("structured_ingest_run_id", str(ctx.exception))

    def test_validate_batch_manifest_rejects_missing_unstructured_run_scope_key(self):
        smoke = self._load_smoke_module("smoke_batch_missing_unstruct_scope_key")
        manifest = self._make_batch_manifest()
        del manifest["run_scopes"]["unstructured_ingest_run_id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("unstructured_ingest_run_id", str(ctx.exception))

    def test_validate_batch_manifest_rejects_missing_citation_token_example(self):
        smoke = self._load_smoke_module("smoke_missing_citation_token")
        manifest = self._make_batch_manifest()
        del manifest["stages"]["retrieval_and_qa"]["citation_token_example"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                smoke._validate_batch_manifest(path)
            self.assertIn("citation_token_example", str(ctx.exception))

    # ── smoke test: independent scenario runners ───────────────────────────────

    def test_run_structured_scenario_writes_valid_manifest(self):
        sys.path.insert(0, str(DEMO_DIR))
        try:
            smoke = _load_module(SMOKE_TEST_PATH, "smoke_structured_scenario")
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                manifest_path = smoke._run_structured_scenario(output_dir)
                self.assertTrue(manifest_path.exists())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["run_scopes"]["batch_mode"], "single_independent_run")
                self.assertIn("structured_ingest", manifest["stages"])
                # Manifest must be inside runs/<run_id>/structured_ingest/
                self.assertIn("runs", manifest_path.parts)
        finally:
            sys.path.pop(0)

    def test_run_unstructured_scenario_writes_valid_manifest(self):
        sys.path.insert(0, str(DEMO_DIR))
        try:
            smoke = _load_module(SMOKE_TEST_PATH, "smoke_unstructured_scenario")
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                manifest_path = smoke._run_unstructured_scenario(output_dir)
                self.assertTrue(manifest_path.exists())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["run_scopes"]["batch_mode"], "single_independent_run")
                self.assertIn("pdf_ingest", manifest["stages"])
                # Manifest must be inside runs/<run_id>/pdf_ingest/
                self.assertIn("runs", manifest_path.parts)
        finally:
            sys.path.pop(0)

    def test_structured_and_unstructured_scenarios_produce_distinct_run_ids(self):
        """Independent structured and unstructured runs must not share a run_id."""
        sys.path.insert(0, str(DEMO_DIR))
        try:
            smoke = _load_module(SMOKE_TEST_PATH, "smoke_distinct_run_ids")
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                structured_path = smoke._run_structured_scenario(output_dir)
                unstructured_path = smoke._run_unstructured_scenario(output_dir)
                s_manifest = json.loads(structured_path.read_text(encoding="utf-8"))
                u_manifest = json.loads(unstructured_path.read_text(encoding="utf-8"))
                self.assertNotEqual(s_manifest["run_id"], u_manifest["run_id"])
        finally:
            sys.path.pop(0)

    def test_smoke_main_runs_all_scenarios_and_writes_batch_manifest(self):
        """main() must run structured, unstructured, and batch scenarios."""
        sys.path.insert(0, str(DEMO_DIR))
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                smoke_module = _load_module(SMOKE_TEST_PATH, "smoke_main_all_scenarios")
                output_dir = Path(tmpdir)
                original_parse_args = smoke_module._parse_args
                try:
                    smoke_module._parse_args = lambda: type("Args", (), {"output_dir": output_dir})()
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        smoke_module.main()
                    output_lines = buf.getvalue().splitlines()
                finally:
                    smoke_module._parse_args = original_parse_args
                # Batch manifest must exist at the root output_dir.
                self.assertTrue((output_dir / "manifest.json").exists())
                # At least three PASS lines (structured, unstructured, batch).
                pass_lines = [line for line in output_lines if "[PASS]" in line]
                self.assertGreaterEqual(len(pass_lines), 3)
        finally:
            sys.path.pop(0)

    # ── regression: ask --all-runs source_uri filtering ───────────────────────

    def test_ask_all_runs_non_interactive_manifest_has_null_source_uri(self):
        """Non-interactive ask --all-runs must write a manifest with retrieval_scope.source_uri=null.

        This is a regression guard: before the fix, _run_independent_stage always
        passed the demo fixture source_uri even in all-runs mode, silently constraining
        retrieval to a single document.
        """
        module = _load_module(RUN_DEMO_PATH, "run_ask_all_runs_regression_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            manifest_path = module.run_independent_demo(config, "ask", all_runs=True)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            retrieval_scope = manifest["stages"]["retrieval_and_qa"]["retrieval_scope"]
            self.assertIsNone(
                retrieval_scope["source_uri"],
                "ask --all-runs must not apply a source_uri filter (whole-database retrieval)",
            )
            self.assertTrue(retrieval_scope["all_runs"])
            self.assertIsNone(retrieval_scope["run_id"])
            # Confirm the run_scopes entry is also null in all-runs mode.
            self.assertIsNone(manifest["run_scopes"].get("unstructured_ingest_run_id"))

    def test_ask_all_runs_interactive_passes_null_source_uri(self):
        """Interactive ask --interactive --all-runs must call run_interactive_qa with source_uri=None.

        This is a regression guard: before the fix, the interactive path hard-coded
        the demo fixture URI, so --all-runs still filtered to a single document.
        """
        module = _load_module(RUN_DEMO_PATH, "run_ask_interactive_all_runs_regression_test")
        captured: dict[str, object] = {}

        def _fake_run_interactive_qa(config, **kwargs):
            captured.update(kwargs)

        args = type(
            "Args",
            (),
            {
                "command": "ask",
                "dry_run": False,
                "interactive": True,
                "all_runs": True,
                "run_id": None,
                "latest": False,
                "output_dir": DEMO_DIR / "artifacts",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "testtesttest",
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
                "question": None,
            },
        )()
        original_parse_args = module.parse_args
        original_run_interactive_qa = module.run_interactive_qa
        try:
            module.parse_args = lambda: args
            module.run_interactive_qa = _fake_run_interactive_qa
            with io.StringIO() as buf, redirect_stdout(buf):
                module.main()
        finally:
            module.parse_args = original_parse_args
            module.run_interactive_qa = original_run_interactive_qa

        self.assertIn("source_uri", captured, "run_interactive_qa must be called with source_uri kwarg")
        self.assertIsNone(
            captured["source_uri"],
            "ask --interactive --all-runs must pass source_uri=None (whole-database retrieval)",
        )
        self.assertTrue(captured.get("all_runs"))
        self.assertIsNone(captured.get("run_id"))

    # ── cluster-aware / expand-graph retrieval flags ───────────────────────────

    def test_ask_cluster_aware_manifest_records_cluster_aware_true(self):
        """Non-interactive ask --cluster-aware must write a manifest with cluster_aware=true.

        This is the intended final validation step for the unstructured-first ER
        architecture: after hybrid alignment the manifest must confirm that
        cluster-aware retrieval was active, not the default plain vector path.
        """
        module = _load_module(RUN_DEMO_PATH, "run_ask_cluster_aware_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            manifest_path = module.run_independent_demo(config, "ask", cluster_aware=True)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stage = manifest["stages"]["retrieval_and_qa"]
            self.assertTrue(
                stage["cluster_aware"],
                "ask --cluster-aware must record cluster_aware=true in the manifest",
            )
            self.assertTrue(
                stage["expand_graph"],
                "ask --cluster-aware implies expand_graph=true in the manifest",
            )

    def test_ask_expand_graph_manifest_records_expand_graph_true(self):
        """Non-interactive ask --expand-graph must write a manifest with expand_graph=true."""
        module = _load_module(RUN_DEMO_PATH, "run_ask_expand_graph_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            manifest_path = module.run_independent_demo(config, "ask", expand_graph=True)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stage = manifest["stages"]["retrieval_and_qa"]
            self.assertTrue(
                stage["expand_graph"],
                "ask --expand-graph must record expand_graph=true in the manifest",
            )
            self.assertFalse(
                stage["cluster_aware"],
                "ask --expand-graph alone must not set cluster_aware=true",
            )

    def test_ask_default_manifest_records_plain_retrieval(self):
        """Non-interactive ask with no retrieval flags must record both flags as false.

        This verifies the baseline plain vector retrieval mode so that the
        difference from graph-aware modes is explicit in manifests.
        """
        module = _load_module(RUN_DEMO_PATH, "run_ask_plain_retrieval_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.Config(
                dry_run=True,
                output_dir=Path(tmpdir),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
            manifest_path = module.run_independent_demo(config, "ask")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stage = manifest["stages"]["retrieval_and_qa"]
            self.assertFalse(
                stage["cluster_aware"],
                "default ask must record cluster_aware=false",
            )
            self.assertFalse(
                stage["expand_graph"],
                "default ask must record expand_graph=false",
            )

    def test_ask_cluster_aware_interactive_passes_cluster_aware_kwarg(self):
        """Interactive ask --cluster-aware must call run_interactive_qa with cluster_aware=True."""
        module = _load_module(RUN_DEMO_PATH, "run_ask_interactive_cluster_aware_test")
        captured: dict[str, object] = {}

        def _fake_run_interactive_qa(config, **kwargs):
            captured.update(kwargs)

        args = type(
            "Args",
            (),
            {
                "command": "ask",
                "dry_run": False,
                "interactive": True,
                "all_runs": False,
                "run_id": None,
                "latest": False,
                "cluster_aware": True,
                "expand_graph": False,
                "output_dir": DEMO_DIR / "artifacts",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "testtesttest",
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
                "question": None,
            },
        )()
        original_parse_args = module.parse_args
        original_run_interactive_qa = module.run_interactive_qa
        original_resolve = module._resolve_ask_scope
        try:
            module.parse_args = lambda: args
            module.run_interactive_qa = _fake_run_interactive_qa
            # Stub _resolve_ask_scope to avoid a live Neo4j call.
            module._resolve_ask_scope = lambda _args, _cfg: ("test-run-id", False)
            with io.StringIO() as buf, redirect_stdout(buf):
                module.main()
        finally:
            module.parse_args = original_parse_args
            module.run_interactive_qa = original_run_interactive_qa
            module._resolve_ask_scope = original_resolve

        self.assertTrue(
            captured.get("cluster_aware"),
            "run_interactive_qa must be called with cluster_aware=True when --cluster-aware is set",
        )

    def test_parse_args_ask_cluster_aware_flag(self):
        """parse_args must accept --cluster-aware for the ask subcommand."""
        module = _load_module(RUN_DEMO_PATH, "run_ask_parse_cluster_aware_test")
        args = module.parse_args(["ask", "--cluster-aware"])
        self.assertTrue(
            getattr(args, "cluster_aware", False),
            "--cluster-aware flag must be parsed as cluster_aware=True",
        )
        self.assertFalse(
            getattr(args, "expand_graph", True),
            "--expand-graph must default to False when not specified",
        )

    def test_parse_args_ask_expand_graph_flag(self):
        """parse_args must accept --expand-graph for the ask subcommand."""
        module = _load_module(RUN_DEMO_PATH, "run_ask_parse_expand_graph_test")
        args = module.parse_args(["ask", "--expand-graph"])
        self.assertTrue(
            getattr(args, "expand_graph", False),
            "--expand-graph flag must be parsed as expand_graph=True",
        )
        self.assertFalse(
            getattr(args, "cluster_aware", True),
            "--cluster-aware must default to False when not specified",
        )

    def test_fetch_dataset_id_warns_on_mixed_dataset_ids(self):
        """_fetch_dataset_id_for_run must warn when a run has multiple distinct dataset_ids."""
        module = _load_module(RUN_DEMO_PATH, "run_fetch_dataset_id_mixed_test")
        import power_atlas.bootstrap.clients as bootstrap_clients

        # Build a fake neo4j that simulates the two-phase query behaviour:
        # - Fast-path query (LIMIT 2) → {"dataset_ids": ["dataset_a", "dataset_b"]}
        # - Slow-path query (count + capped sample) → {"total_count": 3, "sampled_ids": [...]}
        class _FastPathResult:
            def single(self):
                return {"dataset_ids": ["dataset_a", "dataset_b"]}

        class _SlowPathResult:
            def single(self):
                return {
                    "total_count": 3,
                    "sampled_ids": ["dataset_a", "dataset_b", "dataset_c"],
                }

        class _FakeSession:
            def __init__(self):
                self._call_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                self._call_count += 1
                if self._call_count == 1:
                    return _FastPathResult()
                return _SlowPathResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        config = type(
            "Config",
            (),
            {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
            },
        )()

        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_k: _FakeDriver()
        try:
            with self.assertLogs(logger=module.__name__, level="WARNING") as log_cm:
                result = module._fetch_dataset_id_for_run(config, "test-run-id-mixed")
        finally:
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver

        # When multiple distinct dataset_ids are found for a run, the function
        # should warn and return the first sorted dataset_id so the behavior
        # remains deterministic even for an ambiguous result set.
        self.assertEqual(
            result,
            "dataset_a",
            "Should return the first sorted dataset_id when multiple dataset_ids are found for a run",
        )
        # A WARNING about multiple dataset_ids must be logged.
        warning_lines = [line for line in log_cm.output if "WARNING" in line]
        self.assertTrue(
            warning_lines,
            "A WARNING must be logged when a run has multiple dataset_ids",
        )
        combined = "\n".join(log_cm.output)
        self.assertIn(
            "dataset_a",
            combined,
            "Warning must mention the dataset_ids found",
        )
        self.assertIn(
            "dataset_b",
            combined,
            "Warning must mention all dataset_ids found",
        )
        self.assertIn(
            "dataset_c",
            combined,
            "Warning must mention all sampled dataset_ids found",
        )
        self.assertIn(
            "3 distinct dataset_ids",
            combined,
            "Warning must include the distinct-count wording from the new mixed-dataset warning",
        )
        self.assertRegex(
            combined,
            r"Showing the first \d+ sorted dataset_ids",
            "Warning must include the sampled sorted dataset_ids wording from the new mixed-dataset warning",
        )

    def test_fetch_dataset_id_returns_single_id_no_warning(self):
        """_fetch_dataset_id_for_run must return the lone dataset_id with no warning (fast-path, single ID)."""
        module = _load_module(RUN_DEMO_PATH, "run_fetch_dataset_id_single_test")
        import power_atlas.bootstrap.clients as bootstrap_clients

        class _SingleResult:
            def single(self):
                return {"dataset_ids": ["only_dataset"]}

        class _FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                return _SingleResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        config = type(
            "Config",
            (),
            {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
            },
        )()

        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_k: _FakeDriver()
        try:
            with self.assertNoLogs(logger=module.__name__, level="WARNING"):
                result = module._fetch_dataset_id_for_run(config, "test-run-id-single")
        finally:
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver

        self.assertEqual(
            result,
            "only_dataset",
            "Should return the single dataset_id without a warning",
        )

    def test_fetch_dataset_id_returns_none_for_no_datasets(self):
        """_fetch_dataset_id_for_run must return None with no warning when no dataset_ids exist."""
        module = _load_module(RUN_DEMO_PATH, "run_fetch_dataset_id_none_test")
        import power_atlas.bootstrap.clients as bootstrap_clients

        class _EmptyResult:
            def single(self):
                return {"dataset_ids": []}

        class _FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                return _EmptyResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        config = type(
            "Config",
            (),
            {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
            },
        )()

        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_k: _FakeDriver()
        try:
            with self.assertNoLogs(logger=module.__name__, level="WARNING"):
                result = module._fetch_dataset_id_for_run(config, "test-run-id-no-datasets")
        finally:
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver

        self.assertIsNone(
            result,
            "Should return None when no dataset_ids are found for the run",
        )

    def test_fetch_dataset_id_slow_path_fallback_branch(self):
        """_fetch_dataset_id_for_run uses detected_ids when slow-path sampled_ids is empty."""
        module = _load_module(RUN_DEMO_PATH, "run_fetch_dataset_id_fallback_test")
        import power_atlas.bootstrap.clients as bootstrap_clients

        # Simulate the two-phase query:
        # - Fast-path (LIMIT 2) detects two distinct ids.
        # - Slow-path returns total_count=2 but sampled_ids=[] (edge-case empty sample).
        # The function must fall back to detected_ids from the fast path.
        class _FastPathResult:
            def single(self):
                return {"dataset_ids": ["alpha", "beta"]}

        class _SlowPathResult:
            def single(self):
                return {"total_count": 2, "sampled_ids": []}

        class _FakeSession:
            def __init__(self):
                self._call_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                self._call_count += 1
                if self._call_count == 1:
                    return _FastPathResult()
                return _SlowPathResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        config = type(
            "Config",
            (),
            {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
            },
        )()

        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_k: _FakeDriver()
        try:
            with self.assertLogs(logger=module.__name__, level="WARNING") as log_cm:
                result = module._fetch_dataset_id_for_run(config, "test-run-id-fallback")
        finally:
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver

        # Should return the first sorted id from the fast-path detected_ids fallback.
        self.assertEqual(
            result,
            "alpha",
            "Should return the first sorted id from the fast-path fallback when sampled_ids is empty",
        )
        combined = "\n".join(log_cm.output)
        # The warning must mention the fallback reason.
        self.assertIn(
            "fallback",
            combined,
            "Warning must mention the fallback from the fast-path detection",
        )

    def test_fetch_latest_run_id_warns_on_inconsistent_dataset_stamps(self):
        """_fetch_latest_unstructured_run_id must warn when resolved run has multiple dataset_ids."""
        module = _load_module(RUN_DEMO_PATH, "run_fetch_latest_run_id_inconsistent_test")
        import power_atlas.bootstrap.clients as bootstrap_clients

        # Session returns:
        # - First call (latest run query) → run_id record
        # - Second call (consistency LIMIT 2 check) → two distinct dataset_ids
        class _RunIdResult:
            def single(self):
                # Simulate a record whose first element is the run_id.
                class _Record:
                    def __getitem__(self, idx):
                        return "unstructured_ingest-20260101T000000000000Z-abcdef01"
                return _Record()

        class _InconsistentCheckResult:
            def single(self):
                return {"dataset_ids": ["dataset_x", "dataset_y"]}

        class _FakeSession:
            def __init__(self):
                self._call_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                self._call_count += 1
                if self._call_count == 1:
                    return _RunIdResult()
                return _InconsistentCheckResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        config = type(
            "Config",
            (),
            {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
            },
        )()

        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_k: _FakeDriver()
        try:
            with self.assertLogs(logger=module.__name__, level="WARNING") as log_cm:
                result = module._fetch_latest_unstructured_run_id(config)
        finally:
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver

        self.assertEqual(
            result,
            "unstructured_ingest-20260101T000000000000Z-abcdef01",
            "Should still return the resolved run_id even when inconsistency is detected",
        )
        combined = "\n".join(log_cm.output)
        warning_lines = [line for line in log_cm.output if "WARNING" in line]
        self.assertTrue(
            warning_lines,
            "A WARNING must be logged when the resolved run has multiple dataset_ids",
        )
        self.assertIn(
            "dataset_x",
            combined,
            "Warning must mention the conflicting dataset_ids",
        )
        self.assertIn(
            "dataset_y",
            combined,
            "Warning must mention the conflicting dataset_ids",
        )

    def test_resolve_ask_scope_warns_on_resolve_dataset_root_value_error(self):
        """_resolve_ask_scope must emit a warning (not silently skip) when
        resolve_dataset_root raises ValueError for an unknown dataset name."""
        module = _load_module(RUN_DEMO_PATH, "run_resolve_ask_scope_value_error_test")

        config = type(
            "Config",
            (),
            {
                "dry_run": False,
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "test",
                "neo4j_database": "neo4j",
                "dataset_name": "nonexistent_dataset_typo",
            },
        )()
        args = type(
            "Args",
            (),
            {
                "run_id": "explicit-run-id-001",
                "latest": False,
                "all_runs": False,
            },
        )()

        # Stub _fetch_dataset_id_for_run to avoid a live Neo4j call.
        original_fetch = module._fetch_dataset_id_for_run
        module._fetch_dataset_id_for_run = lambda _cfg, _rid: "some_dataset_id"

        env_backup = os.environ.pop("FIXTURE_DATASET", None)
        env_backup_run_id = os.environ.pop("UNSTRUCTURED_RUN_ID", None)
        try:
            with self.assertLogs(logger=module.__name__, level="WARNING") as log_cm:
                run_id, all_runs = module._resolve_ask_scope(args, config)
        finally:
            module._fetch_dataset_id_for_run = original_fetch
            if env_backup is not None:
                os.environ["FIXTURE_DATASET"] = env_backup
            if env_backup_run_id is not None:
                os.environ["UNSTRUCTURED_RUN_ID"] = env_backup_run_id

        # The scope must still return the explicit run_id (pipeline should proceed).
        self.assertEqual(run_id, "explicit-run-id-001")
        self.assertFalse(all_runs)
        # A WARNING about the failed dataset resolution must be logged.
        warning_lines = [line for line in log_cm.output if "WARNING" in line]
        self.assertTrue(
            warning_lines,
            "A WARNING must be logged when resolve_dataset_root raises ValueError",
        )
        combined = "\n".join(log_cm.output)
        self.assertIn(
            "nonexistent_dataset_typo",
            combined,
            "Warning must mention the dataset name that failed to resolve",
        )

    def test_resolve_ask_scope_warning_names_power_atlas_dataset_env(self):
        module = _load_module(RUN_DEMO_PATH, "run_resolve_ask_scope_power_atlas_dataset_test")

        config = type(
            "Config",
            (),
            {
                "dry_run": True,
                "dataset_name": None,
            },
        )()
        args = type(
            "Args",
            (),
            {
                "run_id": None,
                "latest": False,
                "all_runs": False,
            },
        )()

        env_backup_fixture = os.environ.pop("FIXTURE_DATASET", None)
        env_backup_power_atlas = os.environ.pop("POWER_ATLAS_DATASET", None)
        env_backup_run_id = os.environ.get("UNSTRUCTURED_RUN_ID")
        os.environ["POWER_ATLAS_DATASET"] = "demo_dataset_v2"
        os.environ["UNSTRUCTURED_RUN_ID"] = "unstructured_ingest-test-12345678"
        try:
            with self.assertLogs(logger=module.__name__, level="WARNING") as log_cm:
                run_id, all_runs = module._resolve_ask_scope(args, config)
        finally:
            if env_backup_fixture is not None:
                os.environ["FIXTURE_DATASET"] = env_backup_fixture
            else:
                os.environ.pop("FIXTURE_DATASET", None)
            if env_backup_power_atlas is not None:
                os.environ["POWER_ATLAS_DATASET"] = env_backup_power_atlas
            else:
                os.environ.pop("POWER_ATLAS_DATASET", None)
            if env_backup_run_id is not None:
                os.environ["UNSTRUCTURED_RUN_ID"] = env_backup_run_id
            else:
                os.environ.pop("UNSTRUCTURED_RUN_ID", None)

        self.assertEqual(run_id, "unstructured_ingest-test-12345678")
        self.assertFalse(all_runs)
        combined = "\n".join(log_cm.output)
        self.assertIn("POWER_ATLAS_DATASET='demo_dataset_v2'", combined)


class ResetDemoDbTests(unittest.TestCase):
    """Tests for demo/reset_demo_db.py run_reset() and related helpers."""

    def _make_fake_modules(
        self,
        *,
        nodes_deleted: int = 3,
        relationships_deleted: int = 2,
        index_exists: bool = True,
        drop_calls: list | None = None,
        execute_query_calls: list | None = None,
        stale_edges_deleted: int = 0,
    ) -> types.ModuleType:
        """Return fake_neo4j module for reset tests.

        Index drops are detected by watching for ``DROP INDEX <name> IF EXISTS``
        queries issued via session.run().  Matching index names are appended to
        *drop_calls* so tests can assert on them without relying on the
        (removed) vendor ``drop_index_if_exists`` helper.

        *stale_edges_deleted* controls how many relationships the stale pre-v0.3
        participation-edge cleanup query (e.g.
        ``MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT|HAS_OBJECT|HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention) DELETE r``)
        reports as deleted.  Defaults to 0 (clean v0.3 graph).
        """
        if drop_calls is None:
            drop_calls = []
        if execute_query_calls is None:
            execute_query_calls = []

        class _FakeCounters:
            def __init__(self, nodes: int, rels: int) -> None:
                self.nodes_deleted = nodes
                self.relationships_deleted = rels

        class _FakeConsumeResult:
            def __init__(self, nodes: int, rels: int) -> None:
                self.counters = _FakeCounters(nodes, rels)

        class _FakeResult:
            def __init__(self, nodes: int, rels: int) -> None:
                self._nodes = nodes
                self._rels = rels

            def consume(self) -> _FakeConsumeResult:
                return _FakeConsumeResult(self._nodes, self._rels)

        _captured_drop_calls = drop_calls
        _stale_edges_deleted = stale_edges_deleted

        class _FakeSession:
            def __init__(self, nodes: int, rels: int) -> None:
                self._nodes = nodes
                self._rels = rels
                self.most_recent_query: str = ""

            def __enter__(self) -> "_FakeSession":
                return self

            def __exit__(self, *_) -> bool:
                return False

            def run(self, query: str, **_kwargs) -> _FakeResult:
                self.most_recent_query = query
                # Capture DROP INDEX calls so tests can assert on them.
                _drop_match = re.search(
                    r"DROP\s+INDEX\s+(\w+)\s+IF\s+EXISTS", query, re.IGNORECASE
                )
                if _drop_match:
                    _captured_drop_calls.append(_drop_match.group(1))
                # Stale participation-edge cleanup query returns only stale
                # relationship counts (no node deletions).  Match on the
                # scoped pattern (ExtractedClaim → EntityMention) so the mock
                # stays consistent with the scoped Cypher in reset_demo_db.py.
                if (
                    "ExtractedClaim" in query
                    and "EntityMention" in query
                    and "HAS_SUBJECT" in query
                    and "DELETE" in query
                ):
                    return _FakeResult(0, _stale_edges_deleted)
                return _FakeResult(self._nodes, self._rels)

        _index_exists_value = index_exists

        class _FakeDriver:
            def __enter__(self) -> "_FakeDriver":
                return self

            def __exit__(self, *_) -> bool:
                return False

            def session(self, **kwargs) -> _FakeSession:
                _sess = _FakeSession(nodes_deleted, relationships_deleted)
                execute_query_calls.append(("__session__", _sess))
                return _sess

            def execute_query(self, query: str, parameters_: dict | None = None, database_: str = "neo4j"):
                # Returns the standard (records, summary, keys) 3-tuple matching the
                # real neo4j.Driver.execute_query API used throughout this repo.
                execute_query_calls.append((query, parameters_, database_))
                cnt = 1 if _index_exists_value else 0
                return ([{"cnt": cnt}], None, None)

        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = types.SimpleNamespace(
            driver=lambda *_a, **_kw: _FakeDriver()
        )
        return fake_neo4j

    @contextmanager
    def _inject_reset_modules(self, fake_neo4j):
        original = sys.modules.get("neo4j")
        try:
            sys.modules["neo4j"] = fake_neo4j
            yield
        finally:
            if original is None:
                sys.modules.pop("neo4j", None)
            else:
                sys.modules["neo4j"] = original

    def _load_reset_module(self, name: str = "reset_db_test"):
        reset_path = DEMO_DIR / "reset_demo_db.py"
        return _load_module(reset_path, name)

    def test_reset_parse_args_uses_package_settings_defaults(self):
        previous_password = os.environ.pop("NEO4J_PASSWORD", None)
        previous_uri = os.environ.get("NEO4J_URI")
        previous_username = os.environ.get("NEO4J_USERNAME")
        previous_database = os.environ.get("NEO4J_DATABASE")
        os.environ["NEO4J_URI"] = "bolt://reset.test:7687"
        os.environ["NEO4J_USERNAME"] = "reset-user"
        os.environ["NEO4J_DATABASE"] = "reset-db"
        try:
            module = self._load_reset_module("reset_parse_defaults_test")
            args = module.parse_args(["--confirm"])
        finally:
            if previous_uri is None:
                os.environ.pop("NEO4J_URI", None)
            else:
                os.environ["NEO4J_URI"] = previous_uri
            if previous_username is None:
                os.environ.pop("NEO4J_USERNAME", None)
            else:
                os.environ["NEO4J_USERNAME"] = previous_username
            if previous_database is None:
                os.environ.pop("NEO4J_DATABASE", None)
            else:
                os.environ["NEO4J_DATABASE"] = previous_database
            if previous_password is None:
                os.environ.pop("NEO4J_PASSWORD", None)
            else:
                os.environ["NEO4J_PASSWORD"] = previous_password

        self.assertEqual(args.neo4j_uri, "bolt://reset.test:7687")
        self.assertEqual(args.neo4j_username, "reset-user")
        self.assertEqual(args.neo4j_database, "reset-db")
        self.assertIsNone(args.neo4j_password)

    def test_reset_parse_args_cli_overrides_defaults(self):
        previous_password = os.environ.get("NEO4J_PASSWORD")
        previous_uri = os.environ.get("NEO4J_URI")
        previous_username = os.environ.get("NEO4J_USERNAME")
        previous_database = os.environ.get("NEO4J_DATABASE")
        os.environ["NEO4J_URI"] = "bolt://reset.test:7687"
        os.environ["NEO4J_USERNAME"] = "reset-user"
        os.environ["NEO4J_PASSWORD"] = "env-secret"
        os.environ["NEO4J_DATABASE"] = "reset-db"
        try:
            module = self._load_reset_module("reset_parse_cli_override_test")
            args = module.parse_args(
                [
                    "--confirm",
                    "--neo4j-uri",
                    "bolt://override.test:7687",
                    "--neo4j-username",
                    "override-user",
                    "--neo4j-password",
                    "override-secret",
                    "--neo4j-database",
                    "override-db",
                ]
            )
        finally:
            if previous_uri is None:
                os.environ.pop("NEO4J_URI", None)
            else:
                os.environ["NEO4J_URI"] = previous_uri
            if previous_username is None:
                os.environ.pop("NEO4J_USERNAME", None)
            else:
                os.environ["NEO4J_USERNAME"] = previous_username
            if previous_database is None:
                os.environ.pop("NEO4J_DATABASE", None)
            else:
                os.environ["NEO4J_DATABASE"] = previous_database
            if previous_password is None:
                os.environ.pop("NEO4J_PASSWORD", None)
            else:
                os.environ["NEO4J_PASSWORD"] = previous_password

        self.assertEqual(args.neo4j_uri, "bolt://override.test:7687")
        self.assertEqual(args.neo4j_username, "override-user")
        self.assertEqual(args.neo4j_password, "override-secret")
        self.assertEqual(args.neo4j_database, "override-db")

    # ── run_reset report structure ────────────────────────────────────────────

    def test_run_reset_returns_report_with_expected_keys(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=5, relationships_deleted=3, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_keys_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        required_keys = {
            "created_at",
            "target_database",
            "reset_mode",
            "demo_labels_deleted",
            "deleted_nodes",
            "deleted_relationships",
            "stale_participation_edges_deleted",
            "indexes_dropped",
            "indexes_not_found",
            "warnings",
            "idempotent",
        }
        self.assertTrue(required_keys.issubset(report.keys()), f"Missing keys: {required_keys - report.keys()}")

    def test_run_reset_returns_correct_counts_when_nodes_and_index_exist(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=7, relationships_deleted=4, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_counts_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="testdb",
                output_dir=None,
            )

        self.assertEqual(report["deleted_nodes"], 7)
        self.assertEqual(report["deleted_relationships"], 4)
        self.assertEqual(report["target_database"], "testdb")
        self.assertEqual(report["reset_mode"], "demo_full_graph_wipe")
        self.assertFalse(report["idempotent"])
        self.assertEqual(len(drop_calls), 1, "Expected exactly one index drop call")

    def test_run_reset_indexes_dropped_when_index_exists(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=2, relationships_deleted=1, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_index_dropped_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertIn("demo_chunk_embedding_index", report["indexes_dropped"])
        self.assertEqual(report["indexes_not_found"], [])
        self.assertEqual(drop_calls, ["demo_chunk_embedding_index"])

    def test_run_reset_uses_live_pipeline_contract_index_name(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=2, relationships_deleted=1, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_dynamic_index_test")

        import power_atlas.contracts.pipeline as pipeline_contracts

        original_index_name = pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME
        try:
            pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME = "dynamic_reset_index"
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )
        finally:
            pipeline_contracts.CHUNK_EMBEDDING_INDEX_NAME = original_index_name

        self.assertEqual(report["indexes_dropped"], ["dynamic_reset_index"])
        self.assertEqual(report["indexes_not_found"], [])
        self.assertEqual(drop_calls, ["dynamic_reset_index"])

    # ── idempotent no-op paths ────────────────────────────────────────────────

    def test_run_reset_idempotent_when_graph_empty_and_index_absent(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=0, relationships_deleted=0, index_exists=False, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_idempotent_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertTrue(report["idempotent"])
        self.assertEqual(report["deleted_nodes"], 0)
        self.assertEqual(report["deleted_relationships"], 0)
        self.assertEqual(report["indexes_dropped"], [])
        self.assertIn("demo_chunk_embedding_index", report["indexes_not_found"])
        # Expect one warning for no demo nodes found and one for the absent index.
        self.assertTrue(
            any("No demo-owned nodes found" in w for w in report["warnings"]),
            "Expected a warning about no demo-owned nodes being found",
        )
        self.assertTrue(
            any("demo_chunk_embedding_index" in w and "not found" in w for w in report["warnings"]),
            "Expected a warning about the index not being found",
        )
        self.assertEqual(drop_calls, [], "No drop call expected when index is absent")

    def test_run_reset_idempotent_flag_false_when_nodes_deleted(self):
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=1, relationships_deleted=0, index_exists=False
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_idempotent_nodes_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertFalse(report["idempotent"])

    def test_run_reset_idempotent_flag_false_when_index_dropped(self):
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=0, relationships_deleted=0, index_exists=True
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_idempotent_index_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertFalse(report["idempotent"])
        self.assertIn("demo_chunk_embedding_index", report["indexes_dropped"])

    def test_run_reset_idempotent_flag_false_when_stale_edges_deleted(self):
        """idempotent must be False when stale pre-v0.3 participation edges are removed."""
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=0, relationships_deleted=0, index_exists=False, stale_edges_deleted=3
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_idempotent_stale_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertFalse(report["idempotent"])
        self.assertEqual(report["stale_participation_edges_deleted"], 3)
        self.assertTrue(
            any("stale" in w.lower() or "HAS_PARTICIPANT" in w or "HAS_SUBJECT" in w for w in report["warnings"]),
            "Expected a non-migratability warning for stale participation edges",
        )

    def test_run_reset_stale_participation_edges_zero_on_clean_v03_graph(self):
        """stale_participation_edges_deleted is 0 for a clean v0.3 graph."""
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=5, relationships_deleted=3, index_exists=True, stale_edges_deleted=0
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_stale_zero_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertEqual(report["stale_participation_edges_deleted"], 0)

    # ── report file output ────────────────────────────────────────────────────

    def test_run_reset_writes_report_json_to_output_dir(self):
        drop_calls: list = []
        fake_neo4j = self._make_fake_modules(
            nodes_deleted=2, relationships_deleted=1, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_report_write_test")
            with tempfile.TemporaryDirectory() as tmpdir:
                report = module.run_reset(
                    driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                    database="neo4j",
                    output_dir=Path(tmpdir),
                )
                report_path = Path(report["report_path"])
                self.assertTrue(report_path.exists(), "Report file should be written")
                data = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(data["deleted_nodes"], 2)
                self.assertEqual(data["target_database"], "neo4j")
                self.assertIn("demo_chunk_embedding_index", data["indexes_dropped"])

    def test_run_reset_no_report_file_when_output_dir_is_none(self):
        fake_neo4j = self._make_fake_modules()
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_no_report_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertNotIn("report_path", report)

    # ── demo_labels_deleted contract ──────────────────────────────────────────

    def test_run_reset_demo_labels_deleted_matches_constants(self):
        fake_neo4j = self._make_fake_modules()
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_labels_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        expected_labels = {
            "Document", "Chunk",
            "CanonicalEntity", "Claim", "Fact", "Relationship", "Source",
            "ExtractedClaim", "EntityMention",
            "UnresolvedEntity", "ResolvedEntityCluster",
        }
        self.assertEqual(set(report["demo_labels_deleted"]), expected_labels)

    def test_run_reset_delete_query_contains_all_demo_labels(self):
        """Cypher DELETE query must include every label in DEMO_NODE_LABELS."""
        eq_calls: list = []
        fake_neo4j = self._make_fake_modules(execute_query_calls=eq_calls)
        with self._inject_reset_modules(fake_neo4j):
            module = self._load_reset_module("reset_query_labels_test")
            module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        # Find the session object stored by the fake driver's session() call.
        sessions = [entry[1] for entry in eq_calls if entry[0] == "__session__"]
        self.assertTrue(sessions, "Expected at least one session to be created")
        delete_query = sessions[0].most_recent_query
        for label in (
            "Document", "Chunk",
            "CanonicalEntity", "Claim", "Fact", "Relationship", "Source",
            "ExtractedClaim", "EntityMention",
            "UnresolvedEntity", "ResolvedEntityCluster",
        ):
            self.assertIn(
                f"n:{label}", delete_query,
                f"Expected label '{label}' in the generated DELETE query",
            )

    # ── _validate_cypher_identifier ───────────────────────────────────────────

    def test_validate_cypher_identifier_accepts_valid_names(self):
        module = self._load_reset_module("reset_validate_ident_valid_test")
        for valid in ("demo_chunk_embedding_index", "MyIndex", "_index", "a1"):
            module._validate_cypher_identifier(valid, "index name")  # must not raise

    def test_validate_cypher_identifier_rejects_unsafe_names(self):
        module = self._load_reset_module("reset_validate_ident_unsafe_test")
        for unsafe in ("bad`index", "has space", "1starts_with_digit", "semi;colon"):
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {unsafe!r}"):
                module._validate_cypher_identifier(unsafe, "index name")

    def test_validate_cypher_identifier_rejects_non_string(self):
        module = self._load_reset_module("reset_validate_ident_nonstr_test")
        with self.assertRaises(ValueError):
            module._validate_cypher_identifier(123, "index name")  # type: ignore[arg-type]

    # ── run_demo.py reset command ──────────────────────────────────────────────

    def test_reset_command_without_confirm_prints_instructions(self):
        module = _load_module(RUN_DEMO_PATH, "run_reset_no_confirm_test")
        args = type(
            "Args",
            (),
            {
                "command": "reset",
                "confirm": False,
                "dry_run": False,
                "output_dir": DEMO_DIR / "artifacts",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "CHANGE_ME_BEFORE_USE",
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
                "question": None,
            },
        )()
        original_parse_args = module.parse_args
        try:
            module.parse_args = lambda: args
            with io.StringIO() as buffer, redirect_stdout(buffer):
                module.main()
                output = buffer.getvalue()
            self.assertIn("reset_demo_db.py --confirm", output)
            self.assertIn("--confirm", output)
        finally:
            module.parse_args = original_parse_args

    def test_reset_subcommand_accepts_confirm_flag(self):
        module = _load_module(RUN_DEMO_PATH, "run_reset_confirm_arg_test")
        args = module.parse_args(["reset", "--confirm"])
        self.assertEqual(args.command, "reset")
        self.assertTrue(args.confirm)

    def test_reset_subcommand_confirm_defaults_to_false(self):
        module = _load_module(RUN_DEMO_PATH, "run_reset_confirm_default_test")
        args = module.parse_args(["reset"])
        self.assertEqual(args.command, "reset")
        self.assertFalse(args.confirm)

    def test_reset_confirm_with_dry_run_raises_system_exit(self):
        """reset --confirm must refuse when --dry-run is in effect (the default)."""
        module = _load_module(RUN_DEMO_PATH, "run_reset_dry_run_guard_test")
        args = type(
            "Args",
            (),
            {
                "command": "reset",
                "confirm": True,
                "dry_run": True,
                "output_dir": DEMO_DIR / "artifacts",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_username": "neo4j",
                "neo4j_password": "testpassword",
                "neo4j_database": "neo4j",
                "openai_model": "gpt-4o-mini",
                "question": None,
            },
        )()
        original_parse_args = module.parse_args
        try:
            module.parse_args = lambda: args
            with self.assertRaises(SystemExit) as ctx:
                module.main()
            self.assertIn("--live", str(ctx.exception))
        finally:
            module.parse_args = original_parse_args

    def test_reset_command_warning_passthrough_to_stdout(self):
        """Regression: reset command must surface run_reset() warnings via print() to stdout.

        CLI UX intent: warnings returned by run_reset() (e.g. idempotent no-op
        notices) must appear inline in the terminal output with the
        "  warning:" prefix, not via logging.  If the print() call is removed
        or replaced with logging the warnings become invisible to CLI users.
        """
        module = _load_module(RUN_DEMO_PATH, "run_reset_warning_passthrough_test")
        import power_atlas.bootstrap.clients as bootstrap_clients
        args = types.SimpleNamespace(
            command="reset",
            confirm=True,
            dry_run=False,
            output_dir=None,
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testpassword",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
            question=None,
        )

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        # Stub run_reset to return a report containing warnings so that the
        # CLI passthrough code path (the print loop in main()) is exercised.
        stub_warnings = [
            "No demo-owned nodes found; graph may already be empty",
            "Index demo_chunk_embedding_index not found; already dropped",
        ]
        stub_report = {
            "target_database": "neo4j",
            "deleted_nodes": 0,
            "deleted_relationships": 0,
            "indexes_dropped": [],
            "indexes_not_found": ["demo_chunk_embedding_index"],
            "warnings": stub_warnings,
        }
        fake_reset_module = types.ModuleType("demo.reset_demo_db")
        fake_reset_module.run_reset = lambda **_kw: stub_report

        original_parse_args = module.parse_args
        original_reset_db = sys.modules.get("demo.reset_demo_db")
        original_driver = bootstrap_clients.neo4j.GraphDatabase.driver
        try:
            module.parse_args = lambda: args
            bootstrap_clients.neo4j.GraphDatabase.driver = lambda *_a, **_kw: _FakeDriver()
            sys.modules["demo.reset_demo_db"] = fake_reset_module

            with io.StringIO() as buffer, redirect_stdout(buffer):
                module.main()
                output = buffer.getvalue()

            # CLI UX: each warning must be printed with the "  warning:" prefix
            # so it appears inline with the reset completion summary.
            warning_lines = [
                line for line in output.splitlines() if line.startswith("  warning:")
            ]
            self.assertEqual(
                len(warning_lines),
                len(stub_warnings),
                f"Expected {len(stub_warnings)} '  warning:' lines in stdout but got {len(warning_lines)}",
            )
            expected_warning_lines = [
                f"  warning: {warning}" for warning in stub_warnings
            ]
            self.assertEqual(
                warning_lines,
                expected_warning_lines,
                "Expected each stub warning to be surfaced on its own stdout line "
                'with the exact "  warning: {warning}" format',
            )
        finally:
            module.parse_args = original_parse_args
            bootstrap_clients.neo4j.GraphDatabase.driver = original_driver
            if original_reset_db is None:
                sys.modules.pop("demo.reset_demo_db", None)
            else:
                sys.modules["demo.reset_demo_db"] = original_reset_db


if __name__ == "__main__":
    unittest.main()
