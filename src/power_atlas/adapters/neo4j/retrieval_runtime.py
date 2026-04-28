from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from power_atlas.bootstrap import create_neo4j_driver
from power_atlas.contracts import resolve_early_return_rule
from power_atlas.retrieval_live_preflight import prepare_live_retrieval_preflight
from power_atlas.settings import Neo4jSettings

SessionResultT = TypeVar("SessionResultT")


@dataclass(frozen=True)
class RetrievalSearchResult:
    answer_text: str
    hits: list[dict[str, object]]
    warnings: list[str]
    citation_warnings: list[str]


@dataclass(frozen=True)
class InteractiveRetrievalTurnResult:
    display_answer: str
    history_answer: str
    citation_fallback_applied: bool
    debug_summary: str | None


def _build_retriever_labels(*, expand_graph: bool, cluster_aware: bool) -> list[str]:
    retrievers: list[str] = ["VectorCypherRetriever"]
    if cluster_aware:
        retrievers += ["graph expansion", "cluster traversal"]
    elif expand_graph:
        retrievers.append("graph expansion")
    return retrievers


def _build_qa_scope_label(*, all_runs: bool) -> str:
    return "GraphRAG all-runs citations" if all_runs else "GraphRAG run-scoped citations"


def build_retrieval_base_result(
    *,
    citation_run_id: str,
    citation_source_uri: str,
    top_k: int,
    resolved_index_name: str,
    question: str | None,
    effective_qa_model: str,
    qa_prompt_version: str,
    effective_expand_graph: bool,
    cluster_aware: bool,
    retrieval_scope: dict[str, object],
    citation_token_example: str,
    citation_object_example: dict[str, object],
    retrieval_query_contract: str,
    interactive: bool,
    message_history_enabled: bool,
) -> dict[str, object]:
    default_citation_quality: dict[str, object] = {
        "all_cited": False,
        "raw_answer_all_cited": False,
        "evidence_level": "no_answer",
        "warning_count": 0,
        "citation_warnings": [],
    }
    return {
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "top_k": top_k,
        "retriever_type": "VectorCypherRetriever",
        "retriever_index_name": resolved_index_name,
        "question": question,
        "qa_model": effective_qa_model,
        "qa_prompt_version": qa_prompt_version,
        "answer": "",
        "raw_answer": "",
        "citation_fallback_applied": False,
        "all_answers_cited": False,
        "raw_answer_all_cited": False,
        "citation_repair_attempted": False,
        "citation_repair_applied": False,
        "citation_repair_strategy": None,
        "citation_repair_source_chunk_id": None,
        "citation_quality": default_citation_quality,
        "expand_graph": effective_expand_graph,
        "cluster_aware": cluster_aware,
        "retrieval_scope": retrieval_scope,
        "citation_token_example": citation_token_example,
        "citation_object_example": citation_object_example,
        "citation_example": citation_object_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
        "interactive_mode": interactive,
        "message_history_enabled": message_history_enabled,
        "retrieval_path_summary": "",
        "malformed_diagnostics_count": 0,
        "debug_view": {
            "raw_answer_all_cited": False,
            "all_cited": False,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_fallback_applied": False,
            "evidence_level": "no_answer",
            "warning_count": 0,
            "citation_warnings": [],
            "malformed_diagnostics_count": 0,
        },
    }


def build_dry_run_retrieval_result(
    *,
    base: dict[str, object],
    expand_graph: bool,
    cluster_aware: bool,
    all_runs: bool,
) -> dict[str, object]:
    return {
        **base,
        "status": "dry_run",
        "retrievers": _build_retriever_labels(expand_graph=expand_graph, cluster_aware=cluster_aware),
        "qa": _build_qa_scope_label(all_runs=all_runs),
    }


def build_retrieval_skipped_result(
    *,
    base: dict[str, object],
    warning_msg: str,
) -> dict[str, object]:
    return {
        **base,
        "status": "live",
        "retrievers": [],
        "qa": _build_qa_scope_label(all_runs=False),
        "hits": 0,
        "retrieval_results": [],
        "warnings": [warning_msg],
        "retrieval_skipped": True,
    }


def build_early_return_retrieval_result(
    *,
    config: object,
    question: str | None,
    base: dict[str, object],
    expand_graph: bool,
    cluster_aware: bool,
    all_runs: bool,
    logger: logging.Logger,
) -> dict[str, object] | None:
    """Return the dry-run or retrieval-skipped result when an early-return rule matches."""
    early_rule = resolve_early_return_rule(
        is_dry_run=getattr(config, "dry_run", False),
        question=question,
    )
    if early_rule is None:
        return None
    if early_rule.name == "dry_run":
        return build_dry_run_retrieval_result(
            base=base,
            expand_graph=expand_graph,
            cluster_aware=cluster_aware,
            all_runs=all_runs,
        )
    if early_rule.name == "retrieval_skipped":
        warning_msg = "No question provided; skipping vector retrieval."
        logger.warning(warning_msg)
        return build_retrieval_skipped_result(base=base, warning_msg=warning_msg)
    raise RuntimeError(
        f"run_retrieval_and_qa_request_context: matched early-return rule {early_rule.name!r} "
        "has no corresponding payload branch.  Add a branch for this rule."
    )


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

    malformed_count = count_malformed_diagnostics(hits)
    return {
        **base,
        "status": "live",
        "retrievers": _build_retriever_labels(expand_graph=expand_graph, cluster_aware=cluster_aware),
        "qa": _build_qa_scope_label(all_runs=all_runs),
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


def finalize_live_retrieval_result(
    *,
    base: dict[str, object],
    answer_text: str,
    hits: list[dict[str, object]],
    session_warnings: list[str],
    session_citation_warnings: list[str],
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
    """Merge session warnings and finalize the public live retrieval result."""
    warnings_list = list(session_warnings)
    citation_warnings_list = list(session_citation_warnings)
    return build_live_retrieval_result(
        base=base,
        answer_text=answer_text,
        hits=hits,
        warnings=warnings_list,
        citation_warnings=citation_warnings_list,
        all_runs=all_runs,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        citation_token_example=citation_token_example,
        citation_object_example=citation_object_example,
        fallback_preview_max_len=fallback_preview_max_len,
        logger=logger,
        postprocess_answer=postprocess_answer,
        project_postprocess_to_public=project_postprocess_to_public,
        format_retrieval_path_summary=format_retrieval_path_summary,
        count_malformed_diagnostics=count_malformed_diagnostics,
        build_retrieval_debug_view=build_retrieval_debug_view,
    )


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


def run_interactive_retrieval_turn(
    rag: Any,
    *,
    question: str,
    top_k: int,
    query_params: dict[str, object],
    message_history: Any,
    citation_optional_fields: tuple[str, ...],
    logger: logging.Logger,
    all_runs: bool,
    debug: bool,
    postprocess_answer: Callable[..., dict[str, object]],
    build_retrieval_debug_view: Callable[..., dict[str, object]],
    format_postprocess_debug_summary: Callable[[dict[str, object]], str],
    count_malformed_diagnostics: Callable[[list[dict[str, object]]], int],
) -> InteractiveRetrievalTurnResult:
    search_result = execute_retrieval_search(
        rag,
        question=question,
        top_k=top_k,
        query_params=query_params,
        message_history=message_history,
        citation_optional_fields=citation_optional_fields,
        logger=logger,
    )
    pp = postprocess_answer(
        search_result.answer_text,
        search_result.hits,
        all_runs=all_runs,
    )
    debug_summary: str | None = None
    if debug:
        debug_view = build_retrieval_debug_view(
            pp,
            malformed_diagnostics_count=count_malformed_diagnostics(search_result.hits),
        )
        debug_summary = format_postprocess_debug_summary(debug_view)
    return InteractiveRetrievalTurnResult(
        display_answer=pp["display_answer"],
        history_answer=pp["history_answer"],
        citation_fallback_applied=pp["citation_fallback_applied"],
        debug_summary=debug_summary,
    )


def run_with_retrieval_session(
    neo4j_settings: Neo4jSettings,
    *,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    neo4j_database: str | None,
    pipeline_contract: Any,
    build_retriever_and_rag: Callable[..., tuple[Any, Any]],
    run_session: Callable[..., SessionResultT],
) -> SessionResultT:
    with create_neo4j_driver(neo4j_settings) as driver:
        retriever, rag = build_retriever_and_rag(
            driver,
            index_name=index_name,
            retrieval_query=retrieval_query,
            qa_model=qa_model,
            neo4j_database=neo4j_database,
            pipeline_contract=pipeline_contract,
        )
        return run_session(driver=driver, retriever=retriever, rag=rag)


def run_live_retrieval_session(
    *,
    config: object,
    neo4j_settings: Neo4jSettings | None,
    neo4j_settings_type: type[Neo4jSettings],
    require_openai_api_key: Callable[[], None],
    openai_api_key: str,
    openai_error_message: str,
    neo4j_error_message: str,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    pipeline_contract: Any,
    build_retriever_and_rag: Callable[..., tuple[Any, Any]],
    run_session: Callable[..., SessionResultT],
) -> SessionResultT:
    resolved_neo4j_settings, neo4j_database = prepare_live_retrieval_preflight(
        config,
        neo4j_settings,
        neo4j_settings_type=neo4j_settings_type,
        require_openai_api_key=require_openai_api_key,
        openai_api_key=openai_api_key,
        openai_error_message=openai_error_message,
        neo4j_error_message=neo4j_error_message,
    )
    return run_with_retrieval_session(
        resolved_neo4j_settings,
        index_name=index_name,
        retrieval_query=retrieval_query,
        qa_model=qa_model,
        neo4j_database=neo4j_database,
        pipeline_contract=pipeline_contract,
        build_retriever_and_rag=build_retriever_and_rag,
        run_session=run_session,
    )


__all__ = [
    "InteractiveRetrievalTurnResult",
    "RetrievalSearchResult",
    "build_early_return_retrieval_result",
    "build_dry_run_retrieval_result",
    "finalize_live_retrieval_result",
    "build_retrieval_base_result",
    "build_retrieval_skipped_result",
    "build_live_retrieval_result",
    "execute_retrieval_search",
    "run_live_retrieval_session",
    "run_interactive_retrieval_turn",
    "run_with_retrieval_session",
]