from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from power_atlas.bootstrap import create_neo4j_driver

SessionResultT = TypeVar("SessionResultT")


@dataclass(frozen=True)
class RetrievalSearchResult:
    answer_text: str
    hits: list[dict[str, object]]
    warnings: list[str]
    citation_warnings: list[str]


def execute_retrieval_search(
    rag: Any,
    *,
    question: str,
    top_k: int,
    query_params: dict[str, object],
    message_history: Any = None,
    citation_optional_fields: tuple[str, ...],
    logger: logging.Logger | None = None,
) -> RetrievalSearchResult:
    rag_result = rag.search(
        query_text=question,
        retriever_config={"top_k": top_k, "query_params": query_params},
        return_context=True,
        message_history=message_history,
    )

    answer_text: str = rag_result.answer if rag_result else ""
    warnings: list[str] = []
    citation_warnings: list[str] = []
    hits: list[dict[str, object]] = []
    if rag_result and rag_result.retriever_result:
        for item in rag_result.retriever_result.items:
            meta = item.metadata or {}
            citation_obj = meta.get("citation_object") or {}
            missing_fields = [field for field in citation_optional_fields if citation_obj.get(field) is None]
            if missing_fields:
                if logger is not None:
                    logger.info(
                        "Chunk %r missing optional citation fields: %s",
                        citation_obj.get("chunk_id"),
                        ", ".join(missing_fields),
                    )
                warnings.append(
                    f"Chunk {citation_obj.get('chunk_id')!r} missing optional citation fields: {', '.join(missing_fields)}"
                )
            if meta.get("empty_chunk_text"):
                chunk_id_val = citation_obj.get("chunk_id")
                empty_text_warning = f"Chunk {chunk_id_val!r} has empty or whitespace-only text."
                warnings.append(empty_text_warning)
                citation_warnings.append(empty_text_warning)
            hits.append({"content": item.content, "metadata": meta})
    return RetrievalSearchResult(
        answer_text=answer_text,
        hits=hits,
        warnings=warnings,
        citation_warnings=citation_warnings,
    )


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


__all__ = ["RetrievalSearchResult", "execute_retrieval_search", "run_with_retrieval_session"]