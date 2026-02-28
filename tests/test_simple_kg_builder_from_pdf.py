import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "build_graph"
    / "simple_kg_builder_from_pdf.py"
)


def _load_script_module(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name!r} from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
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
        self.assertTrue(hasattr(module.KG_SCHEMA, "node_types"))
        self.assertTrue(
            {
                "Person",
                "Organization",
                "Event",
                "FactSheet",
                "AnalystNote",
            }.issubset(node_labels)
        )

        for node in module.KG_SCHEMA.node_types:
            property_names = {prop.name for prop in node.properties}
            for prop in node.properties:
                self.assertIsInstance(prop, module.PropertyType)
            if node.label == "FactSheet":
                self.assertIn("firm_name", property_names)
            elif node.label == "AnalystNote":
                self.assertIn("subject", property_names)
            else:
                self.assertIn("name", property_names)

    def test_entity_resolution_uses_label_specific_properties(self):
        module = _load_script_module("simple_kg_builder_from_pdf_resolution_test")
        expected = {
            "Person": "name",
            "Organization": "name",
            "Event": "name",
            "FactSheet": "firm_name",
            "AnalystNote": "subject",
        }
        self.assertEqual(module.ENTITY_RESOLUTION_PROPERTY_BY_LABEL, expected)

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

    def test_chunk_preparation_keeps_deterministic_ids_and_provenance(self):
        module = _load_script_module("simple_kg_builder_from_pdf_chunk_prep")
        document_path = "/tmp/doc.pdf"
        document_info = module.DocumentInfo(
            path=document_path,
            metadata={"corpus": "demo", "doc_type": "facts"},
            uid=document_path,
            document_type="facts",
        )
        chunks = module.TextChunks(
            chunks=[
                module.TextChunk(text="a", index=0),
                module.TextChunk(text="b", index=1),
            ]
        )
        prepared = module._prepare_chunks_for_document(chunks, document_info)
        self.assertEqual(
            [chunk.uid for chunk in prepared.chunks],
            [f"{document_path}:0", f"{document_path}:1"],
        )
        for chunk in prepared.chunks:
            self.assertEqual(
                chunk.metadata.get(module.DOCUMENT_PATH_PROPERTY), document_path
            )
            self.assertEqual(chunk.metadata.get("corpus"), "demo")
            self.assertEqual(chunk.metadata.get("doc_type"), "facts")
            # Keep chunk ids in metadata so Neo4jChunkReader can round-trip them.
            self.assertEqual(
                chunk.metadata.get(module.LEXICAL_GRAPH_CONFIG.chunk_id_property),
                chunk.uid,
            )

    def test_document_scoped_filter_query_uses_provenance_pattern(self):
        module = _load_script_module("simple_kg_builder_from_pdf_filter_query_test")
        query = module._build_document_scoped_filter_query(
            ["/tmp/b.pdf", "/tmp/a.pdf"], "Person"
        )
        self.assertIn("WHERE entity:Person", query)
        self.assertIn(
            "(entity)-[:FROM_CHUNK]->(:Chunk)-[:FROM_DOCUMENT]->(doc:Document)", query
        )
        self.assertIn('doc.path IN ["/tmp/a.pdf", "/tmp/b.pdf"]', query)

    def test_reset_document_derived_graph_calls_entity_then_lexical_reset(self):
        module = _load_script_module("simple_kg_builder_from_pdf_reset_combo_test")
        driver = object()
        call_order = []
        with (
            patch.object(module, "reset_document_entity_graph") as entity_reset,
            patch.object(module, "reset_document_lexical_graph") as lexical_reset,
        ):
            entity_reset.side_effect = lambda *args, **kwargs: call_order.append(
                "entity"
            )
            lexical_reset.side_effect = lambda *args, **kwargs: call_order.append(
                "lexical"
            )
            module.reset_document_derived_graph(
                neo4j_driver=driver, document_path="/tmp/doc.pdf"
            )
        entity_reset.assert_called_once_with(driver, "/tmp/doc.pdf")
        lexical_reset.assert_called_once_with(driver, "/tmp/doc.pdf")
        self.assertEqual(call_order, ["entity", "lexical"])


if __name__ == "__main__":
    unittest.main()
