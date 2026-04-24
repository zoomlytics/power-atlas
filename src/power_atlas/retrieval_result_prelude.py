from __future__ import annotations

from collections.abc import Callable
from typing import Any


def prepare_retrieval_result_prelude(
    *,
    run_id: str | None,
    source_uri: str | None,
    all_runs: bool,
    top_k: int,
    resolved_index_name: str,
    question: str | None,
    effective_qa_model: str,
    qa_prompt_version: str,
    expand_graph: bool,
    cluster_aware: bool,
    retrieval_query_contract: str,
    interactive: bool,
    message_history_enabled: bool,
    resolve_dataset_root: Callable[[], Any],
    ambiguous_dataset_error_type: type[Exception],
    build_citation_token: Callable[..., str],
    build_retrieval_base_result: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Build the single-shot retrieval prelude before early-return/live branching."""
    citation_run_id = run_id if run_id is not None else "example_run_id"
    if source_uri is not None:
        citation_source_uri = source_uri
    else:
        try:
            citation_source_uri = resolve_dataset_root().pdf_path.resolve().as_uri()
        except ambiguous_dataset_error_type:
            citation_source_uri = "placeholder://citation-source"

    citation_token_example = build_citation_token(
        chunk_id="example_chunk",
        run_id=citation_run_id,
        source_uri=citation_source_uri,
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=999,
    )
    effective_expand_graph = expand_graph or cluster_aware
    citation_object_example: dict[str, object] = {
        "chunk_id": "example_chunk",
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 999,
    }
    retrieval_scope: dict[str, object] = {
        "run_id": run_id,
        "source_uri": source_uri,
        "scope_widened": all_runs,
        "all_runs": all_runs,
    }
    base = build_retrieval_base_result(
        citation_run_id=citation_run_id,
        citation_source_uri=citation_source_uri,
        top_k=top_k,
        resolved_index_name=resolved_index_name,
        question=question,
        effective_qa_model=effective_qa_model,
        qa_prompt_version=qa_prompt_version,
        effective_expand_graph=effective_expand_graph,
        cluster_aware=cluster_aware,
        retrieval_scope=retrieval_scope,
        citation_token_example=citation_token_example,
        citation_object_example=citation_object_example,
        retrieval_query_contract=retrieval_query_contract,
        interactive=interactive,
        message_history_enabled=message_history_enabled,
    )
    return {
        "base": base,
        "citation_token_example": citation_token_example,
        "citation_object_example": citation_object_example,
        "effective_expand_graph": effective_expand_graph,
        "retrieval_scope": retrieval_scope,
    }


__all__ = ["prepare_retrieval_result_prelude"]