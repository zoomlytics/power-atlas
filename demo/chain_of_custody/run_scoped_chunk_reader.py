from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import re
from neo4j_graphrag.experimental.components.neo4j_reader import Neo4jChunkReader
from neo4j_graphrag.experimental.components.types import (
    LexicalGraphConfig,
    TextChunk,
    TextChunks,
)
from pydantic import validate_call

if TYPE_CHECKING:
    import neo4j

logger = logging.getLogger(__name__)


class RunScopedNeo4jChunkReader(Neo4jChunkReader):
    """Chunk reader that scopes results to a specific run_id (and optional source_uri/corpus)."""

    def __init__(
        self,
        driver: "neo4j.Driver",
        *,
        run_id: str,
        source_uri: str | None = None,
        corpus: str | None = None,
        fetch_embeddings: bool = False,
        neo4j_database: str | None = None,
    ):
        super().__init__(
            driver=driver,
            fetch_embeddings=fetch_embeddings,
            neo4j_database=neo4j_database,
        )
        self.run_id = run_id
        self.source_uri = source_uri
        self.corpus = corpus

    @staticmethod
    def _validate_identifier(value: str, kind: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {kind}: expected string, got {type(value).__name__}")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError(f"Unsafe {kind}: {value!r}")
        return value

    def _get_query(
        self,
        chunk_label: str,
        index_property: str,
        embedding_property: str,
    ) -> str:
        filters = ["c.run_id = $run_id"]
        if self.source_uri is not None:
            filters.append("c.source_uri = $source_uri")
        if self.corpus is not None:
            filters.append("c.corpus = $corpus")

        return_properties = [".*"]
        if not self.fetch_embeddings:
            safe_embedding_property = self._validate_identifier(embedding_property, "embedding_property")
            return_properties.append(f"{safe_embedding_property}: null")

        query = f"MATCH (c:`{chunk_label}`)\nWHERE {' AND '.join(filters)}\nRETURN c {{ {', '.join(return_properties)} }} as chunk "
        if index_property:
            safe_index_property = self._validate_identifier(index_property, "index_property")
            query += f"ORDER BY c.{safe_index_property}"
        return query

    @validate_call
    async def run(
        self,
        lexical_graph_config: LexicalGraphConfig = LexicalGraphConfig(),
    ) -> TextChunks:
        import neo4j

        query = self._get_query(
            lexical_graph_config.chunk_node_label,
            lexical_graph_config.chunk_index_property,
            lexical_graph_config.chunk_embedding_property,
        )
        params = {"run_id": self.run_id}
        if self.source_uri:
            params["source_uri"] = self.source_uri
        if self.corpus:
            params["corpus"] = self.corpus

        result, _, _ = self.driver.execute_query(
            query,
            parameters_=params,
            database_=self.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        chunks = []
        for record in result:
            chunk = record.get("chunk")
            input_data = {
                "text": chunk.pop(lexical_graph_config.chunk_text_property, ""),
                "index": chunk.pop(lexical_graph_config.chunk_index_property, -1),
            }
            if (
                uid := chunk.pop(lexical_graph_config.chunk_id_property, None)
            ) is not None:
                input_data["uid"] = uid
            input_data["metadata"] = chunk
            chunks.append(TextChunk(**input_data))

        if not chunks:
            message = "No chunks returned for run-scoped query"
            details = {
                "run_id": self.run_id,
                "source_uri": self.source_uri,
                "corpus": self.corpus,
            }
            logger.warning("%s: %r", message, details)
            raise ValueError(f"{message}: {details}")

        return TextChunks(chunks=chunks)
