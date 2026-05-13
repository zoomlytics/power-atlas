from __future__ import annotations

import logging

from power_atlas.bootstrap import build_settings
from power_atlas.claim_extraction_diagnostics_artifact import (
    resolve_claim_extraction_diagnostics_artifact,
    resolve_current_claim_extraction_diagnostics_artifact,
)
from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (
    run_claim_extraction_diagnostics_report_main,
)
from power_atlas.interfaces.cli.claim_extraction_diagnostics_report_support import (
    build_claim_extraction_diagnostics_report_settings,
    parse_claim_extraction_diagnostics_report_args,
)

_logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None):
    return parse_claim_extraction_diagnostics_report_args(
        argv,
        default_output_dir=build_settings().output_dir,
        doc_epilog=None,
    )


def main(argv: list[str] | None = None) -> None:
    run_claim_extraction_diagnostics_report_main(
        parse_args=_parse_args,
        build_settings=build_claim_extraction_diagnostics_report_settings,
        resolve_artifact=resolve_claim_extraction_diagnostics_artifact,
        resolve_current_artifact=resolve_current_claim_extraction_diagnostics_artifact,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


__all__ = ["main"]


if __name__ == "__main__":
    main()