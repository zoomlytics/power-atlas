import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo" / "chain_of_custody"
RUN_DEMO_PATH = DEMO_DIR / "run_demo.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ChainOfCustodyDemoTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
