"""This example illustrates how to get started easily with the SimpleKGPipeline
and ingest PDF into a Neo4j Knowledge Graph.

This example assumes a Neo4j db is up and running. Update the credentials below
if needed.

OPENAI_API_KEY needs to be in the env vars.
"""

import asyncio
import os
from pathlib import Path

import neo4j
from dotenv import load_dotenv
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    NodeType,
    Pattern,
    PropertyType,
    RelationshipType,
)
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.experimental.pipeline.pipeline import PipelineResult
from neo4j_graphrag.llm import LLMInterface
from neo4j_graphrag.llm import OpenAILLM

from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
    FixedSizeSplitter,
)

load_dotenv()

# Tune these
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))       # characters (see note below)
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
APPROXIMATE = os.getenv("CHUNK_APPROXIMATE", "true").lower() == "true"

text_splitter = FixedSizeSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    approximate=APPROXIMATE,
)

# Neo4j db infos
URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "testtesttest")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
AUTH = (USERNAME, PASSWORD)

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


def reset_document_lexical_graph(
    neo4j_driver: neo4j.Driver, document_path: str
) -> None:
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


async def define_and_run_pipeline(
    neo4j_driver: neo4j.Driver,
    llm: LLMInterface,
) -> list[PipelineResult]:
    # Create an instance of the SimpleKGPipeline
    kg_builder = SimpleKGPipeline(
        llm=llm,
        driver=neo4j_driver,
        embedder=OpenAIEmbeddings(),
        schema=KG_SCHEMA,
        neo4j_database=DATABASE,
        text_splitter=text_splitter,
    )
    results: list[PipelineResult] = []
    for item in DOCUMENTS_TO_INGEST:
        file_path = item["file_path"]
        document_metadata = item["document_metadata"]
        file_path_str = file_path.resolve().as_posix()
        print(f"[ingest] preparing path={file_path_str} metadata={document_metadata}")
        reset_document_lexical_graph(neo4j_driver, file_path_str)
        print(f"[ingest] running pipeline path={file_path_str}")
        result = await kg_builder.run_async(
            file_path=file_path_str,
            document_metadata=document_metadata,
        )
        results.append(result)
        print(f"[ingest] completed path={file_path_str}")
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
    with neo4j.GraphDatabase.driver(URI, auth=AUTH) as driver:
        res = await define_and_run_pipeline(driver, llm)
    await llm.async_client.close()
    return res


if __name__ == "__main__":
    res = asyncio.run(main())
    print(res)
