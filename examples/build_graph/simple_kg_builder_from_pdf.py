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
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.experimental.pipeline.pipeline import PipelineResult
from neo4j_graphrag.llm import LLMInterface
from neo4j_graphrag.llm import OpenAILLM

from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
    FixedSizeSplitter,
)

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

root_dir = Path(__file__).parents[1]
file_path = root_dir / "data" / "Harry Potter and the Chamber of Secrets Summary.pdf"


async def define_and_run_pipeline(
    neo4j_driver: neo4j.Driver,
    llm: LLMInterface,
) -> PipelineResult:
    # Create an instance of the SimpleKGPipeline
    kg_builder = SimpleKGPipeline(
        llm=llm,
        driver=neo4j_driver,
        embedder=OpenAIEmbeddings(),
        schema="FREE",
        neo4j_database=DATABASE,
        text_splitter=text_splitter,
)
    return await kg_builder.run_async(
        file_path=str(file_path),
        # optional, add document metadata, each item will
        # be saved as a property of the Document node
        # document_metadata={"author": "J. K. Rowling"},
    )


async def main() -> PipelineResult:
    llm = OpenAILLM(
        model_name="gpt-4o",
        model_params={
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        },
    )
    with neo4j.GraphDatabase.driver(URI, auth=AUTH) as driver:
        res = await define_and_run_pipeline(driver, llm)
    await llm.async_client.close()
    return res


if __name__ == "__main__":
    res = asyncio.run(main())
    print(res)
