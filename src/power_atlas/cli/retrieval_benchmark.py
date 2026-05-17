from __future__ import annotations

import logging

from power_atlas.bootstrap import AppBaseline, build_settings
from power_atlas.interfaces.cli.retrieval_benchmark_entrypoint import (
    run_retrieval_benchmark_main,
)
from power_atlas.interfaces.cli.retrieval_benchmark_support import (
    build_retrieval_benchmark_cli_request_context,
    parse_retrieval_benchmark_args,
)
from power_atlas.retrieval_benchmark_entrypoint import (
    run_retrieval_benchmark_request_context,
)

_logger = logging.getLogger(__name__)


def _parse_args(
    argv: list[str] | None = None,
    *,
    app_baseline: AppBaseline | None = None,
):
    return parse_retrieval_benchmark_args(
        argv,
        default_output_dir=build_settings(app_baseline=app_baseline).output_dir,
        doc_epilog=None,
        app_baseline=app_baseline,
    )


def main(argv: list[str] | None = None) -> None:
    run_retrieval_benchmark_main(
        parse_args=_parse_args,
        build_cli_request_context=build_retrieval_benchmark_cli_request_context,
        run_retrieval_benchmark_request_context=run_retrieval_benchmark_request_context,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


__all__ = ["main"]


if __name__ == "__main__":
    main()