import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
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

    def test_run_pdf_ingest_non_dry_run_raises_not_implemented(self):
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
        with self.assertRaises(NotImplementedError):
            module._run_pdf_ingest(config)

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
        self.assertIn("blocked by [#150]", readme_text)
        self.assertIn("## Conceptual model", readme_text)
        self.assertIn("sequential independent runs", readme_text)
        self.assertIn("zoomlytics/power-atlas#151", readme_text)
        self.assertIn("non-destructive", readme_text)
        self.assertIsInstance(config, dict)
        self.assertIn("llm_config", config)
        self.assertIn("embedder_config", config)
        self.assertIn("from_pdf", config)
        self.assertEqual(config["llm_config"]["params_"]["model_name"]["var_"], "OPENAI_MODEL")
        self.assertEqual(config["embedder_config"]["params_"]["model"], "text-embedding-3-small")


if __name__ == "__main__":
    unittest.main()
