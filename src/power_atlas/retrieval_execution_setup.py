from __future__ import annotations

from collections.abc import Callable


def prepare_retrieval_execution_settings(
    *,
    index_name: str | None,
    pipeline_contract: object,
    qa_model: str | None,
    expand_graph: bool,
    cluster_aware: bool,
    all_runs: bool,
    pipeline_contract_value: Callable[[str, object], str],
    select_runtime_retrieval_query: Callable[..., str],
    default_qa_model: str = "gpt-5.4",
) -> tuple[str, str, str]:
    """Resolve the index, QA model, and retrieval query for live retrieval execution."""
    resolved_index_name = (
        index_name
        if index_name is not None
        else pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME", pipeline_contract)
    )
    effective_qa_model = qa_model or default_qa_model
    retrieval_query = select_runtime_retrieval_query(
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
    )
    return resolved_index_name, effective_qa_model, retrieval_query


__all__ = ["prepare_retrieval_execution_settings"]