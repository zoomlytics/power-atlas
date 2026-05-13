from __future__ import annotations

import argparse
import os
from pathlib import Path

from power_atlas.bootstrap import build_settings


def build_claim_extraction_diagnostics_report_settings(args: argparse.Namespace):
    environ = dict(os.environ)
    environ["POWER_ATLAS_OUTPUT_DIR"] = str(args.output_dir)
    if args.dataset_id is not None:
        environ["POWER_ATLAS_DATASET"] = args.dataset_id
    return build_settings(environ=environ)


def parse_claim_extraction_diagnostics_report_args(
    argv: list[str] | None = None,
    *,
    default_output_dir: Path,
    doc_epilog: str | None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read and format a persisted claim-extraction diagnostics artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=doc_epilog,
    )
    selector_group = parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument(
        "--run-id",
        default=None,
        help="Pipeline run_id whose claim-extraction diagnostics artifact should be reported.",
    )
    selector_group.add_argument(
        "--current",
        action="store_true",
        help="Resolve the newest run for --stage-prefix and report its diagnostics artifact.",
    )
    parser.add_argument(
        "--stage-prefix",
        default=None,
        help=(
            "Run prefix used with --current (for example 'unstructured_ingest'). "
            "Ignored when --run-id is provided."
        ),
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help=(
            "Dataset identifier used when resolving --current. When omitted, the current-run "
            "lookup falls back to the configured POWER_ATLAS_DATASET if present."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=(
            "Base output directory containing runs/ (default: pipelines/). "
            "Artifacts are read from <output_dir>/runs/<run_id>/claim_extraction_diagnostics/."
        ),
    )
    return parser.parse_args(argv)


__all__ = [
    "build_claim_extraction_diagnostics_report_settings",
    "parse_claim_extraction_diagnostics_report_args",
]