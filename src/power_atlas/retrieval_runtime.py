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


def build_live_retrieval_result(
    *,
    base: dict[str, object],
    answer_text: str,
    hits: list[dict[str, object]],
    warnings: list[str],
    citation_warnings: list[str],
    all_runs: bool,
    expand_graph: bool,
    cluster_aware: bool,
    citation_token_example: str,
    citation_object_example: dict[str, object],
    fallback_preview_max_len: int,
    logger: logging.Logger,
    postprocess_answer: Callable[..., dict[str, object]],
    project_postprocess_to_public: Callable[[dict[str, object]], dict[str, object]],
    format_retrieval_path_summary: Callable[[list[dict[str, object]]], str],
    count_malformed_diagnostics: Callable[[list[dict[str, object]]], int],
    build_retrieval_debug_view: Callable[..., dict[str, object]],
) -> dict[str, object]:
    warnings_list = list(warnings)
    citation_warnings_list = list(citation_warnings)
    n_retrieval_citation_warnings = len(citation_warnings_list)
    pp = postprocess_answer(
        answer_text,
        hits,
        all_runs=all_runs,
        existing_citation_warnings=citation_warnings_list,
    )
    for warning in pp["citation_warnings"][n_retrieval_citation_warnings:]:
        warnings_list.append(warning)
    if pp["citation_fallback_applied"]:
        display = pp["display_answer"]
        fallback_preview = (
            display[:fallback_preview_max_len] + "..."
            if len(display) > fallback_preview_max_len
            else display
        )
        logger.warning(
            "Answer replaced with citation fallback (length=%d, preview=%r)",
            len(display),
            fallback_preview,
        )

    actual_citation_token = citation_token_example
    actual_citation_object = citation_object_example
    if hits:
        first_meta = hits[0].get("metadata") or {}
        if first_meta.get("citation_token"):
            actual_citation_token = first_meta["citation_token"]
        if first_meta.get("citation_object"):
            actual_citation_object = first_meta["citation_object"]

    live_retrievers: list[str] = ["VectorCypherRetriever"]
    if cluster_aware:
        live_retrievers += ["graph expansion", "cluster traversal"]
    elif expand_graph:
        live_retrievers.append("graph expansion")

    qa_scope_label = "GraphRAG all-runs citations" if all_runs else "GraphRAG run-scoped citations"
    malformed_count = count_malformed_diagnostics(hits)
    return {
        **base,
        "status": "live",
        "retrievers": live_retrievers,
        "qa": qa_scope_label,
        "hits": len(hits),
        "retrieval_results": hits,
        "warnings": warnings_list,
        "citation_token_example": actual_citation_token,
        "citation_object_example": actual_citation_object,
        "citation_example": actual_citation_object,
        **project_postprocess_to_public(pp),
        "retrieval_path_summary": format_retrieval_path_summary(hits),
        "malformed_diagnostics_count": malformed_count,
        "debug_view": build_retrieval_debug_view(pp, malformed_diagnostics_count=malformed_count),
    }


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


__all__ = [
    "RetrievalSearchResult",
    "build_live_retrieval_result",
    "execute_retrieval_search",
    "run_with_retrieval_session",
]