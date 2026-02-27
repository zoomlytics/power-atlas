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


# Instantiate NodeType and RelationshipType objects. This defines the
# entities and relations the LLM will be looking for in the text.
NODE_TYPES = [
    {"label": "Character", "description": "A person or sentient being in the story"},
    {"label": "Group", "description": "A group, faction, family, school house, or organization"},
    {"label": "Location", "description": "A physical place or setting"},
    {"label": "Artifact", "description": "A named object of plot significance (diary, sword, etc.)"},
    {"label": "Creature", "description": "A non-human creature (basilisk, phoenix, etc.)"},
    {"label": "Event", "description": "A major plot event or incident"},
]

RELATIONSHIP_TYPES = [
    {"label": "ALLY_OF", "description": "Characters who cooperate"},
    {"label": "ENEMY_OF", "description": "Characters who oppose each other"},
    {"label": "MEMBER_OF", "description": "Character belongs to a group"},
    {"label": "LOCATED_IN", "description": "Entity/event is located in a place"},
    {"label": "OWNS", "description": "Character or group owns/possesses an artifact"},
    {"label": "USES", "description": "Character uses an artifact"},
    {"label": "INVOLVES", "description": "Event involves a character/creature/artifact"},
    {"label": "CAUSES", "description": "Event causes another event"},
]

PATTERNS = [
    ("Character", "ALLY_OF", "Character"),
    ("Character", "ENEMY_OF", "Character"),
    ("Character", "MEMBER_OF", "Group"),
    ("Group", "LOCATED_IN", "Location"),
    ("Character", "LOCATED_IN", "Location"),
    ("Event", "LOCATED_IN", "Location"),
    ("Character", "OWNS", "Artifact"),
    ("Group", "OWNS", "Artifact"),
    ("Character", "USES", "Artifact"),
    ("Event", "INVOLVES", "Character"),
    ("Event", "INVOLVES", "Creature"),
    ("Event", "INVOLVES", "Artifact"),
    ("Event", "CAUSES", "Event"),
]


async def define_and_run_pipeline(
    neo4j_driver: neo4j.Driver,
    llm: LLMInterface,
) -> PipelineResult:
    # Create an instance of the SimpleKGPipeline
    kg_builder = SimpleKGPipeline(
        llm=llm,
        driver=neo4j_driver,
        embedder=OpenAIEmbeddings(),
        schema={
            "node_types": NODE_TYPES,
            "relationship_types": RELATIONSHIP_TYPES,
            "patterns": PATTERNS,
        },
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
