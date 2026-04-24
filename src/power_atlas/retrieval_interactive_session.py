from __future__ import annotations

from collections.abc import Callable
from typing import Any


def run_interactive_session_loop(
    *,
    rag: Any,
    history: Any,
    top_k: int,
    query_params: dict[str, object],
    citation_optional_fields: tuple[str, ...],
    logger: Any,
    all_runs: bool,
    debug: bool,
    run_interactive_turn: Callable[..., Any],
    postprocess_answer: Callable[..., dict[str, object]],
    build_retrieval_debug_view: Callable[..., dict[str, object]],
    format_postprocess_debug_summary: Callable[[dict[str, object]], str],
    count_malformed_diagnostics: Callable[[list[dict[str, object]]], int],
    llm_message_factory: Callable[..., Any],
    input_fn: Callable[[str], str] | None = None,
    print_fn: Callable[..., None] | None = None,
) -> None:
    """Run the interactive retrieval REPL loop for a prepared GraphRAG session."""
    if input_fn is None:
        input_fn = input
    if print_fn is None:
        print_fn = print
    try:
        while True:
            try:
                question = input_fn("Question: ").strip()
            except EOFError:
                print_fn()
                break
            if not question:
                continue
            if question.lower() in ("exit", "quit"):
                break
            turn_result = run_interactive_turn(
                rag,
                question=question,
                top_k=top_k,
                query_params=query_params,
                message_history=history,
                citation_optional_fields=citation_optional_fields,
                logger=logger,
                all_runs=all_runs,
                debug=debug,
                postprocess_answer=postprocess_answer,
                build_retrieval_debug_view=build_retrieval_debug_view,
                format_postprocess_debug_summary=format_postprocess_debug_summary,
                count_malformed_diagnostics=count_malformed_diagnostics,
            )
            print_fn(f"\nAnswer:\n{turn_result.display_answer}\n")
            if turn_result.citation_fallback_applied:
                print_fn(
                    "WARNING: Not all answer sentences or bullets are cited - evidence quality may be degraded."
                )
            if turn_result.debug_summary is not None:
                print_fn(turn_result.debug_summary)
            history.add_messages(
                [
                    llm_message_factory(role="user", content=question),
                    llm_message_factory(role="assistant", content=turn_result.history_answer),
                ]
            )
    except KeyboardInterrupt:
        print_fn()


__all__ = ["run_interactive_session_loop"]