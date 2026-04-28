from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_retriever_and_rag(
    driver: Any,
    *,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    neo4j_database: str | None,
    embedder_model_name: str,
    result_formatter: Callable[[Any], Any],
    embedder_factory: type[Any],
    retriever_factory: type[Any],
    rag_factory: type[Any],
    build_embedder: Callable[..., Any],
    build_llm: Callable[[str], Any],
    prompt_template: str,
) -> tuple[Any, Any]:
    """Construct the retriever and GraphRAG pair for a live retrieval session."""
    embedder = build_embedder(
        embedder_model_name,
        embedder_factory=embedder_factory,
    )
    retriever = retriever_factory(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        retrieval_query=retrieval_query,
        result_formatter=result_formatter,
        neo4j_database=neo4j_database,
    )
    llm = build_llm(qa_model)
    rag = rag_factory(
        retriever=retriever,
        llm=llm,
        prompt_template=prompt_template,
    )
    return retriever, rag


__all__ = ["build_retriever_and_rag"]