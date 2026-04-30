from __future__ import annotations

from collections.abc import Callable
from typing import Any


def run_reset_demo_main(
    *,
    parse_args: Callable[[], Any],
    build_settings_from_args: Callable[[Any], Any],
    build_app_context: Callable[..., Any],
    create_neo4j_driver: Callable[[Any], Any],
    run_reset: Callable[..., dict[str, Any]],
    emit: Callable[[str], None] = print,
) -> None:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to run without --confirm")
    if not args.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD environment variable or --neo4j-password must be set")

    settings = build_settings_from_args(args)
    app_context = build_app_context(settings=settings)
    driver = create_neo4j_driver(settings)
    with driver:
        report = run_reset(
            driver=driver,
            database=args.neo4j_database,
            output_dir=args.output_dir,
            pipeline_contract=app_context.pipeline_contract,
        )

    emit(
        f"Demo graph reset complete: "
        f"database={report['target_database']} "
        f"nodes_deleted={report['deleted_nodes']} "
        f"relationships_deleted={report['deleted_relationships']} "
        f"indexes_dropped={report['indexes_dropped']}"
    )
    if report.get("warnings"):
        for warning in report["warnings"]:
            emit(f"  warning: {warning}")
    if report.get("report_path"):
        emit(f"Reset report written to: {report['report_path']}")


__all__ = ["run_reset_demo_main"]