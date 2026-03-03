import csv
import importlib.util
import io
import json
import os
import types
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path

import yaml


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo" / "chain_of_custody"
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


class ChainOfCustodyDemoTests(unittest.TestCase):
    def test_parse_args_supports_expected_subcommands(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_parse_args_test")
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
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_main_reset_test")
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
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = module.run_demo(
                module.DemoConfig(
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
        self.assertEqual(data["dataset"], "chain_of_custody_dataset_v1")
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

    def test_run_pdf_ingest_non_dry_run_executes_config_pipeline_and_provenance_flow(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_non_dry_test")
        config = module.DemoConfig(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}

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
                if "document_count" in query and "chunk_count" in query:
                    return _FakeResult({"document_count": 1, "chunk_count": 2})
                if "missing_chunk_order_count" in query:
                    return _FakeResult({"missing_chunk_order_count": 0})
                if "missing_embedding_count" in query:
                    return _FakeResult({"missing_embedding_count": 0})
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
                return {"ok": True}

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
        fake_indexes.create_vector_index = lambda _driver, index_name, database_=None, **kwargs: calls.update(
            {"index_name": index_name, "index_kwargs": {"database_": database_, **kwargs}}
        )

        injected_modules = {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.indexes": fake_indexes,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
        original_env = {
            key: (key in os.environ, os.environ.get(key))
            for key in (
                "NEO4J_URI",
                "NEO4J_USERNAME",
                "NEO4J_PASSWORD",
                "NEO4J_DATABASE",
                "OPENAI_MODEL",
                "OPENAI_API_KEY",
            )
        }
        try:
            sys.modules.update(injected_modules)
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(result["status"], "live")
        self.assertEqual(result["vector_index"]["creation_strategy"], "neo4j_graphrag.indexes.create_vector_index")
        self.assertEqual(calls["index_name"], "chain_custody_chunk_embedding_index")
        self.assertEqual(calls["index_kwargs"]["label"], "Chunk")
        self.assertEqual(calls["index_kwargs"]["embedding_property"], "embedding")
        self.assertEqual(calls["index_kwargs"]["dimensions"], 1536)
        self.assertEqual(calls["index_kwargs"]["similarity_fn"], "cosine")
        self.assertEqual(calls["index_kwargs"]["database_"], "neo4j")
        try:
            self.assertEqual(
                calls["config_path"],
                str(DEMO_DIR / "config" / "pdf_simple_kg_pipeline.yaml"),
            )
            self.assertEqual(
                calls["run_params"]["file_path"],
                str(DEMO_DIR / "fixtures" / "unstructured" / "chain_of_custody.pdf"),
            )
            self.assertNotIn("pdf_loader", calls["run_params"])
            self.assertTrue(
                any("SET d.run_id" in query for query, _ in calls.get("queries", [])),
                "Expected post-ingest provenance query to run",
            )
            normalized_query = next(query for query, _ in calls["queries"] if "SET d.run_id" in query)
            self.assertIn("d.run_id IS NULL OR d.run_id = $run_id", normalized_query)
            self.assertNotIn("id(c)", normalized_query)
            self.assertTrue(
                any(
                    "document_count" in query and "chunk_count" in query
                    for query, _ in calls["queries"]
                )
            )
            restored_env = {key: (key in os.environ, os.environ.get(key)) for key in original_env}
            self.assertEqual(restored_env, original_env)
        finally:
            if had_openai_api_key:
                os.environ["OPENAI_API_KEY"] = original_openai_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_run_pdf_ingest_non_dry_run_falls_back_to_cypher_index_creation(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_non_dry_fallback_test")
        config = module.DemoConfig(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )
        calls: dict[str, object] = {}

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
                if "document_count" in query and "chunk_count" in query:
                    return _FakeResult({"document_count": 1, "chunk_count": 2})
                if "missing_chunk_order_count" in query:
                    return _FakeResult({"missing_chunk_order_count": 0})
                if "missing_embedding_count" in query:
                    return _FakeResult({"missing_embedding_count": 0})
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
                return {"ok": True}

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

        def _raise_index_error(*_args, **_kwargs):
            raise RuntimeError("index helper unavailable")

        fake_indexes.create_vector_index = _raise_index_error

        injected_modules = {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.indexes": fake_indexes,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        try:
            sys.modules.update(injected_modules)
            os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
            result = module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
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

        self.assertEqual(result["vector_index"]["creation_strategy"], "cypher_fallback")
        self.assertEqual(result["vector_index_fallback_reason"], "RuntimeError: index helper unavailable")
        self.assertTrue(
            any("CREATE VECTOR INDEX `chain_custody_chunk_embedding_index` IF NOT EXISTS" in query for query, _ in calls["queries"])
        )

    def test_run_pdf_ingest_non_dry_run_rejects_unsafe_cypher_fallback_identifiers(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_non_dry_unsafe_identifier_test")
        config = module.DemoConfig(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
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

            def single(self):
                return {}

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
                return _FakeSession()

        class _FakePipeline:
            async def run(self, params):
                return {"ok": True}

        class _FakePipelineRunner:
            @staticmethod
            def from_config_file(path):
                return _FakePipeline()

        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *_args, **_kwargs: _FakeDriver())
        fake_runner = types.ModuleType("neo4j_graphrag.experimental.pipeline.config.runner")
        fake_runner.PipelineRunner = _FakePipelineRunner
        fake_indexes = types.ModuleType("neo4j_graphrag.indexes")
        def _raise_index_error(*_args, **_kwargs):
            raise RuntimeError("index helper unavailable")
        fake_indexes.create_vector_index = _raise_index_error

        injected_modules = {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.indexes": fake_indexes,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        original_identifiers = {
            "CHUNK_EMBEDDING_INDEX_NAME": module.CHUNK_EMBEDDING_INDEX_NAME,
            "CHUNK_EMBEDDING_LABEL": module.CHUNK_EMBEDDING_LABEL,
            "CHUNK_EMBEDDING_PROPERTY": module.CHUNK_EMBEDDING_PROPERTY,
        }
        try:
            sys.modules.update(injected_modules)
            os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
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
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            if had_openai_api_key:
                os.environ["OPENAI_API_KEY"] = original_openai_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_run_pdf_ingest_non_dry_run_raises_when_no_run_scoped_documents_or_chunks(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_non_dry_missing_nodes_test")
        config = module.DemoConfig(
            dry_run=False,
            output_dir=DEMO_DIR / "artifacts",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            openai_model="gpt-4o-mini",
        )

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
                if "document_count" in query and "chunk_count" in query:
                    return _FakeResult({"document_count": 0, "chunk_count": 0})
                return _FakeResult()

        class _FakeDriver:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def session(self, **kwargs):
                return _FakeSession()

        class _FakePipeline:
            async def run(self, params):
                return {"ok": True}

        class _FakePipelineRunner:
            @staticmethod
            def from_config_file(path):
                return _FakePipeline()

        fake_neo4j = types.ModuleType("neo4j")
        fake_neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *_args, **_kwargs: _FakeDriver())
        fake_runner = types.ModuleType("neo4j_graphrag.experimental.pipeline.config.runner")
        fake_runner.PipelineRunner = _FakePipelineRunner
        fake_indexes = types.ModuleType("neo4j_graphrag.indexes")
        fake_indexes.create_vector_index = lambda *_args, **_kwargs: None

        injected_modules = {
            "neo4j": fake_neo4j,
            "neo4j_graphrag.indexes": fake_indexes,
            "neo4j_graphrag.experimental.pipeline.config.runner": fake_runner,
        }
        originals = {name: sys.modules.get(name) for name in injected_modules}
        had_openai_api_key = "OPENAI_API_KEY" in os.environ
        original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        try:
            sys.modules.update(injected_modules)
            os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
            with self.assertRaisesRegex(
                ValueError,
                "expected at least one Document and Chunk for this run",
            ):
                module._run_pdf_ingest(config, run_id="unstructured_ingest-test")
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

    def test_run_pdf_ingest_non_dry_run_requires_openai_api_key(self):
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_non_dry_requires_openai_key_test")
        config = module.DemoConfig(
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
        module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_independent_test")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = module.DemoConfig(
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
                smoke_module = _load_module(SMOKE_TEST_PATH, "chain_of_custody_smoke_test_module")
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
            "demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml",
            readme_text,
        )
        self.assertIn(
            "vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py",
            readme_text,
        )
        self.assertIn("chain_custody_chunk_embedding_index", readme_text)
        self.assertIn("vendor examples use `NEO4J_USER`", readme_text)
        self.assertIn("config_url.json", readme_text)
        self.assertIn("simple_kg_pipeline_config_url.json", readme_text)
        self.assertIn("simple_kg_builder_from_pdf.py", readme_text)
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
        self.assertIn("demo_contract", config)
        self.assertIn("neo4j_database", config)
        self.assertEqual(config["neo4j_database"]["var_"], "NEO4J_DATABASE")
        self.assertEqual(config["llm_config"]["params_"]["model_name"]["var_"], "OPENAI_MODEL")
        self.assertEqual(config["embedder_config"]["params_"]["model"], "text-embedding-3-small")
        self.assertEqual(config["demo_contract"]["chunk_embedding"]["dimensions"], 1536)

    def test_run_demo_warns_and_falls_back_when_pipeline_yaml_cannot_be_parsed(self):
        original_safe_load = yaml.safe_load
        try:
            yaml.safe_load = lambda *_args, **_kwargs: (_ for _ in ()).throw(yaml.YAMLError("bad yaml"))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                module = _load_module(RUN_DEMO_PATH, "chain_of_custody_run_demo_yaml_warn_test")
            self.assertEqual(module.CHUNK_EMBEDDING_INDEX_NAME, "chain_custody_chunk_embedding_index")
            self.assertEqual(module.CHUNK_EMBEDDING_LABEL, "Chunk")
            self.assertEqual(module.CHUNK_EMBEDDING_PROPERTY, "embedding")
            self.assertEqual(module.CHUNK_EMBEDDING_DIMENSIONS, 1536)
            self.assertTrue(
                any("Falling back to default chunk embedding contract" in str(w.message) for w in caught),
                "Expected warning when pipeline config cannot be parsed",
            )
        finally:
            yaml.safe_load = original_safe_load


if __name__ == "__main__":
    unittest.main()
