from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from power_atlas.bootstrap import create_neo4j_driver

SessionResultT = TypeVar("SessionResultT")


def run_with_retrieval_session(
    config: object,
    *,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    neo4j_database: str | None,
    pipeline_contract: Any,
    build_retriever_and_rag: Callable[..., tuple[Any, Any]],
    run_session: Callable[..., SessionResultT],
) -> SessionResultT:
    with create_neo4j_driver(config) as driver:
        retriever, rag = build_retriever_and_rag(
            driver,
            index_name=index_name,
            retrieval_query=retrieval_query,
            qa_model=qa_model,
            neo4j_database=neo4j_database,
            pipeline_contract=pipeline_contract,
        )
        return run_session(driver=driver, retriever=retriever, rag=rag)


__all__ = ["run_with_retrieval_session"]