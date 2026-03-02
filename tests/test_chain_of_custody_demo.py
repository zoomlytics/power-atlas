import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


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
            self.assertEqual(
                set(manifest["stages"].keys()),
                {
                    "structured_ingest",
                    "pdf_ingest",
                    "claim_and_mention_extraction",
                    "retrieval_and_qa",
                },
            )
            self.assertEqual(manifest["stages"]["structured_ingest"]["claims"], 2)

    def test_fixture_manifest_tracks_dataset_and_provenance(self):
        fixture_manifest = DEMO_DIR / "fixtures" / "manifest.json"
        data = json.loads(fixture_manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["dataset"], "chain_of_custody_dataset_v1")
        self.assertGreaterEqual(len(data["provenance"]), 2)

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


if __name__ == "__main__":
    unittest.main()
