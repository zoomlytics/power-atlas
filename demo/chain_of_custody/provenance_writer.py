from __future__ import annotations

from typing import Any

import neo4j
from neo4j_graphrag.experimental.components.kg_writer import (
    KGWriterModel,
    Neo4jWriter,
)
from neo4j_graphrag.experimental.components.types import (
    LexicalGraphConfig,
    Neo4jGraph,
)
from neo4j_graphrag.experimental.pipeline.types.context import RunContext
from pydantic import validate_call


class ProvenanceNeo4jWriter(Neo4jWriter):
    """Neo4j writer that ensures provenance fields are attached before ingest."""

    def __init__(
        self,
        driver: neo4j.Driver,
        neo4j_database: str | None = None,
        dataset_id: str | None = None,
    ) -> None:
        super().__init__(driver=driver, neo4j_database=neo4j_database)
        self.dataset_id = dataset_id

    def _apply_provenance(
        self,
        graph: Neo4jGraph,
        lexical_graph_config: LexicalGraphConfig,
        run_id: str | None,
    ) -> None:
        document_label = lexical_graph_config.document_node_label
        chunk_label = lexical_graph_config.chunk_node_label
        chunk_to_document_rel = lexical_graph_config.chunk_to_document_relationship_type

        document_props: dict[str, dict[str, Any]] = {}
        for node in graph.nodes:
            if node.label != document_label:
                continue
            props = dict(node.properties or {})
            if run_id:
                props.setdefault("run_id", run_id)
            if self.dataset_id:
                props.setdefault("dataset_id", self.dataset_id)
            # Prefer explicit source_uri if present; otherwise fall back to the path.
            source_uri = props.get("source_uri") or props.get("path")
            if source_uri:
                props.setdefault("source_uri", source_uri)
            node.properties = props
            document_props[node.id] = props

        if not document_props:
            return

        chunk_to_document: dict[str, str] = {
            rel.start_node_id: rel.end_node_id
            for rel in graph.relationships
            if rel.type == chunk_to_document_rel
        }

        for node in graph.nodes:
            if node.label != chunk_label:
                continue
            props = dict(node.properties or {})
            doc_id = chunk_to_document.get(node.id)
            doc_props = document_props.get(doc_id) if doc_id else None
            if run_id:
                props.setdefault("run_id", run_id)
            if self.dataset_id:
                props.setdefault("dataset_id", doc_props.get("dataset_id") if doc_props else self.dataset_id)
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
        self._apply_provenance(
            graph=graph,
            lexical_graph_config=lexical_graph_config,
            run_id=context_.run_id,
        )
        return await super().run(graph=graph, lexical_graph_config=lexical_graph_config)
