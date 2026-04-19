from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from power_atlas.context import RequestContext


def run_orchestrated_request_context(
    request_context: RequestContext,
    *,
    resolve_dataset_root: Callable[[str], object],
    build_orchestrated_run_plan: Callable[..., object],
    make_run_id: Callable[[str], str],
    now_iso: Callable[[], str],
    run_pdf_ingest_request_context: Callable[..., dict[str, Any]],
    extract_pdf_source_uri: Callable[[dict[str, Any] | object], str | None],
    scope_request_context: Callable[..., RequestContext],
    run_claim_extraction_request_context: Callable[[RequestContext], dict[str, Any]],
    run_claim_participation_request_context: Callable[[RequestContext], dict[str, Any]],
    run_entity_resolution_request_context: Callable[..., dict[str, Any]],
    run_retrieval_request_context: Callable[..., dict[str, Any]],
    run_structured_ingest_request_context: Callable[..., dict[str, Any]],
    run_retrieval_benchmark: Callable[..., dict[str, Any]],
    emit_stage_warnings: Callable[[Any, list[tuple[str, object]]], None],
    build_batch_manifest: Callable[..., dict[str, Any]],
    write_batch_manifest_artifacts: Callable[..., Path],
    logger,
    format_traceback: Callable[[], str],
) -> Path:
    config = request_context.config
    config.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = resolve_dataset_root(config.dataset_name)
    plan = build_orchestrated_run_plan(
        request_context,
        dataset_id=dataset_root.dataset_id,
        fixture_dir=dataset_root.root,
        pdf_filename=dataset_root.pdf_filename,
        started_at=now_iso(),
        structured_run_id=make_run_id("structured_ingest"),
        unstructured_run_id=make_run_id("unstructured_ingest"),
    )

    pdf_stage = run_pdf_ingest_request_context(
        plan.unstructured_request_context,
        fixtures_dir=plan.fixture_dir,
        pdf_filename=plan.pdf_filename,
        dataset_id=plan.dataset_id,
    )
    pdf_source_uri = extract_pdf_source_uri(pdf_stage)
    scoped_unstructured_request_context = scope_request_context(
        plan.request_context,
        run_id=plan.unstructured_run_id,
        source_uri=pdf_source_uri,
    )

    claim_stage = run_claim_extraction_request_context(scoped_unstructured_request_context)
    claim_participation_stage = run_claim_participation_request_context(
        scoped_unstructured_request_context
    )
    entity_resolution_unstructured_stage = run_entity_resolution_request_context(
        scoped_unstructured_request_context,
        resolution_mode="unstructured_only",
        artifact_subdir="entity_resolution_unstructured_only",
        dataset_id=plan.dataset_id,
    )
    retrieval_unstructured_stage = run_retrieval_request_context(
        scoped_unstructured_request_context,
        question=plan.question,
    )

    structured_stage = run_structured_ingest_request_context(
        plan.structured_request_context,
        fixtures_dir=plan.fixture_dir,
        dataset_id=plan.dataset_id,
    )
    entity_resolution_hybrid_stage = run_entity_resolution_request_context(
        scoped_unstructured_request_context,
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution_hybrid",
        dataset_id=plan.dataset_id,
    )
    retrieval_stage = run_retrieval_request_context(
        scoped_unstructured_request_context,
        question=plan.question,
    )

    hybrid_alignment_version: str | None = (
        entity_resolution_hybrid_stage.get("alignment_version")
        if isinstance(entity_resolution_hybrid_stage, dict)
        else None
    )
    if hybrid_alignment_version is None:
        logger.warning(
            "Orchestrated retrieval benchmark: alignment_version was not forwarded from the "
            "hybrid entity resolution stage (got None). The benchmark will aggregate across "
            "ALL alignment versions in the database rather than scoping to the current "
            "alignment cohort. If this is unexpected, check that the hybrid stage completed "
            "successfully and returned an 'alignment_version' key."
        )
    try:
        benchmark_stage = run_retrieval_benchmark(
            config,
            run_id=plan.unstructured_run_id,
            dataset_id=plan.dataset_id,
            alignment_version=hybrid_alignment_version,
            output_dir=config.output_dir,
            suppress_alignment_version_warning=hybrid_alignment_version is None,
        )
    except Exception as benchmark_exc:  # noqa: BLE001
        tb = format_traceback()
        logger.error(
            "retrieval_benchmark failed; manifest will be written with error status. %s", tb
        )
        benchmark_stage = {
            "status": "error",
            "error": str(benchmark_exc),
            "traceback": tb,
        }

    emit_stage_warnings(
        logger,
        [
            ("pdf_ingest", pdf_stage),
            ("claim_and_mention_extraction", claim_stage),
            ("claim_participation", claim_participation_stage),
            ("entity_resolution_unstructured_only", entity_resolution_unstructured_stage),
            ("retrieval_and_qa_unstructured_only", retrieval_unstructured_stage),
            ("structured_ingest", structured_stage),
            ("entity_resolution_hybrid", entity_resolution_hybrid_stage),
            ("retrieval_and_qa", retrieval_stage),
            ("retrieval_benchmark", benchmark_stage),
        ],
    )

    manifest = build_batch_manifest(
        config=config,
        structured_run_id=plan.structured_run_id,
        unstructured_run_id=plan.unstructured_run_id,
        structured_stage=structured_stage,
        pdf_stage=pdf_stage,
        claim_stage=claim_stage,
        claim_participation_stage=claim_participation_stage,
        entity_resolution_unstructured_stage=entity_resolution_unstructured_stage,
        retrieval_unstructured_stage=retrieval_unstructured_stage,
        entity_resolution_hybrid_stage=entity_resolution_hybrid_stage,
        retrieval_stage=retrieval_stage,
        retrieval_benchmark_stage=benchmark_stage,
        dataset_id=plan.dataset_id,
        started_at=plan.started_at,
        finished_at=now_iso(),
    )

    return write_batch_manifest_artifacts(config.output_dir, manifest=manifest)


__all__ = ["run_orchestrated_request_context"]