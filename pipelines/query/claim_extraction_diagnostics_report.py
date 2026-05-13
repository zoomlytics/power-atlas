"""Claim-extraction diagnostics artifact reporting script.

Reads an existing claim-extraction diagnostics artifact and prints a small
human-readable summary plus a trailing JSON summary line.

Usage
-----
Use one of the following forms:

    # Scoped to a specific run
    python pipelines/query/claim_extraction_diagnostics_report.py \
        --run-id unstructured_ingest-20240101T000000000000Z-abcd1234

    # Resolve the latest run for a stage prefix
    python pipelines/query/claim_extraction_diagnostics_report.py \
        --current \
        --stage-prefix unstructured_ingest

Environment variables
---------------------
POWER_ATLAS_OUTPUT_DIR  (default: artifacts)
POWER_ATLAS_DATASET     (optional default dataset for --current lookups)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from power_atlas.claim_extraction_diagnostics_artifact import (  # noqa: E402
    resolve_claim_extraction_diagnostics_artifact,
    resolve_current_claim_extraction_diagnostics_artifact,
)
from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (  # noqa: E402
    run_claim_extraction_diagnostics_report_main,
)
from power_atlas.interfaces.cli.claim_extraction_diagnostics_report_support import (  # noqa: E402
    build_claim_extraction_diagnostics_report_settings as _build_claim_extraction_diagnostics_report_settings_impl,
    parse_claim_extraction_diagnostics_report_args as _parse_claim_extraction_diagnostics_report_args_impl,
)

_PIPELINES_DIR = Path(__file__).resolve().parent.parent

_logger = logging.getLogger(__name__)


def _build_settings(args: argparse.Namespace):
    return _build_claim_extraction_diagnostics_report_settings_impl(args)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_claim_extraction_diagnostics_report_args_impl(
        argv,
        default_output_dir=_PIPELINES_DIR,
        doc_epilog=__doc__,
    )


def main(argv: list[str] | None = None) -> None:
    run_claim_extraction_diagnostics_report_main(
        parse_args=_parse_args,
        build_settings=_build_settings,
        resolve_artifact=resolve_claim_extraction_diagnostics_artifact,
        resolve_current_artifact=resolve_current_claim_extraction_diagnostics_artifact,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


if __name__ == "__main__":
    main()