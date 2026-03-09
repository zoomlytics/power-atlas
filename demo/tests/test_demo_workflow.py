import csv
import importlib.util
import io
import json
import os
import shutil
import types
import sys
import tempfile
import unittest
import warnings
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import yaml

from demo.contracts import PROMPT_IDS


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
        index_creator=None,
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
        fake_indexes = types.ModuleType("neo4j_graphrag.indexes")
        fake_indexes.create_vector_index = index_creator or (lambda *_args, **_kwargs: None)

        return {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.indexes": fake_indexes,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }

    @contextmanager
    def _with_injected_pdf_ingest_modules(self, injected_modules: dict[str, types.ModuleType]):
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        try:
            sys.modules.update(injected_modules)
            os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
            yield
        finally:
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
        with self.assertRaises(SystemExit):
            module.parse_args(["--dry-run", "ingest", "--live"])
        with self.assertRaises(SystemExit):
            module.parse_args(["--dry-run", "ingest", "--l"])

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
            self.assertIn("resolution_run_id", manifest["run_scopes"])
            self.assertEqual(
                set(manifest["stages"].keys()),
                {
                    "structured_ingest",
                    "pdf_ingest",
                    "claim_and_mention_extraction",
                    "entity_resolution",
                    "retrieval_and_qa",
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
                manifest["stages"]["entity_resolution"]["run_id"],
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

            with self._with_injected_modules({"neo4j": fake_neo4j}):
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
            original_fixtures_dir = module.FIXTURES_DIR
            try:
                module.FIXTURES_DIR = copied_fixtures
                result = module._lint_and_clean_structured_csvs("structured_ingest-test", output_dir)
            finally:
                module.FIXTURES_DIR = original_fixtures_dir

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
            original_fixtures_dir = module.FIXTURES_DIR
            try:
                module.FIXTURES_DIR = copied_fixtures
                result = module._lint_and_clean_structured_csvs("structured_ingest-test", output_dir)
            finally:
                module.FIXTURES_DIR = original_fixtures_dir

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
            original_fixtures_dir = module.FIXTURES_DIR
            try:
                module.FIXTURES_DIR = copied_fixtures
                with self.assertRaises(ValueError):
                    module._lint_and_clean_structured_csvs("structured_ingest-test", output_dir)
            finally:
                module.FIXTURES_DIR = original_fixtures_dir

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
            original_fixtures_dir = module.FIXTURES_DIR
            try:
                module.FIXTURES_DIR = copied_fixtures
                with self.assertRaises(ValueError):
                    module._lint_and_clean_structured_csvs("structured_ingest-test", output_dir)
            finally:
                module.FIXTURES_DIR = original_fixtures_dir

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
            original_fixtures_dir = module.FIXTURES_DIR
            try:
                module.FIXTURES_DIR = copied_fixtures
                with self.assertRaises(ValueError):
                    module._lint_and_clean_structured_csvs("structured_ingest-test", output_dir)
            finally:
                module.FIXTURES_DIR = original_fixtures_dir

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
            index_creator=lambda _driver, index_name, database_=None, **kwargs: calls.update(
                {"index_name": index_name, "index_kwargs": {"database_": database_, **kwargs}}
            ),
        )
        expected_fingerprint = module._sha256_file(
            DEMO_DIR / "fixtures" / "unstructured" / "chain_of_custody.pdf"
        )
        initial_openai_state = ("OPENAI_API_KEY" in os.environ, os.environ.get("OPENAI_API_KEY"))
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
            module._sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(
            result["pipeline_config_sha256"],
            module._sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(summary["embedding_model"], module.EMBEDDER_MODEL_NAME)
        self.assertEqual(result["vector_index"]["creation_strategy"], "neo4j_graphrag.indexes.create_vector_index")
        self.assertEqual(result["pipeline_result"], {"ok": True})
        self.assertEqual(result["provenance"]["dataset_id"], "demo_dataset_v1")
        self.assertEqual(calls["index_name"], "demo_chunk_embedding_index")
        self.assertEqual(calls["index_kwargs"]["label"], "Chunk")
        self.assertEqual(calls["index_kwargs"]["embedding_property"], "embedding")
        self.assertEqual(calls["index_kwargs"]["dimensions"], 1536)
        self.assertEqual(calls["index_kwargs"]["similarity_fn"], "cosine")
        self.assertEqual(calls["index_kwargs"]["database_"], "neo4j")
        self.assertEqual(
            calls["config_path"],
            str(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
        )
        self.assertEqual(
            calls["run_params"]["file_path"],
            str(DEMO_DIR / "fixtures" / "unstructured" / "chain_of_custody.pdf"),
        )
        expected_pdf_uri = (DEMO_DIR / "fixtures" / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
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
            expected_fingerprint = module._sha256_file(
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
                module._sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
            )
            self.assertEqual(summary["vector_index"]["creation_strategy"], "dry_run")
            self.assertEqual(result["pdf_fingerprint_sha256"], expected_fingerprint)
            self.assertEqual(
                result["pipeline_config_sha256"],
                module._sha256_file(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
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

    def test_run_pdf_ingest_non_dry_run_falls_back_to_cypher_index_creation(self):
        module = _load_module(RUN_DEMO_PATH, "run_non_dry_fallback_test")
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

        def _raise_index_error(*_args, **_kwargs):
            raise RuntimeError("index helper unavailable")

        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            query_payloads={
                "document_count": {"document_count": 1, "chunk_count": 2},
                "missing_chunk_order_count": {"missing_chunk_order_count": 0},
                "missing_embedding_count": {"missing_embedding_count": 0},
                "missing_page_count": {"missing_page_count": 0},
                "missing_char_offset_count": {"missing_char_offset_count": 0},
            },
            index_creator=_raise_index_error,
        )
        with self._with_injected_pdf_ingest_modules(injected_modules):
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")

        self.assertEqual(result["vector_index"]["creation_strategy"], "cypher_fallback")
        self.assertEqual(result["vector_index_fallback_reason"], "RuntimeError: index helper unavailable")
        self.assertTrue(
            any("CREATE VECTOR INDEX `demo_chunk_embedding_index` IF NOT EXISTS" in query for query, _ in calls["queries"])
        )

    def test_run_pdf_ingest_non_dry_run_rejects_unsafe_cypher_fallback_identifiers(self):
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
        def _raise_index_error(*_args, **_kwargs):
            raise RuntimeError("index helper unavailable")
        injected_modules = self._build_pdf_ingest_test_modules(
            calls=calls,
            index_creator=_raise_index_error,
        )
        original_identifiers = {
            "CHUNK_EMBEDDING_INDEX_NAME": module.CHUNK_EMBEDDING_INDEX_NAME,
            "CHUNK_EMBEDDING_LABEL": module.CHUNK_EMBEDDING_LABEL,
            "CHUNK_EMBEDDING_PROPERTY": module.CHUNK_EMBEDDING_PROPERTY,
        }
        try:
            with self._with_injected_pdf_ingest_modules(injected_modules):
                for attr_name, value, expected in [
                    ("CHUNK_EMBEDDING_INDEX_NAME", "bad`index", "Unsafe index name for Cypher fallback"),
                    ("CHUNK_EMBEDDING_LABEL", "Chunk:Bad", "Unsafe label for Cypher fallback"),
                    ("CHUNK_EMBEDDING_PROPERTY", "embedding`bad", "Unsafe property for Cypher fallback"),
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
            with self.assertRaises(SystemExit) as raised:
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

    def test_readme_documents_config_driven_pdf_ingest_and_chunk_index(self):
        readme_text = (DEMO_DIR / "README.md").read_text(encoding="utf-8")
        config_text = (DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml").read_text(encoding="utf-8")
        config = yaml.safe_load(config_text)
        self.assertIn(
            "demo/config/pdf_simple_kg_pipeline.yaml",
            readme_text,
        )
        self.assertIn(
            "vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py",
            readme_text,
        )
        self.assertIn("demo_chunk_embedding_index", readme_text)
        self.assertIn("NEO4J_USERNAME", readme_text)
        self.assertIn("create_vector_index.py", readme_text)
        self.assertIn("## Conceptual model", readme_text)
        self.assertIn("sequential independent runs", readme_text)
        self.assertIn("zoomlytics/power-atlas#151", readme_text)
        self.assertIn("run-scoped post-ingest normalization", readme_text)
        self.assertIn("non-destructive", readme_text)
        self.assertIsInstance(config, dict)
        self.assertIn("llm_config", config)
        self.assertIn("embedder_config", config)
        self.assertIn("neo4j_config", config)
        self.assertIn("from_pdf", config)
        self.assertIn("contract", config)
        neo4j_database_value = config.get("neo4j_database") or config.get("kg_writer", {}).get("params_", {}).get("neo4j_database")
        self.assertIsNotNone(neo4j_database_value)
        if isinstance(neo4j_database_value, dict):
            self.assertEqual(neo4j_database_value.get("var_"), "NEO4J_DATABASE")
        else:
            self.assertEqual(neo4j_database_value, "neo4j")
        self.assertEqual(config["llm_config"]["params_"]["model_name"]["var_"], "OPENAI_MODEL")
        self.assertEqual(config["embedder_config"]["params_"]["model"], "text-embedding-3-small")
        self.assertEqual(config["contract"]["chunk_embedding"]["dimensions"], 1536)

    def test_run_demo_warns_and_falls_back_when_pipeline_yaml_cannot_be_parsed(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: (_ for _ in ()).throw(yaml.YAMLError("bad yaml"))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                module = _load_module(RUN_DEMO_PATH, "run_yaml_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("Falling back to default chunk embedding contract" in str(w.message) for w in caught),
                "Expected warning when pipeline config cannot be parsed",
            )
        finally:
            yaml.safe_load = original_safe_load

    def test_run_demo_warns_and_falls_back_when_pipeline_yaml_top_level_is_not_mapping(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: []
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                module = _load_module(RUN_DEMO_PATH, "run_yaml_top_level_type_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("expected mapping at top-level" in str(w.message) for w in caught),
                "Expected warning when pipeline config top-level is not a mapping",
            )
        finally:
            yaml.safe_load = original_safe_load

    def test_run_demo_warns_and_falls_back_when_chunk_embedding_is_not_mapping(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: {"contract": {"chunk_embedding": []}}
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                module = _load_module(RUN_DEMO_PATH, "run_chunk_contract_type_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "demo_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("contract.chunk_embedding" in str(w.message) for w in caught),
                "Expected warning when chunk embedding contract is not a mapping",
            )
        finally:
            yaml.safe_load = original_safe_load


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
    ) -> tuple[types.ModuleType, types.ModuleType]:
        """Return (fake_neo4j, fake_neo4j_graphrag_indexes) for reset tests."""
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

        class _FakeSession:
            def __init__(self, nodes: int, rels: int) -> None:
                self._nodes = nodes
                self._rels = rels

            def __enter__(self) -> "_FakeSession":
                return self

            def __exit__(self, *_) -> bool:
                return False

            def run(self, query: str, **_kwargs) -> _FakeResult:
                return _FakeResult(self._nodes, self._rels)

        _index_exists_value = index_exists

        class _FakeExecuteQueryResult:
            def __init__(self, cnt: int) -> None:
                self.records = [{"cnt": cnt}]

        class _FakeDriver:
            def __enter__(self) -> "_FakeDriver":
                return self

            def __exit__(self, *_) -> bool:
                return False

            def session(self, **kwargs) -> _FakeSession:
                return _FakeSession(nodes_deleted, relationships_deleted)

            def execute_query(self, query: str, params: dict, database_: str = "neo4j") -> _FakeExecuteQueryResult:
                # `database_` with trailing underscore matches neo4j.Driver.execute_query's
                # real keyword argument name, which uses the trailing underscore to avoid
                # shadowing the built-in `database` name.
                execute_query_calls.append((query, params, database_))
                cnt = 1 if _index_exists_value else 0
                return _FakeExecuteQueryResult(cnt)

        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = types.SimpleNamespace(
            driver=lambda *_a, **_kw: _FakeDriver()
        )

        fake_indexes = types.ModuleType("neo4j_graphrag.indexes")
        fake_indexes.drop_index_if_exists = lambda driver, name, neo4j_database=None: drop_calls.append(name)

        return fake_neo4j, fake_indexes

    @contextmanager
    def _inject_reset_modules(self, fake_neo4j, fake_indexes):
        names = ["neo4j", "neo4j_graphrag.indexes"]
        originals = {n: sys.modules.get(n) for n in names}
        try:
            sys.modules["neo4j"] = fake_neo4j
            sys.modules["neo4j_graphrag.indexes"] = fake_indexes
            yield
        finally:
            for n, orig in originals.items():
                if orig is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = orig

    def _load_reset_module(self, name: str = "reset_db_test"):
        reset_path = DEMO_DIR / "reset_demo_db.py"
        return _load_module(reset_path, name)

    # ── run_reset report structure ────────────────────────────────────────────

    def test_run_reset_returns_report_with_expected_keys(self):
        drop_calls: list = []
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=5, relationships_deleted=3, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
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
            "indexes_dropped",
            "indexes_not_found",
            "warnings",
            "idempotent",
        }
        self.assertTrue(required_keys.issubset(report.keys()), f"Missing keys: {required_keys - report.keys()}")

    def test_run_reset_returns_correct_counts_when_nodes_and_index_exist(self):
        drop_calls: list = []
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=7, relationships_deleted=4, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
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
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=2, relationships_deleted=1, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
            module = self._load_reset_module("reset_index_dropped_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertIn("demo_chunk_embedding_index", report["indexes_dropped"])
        self.assertEqual(report["indexes_not_found"], [])
        self.assertEqual(drop_calls, ["demo_chunk_embedding_index"])

    # ── idempotent no-op paths ────────────────────────────────────────────────

    def test_run_reset_idempotent_when_graph_empty_and_index_absent(self):
        drop_calls: list = []
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=0, relationships_deleted=0, index_exists=False, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
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
        # Expect one warning for the empty graph and one for the absent index.
        self.assertTrue(
            any("already empty" in w for w in report["warnings"]),
            "Expected a warning about graph already being empty",
        )
        self.assertTrue(
            any("demo_chunk_embedding_index" in w and "not found" in w for w in report["warnings"]),
            "Expected a warning about the index not being found",
        )
        self.assertEqual(drop_calls, [], "No drop call expected when index is absent")

    def test_run_reset_idempotent_flag_false_when_nodes_deleted(self):
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=1, relationships_deleted=0, index_exists=False
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
            module = self._load_reset_module("reset_idempotent_nodes_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertFalse(report["idempotent"])

    def test_run_reset_idempotent_flag_false_when_index_dropped(self):
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=0, relationships_deleted=0, index_exists=True
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
            module = self._load_reset_module("reset_idempotent_index_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertFalse(report["idempotent"])
        self.assertIn("demo_chunk_embedding_index", report["indexes_dropped"])

    # ── report file output ────────────────────────────────────────────────────

    def test_run_reset_writes_report_json_to_output_dir(self):
        drop_calls: list = []
        fake_neo4j, fake_indexes = self._make_fake_modules(
            nodes_deleted=2, relationships_deleted=1, index_exists=True, drop_calls=drop_calls
        )
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
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
        fake_neo4j, fake_indexes = self._make_fake_modules()
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
            module = self._load_reset_module("reset_no_report_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        self.assertNotIn("report_path", report)

    # ── demo_labels_deleted contract ──────────────────────────────────────────

    def test_run_reset_demo_labels_deleted_matches_constants(self):
        fake_neo4j, fake_indexes = self._make_fake_modules()
        with self._inject_reset_modules(fake_neo4j, fake_indexes):
            module = self._load_reset_module("reset_labels_test")
            report = module.run_reset(
                driver=fake_neo4j.GraphDatabase.driver("neo4j://localhost:7687"),
                database="neo4j",
                output_dir=None,
            )

        expected_labels = {"Document", "Chunk", "Claim", "CanonicalEntity", "EntityMention"}
        self.assertEqual(set(report["demo_labels_deleted"]), expected_labels)

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


if __name__ == "__main__":
    unittest.main()
