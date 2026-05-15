from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from power_atlas.bootstrap import build_runtime_config, build_settings


def build_smoke_test_config(output_dir: Path) -> Any:
    settings = build_settings()
    return build_runtime_config(settings, dry_run=True, output_dir=output_dir)


def run_structured_smoke_scenario(
    output_dir: Path,
    *,
    build_config: Callable[[Path], Any] = build_smoke_test_config,
    request_context_from_config: Callable[..., Any],
    run_independent_demo: Callable[[Any, str], Path],
    validate_independent_manifest: Callable[[Path, str, str], None],
) -> Path:
    config = build_config(output_dir)
    request_context = request_context_from_config(config, command="ingest-structured")
    manifest_path = run_independent_demo(request_context, "ingest-structured")
    validate_independent_manifest(
        manifest_path,
        expected_stage="structured_ingest",
        expected_run_scope_key="structured_ingest_run_id",
    )
    return manifest_path


def run_unstructured_smoke_scenario(
    output_dir: Path,
    *,
    build_config: Callable[[Path], Any] = build_smoke_test_config,
    request_context_from_config: Callable[..., Any],
    run_independent_demo: Callable[[Any, str], Path],
    validate_independent_manifest: Callable[[Path, str, str], None],
) -> Path:
    config = build_config(output_dir)
    request_context = request_context_from_config(config, command="ingest-pdf")
    manifest_path = run_independent_demo(request_context, "ingest-pdf")
    validate_independent_manifest(
        manifest_path,
        expected_stage="pdf_ingest",
        expected_run_scope_key="unstructured_ingest_run_id",
    )
    return manifest_path


def run_batch_smoke_scenario(
    output_dir: Path,
    *,
    build_config: Callable[[Path], Any] = build_smoke_test_config,
    request_context_from_config: Callable[..., Any],
    run_demo: Callable[[Any], Path],
    validate_batch_manifest: Callable[[Path], None],
) -> Path:
    config = build_config(output_dir)
    request_context = request_context_from_config(config, command="ingest")
    manifest_path = run_demo(request_context)
    validate_batch_manifest(manifest_path)
    return manifest_path


__all__ = [
    "build_smoke_test_config",
    "run_batch_smoke_scenario",
    "run_structured_smoke_scenario",
    "run_unstructured_smoke_scenario",
]