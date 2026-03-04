import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path


PROVENANCE_WRITER_PATH = Path(__file__).resolve().parents[1] / "demo" / "chain_of_custody" / "provenance_writer.py"


@contextmanager
def _with_injected_modules(injected: dict[str, types.ModuleType]):
    originals = {name: sys.modules.get(name) for name in injected}
    try:
        sys.modules.update(injected)
        yield
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _load_provenance_writer():
    class _FakeNeo4jWriter:
        def __init__(self, *args, **kwargs):
            self._init_args = (args, kwargs)

        async def run(self, graph, lexical_graph_config=None):
            return {"graph": graph, "config": lexical_graph_config}

    fake_neo4j = types.ModuleType("neo4j")
    fake_neo4j.Driver = object

    fake_types = types.ModuleType("neo4j_graphrag.experimental.components.types")

    class LexicalGraphConfig:
        def __init__(
            self,
            document_node_label: str = "Document",
            chunk_node_label: str = "Chunk",
            chunk_to_document_relationship_type: str = "FROM_DOCUMENT",
        ):
            self.document_node_label = document_node_label
            self.chunk_node_label = chunk_node_label
            self.chunk_to_document_relationship_type = chunk_to_document_relationship_type

    class Node:
        def __init__(self, id: str, label: str, properties: dict | None = None):
            self.id = id
            self.label = label
            self.properties = properties or {}

    class Relationship:
        def __init__(self, start_node_id: str, end_node_id: str, type: str):
            self.start_node_id = start_node_id
            self.end_node_id = end_node_id
            self.type = type

    class Neo4jGraph:
        def __init__(self, nodes=None, relationships=None):
            self.nodes = list(nodes or [])
            self.relationships = list(relationships or [])

    fake_types.LexicalGraphConfig = LexicalGraphConfig
    fake_types.Node = Node
    fake_types.Relationship = Relationship
    fake_types.Neo4jGraph = Neo4jGraph

    fake_kg_writer = types.ModuleType("neo4j_graphrag.experimental.components.kg_writer")
    fake_kg_writer.Neo4jWriter = _FakeNeo4jWriter
    fake_kg_writer.KGWriterModel = dict

    fake_context = types.ModuleType("neo4j_graphrag.experimental.pipeline.types.context")
    fake_context.RunContext = object

    fake_pydantic = types.ModuleType("pydantic")

    def _validate_call(func=None, **_kwargs):
        return func

    fake_pydantic.validate_call = _validate_call

    # Mark parent modules as packages by setting __path__
    fake_graphrag = types.ModuleType("neo4j_graphrag")
    fake_graphrag.__path__ = []

    fake_graphrag_experimental = types.ModuleType("neo4j_graphrag.experimental")
    fake_graphrag_experimental.__path__ = []

    fake_components = types.ModuleType("neo4j_graphrag.experimental.components")
    fake_components.__path__ = []

    fake_pipeline = types.ModuleType("neo4j_graphrag.experimental.pipeline")
    fake_pipeline.__path__ = []

    fake_pipeline_types = types.ModuleType("neo4j_graphrag.experimental.pipeline.types")
    fake_pipeline_types.__path__ = []

    injected = {
        "neo4j": fake_neo4j,
        "neo4j_graphrag": fake_graphrag,
        "neo4j_graphrag.experimental": fake_graphrag_experimental,
        "neo4j_graphrag.experimental.components": fake_components,
        "neo4j_graphrag.experimental.components.kg_writer": fake_kg_writer,
        "neo4j_graphrag.experimental.components.types": fake_types,
        "neo4j_graphrag.experimental.pipeline": fake_pipeline,
        "neo4j_graphrag.experimental.pipeline.types": fake_pipeline_types,
        "neo4j_graphrag.experimental.pipeline.types.context": fake_context,
        "pydantic": fake_pydantic,
    }

    with _with_injected_modules(injected):
        spec = importlib.util.spec_from_file_location("provenance_writer", PROVENANCE_WRITER_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import {PROVENANCE_WRITER_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, fake_types


def test_apply_provenance_prefers_document_metadata_and_propagates_to_chunks():
    module, fake_types = _load_provenance_writer()
    ProvenanceNeo4jWriter = module.ProvenanceNeo4jWriter
    LexicalGraphConfig = fake_types.LexicalGraphConfig
    Node = fake_types.Node
    Relationship = fake_types.Relationship
    Neo4jGraph = fake_types.Neo4jGraph

    config = LexicalGraphConfig(
        document_node_label="Document",
        chunk_node_label="Chunk",
        chunk_to_document_relationship_type="FROM_DOCUMENT",
    )
    doc1 = Node(
        "d1",
        "Document",
        {
            "metadata": {"run_id": "stage-run", "dataset_id": "doc-ds", "source_uri": "doc-src"},
            "path": "ignored-path",
        },
    )
    doc2 = Node("d2", "Document", {"path": "file:///doc2.pdf"})
    chunk1 = Node("c1", "Chunk", {})
    chunk2 = Node("c2", "Chunk", {})
    chunk3 = Node("c3", "Chunk", {})
    rel1 = Relationship("c1", "d1", "FROM_DOCUMENT")
    rel2 = Relationship("c2", "d2", "FROM_DOCUMENT")
    graph = Neo4jGraph(nodes=[doc1, doc2, chunk1, chunk2, chunk3], relationships=[rel1, rel2])

    writer = ProvenanceNeo4jWriter(driver=None, dataset_id="writer-ds")
    writer._apply_provenance(graph=graph, lexical_graph_config=config, run_id=None)

    assert doc1.properties["run_id"] == "stage-run"
    assert doc1.properties["dataset_id"] == "doc-ds"
    assert doc1.properties["source_uri"] == "doc-src"

    assert doc2.properties.get("run_id") is None
    assert doc2.properties["dataset_id"] == "writer-ds"
    assert doc2.properties["source_uri"] == "file:///doc2.pdf"

    assert chunk1.properties["run_id"] == "stage-run"
    assert chunk1.properties["dataset_id"] == "doc-ds"
    assert chunk1.properties["source_uri"] == "doc-src"

    assert chunk2.properties.get("run_id") is None
    assert chunk2.properties["dataset_id"] == "writer-ds"
    assert chunk2.properties["source_uri"] == "file:///doc2.pdf"

    assert chunk3.properties["dataset_id"] == "writer-ds"
    assert "run_id" not in chunk3.properties
    assert "source_uri" not in chunk3.properties
