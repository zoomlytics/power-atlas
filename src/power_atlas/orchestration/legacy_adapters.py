from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def lint_and_clean_structured_csvs_legacy(
    run_id: str,
    output_dir: Path,
    *,
    resolve_dataset_root: Callable[..., object],
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    dataset_root = resolve_dataset_root()
    return lint_and_clean_structured_csvs(
        run_id=run_id,
        output_dir=output_dir,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )


def run_structured_ingest_legacy(
    config,
    run_id: str,
    *,
    resolve_dataset_root: Callable[[str], object],
    request_context_from_config: Callable[..., object],
    run_structured_ingest_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    dataset_root = resolve_dataset_root(config.dataset_name)
    return run_structured_ingest_request_context(
        request_context_from_config(config, command="ingest-structured", run_id=run_id),
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )


def run_pdf_ingest_legacy(
    config,
    run_id: str | None = None,
    *,
    resolve_dataset_root: Callable[[str], object],
    request_context_from_config: Callable[..., object],
    run_pdf_ingest_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    dataset_root = resolve_dataset_root(config.dataset_name)
    return run_pdf_ingest_request_context(
        request_context_from_config(config, command="ingest-pdf", run_id=run_id),
        fixtures_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        dataset_id=dataset_root.dataset_id,
    )


def run_claim_and_mention_extraction_legacy(
    config,
    *,
    run_id: str,
    source_uri: str | None,
    request_context_from_config: Callable[..., object],
    run_claim_extraction_request_context: Callable[[object], dict[str, Any]],
) -> dict[str, Any]:
    return run_claim_extraction_request_context(
        request_context_from_config(
            config,
            command="extract-claims",
            run_id=run_id,
            source_uri=source_uri,
        )
    )


def run_entity_resolution_legacy(
    config,
    *,
    run_id: str,
    source_uri: str | None = None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    request_context_from_config: Callable[..., object],
    run_entity_resolution_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return run_entity_resolution_request_context(
        request_context_from_config(
            config,
            command="resolve-entities",
            run_id=run_id,
            source_uri=source_uri,
        ),
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
    )


def run_retrieval_and_qa_legacy(
    config,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    question: str | None = None,
    cluster_aware: bool = False,
    expand_graph: bool = False,
    all_runs: bool = False,
    request_context_from_config: Callable[..., object],
    run_retrieval_request_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return run_retrieval_request_context(
        request_context_from_config(
            config,
            command="ask",
            run_id=run_id,
            all_runs=all_runs,
            source_uri=source_uri,
        ),
        question=question,
        cluster_aware=cluster_aware,
        expand_graph=expand_graph,
    )


__all__ = [
    "lint_and_clean_structured_csvs_legacy",
    "run_claim_and_mention_extraction_legacy",
    "run_entity_resolution_legacy",
    "run_pdf_ingest_legacy",
    "run_retrieval_and_qa_legacy",
    "run_structured_ingest_legacy",
]