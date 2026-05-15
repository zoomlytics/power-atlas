from __future__ import annotations

from typing import Any

from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, Neo4jGraph
from neo4j_graphrag.generation import RagTemplate

try:
    from neo4j_graphrag.experimental.components.types import TextChunk, TextChunks
except ModuleNotFoundError:
    class TextChunk:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class TextChunks:  # type: ignore[no-redef]
        def __init__(self, chunks: list[TextChunk]) -> None:
            self.chunks = chunks

__all__ = [
    "LexicalGraphConfig",
    "Neo4jGraph",
    "RagTemplate",
    "TextChunk",
    "TextChunks",
]
