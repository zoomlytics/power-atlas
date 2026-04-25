from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_single_shot_session_runner(
    *,
    question: str,
    top_k: int,
    query_params: dict[str, object],
    message_history: Any,
    citation_optional_fields: tuple[str, ...],
    logger: Any,
    execute_search: Callable[..., Any],
) -> Callable[..., tuple[str, list[dict[str, object]], list[str], list[str]]]:
    """Bind single-shot retrieval inputs into a session callback for live session setup."""

    def _run_single_shot_session(*, driver: object, retriever: object, rag: Any) -> tuple[str, list[dict[str, object]], list[str], list[str]]:
        del driver, retriever
        return run_single_shot_retrieval_session(
            rag=rag,
            question=question,
            top_k=top_k,
            query_params=query_params,
            message_history=message_history,
            citation_optional_fields=citation_optional_fields,
            logger=logger,
            execute_search=execute_search,
        )

    return _run_single_shot_session


def run_single_shot_retrieval_session(
    *,
    rag: Any,
    question: str,
    top_k: int,
    query_params: dict[str, object],
    message_history: Any,
    citation_optional_fields: tuple[str, ...],
    logger: Any,
    execute_search: Callable[..., Any],
) -> tuple[str, list[dict[str, object]], list[str], list[str]]:
    """Run one retrieval-backed QA turn and normalize the session result tuple."""
    search_result = execute_search(
        rag,
        question=question,
        top_k=top_k,
        query_params=query_params,
        message_history=message_history,
        citation_optional_fields=citation_optional_fields,
        logger=logger,
    )
    return (
        search_result.answer_text,
        search_result.hits,
        search_result.warnings,
        search_result.citation_warnings,
    )


__all__ = ["build_single_shot_session_runner", "run_single_shot_retrieval_session"]