from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from neo4j_graphrag.experimental.components.kg_writer import KGWriterModel, Neo4jWriter
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, Neo4jGraph
from neo4j_graphrag.experimental.pipeline.types.context import RunContext
from pydantic import validate_call

try:
    from neo4j_graphrag.experimental.components.neo4j_reader import Neo4jChunkReader
    from neo4j_graphrag.experimental.components.types import TextChunk, TextChunks
except ModuleNotFoundError as exc:
    if exc.name != "neo4j_graphrag.experimental.components.neo4j_reader":
        raise

    class Neo4jChunkReader:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.driver = kwargs.get("driver") or (args[0] if args else None)
            self.fetch_embeddings = kwargs.get("fetch_embeddings", False)
            self.neo4j_database = kwargs.get("neo4j_database")

    class TextChunk:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class TextChunks:  # type: ignore[no-redef]
        def __init__(self, chunks: list[TextChunk]) -> None:
            self.chunks = chunks

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import neo4j


def validate_cypher_identifier(value: str, kind: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {kind}: expected string, got {type(value).__name__}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind}: {value!r}")
    return value


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
        return validate_cypher_identifier(value, kind)

    @staticmethod
    def validate_identifier(value: str, kind: str) -> str:
        return validate_cypher_identifier(value, kind)

    def _get_query(
        self,
        chunk_label: str,
        index_property: str,
        embedding_property: str,
    ) -> str:
        safe_chunk_label = validate_cypher_identifier(chunk_label, "chunk_label")
        filters = ["c.run_id = $run_id"]
        if self.source_uri is not None:
            filters.append("c.source_uri = $source_uri")
        if self.corpus is not None:
            filters.append("c.corpus = $corpus")

        return_properties = [".*"]
        if not self.fetch_embeddings:
            safe_embedding_property = validate_cypher_identifier(embedding_property, "embedding_property")
            return_properties.append(f"{safe_embedding_property}: null")

        query = f"MATCH (c:`{safe_chunk_label}`)\nWHERE {' AND '.join(filters)}\nRETURN c {{ {', '.join(return_properties)} }} as chunk "
        if index_property:
            safe_index_property = validate_cypher_identifier(index_property, "index_property")
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
        if self.source_uri is not None:
            params["source_uri"] = self.source_uri
        if self.corpus is not None:
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
            if (uid := chunk.pop(lexical_graph_config.chunk_id_property, None)) is not None:
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


class ProvenanceNeo4jWriter(Neo4jWriter):
    """Neo4j writer that applies run_id/dataset_id/source_uri to Document and Chunk nodes before ingest."""

    def __init__(self, driver: "neo4j.Driver", neo4j_database: str | None = None, dataset_id: str | None = None) -> None:
        super().__init__(driver=driver, neo4j_database=neo4j_database)
        self.dataset_id = dataset_id

    def _apply_provenance(self, graph: Neo4jGraph, lexical_graph_config: LexicalGraphConfig, run_id: str | None) -> None:
        document_label = lexical_graph_config.document_node_label
        chunk_label = lexical_graph_config.chunk_node_label
        chunk_to_document_rel = lexical_graph_config.chunk_to_document_relationship_type

        document_props: dict[str, dict[str, Any]] = {}
        for node in graph.nodes:
            if node.label != document_label:
                continue
            props = dict(node.properties or {})
            metadata = props.get("metadata")
            metadata_props = metadata if isinstance(metadata, dict) else {}
            metadata_run_id = metadata_props.get("run_id")
            metadata_dataset_id = metadata_props.get("dataset_id")
            metadata_source_uri = metadata_props.get("source_uri")
            if metadata_run_id:
                props.setdefault("run_id", metadata_run_id)
            elif run_id:
                props.setdefault("run_id", run_id)
            if metadata_dataset_id:
                props.setdefault("dataset_id", metadata_dataset_id)
            elif self.dataset_id:
                props.setdefault("dataset_id", self.dataset_id)
            source_uri = props.get("source_uri") or metadata_source_uri or props.get("path")
            if source_uri:
                props.setdefault("source_uri", source_uri)
            node.properties = props
            document_props[node.id] = props

        if not document_props:
            return

        chunk_to_document: dict[str, str] = {
            rel.start_node_id: rel.end_node_id for rel in graph.relationships if rel.type == chunk_to_document_rel
        }

        for node in graph.nodes:
            if node.label != chunk_label:
                continue
            props = dict(node.properties or {})
            doc_id = chunk_to_document.get(node.id)
            doc_props = document_props.get(doc_id) if doc_id else None
            doc_run_id = doc_props.get("run_id") if doc_props else None
            if doc_run_id is not None:
                props.setdefault("run_id", doc_run_id)
            elif run_id:
                props.setdefault("run_id", run_id)
            dataset_value = None
            if doc_props and doc_props.get("dataset_id"):
                dataset_value = doc_props.get("dataset_id")
            elif self.dataset_id:
                dataset_value = self.dataset_id
            if dataset_value:
                props.setdefault("dataset_id", dataset_value)
            if doc_props:
                source_uri = doc_props.get("source_uri")
                if source_uri:
                    props.setdefault("source_uri", source_uri)
            node.properties = props

    @validate_call
    async def run_with_context(
        self,
        context_: RunContext,
        graph: Neo4jGraph,
        lexical_graph_config: LexicalGraphConfig = LexicalGraphConfig(),
    ) -> KGWriterModel:
        self._apply_provenance(graph=graph, lexical_graph_config=lexical_graph_config, run_id=None)
        return await super().run(graph=graph, lexical_graph_config=lexical_graph_config)


__all__ = [
    "ProvenanceNeo4jWriter",
    "RunScopedNeo4jChunkReader",
    "validate_cypher_identifier",
]