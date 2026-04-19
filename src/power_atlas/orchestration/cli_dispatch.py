from __future__ import annotations

from typing import Any, Callable


CONFIG_COMMANDS = {
    "ingest",
    "ingest-structured",
    "ingest-pdf",
    "extract-claims",
    "resolve-entities",
    "ask",
}


def execute_lint_structured_command(
    args,
    *,
    emit: Callable[[str], None],
    build_request_context_from_args: Callable[..., Any],
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]],
    make_run_id: Callable[[str], str],
    resolve_dataset_root: Callable[[str | None], Any],
) -> None:
    request_context = build_request_context_from_args(args, dry_run=True)
    config = request_context.config
    dataset_root = resolve_dataset_root(config.dataset_name)
    run_id = make_run_id("structured_lint")
    lint_result = lint_and_clean_structured_csvs(
        run_id=run_id,
        output_dir=config.output_dir,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )
    emit(f"Structured lint report written to: {lint_result['lint_report_path']}")


def execute_config_command(
    args,
    *,
    emit: Callable[[str], None],
    build_request_context_from_args: Callable[..., Any],
    run_demo: Callable[[Any], Any],
    prepare_ask_request_context: Callable[..., Any],
    run_interactive_qa_request_context: Callable[..., None],
    run_independent_stage: Callable[..., Any],
    format_scope_label: Callable[[str | None, bool], str],
) -> None:
    request_context = build_request_context_from_args(args)
    if args.command == "ingest":
        manifest_path = run_demo(request_context)
        emit(f"Demo manifest written to: {manifest_path}")
        return
    if args.command == "ask" and getattr(args, "interactive", False):
        if request_context.config.dry_run:
            raise SystemExit(
                "Interactive 'ask' is not supported in dry-run mode. "
                "Re-run the command with --live to enable live Neo4j/OpenAI calls."
            )
        request_context = prepare_ask_request_context(args, request_context)
        scope_line = (
            f"Using retrieval scope: {format_scope_label(request_context.run_id, request_context.all_runs)}"
        )
        emit(scope_line)
        run_interactive_qa_request_context(
            request_context,
            cluster_aware=getattr(args, "cluster_aware", False),
            expand_graph=getattr(args, "expand_graph", False),
            debug=getattr(args, "debug", False),
        )
        return
    if args.command == "ask":
        request_context = prepare_ask_request_context(args, request_context)
        scope_line = (
            f"Using retrieval scope: {format_scope_label(request_context.run_id, request_context.all_runs)}"
        )
        manifest_path = run_independent_stage(
            request_context,
            args.command,
            resolved_run_id=request_context.run_id,
            all_runs=request_context.all_runs,
            cluster_aware=getattr(args, "cluster_aware", False),
            expand_graph=getattr(args, "expand_graph", False),
        )
        emit(scope_line)
        emit(f"Independent run manifest written to: {manifest_path}")
        return
    manifest_path = run_independent_stage(request_context, args.command)
    emit(f"Independent run manifest written to: {manifest_path}")


def reset_instructions_text() -> str:
    return (
        "To reset the demo graph, run:\n"
        "  python demo/reset_demo_db.py --confirm\n"
        "Or pass --confirm to this command:\n"
        "  python demo/run_demo.py --live reset --confirm\n"
        "See demo/reset_demo_db.py for full usage."
    )


def execute_reset_command(
    args,
    *,
    emit: Callable[[str], None],
    build_request_context_from_args: Callable[..., Any],
    create_driver: Callable[[Any], Any],
    load_reset_runner: Callable[[], Callable[..., dict[str, Any]]],
) -> None:
    if not getattr(args, "confirm", False):
        emit(reset_instructions_text())
        return
    if getattr(args, "dry_run", True):
        raise SystemExit(
            "reset --confirm requires --live; re-run with:\n"
            "  python demo/run_demo.py --live reset --confirm"
        )
    if not args.neo4j_password or args.neo4j_password == "CHANGE_ME_BEFORE_USE":
        raise SystemExit(
            "Set NEO4J_PASSWORD or pass --neo4j-password when running reset --confirm"
        )
    request_context = build_request_context_from_args(args)
    config = request_context.config
    run_reset = load_reset_runner()
    driver = create_driver(config)
    with driver:
        report = run_reset(
            driver=driver,
            database=config.neo4j_database,
            output_dir=config.output_dir,
            pipeline_contract=request_context.pipeline_contract,
        )
    emit(
        f"Demo graph reset complete: database={report['target_database']} "
        f"nodes_deleted={report['deleted_nodes']} "
        f"relationships_deleted={report['deleted_relationships']} "
        f"indexes_dropped={report['indexes_dropped']}"
    )
    for warning in report.get("warnings") or []:
        emit(f"  warning: {warning}")
    if report.get("report_path"):
        emit(f"Reset report written to: {report['report_path']}")


def dispatch_cli_command(
    args,
    *,
    emit: Callable[[str], None],
    build_request_context_from_args: Callable[..., Any],
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]],
    make_run_id: Callable[[str], str],
    resolve_dataset_root: Callable[[str | None], Any],
    run_demo: Callable[[Any], Any],
    prepare_ask_request_context: Callable[..., Any],
    run_interactive_qa_request_context: Callable[..., None],
    run_independent_stage: Callable[..., Any],
    format_scope_label: Callable[[str | None, bool], str],
    create_driver: Callable[[Any], Any],
    load_reset_runner: Callable[[], Callable[..., dict[str, Any]]],
) -> None:
    if args.command == "lint-structured":
        execute_lint_structured_command(
            args,
            emit=emit,
            build_request_context_from_args=build_request_context_from_args,
            lint_and_clean_structured_csvs=lint_and_clean_structured_csvs,
            make_run_id=make_run_id,
            resolve_dataset_root=resolve_dataset_root,
        )
        return
    if args.command in CONFIG_COMMANDS:
        execute_config_command(
            args,
            emit=emit,
            build_request_context_from_args=build_request_context_from_args,
            run_demo=run_demo,
            prepare_ask_request_context=prepare_ask_request_context,
            run_interactive_qa_request_context=run_interactive_qa_request_context,
            run_independent_stage=run_independent_stage,
            format_scope_label=format_scope_label,
        )
        return
    if args.command == "reset":
        execute_reset_command(
            args,
            emit=emit,
            build_request_context_from_args=build_request_context_from_args,
            create_driver=create_driver,
            load_reset_runner=load_reset_runner,
        )
        return
    emit(f"Stub: '{args.command}' command scaffold is ready.")


__all__ = [
    "CONFIG_COMMANDS",
    "dispatch_cli_command",
    "execute_config_command",
    "execute_lint_structured_command",
    "execute_reset_command",
    "reset_instructions_text",
]