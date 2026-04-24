from __future__ import annotations

from collections.abc import Callable
from typing import Any


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


__all__ = ["run_single_shot_retrieval_session"]