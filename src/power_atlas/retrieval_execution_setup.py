from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalExecutionContext:
    pipeline_contract: object
    resolved_index_name: str
    effective_qa_model: str
    retrieval_query: str


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


def prepare_retrieval_execution_context(
    *,
    config: object,
    pipeline_contract: object | None,
    index_name: str | None,
    expand_graph: bool,
    cluster_aware: bool,
    all_runs: bool,
    resolve_pipeline_contract: Callable[[object, object | None], object],
    pipeline_contract_value: Callable[[str, object], str],
    select_runtime_retrieval_query: Callable[..., str],
    default_qa_model: str = "gpt-5.4",
) -> RetrievalExecutionContext:
    """Resolve the shared execution context used by single-shot and interactive retrieval."""
    resolved_pipeline_contract = resolve_pipeline_contract(config, pipeline_contract)
    resolved_index_name, effective_qa_model, retrieval_query = prepare_retrieval_execution_settings(
        index_name=index_name,
        pipeline_contract=resolved_pipeline_contract,
        qa_model=getattr(config, "openai_model", None),
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        pipeline_contract_value=pipeline_contract_value,
        select_runtime_retrieval_query=select_runtime_retrieval_query,
        default_qa_model=default_qa_model,
    )
    return RetrievalExecutionContext(
        pipeline_contract=resolved_pipeline_contract,
        resolved_index_name=resolved_index_name,
        effective_qa_model=effective_qa_model,
        retrieval_query=retrieval_query,
    )


def build_live_retrieval_query_params(
    *,
    run_id: str | None,
    source_uri: str | None,
    all_runs: bool,
    cluster_aware: bool,
    build_query_params: Callable[..., dict[str, object]],
    run_id_error_message: str,
) -> dict[str, object]:
    """Validate live run scope and build retrieval query params via the injected seam."""
    if not all_runs and run_id is None:
        raise ValueError(run_id_error_message)
    return build_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
    )


__all__ = [
    "RetrievalExecutionContext",
    "build_live_retrieval_query_params",
    "prepare_retrieval_execution_context",
    "prepare_retrieval_execution_settings",
]