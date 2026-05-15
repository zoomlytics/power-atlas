from __future__ import annotations

from typing import Any

from neo4j_graphrag.experimental.components.entity_relation_extractor import LLMEntityRelationExtractor
from neo4j_graphrag.experimental.components.kg_writer import KGWriterModel, Neo4jWriter
from neo4j_graphrag.experimental.components.schema import GraphSchema, NodeType, PropertyType, RelationshipType
from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner
from neo4j_graphrag.experimental.pipeline.types.context import RunContext
from neo4j_graphrag.experimental.components.data_loader import PdfLoader, is_default_fs
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import FixedSizeSplitter


try:
    from neo4j_graphrag.experimental.components.neo4j_reader import Neo4jChunkReader
except ModuleNotFoundError:
    class Neo4jChunkReader:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.driver = kwargs.get("driver") or (args[0] if args else None)
            self.fetch_embeddings = kwargs.get("fetch_embeddings", False)
            self.neo4j_database = kwargs.get("neo4j_database")

__all__ = [
    "GraphSchema",
    "NodeType",
    "PropertyType",
    "RelationshipType",
    "KGWriterModel",
    "LLMEntityRelationExtractor",
    "Neo4jChunkReader",
    "Neo4jWriter",
    "PipelineRunner",
    "RunContext",
    "PdfLoader",
    "is_default_fs",
    "FixedSizeSplitter",
]
