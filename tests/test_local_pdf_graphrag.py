import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "retrieve"
    / "local_pdf_graphrag.py"
)


def _load_script_module(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class LocalPdfGraphRagScriptTests(unittest.TestCase):
    def test_build_query_params_supports_all_and_specific_doc_types(self):
        module = _load_script_module("local_pdf_graphrag_params_test")
        self.assertEqual(
            module._build_query_params(corpus="power_atlas_demo", doc_type="all", document_path=""),
            {"corpus": "power_atlas_demo", "doc_type": None, "document_path": None},
        )
        self.assertEqual(
            module._build_query_params(corpus="", doc_type="facts", document_path="/tmp/a.pdf"),
            {"corpus": None, "doc_type": "facts", "document_path": "/tmp/a.pdf"},
        )

    def test_build_query_params_rejects_invalid_doc_type(self):
        module = _load_script_module("local_pdf_graphrag_invalid_doc_type_test")
        with self.assertRaises(ValueError):
            module._build_query_params(corpus="", doc_type="memo", document_path="")

    def test_dedup_retrieved_items_removes_duplicate_contexts(self):
        module = _load_script_module("local_pdf_graphrag_dedupe_test")
        duplicate_content = "[source: a.pdf | hitChunk: 1 | score: 0.9]\\nBody"
        unique_content = "[source: b.pdf | hitChunk: 3 | score: 0.8]\\nBody"
        retriever_result = SimpleNamespace(
            items=[
                SimpleNamespace(content=duplicate_content),
                SimpleNamespace(content=duplicate_content),
                SimpleNamespace(content=unique_content),
            ]
        )
        removed, deduped = module._dedupe_retrieved_items(retriever_result)
        self.assertEqual(removed, 1)
        self.assertEqual(len(deduped), 2)


if __name__ == "__main__":
    unittest.main()
