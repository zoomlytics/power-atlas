"""Canonical KG+RAG demo using a two-pipeline pattern.

Pipeline A (lexical): builds the lexical graph only (Document + Chunk, embeddings).
Pipeline B (entity): reads chunks from Neo4j and extracts the entity graph with
`create_lexical_graph=False`, reusing the stored lexical graph. Either pipeline can
be re-run independently via environment flags to align with the upstream vendor
example: `text_to_lexical_graph_to_entity_graph_two_pipelines.py`.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Iterable

import logging
import neo4j
from dotenv import load_dotenv
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.experimental.components.embedder import TextChunkEmbedder
from neo4j_graphrag.experimental.components.entity_relation_extractor import (
    LLMEntityRelationExtractor,
)
from neo4j_graphrag.experimental.components.kg_writer import Neo4jWriter
from neo4j_graphrag.experimental.components.lexical_graph import LexicalGraphBuilder
from neo4j_graphrag.experimental.components.neo4j_reader import Neo4jChunkReader
from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    NodeType,
    Pattern,
    PropertyType,
    RelationshipType,
    SchemaBuilder,
)
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
    FixedSizeSplitter,
)
from neo4j_graphrag.experimental.components.types import (
    DocumentInfo,
    LexicalGraphConfig,
    Neo4jNode,
    TextChunk,
    TextChunks,
)
from neo4j_graphrag.experimental.pipeline.pipeline import PipelineResult
from neo4j_graphrag.llm import LLMInterface
from neo4j_graphrag.llm import OpenAILLM
try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
except ImportError:  # optional dependency
    class PdfReadError(RuntimeError):
        """Raised when attempting to read PDFs without the optional pypdf dependency."""

    def PdfReader(*args, **kwargs):  # type: ignore
        raise RuntimeError(
            "The 'pypdf' package is required to load PDF files in this example. "
            "Install it with `pip install pypdf`, or disable the lexical pipeline."
        )

logger = logging.getLogger(__name__)

load_dotenv()

# Chunking knobs (env overrides supported)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
APPROXIMATE = os.getenv("CHUNK_APPROXIMATE", "true").lower() == "true"

text_splitter = FixedSizeSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    approximate=APPROXIMATE,
)

# Shared property keys for provenance
DOCUMENT_PATH_PROPERTY = "document_path"

# Neo4j db infos
URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "testtesttest")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
AUTH = (USERNAME, PASSWORD)

# Pipeline toggles (lexical/entity can be run independently)
RUN_LEXICAL_PIPELINE = os.getenv("RUN_LEXICAL_PIPELINE", "true").lower() == "true"
RUN_ENTITY_PIPELINE = os.getenv("RUN_ENTITY_PIPELINE", "true").lower() == "true"
RESET_LEXICAL_GRAPH = os.getenv("RESET_LEXICAL_GRAPH", "true").lower() == "true"
RESET_ENTITY_GRAPH = os.getenv("RESET_ENTITY_GRAPH", "false").lower() == "true"

root_dir = Path(__file__).resolve().parents[1]
DOCUMENTS_TO_INGEST = (
    {
        "file_path": (root_dir / "data" / "power_atlas_factsheet.pdf").resolve(),
        "document_metadata": {"corpus": "power_atlas_demo", "doc_type": "facts"},
    },
    {
        "file_path": (root_dir / "data" / "power_atlas_analyst_note.pdf").resolve(),
        "document_metadata": {"corpus": "power_atlas_demo", "doc_type": "narrative"},
    },
)

# Keep labels and properties aligned with vendor defaults so Neo4jChunkReader can
# round-trip chunk ids and provenance relationships (FROM_CHUNK, FROM_DOCUMENT).
LEXICAL_GRAPH_CONFIG = LexicalGraphConfig()

KG_SCHEMA = GraphSchema(
    node_types=(
        NodeType(
            label="Person",
            description="A named individual mentioned in the document.",
            properties=(
                PropertyType(
                    name="name",
                    type="STRING",
                    description="Full name of the person.",
                    required=True,
                ),
            ),
            additional_properties=True,
        ),
        NodeType(
            label="Organization",
            description="An organization, company, or institution.",
            properties=(
                PropertyType(
                    name="name",
                    type="STRING",
                    description="Official organization name.",
                    required=True,
                ),
            ),
            additional_properties=True,
        ),
        NodeType(
            label="Event",
            description="A notable event referenced in the document.",
            properties=(
                PropertyType(
                    name="name",
                    type="STRING",
                    description="Canonical event name.",
                    required=True,
                ),
            ),
            additional_properties=True,
        ),
    ),
    relationship_types=(
        RelationshipType(
            label="RELATED_TO",
            description="General relationship between extracted entities.",
            properties=(),
            additional_properties=True,
        ),
    ),
    patterns=(
        Pattern(source="Person", relationship="RELATED_TO", target="Person"),
        Pattern(source="Person", relationship="RELATED_TO", target="Organization"),
        Pattern(source="Person", relationship="RELATED_TO", target="Event"),
        Pattern(source="Organization", relationship="RELATED_TO", target="Organization"),
        Pattern(source="Organization", relationship="RELATED_TO", target="Event"),
    ),
    additional_node_types=True,
    additional_relationship_types=True,
    additional_patterns=True,
)


def _load_pdf_text(file_path: Path) -> str:
    try:
        reader = PdfReader(str(file_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except (PdfReadError, FileNotFoundError, OSError) as exc:  # pragma: no cover
        raise RuntimeError(
            f"Failed to read PDF at {file_path}: {type(exc).__name__}"
        ) from exc


def _prepare_chunks_for_document(
    chunks: TextChunks, document_info: DocumentInfo
) -> TextChunks:
    """Ensure each chunk carries a stable chunk id + document provenance properties.

    Chunk ids are deterministic per (document path, chunk index) so the entity
    pipeline can reattach FROM_CHUNK relationships without recreating the lexical
    graph.
    """
    prepared: list[TextChunk] = []
    for chunk in chunks.chunks:
        chunk_id = f"{document_info.uid}:{chunk.index}"
        metadata = chunk.metadata.copy() if chunk.metadata else {}
        metadata.update(
            {
                LEXICAL_GRAPH_CONFIG.chunk_id_property: chunk_id,
                DOCUMENT_PATH_PROPERTY: document_info.path,
            }
        )
        if document_info.metadata:
            metadata.update(document_info.metadata)
        prepared.append(
            TextChunk(
                text=chunk.text,
                index=chunk.index,
                uid=chunk_id,
                metadata=metadata,
            )
        )
    return TextChunks(chunks=prepared)


def _read_document_chunks(
    reader: Neo4jChunkReader,
    document_path: str,
    lexical_graph_config: LexicalGraphConfig = LEXICAL_GRAPH_CONFIG,
) -> TextChunks:
    """Read chunks for a single document directly from Neo4j."""
    if reader.fetch_embeddings:
        return_properties = ".*"
    else:
        return_properties = (
            f".*, {lexical_graph_config.chunk_embedding_property}: null"
        )
    query = (
        f"MATCH (d:`{lexical_graph_config.document_node_label}` {{path: $path}})"
        f"<-[:{lexical_graph_config.chunk_to_document_relationship_type}]-(c:`{lexical_graph_config.chunk_node_label}`) "
        f"RETURN c {{ {return_properties} }} as chunk "
    )
    if lexical_graph_config.chunk_index_property:
        query += f"ORDER BY c.{lexical_graph_config.chunk_index_property}"
    result = reader.driver.execute_query(
        query,
        path=document_path,
        database_=reader.neo4j_database,
        routing_=neo4j.RoutingControl.READ,
    )[0]
    chunks = []
    for record in result:
        chunk = record.get("chunk")
        input_data = {
            "text": chunk.pop(lexical_graph_config.chunk_text_property, ""),
            "index": chunk.pop(lexical_graph_config.chunk_index_property, -1),
        }
        uid = chunk.pop(lexical_graph_config.chunk_id_property, None)
        if uid is not None:
            input_data["uid"] = uid
        input_data["metadata"] = chunk
        chunks.append(TextChunk(**input_data))
    return TextChunks(chunks=chunks)


def _attach_document_provenance(
    graph_nodes: Iterable[Neo4jNode], document_info: DocumentInfo
) -> None:
    lexical_node_labels = set(LEXICAL_GRAPH_CONFIG.lexical_graph_node_labels)
    for node in graph_nodes:
        node_label = node.label  # Neo4jNode.label is a single primary label
        if node_label in lexical_node_labels:
            continue
        node.properties.setdefault(DOCUMENT_PATH_PROPERTY, document_info.path)
        if document_info.metadata:
            for key, value in document_info.metadata.items():
                node.properties.setdefault(key, value)
        if document_info.document_type:
            node.properties.setdefault("doc_type", document_info.document_type)


def reset_document_lexical_graph(neo4j_driver: neo4j.Driver, document_path: str) -> None:
    """Remove only Document/Chunk nodes for a path; entity graph is left intact."""
    count_query = """
    MATCH (d:Document {path: $path})
    OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
    RETURN count(DISTINCT d) AS documents_deleted, count(DISTINCT c) AS chunks_deleted
    """
    delete_chunks_query = """
    MATCH (d:Document {path: $path})<-[:FROM_DOCUMENT]-(c:Chunk)
    DETACH DELETE c
    """
    delete_document_query = """
    MATCH (d:Document {path: $path})
    DETACH DELETE d
    """
    with neo4j_driver.session(database=DATABASE) as session:
        record = session.run(count_query, path=document_path).single()
        session.run(delete_chunks_query, path=document_path).consume()
        session.run(delete_document_query, path=document_path).consume()
    documents_deleted = record["documents_deleted"] if record else 0
    chunks_deleted = record["chunks_deleted"] if record else 0
    print(
        f"[reset] path={document_path} documents_deleted={documents_deleted} "
        f"chunks_deleted={chunks_deleted}"
    )


def reset_document_entity_graph(neo4j_driver: neo4j.Driver, document_path: str) -> None:
    """Remove entity nodes tied to a document while leaving lexical graph untouched."""
    delete_entities_query = (
        "MATCH (d:`{doc_label}` {{path: $path}}) "
        "OPTIONAL MATCH (d)<-[:{chunk_rel}]-(c:`{chunk_label}`) "
        "OPTIONAL MATCH (c)<-[rel:{node_to_chunk}]-(n) "
        "WITH [n IN collect(DISTINCT n) WHERE n IS NOT NULL] AS candidate_nodes, "
        "[r IN collect(DISTINCT rel) WHERE r IS NOT NULL] AS rels "
        "FOREACH (r IN rels | DELETE r) "
        "WITH candidate_nodes "
        "UNWIND [n IN candidate_nodes WHERE n IS NOT NULL] AS n "
        "WITH DISTINCT n "
        "WHERE NOT (n)-[:{node_to_chunk}]-() "
        "DETACH DELETE n"
    ).format(
        doc_label=LEXICAL_GRAPH_CONFIG.document_node_label,
        chunk_rel=LEXICAL_GRAPH_CONFIG.chunk_to_document_relationship_type,
        chunk_label=LEXICAL_GRAPH_CONFIG.chunk_node_label,
        node_to_chunk=LEXICAL_GRAPH_CONFIG.node_to_chunk_relationship_type,
    )
    with neo4j_driver.session(database=DATABASE) as session:
        summary = session.run(delete_entities_query, path=document_path).consume()
    deleted_nodes = summary.counters.nodes_deleted if summary else 0
    deleted_rels = summary.counters.relationships_deleted if summary else 0
    print(
        f"[reset] entity graph removed for path={document_path} "
        f"nodes_deleted={deleted_nodes} rels_deleted={deleted_rels}"
    )


async def _run_lexical_pipeline(
    neo4j_driver: neo4j.Driver,
    document_info: DocumentInfo,
    text: str,
    splitter: FixedSizeSplitter = text_splitter,
) -> PipelineResult:
    splitter_result = await splitter.run(text)
    prepared_chunks = _prepare_chunks_for_document(splitter_result, document_info)
    embedded_chunks = await TextChunkEmbedder(embedder=OpenAIEmbeddings()).run(
        prepared_chunks
    )
    lexical_graph = await LexicalGraphBuilder(config=LEXICAL_GRAPH_CONFIG).run(
        text_chunks=embedded_chunks,
        document_info=document_info,
    )
    writer = Neo4jWriter(
        neo4j_driver,
        neo4j_database=DATABASE,
        clean_db=False,
    )
    writer_result = await writer.run(
        graph=lexical_graph.graph,
        lexical_graph_config=LEXICAL_GRAPH_CONFIG,
    )
    return PipelineResult(run_id=document_info.uid, result=writer_result)


async def _run_entity_pipeline(
    neo4j_driver: neo4j.Driver,
    llm: LLMInterface,
) -> list[PipelineResult]:
    reader = Neo4jChunkReader(
        neo4j_driver,
        neo4j_database=DATABASE,
    )
    schema_builder = SchemaBuilder()
    extractor = LLMEntityRelationExtractor(
        llm=llm,
        create_lexical_graph=False,
    )
    writer = Neo4jWriter(
        neo4j_driver,
        neo4j_database=DATABASE,
        clean_db=False,
    )
    results: list[PipelineResult] = []
    for item in DOCUMENTS_TO_INGEST:
        file_path = item["file_path"]
        document_metadata = item["document_metadata"]
        file_path_str = file_path.as_posix()
        print(f"[entity] reading chunks for path={file_path_str}")
        document_info = DocumentInfo(
            path=file_path_str,
            metadata=document_metadata,
            uid=file_path_str,
            document_type=document_metadata.get("doc_type"),
        )
        document_chunks = _read_document_chunks(
            reader, file_path_str, lexical_graph_config=LEXICAL_GRAPH_CONFIG
        )
        if not document_chunks.chunks:
            logger.warning(
                "No chunks found for %s; skipping entity pass", file_path_str
            )
            continue
        schema = await schema_builder.run(
            node_types=KG_SCHEMA.node_types,
            relationship_types=KG_SCHEMA.relationship_types,
            patterns=KG_SCHEMA.patterns,
        )
        graph = await extractor.run(
            chunks=document_chunks,
            lexical_graph_config=LEXICAL_GRAPH_CONFIG,
            schema=schema,
            document_info=document_info,
        )
        _attach_document_provenance(graph.nodes, document_info)
        writer_result = await writer.run(
            graph=graph,
            lexical_graph_config=LEXICAL_GRAPH_CONFIG,
        )
        results.append(PipelineResult(run_id=file_path_str, result=writer_result))
        print(f"[entity] completed extraction for path={file_path_str}")
    return results


async def define_and_run_pipeline(
    neo4j_driver: neo4j.Driver,
    llm: LLMInterface,
) -> list[PipelineResult]:
    results: list[PipelineResult] = []
    for item in DOCUMENTS_TO_INGEST:
        file_path = item["file_path"]
        document_metadata = item["document_metadata"]
        file_path_str = file_path.as_posix()
        document_info = DocumentInfo(
            path=file_path_str,
            metadata=document_metadata,
            uid=file_path_str,
            document_type=document_metadata.get("doc_type"),
        )
        if RUN_LEXICAL_PIPELINE and RESET_LEXICAL_GRAPH:
            reset_document_lexical_graph(neo4j_driver, file_path_str)
        if RUN_LEXICAL_PIPELINE:
            print(f"[lexical] running ingestion for {file_path_str}")
            text = _load_pdf_text(file_path)
            lexical_result = await _run_lexical_pipeline(
                neo4j_driver,
                document_info,
                text=text,
            )
            results.append(lexical_result)
        if RUN_ENTITY_PIPELINE and RESET_ENTITY_GRAPH:
            reset_document_entity_graph(neo4j_driver, file_path_str)
    if RUN_ENTITY_PIPELINE:
        entity_results = await _run_entity_pipeline(neo4j_driver, llm)
        results.extend(entity_results)
    return results


async def main() -> list[PipelineResult]:
    llm = OpenAILLM(
        model_name="gpt-4o",
        model_params={
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        },
    )
    print(
        f"[config] chunk_size={CHUNK_SIZE} chunk_overlap={CHUNK_OVERLAP} "
        f"approximate={APPROXIMATE}"
    )
    print(
        "[config] pipelines: "
        f"lexical={RUN_LEXICAL_PIPELINE} reset_lexical={RESET_LEXICAL_GRAPH}; "
        f"entity={RUN_ENTITY_PIPELINE} reset_entity={RESET_ENTITY_GRAPH}"
    )
    with neo4j.GraphDatabase.driver(URI, auth=AUTH) as driver:
        res = await define_and_run_pipeline(driver, llm)
    await llm.async_client.close()
    return res


if __name__ == "__main__":
    res = asyncio.run(main())
    print(res)
