from __future__ import annotations

from collections.abc import Callable
from typing import Any


def run_retrieval_with_runtime_inputs(
    config: Any,
    *,
    run_id: str | None,
    source_uri: str | None,
    top_k: int,
    index_name: str | None,
    question: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    message_history: object,
    interactive: bool,
    all_runs: bool,
    pipeline_contract: Any,
    retrieval_policy: Any,
    neo4j_settings: Any,
    run_impl: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Run retrieval with explicitly bound runtime inputs and no RequestContext dependency."""
    return run_impl(
        config,
        run_id=run_id,
        source_uri=source_uri,
        top_k=top_k,
        index_name=index_name or pipeline_contract.chunk_embedding_index_name,
        question=question if question is not None else getattr(config, "question", None),
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        all_runs=all_runs,
        pipeline_contract=pipeline_contract,
        retrieval_policy=retrieval_policy,
        neo4j_settings=neo4j_settings,
    )


def run_interactive_retrieval_with_runtime_inputs(
    config: Any,
    *,
    run_id: str | None,
    source_uri: str | None,
    top_k: int,
    index_name: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    all_runs: bool,
    debug: bool,
    pipeline_contract: Any,
    retrieval_policy: Any,
    neo4j_settings: Any,
    run_impl: Callable[..., Any],
) -> Any:
    """Run interactive retrieval with explicitly bound runtime inputs and no RequestContext dependency."""
    return run_impl(
        config,
        run_id=run_id,
        source_uri=source_uri,
        top_k=top_k,
        index_name=index_name or pipeline_contract.chunk_embedding_index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        debug=debug,
        pipeline_contract=pipeline_contract,
        retrieval_policy=retrieval_policy,
        neo4j_settings=neo4j_settings,
    )


__all__ = [
    "run_interactive_retrieval_with_runtime_inputs",
    "run_retrieval_with_runtime_inputs",
]