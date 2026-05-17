from __future__ import annotations

import logging

from power_atlas.bootstrap import AppBaseline, build_settings
from power_atlas.graph_health_diagnostics import run_graph_health_diagnostics_request_context
from power_atlas.interfaces.cli.graph_health_diagnostics_entrypoint import (
    run_graph_health_diagnostics_main,
)
from power_atlas.interfaces.cli.graph_health_diagnostics_support import (
    build_graph_health_cli_request_context,
    parse_graph_health_diagnostics_args,
)

_logger = logging.getLogger(__name__)


def _parse_args(
    argv: list[str] | None = None,
    *,
    app_baseline: AppBaseline | None = None,
):
    return parse_graph_health_diagnostics_args(
        argv,
        default_output_dir=build_settings(app_baseline=app_baseline).output_dir,
        doc_epilog=None,
        app_baseline=app_baseline,
    )


def main(argv: list[str] | None = None) -> None:
    run_graph_health_diagnostics_main(
        parse_args=_parse_args,
        build_cli_request_context=build_graph_health_cli_request_context,
        run_graph_health_diagnostics_request_context=run_graph_health_diagnostics_request_context,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


__all__ = ["main"]


if __name__ == "__main__":
    main()