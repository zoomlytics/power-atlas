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
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name!r} from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
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

    def test_build_retriever_filters_skips_empty_values(self):
        module = _load_script_module("local_pdf_graphrag_filters_test")
        self.assertEqual(
            module._build_retriever_filters(corpus="power_atlas_demo", doc_type="all", document_path=""),
            {"corpus": "power_atlas_demo"},
        )
        self.assertEqual(
            module._build_retriever_filters(corpus="", doc_type="facts", document_path="/tmp/a.pdf"),
            {"doc_type": "facts", "document_path": "/tmp/a.pdf"},
        )

    def test_result_formatter_builds_deterministic_source_header_and_window(self):
        module = _load_script_module("local_pdf_graphrag_result_formatter_test")
        formatted = module._result_formatter(
            {
                "source_path": "/tmp/demo.pdf",
                "hit_chunk": 3,
                "similarity_score": 0.83,
                "hit_text": "hit body",
                "prev_chunk": 2,
                "prev_text": "prev body",
                "next_chunk": 4,
                "next_text": "next body",
            }
        )
        self.assertIn("[source: /tmp/demo.pdf | hitChunk: 3 | score: 0.83]", formatted.content)
        self.assertIn("[prev chunk: 2]\nprev body", formatted.content)
        self.assertIn("[hitChunk: 3 | score: 0.83]\nhit body", formatted.content)
        self.assertIn("[next chunk: 4]\nnext body", formatted.content)

    def test_rag_prompt_template_keeps_strict_citation_instruction(self):
        module = _load_script_module("local_pdf_graphrag_prompt_template_test")
        template = module.QA_PROMPT_TEMPLATE.template
        self.assertIn("Every bullet MUST end with a citation", template)
        self.assertIn("{context}", template)
        self.assertIn("{query_text}", template)
        self.assertIn("{examples}", template)

    def test_normalize_context_text_unescapes_common_sequences(self):
        module = _load_script_module("local_pdf_graphrag_normalize_test")
        normalized = module._normalize_context_text("line1\\nline2\\tcell\\r")
        self.assertEqual(normalized, "line1\nline2\tcell")
        normalized_quotes = module._normalize_context_text("\\\"quoted\\\" and \\\\ slash and \\u2192")
        self.assertEqual(normalized_quotes, "\"quoted\" and \\ slash and →")
        preserved_hex_escape = module._normalize_context_text("\\x1b[31mRed")
        self.assertEqual(preserved_hex_escape, "\\x1b[31mRed")
        sanitized_control = module._normalize_context_text("before\x1b[31mred")
        self.assertEqual(sanitized_control, "before[31mred")
        sanitized_controls = module._normalize_context_text("a\x01b\x7fc")
        self.assertEqual(sanitized_controls, "abc")

    def test_dedup_retrieved_items_removes_duplicate_contexts(self):
        module = _load_script_module("local_pdf_graphrag_dedupe_test")
        duplicate_content = "<Record content='[source: a.pdf | hitChunk: 1 | score: 0.9]\\nBody'>"
        unique_content = "<Record content='[source: b.pdf | hitChunk: 3 | score: 0.8]\\nBody'>"
        retriever_result = SimpleNamespace(
            items=[
                SimpleNamespace(content=duplicate_content),
                SimpleNamespace(content="[source: a.pdf | hitChunk: 1 | score: 0.9]\\nBody"),
                SimpleNamespace(content=unique_content),
            ]
        )
        removed, deduped = module._dedupe_retrieved_items(retriever_result)
        self.assertEqual(removed, 1)
        self.assertEqual(len(deduped), 2)

    def test_dedup_retrieved_items_removes_identical_wrapped_duplicates(self):
        module = _load_script_module("local_pdf_graphrag_dedupe_wrapped_test")
        wrapped = "<Record content='[source: a.pdf | hitChunk: 2 | score: 0.7]\\nBody'>"
        retriever_result = SimpleNamespace(items=[SimpleNamespace(content=wrapped), SimpleNamespace(content=wrapped)])
        removed, deduped = module._dedupe_retrieved_items(retriever_result)
        self.assertEqual(removed, 1)
        self.assertEqual(len(deduped), 1)


if __name__ == "__main__":
    unittest.main()
