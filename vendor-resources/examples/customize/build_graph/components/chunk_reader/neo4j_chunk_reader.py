import asyncio
import warnings

import neo4j
from neo4j_graphrag.experimental.components.neo4j_reader import Neo4jChunkReader
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, TextChunk, TextChunks


class RunScopedNeo4jChunkReader(Neo4jChunkReader):
    """Read chunks for a specific run (and optional source URI) only."""

    def __init__(
        self,
        driver: neo4j.Driver,
        run_id: str,
        *,
        source_uri: str | None = None,
        fetch_embeddings: bool = False,
        neo4j_database: str | None = None,
        fail_on_empty: bool = True,
    ) -> None:
        super().__init__(
            driver=driver,
            fetch_embeddings=fetch_embeddings,
            neo4j_database=neo4j_database,
        )
        self.run_id = run_id
        self.source_uri = source_uri
        self.fail_on_empty = fail_on_empty

    def _get_query(
        self,
        chunk_label: str,
        index_property: str,
        embedding_property: str,
    ) -> str:
        return_properties = [".*"]
        if not self.fetch_embeddings:
            return_properties.append(f"{embedding_property}: null")
        where_clauses = ["c.run_id = $run_id"]
        if self.source_uri:
            where_clauses.append("c.source_uri = $source_uri")
        query = (
            f"MATCH (c:`{chunk_label}`)\n"
            f"WHERE {' AND '.join(where_clauses)}\n"
            f"RETURN c {{ {', '.join(return_properties)} }} as chunk "
        )
        if index_property:
            query += f"ORDER BY c.{index_property}"
        return query

    async def run(
        self,
        lexical_graph_config: LexicalGraphConfig = LexicalGraphConfig(),
    ) -> TextChunks:
        query = self._get_query(
            lexical_graph_config.chunk_node_label,
            lexical_graph_config.chunk_index_property,
            lexical_graph_config.chunk_embedding_property,
        )
        parameters = {"run_id": self.run_id}
        if self.source_uri:
            parameters["source_uri"] = self.source_uri
        result, _, _ = self.driver.execute_query(
            query,
            database_=self.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
            **parameters,
        )
        chunks: list[TextChunk] = []
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
            msg = "No chunks found for the specified run_id/source_uri filters"
            if self.fail_on_empty:
                raise ValueError(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)

        return TextChunks(chunks=chunks)


async def main(driver: neo4j.Driver) -> TextChunks:
    config = LexicalGraphConfig(  # only needed to overwrite the default values
        chunk_node_label="TextPart",
    )
    reader = Neo4jChunkReader(driver)
    result = await reader.run(lexical_graph_config=config)
    return result


if __name__ == "__main__":
    with neo4j.GraphDatabase.driver(
        "bolt://localhost:7687", auth=("neo4j", "password")
    ) as driver:
        print(asyncio.run(main(driver)))
