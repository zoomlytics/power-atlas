from __future__ import annotations

from collections.abc import Callable
from typing import Any

from power_atlas.context import RequestContext


def run_retrieval_request_context(
    request_context: RequestContext,
    *,
    top_k: int,
    index_name: str | None,
    question: str | None,
    expand_graph: bool,
    cluster_aware: bool,
    message_history: object,
    interactive: bool,
    run_impl: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Bind RequestContext state onto the retrieval stage implementation."""
    return run_impl(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        top_k=top_k,
        index_name=index_name or request_context.pipeline_contract.chunk_embedding_index_name,
        question=question if question is not None else getattr(request_context.config, "question", None),
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        all_runs=request_context.all_runs,
        pipeline_contract=request_context.pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
    )


def run_interactive_request_context(
    request_context: RequestContext,
    *,
    top_k: int,
    index_name: str | None,
    expand_graph: bool,
    cluster_aware: bool,
    all_runs: bool | None,
    debug: bool,
    run_impl: Callable[..., Any],
) -> Any:
    """Bind RequestContext state onto the interactive retrieval stage implementation."""
    return run_impl(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        top_k=top_k,
        index_name=index_name or request_context.pipeline_contract.chunk_embedding_index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=request_context.all_runs if all_runs is None else all_runs,
        debug=debug,
        pipeline_contract=request_context.pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
    )


__all__ = [
    "run_interactive_request_context",
    "run_retrieval_request_context",
]