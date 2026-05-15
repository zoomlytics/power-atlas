import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
AUTH = (
    os.getenv("NEO4J_USERNAME", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

EXAMPLES_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = EXAMPLES_ROOT / "data"

DOCUMENT_PATH_PROPERTY = "document_path"
LEXICAL_GRAPH_CONFIG = SimpleNamespace(chunk_id_property="chunk_id")


@dataclass(frozen=True)
class PropertyType:
    name: str
    value_type: str = "string"


@dataclass(frozen=True)
class NodeType:
    label: str
    properties: list[PropertyType]


@dataclass(frozen=True)
class KnowledgeGraphSchema:
    node_types: list[NodeType]


@dataclass(frozen=True)
class DocumentInfo:
    path: str
    metadata: dict[str, Any]
    uid: str
    document_type: str


@dataclass
class TextChunk:
    text: str
    index: int
    uid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextChunks:
    chunks: list[TextChunk]


KG_SCHEMA = KnowledgeGraphSchema(
    node_types=[
        NodeType("Person", [PropertyType("name")]),
        NodeType("Organization", [PropertyType("name")]),
        NodeType("Event", [PropertyType("name")]),
        NodeType("FactSheet", [PropertyType("firm_name"), PropertyType("doc_type")]),
        NodeType("AnalystNote", [PropertyType("subject"), PropertyType("doc_type")]),
    ]
)

ENTITY_RESOLUTION_PROPERTY_BY_LABEL = {
    "Person": "name",
    "Organization": "name",
    "Event": "name",
    "FactSheet": "firm_name",
    "AnalystNote": "subject",
}

DOCUMENTS_TO_INGEST = [
    {
        "file_path": (DATA_DIR / "power_atlas_factsheet.pdf").resolve(),
        "document_metadata": {
            "corpus": "power_atlas_demo",
            "doc_type": "facts",
        },
    },
    {
        "file_path": (DATA_DIR / "power_atlas_analyst_note.pdf").resolve(),
        "document_metadata": {
            "corpus": "power_atlas_demo",
            "doc_type": "narrative",
        },
    },
]


def _prepare_chunks_for_document(chunks: TextChunks, document_info: DocumentInfo) -> TextChunks:
    prepared_chunks: list[TextChunk] = []
    for chunk in chunks.chunks:
        metadata = dict(chunk.metadata)
        metadata[DOCUMENT_PATH_PROPERTY] = document_info.path
        metadata.update(document_info.metadata)
        uid = f"{document_info.uid}:{chunk.index}"
        metadata[LEXICAL_GRAPH_CONFIG.chunk_id_property] = uid
        prepared_chunks.append(
            TextChunk(
                text=chunk.text,
                index=chunk.index,
                uid=uid,
                metadata=metadata,
            )
        )
    return TextChunks(chunks=prepared_chunks)


def _build_document_scoped_filter_query(document_paths: list[str], entity_label: str) -> str:
    normalized_paths = sorted({path for path in document_paths if path})
    encoded_paths = json.dumps(normalized_paths)
    return (
        f"MATCH (entity)\n"
        f"WHERE entity:{entity_label}\n"
        "  AND EXISTS {\n"
        "      MATCH (entity)-[:FROM_CHUNK]->(:Chunk)-[:FROM_DOCUMENT]->(doc:Document)\n"
        f"      WHERE doc.path IN {encoded_paths}\n"
        "  }\n"
        "RETURN entity"
    )


def _load_pdf_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="ignore")


async def _run_lexical_pipeline(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    return TextChunks(chunks=[])


async def _run_entity_pipeline(*args: Any, **kwargs: Any) -> list[Any]:
    del args, kwargs
    return []


def reset_document_derived_graph(*, neo4j_driver: Any, document_path: str) -> None:
    with neo4j_driver.session(database=DATABASE) as session:
        with session.begin_transaction() as tx:
            tx.run(
                """
                MATCH (d:Document {path: $path})
                OPTIONAL MATCH (c:Chunk)-[:FROM_DOCUMENT]->(d)
                RETURN count(DISTINCT d) AS documents_found, count(DISTINCT c) AS chunks_found
                """,
                path=document_path,
            ).single()
            tx.run(
                """
                MATCH (d:Document {path: $path})<-[:FROM_DOCUMENT]-(c:Chunk)
                OPTIONAL MATCH (c)<-[rel:FROM_CHUNK|HAS_ENTITY]-(entity)
                DETACH DELETE entity, rel
                """,
                path=document_path,
            ).consume()
            tx.run(
                """
                MATCH (d:Document {path: $path})<-[:FROM_DOCUMENT]-(c:Chunk)
                DETACH DELETE c
                """,
                path=document_path,
            ).consume()
            tx.run(
                """
                MATCH (d:Document {path: $path})
                DELETE d
                """,
                path=document_path,
            ).consume()
            tx.commit()


def reset_document_lexical_graph(neo4j_driver: Any, document_path: str) -> None:
    reset_document_derived_graph(neo4j_driver=neo4j_driver, document_path=document_path)


async def define_and_run_pipeline(neo4j_driver: Any, llm: Any) -> dict[str, Any]:
    del llm
    run_lexical_pipeline = os.getenv("RUN_LEXICAL_PIPELINE", "true").lower() == "true"
    reset_lexical_graph = os.getenv("RESET_LEXICAL_GRAPH", "true").lower() == "true"
    run_entity_pipeline = os.getenv("RUN_ENTITY_PIPELINE", "true").lower() == "true"
    reset_entity_graph = os.getenv("RESET_ENTITY_GRAPH", "false").lower() == "true"

    if run_lexical_pipeline and reset_lexical_graph and run_entity_pipeline and not reset_entity_graph:
        logger.warning(
            "RESET_LEXICAL_GRAPH=true with RUN_ENTITY_PIPELINE=true and RESET_ENTITY_GRAPH=false may leave orphaned entity nodes."
        )

    processed_documents = 0
    for item in DOCUMENTS_TO_INGEST:
        document_path = item["file_path"]
        if run_lexical_pipeline and reset_lexical_graph:
            reset_document_lexical_graph(neo4j_driver, str(document_path))
        _load_pdf_text(document_path)
        await _run_lexical_pipeline(
            neo4j_driver,
            file_path=str(document_path),
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            document_metadata=item["document_metadata"],
        )
        if run_entity_pipeline:
            await _run_entity_pipeline(
                neo4j_driver,
                file_path=str(document_path),
                document_metadata=item["document_metadata"],
            )
        processed_documents += 1

    return {
        "status": "ok",
        "documents_processed": processed_documents,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }


async def main() -> dict[str, Any]:
    return await define_and_run_pipeline(neo4j_driver=None, llm=None)


if __name__ == "__main__":
    print(asyncio.run(main()))