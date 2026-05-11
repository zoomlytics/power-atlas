"""Post-hybrid retrieval benchmark stage compatibility shell.

The package-owned retrieval benchmark runtime now lives in
``power_atlas.retrieval_benchmark_runner``. This stage module keeps the legacy
import surface for direct tests, standalone scripts, and compatibility callers
that still import benchmark helpers from ``demo.stages.retrieval_benchmark``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from power_atlas.context import RequestContext
from power_atlas.retrieval_benchmark_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    neo4j_settings_from_request_context as _neo4j_settings_from_request_context,
    run_retrieval_benchmark as _run_retrieval_benchmark,
    run_retrieval_benchmark_request_context as _run_retrieval_benchmark_request_context,
)
from power_atlas.retrieval_benchmark_runner import (
    BENCHMARK_CASES,
    BenchmarkCaseDefinition,
    BenchmarkCaseResult,
    PairwiseCaseResult,
    RetrievalBenchmarkArtifact,
    _Q_CANONICAL_SINGLE,
    _Q_CATALOG_EXISTENCE_CHECK,
    _Q_LOWER_LAYER_CHAIN,
    _Q_PAIRWISE_CANONICAL,
    _classify_fragmentation_type,
    _compute_benchmark_summary,
    _count_distinct,
    _count_distinct_claims,
    _count_distinct_clusters,
    _detect_fragmentation,
    _records_to_dicts,
    build_benchmark_artifact,
    build_benchmark_case_result,
    run_retrieval_benchmark_runtime as _run_retrieval_benchmark_runtime_impl,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "BENCHMARK_CASES",
    "BenchmarkCaseDefinition",
    "BenchmarkCaseResult",
    "PairwiseCaseResult",
    "RetrievalBenchmarkArtifact",
    "build_benchmark_case_result",
    "build_benchmark_artifact",
    "run_retrieval_benchmark",
    "run_retrieval_benchmark_request_context",
    "_Q_CATALOG_EXISTENCE_CHECK",
]


def _run_retrieval_benchmark_impl(
    *,
    dry_run: bool,
    output_dir: Path,
    neo4j_settings: Any | None,
    run_id: str | None = None,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    benchmark_cases: list[BenchmarkCaseDefinition] | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, Any]:
    return _run_retrieval_benchmark_runtime_impl(
        dry_run=dry_run,
        output_dir=output_dir,
        neo4j_settings=neo4j_settings,
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        benchmark_cases=benchmark_cases,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        logger=_logger,
    )


def run_retrieval_benchmark(
    config: Any,
    *,
    run_id: str | None = None,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    benchmark_cases: list[BenchmarkCaseDefinition] | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, Any]:
    return _run_retrieval_benchmark(
        config,
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        output_dir=output_dir,
        benchmark_cases=benchmark_cases,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        impl_runner=_run_retrieval_benchmark_impl,
    )


def run_retrieval_benchmark_request_context(
    request_context: RequestContext,
    *,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    output_dir: Path | None = None,
    benchmark_cases: list[BenchmarkCaseDefinition] | None = None,
    suppress_alignment_version_warning: bool = False,
) -> dict[str, Any]:
    return _run_retrieval_benchmark_request_context(
        request_context,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        output_dir=output_dir,
        benchmark_cases=benchmark_cases,
        suppress_alignment_version_warning=suppress_alignment_version_warning,
        impl_runner=_run_retrieval_benchmark_impl,
    )
