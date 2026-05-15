from __future__ import annotations

import json
from pathlib import Path

from power_atlas.interfaces.cli.smoke_test_entrypoint import run_smoke_test_main
from power_atlas.interfaces.cli.smoke_test_support import parse_smoke_test_args
from power_atlas.smoke_test_scenarios import build_smoke_test_config as _build_smoke_test_config_impl
from power_atlas.smoke_test_scenarios import run_batch_smoke_scenario as _run_batch_smoke_scenario_impl
from power_atlas.smoke_test_scenarios import (
    run_structured_smoke_scenario as _run_structured_smoke_scenario_impl,
)
from power_atlas.smoke_test_scenarios import (
    run_unstructured_smoke_scenario as _run_unstructured_smoke_scenario_impl,
)
from power_atlas.smoke_test_validation import validate_batch_manifest as _validate_batch_manifest_impl
from power_atlas.smoke_test_validation import validate_citation_token as _validate_citation_token_impl
from power_atlas.smoke_test_validation import (
    validate_independent_manifest as _validate_independent_manifest_impl,
)
from run_demo import _request_context_from_config, run_demo, run_independent_demo


def _parse_args(argv: list[str] | None = None):
    return parse_smoke_test_args(argv)


def _validate_citation_token(token: str) -> dict:
    return _validate_citation_token_impl(token)


def _validate_independent_manifest(
    manifest_path: Path, expected_stage: str, expected_run_scope_key: str
) -> None:
    _validate_independent_manifest_impl(manifest_path, expected_stage, expected_run_scope_key)


def _validate_batch_manifest(manifest_path: Path) -> None:
    _validate_batch_manifest_impl(manifest_path)


def _build_config(output_dir: Path):
    return _build_smoke_test_config_impl(output_dir)


def _run_structured_scenario(output_dir: Path) -> Path:
    """Run and validate the structured-only independent path.

    Runs 'ingest-structured' in dry-run mode and validates the resulting
    stage-scoped manifest at runs/<run_id>/structured_ingest/manifest.json.
    """
    return _run_structured_smoke_scenario_impl(
        output_dir,
        build_config=_build_config,
        request_context_from_config=_request_context_from_config,
        run_independent_demo=run_independent_demo,
        validate_independent_manifest=_validate_independent_manifest,
    )


def _run_unstructured_scenario(output_dir: Path) -> Path:
    """Run and validate the unstructured-only independent path.

    Runs 'ingest-pdf' in dry-run mode and validates the resulting
    stage-scoped manifest at runs/<run_id>/pdf_ingest/manifest.json.
    """
    return _run_unstructured_smoke_scenario_impl(
        output_dir,
        build_config=_build_config,
        request_context_from_config=_request_context_from_config,
        run_independent_demo=run_independent_demo,
        validate_independent_manifest=_validate_independent_manifest,
    )


def _run_batch_scenario(output_dir: Path) -> Path:
    """Run and validate the orchestrated batch path (sequential independent runs).

    Runs the full demo orchestration in dry-run mode and validates:
    - All required stages are present.
    - Structured and unstructured run_ids are distinct (no implicit coupling).
    - Citation tokens are well-formed per citation contract (#159).
    - QA signals are present and valid.
    """
    return _run_batch_smoke_scenario_impl(
        output_dir,
        build_config=_build_config,
        request_context_from_config=_request_context_from_config,
        run_demo=run_demo,
        validate_batch_manifest=_validate_batch_manifest,
    )


# Backward-compatible aliases for scripts and tests that call these directly.
def _run_and_validate(output_dir: Path) -> Path:
    return _run_batch_scenario(output_dir)


_validate_manifest = _validate_batch_manifest


def main() -> None:
    run_smoke_test_main(
        parse_args=_parse_args,
        run_structured_scenario=_run_structured_scenario,
        run_unstructured_scenario=_run_unstructured_scenario,
        run_batch_scenario=_run_batch_scenario,
    )


if __name__ == "__main__":
    main()
