from __future__ import annotations

from collections.abc import Callable
from typing import Any

from power_atlas.context import RequestContext, RequestRuntime
from power_atlas.retrieval_runtime_bindings import (
    run_interactive_retrieval_with_runtime_inputs,
    run_retrieval_with_runtime_inputs,
)


def run_retrieval_runtime(
    request_runtime: RequestRuntime,
    *,
    top_k: int,
    index_name: str | None,
    question: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    message_history: object,
    interactive: bool,
    run_impl: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Bind request-scoped runtime state onto the retrieval stage implementation."""
    return run_retrieval_with_runtime_inputs(
        request_runtime.config,
        run_id=request_runtime.run_id,
        source_uri=request_runtime.source_uri,
        top_k=top_k,
        index_name=index_name,
        question=question,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        all_runs=request_runtime.all_runs,
        pipeline_contract=request_runtime.pipeline_contract,
        retrieval_policy=request_runtime.policies.retrieval,
        neo4j_settings=request_runtime.settings.neo4j,
        run_impl=run_impl,
    )


def run_retrieval_request_context(
    request_context: RequestContext,
    *,
    top_k: int,
    index_name: str | None,
    question: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    message_history: object,
    interactive: bool,
    run_impl: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Bind RequestContext state onto the retrieval stage implementation."""
    return run_retrieval_runtime(
        request_context.runtime,
        top_k=top_k,
        index_name=index_name,
        question=question,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        run_impl=run_impl,
    )


def run_interactive_runtime(
    request_runtime: RequestRuntime,
    *,
    top_k: int,
    index_name: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    all_runs: bool | None,
    debug: bool,
    run_impl: Callable[..., Any],
) -> Any:
    """Bind request-scoped runtime state onto the interactive retrieval stage implementation."""
    return run_interactive_retrieval_with_runtime_inputs(
        request_runtime.config,
        run_id=request_runtime.run_id,
        source_uri=request_runtime.source_uri,
        top_k=top_k,
        index_name=index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=request_runtime.all_runs if all_runs is None else all_runs,
        debug=debug,
        pipeline_contract=request_runtime.pipeline_contract,
        retrieval_policy=request_runtime.policies.retrieval,
        neo4j_settings=request_runtime.settings.neo4j,
        run_impl=run_impl,
    )


def run_interactive_request_context(
    request_context: RequestContext,
    *,
    top_k: int,
    index_name: str | None,
    expand_graph: bool | None,
    cluster_aware: bool | None,
    all_runs: bool | None,
    debug: bool,
    run_impl: Callable[..., Any],
) -> Any:
    """Bind RequestContext state onto the interactive retrieval stage implementation."""
    return run_interactive_runtime(
        request_context.runtime,
        top_k=top_k,
        index_name=index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        debug=debug,
        run_impl=run_impl,
    )


__all__ = [
    "run_interactive_runtime",
    "run_interactive_request_context",
    "run_retrieval_runtime",
    "run_retrieval_request_context",
]