from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import Any


def load_demo_reset_runner() -> Callable[..., Any]:
    return __import__("demo.reset_demo_db", fromlist=["run_reset"]).run_reset


def run_demo_main(
    *,
    parse_args: Callable[[], Namespace],
    dispatch_cli_command: Callable[..., Any],
    build_demo_cli_dispatch_kwargs: Callable[..., dict[str, Any]],
    build_request_context_from_args: Callable[..., Any],
    lint_and_clean_structured_csvs: Callable[..., Any],
    make_run_id: Callable[..., str],
    resolve_dataset_root: Callable[..., Any],
    run_demo: Callable[..., Path],
    prepare_ask_request_context: Callable[..., Any],
    resolve_run_interactive_qa_request_context: Callable[[], Callable[..., Any]],
    run_independent_stage: Callable[..., Path],
    format_scope_label: Callable[..., str],
    resolve_create_driver: Callable[[], Callable[..., Any]],
    resolve_load_reset_runner: Callable[[], Callable[..., Any]],
    emit: Callable[[str], None] = print,
) -> None:
    args = parse_args()
    try:
        dispatch_cli_command(
            args,
            emit=emit,
            **build_demo_cli_dispatch_kwargs(
                build_request_context_from_args=build_request_context_from_args,
                lint_and_clean_structured_csvs=lint_and_clean_structured_csvs,
                make_run_id=make_run_id,
                resolve_dataset_root=resolve_dataset_root,
                run_demo=run_demo,
                prepare_ask_request_context=prepare_ask_request_context,
                resolve_run_interactive_qa_request_context=resolve_run_interactive_qa_request_context,
                run_independent_stage=run_independent_stage,
                format_scope_label=format_scope_label,
                resolve_create_driver=resolve_create_driver,
                resolve_load_reset_runner=resolve_load_reset_runner,
            ),
        )
    except SystemExit:
        raise
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


__all__ = ["load_demo_reset_runner", "run_demo_main"]