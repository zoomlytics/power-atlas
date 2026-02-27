import importlib.util
import os
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "build_graph"
    / "simple_kg_builder_from_pdf.py"
)


def _load_script_module(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class SimpleKgBuilderFromPdfScriptTests(unittest.TestCase):
    def test_documents_and_metadata_are_configured_for_both_synthetic_pdfs(self):
        module = _load_script_module("simple_kg_builder_from_pdf_docs_test")
        files = {item["file_path"].name: item["document_metadata"] for item in module.DOCUMENTS_TO_INGEST}
        for item in module.DOCUMENTS_TO_INGEST:
            self.assertTrue(item["file_path"].is_absolute())
            self.assertEqual(item["file_path"], item["file_path"].resolve())

        self.assertEqual(
            files,
            {
                "power_atlas_factsheet.pdf": {
                    "corpus": "power_atlas_demo",
                    "doc_type": "facts",
                },
                "power_atlas_analyst_note.pdf": {
                    "corpus": "power_atlas_demo",
                    "doc_type": "narrative",
                },
            },
        )

    def test_schema_is_guided_and_not_free(self):
        module = _load_script_module("simple_kg_builder_from_pdf_schema_test")
        node_labels = {node.label for node in module.KG_SCHEMA.node_types}
        self.assertNotEqual(module.KG_SCHEMA, "FREE")
        self.assertTrue({"Person", "Organization", "Event"}.issubset(node_labels))

        for node in module.KG_SCHEMA.node_types:
            self.assertIn("name", {prop.name for prop in node.properties})

    def test_chunk_settings_honor_environment_variables(self):
        previous_chunk_size = os.environ.get("CHUNK_SIZE")
        previous_chunk_overlap = os.environ.get("CHUNK_OVERLAP")
        try:
            os.environ["CHUNK_SIZE"] = "256"
            os.environ["CHUNK_OVERLAP"] = "32"
            module = _load_script_module("simple_kg_builder_from_pdf_env_test")
            self.assertEqual(module.CHUNK_SIZE, 256)
            self.assertEqual(module.CHUNK_OVERLAP, 32)
        finally:
            if previous_chunk_size is None:
                os.environ.pop("CHUNK_SIZE", None)
            else:
                os.environ["CHUNK_SIZE"] = previous_chunk_size
            if previous_chunk_overlap is None:
                os.environ.pop("CHUNK_OVERLAP", None)
            else:
                os.environ["CHUNK_OVERLAP"] = previous_chunk_overlap


if __name__ == "__main__":
    unittest.main()
