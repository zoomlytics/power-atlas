from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DemoStageEntrypoints:
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]]
    format_scope_label: Callable[[str | None, bool], str]
    run_claim_and_mention_extraction_request_context: Callable[..., dict[str, Any]]
    run_claim_participation_request_context: Callable[..., dict[str, Any]]
    run_entity_resolution_request_context: Callable[..., dict[str, Any]]
    run_pdf_ingest_request_context: Callable[..., dict[str, Any]]
    run_structured_ingest_request_context: Callable[..., dict[str, Any]]
    run_interactive_qa_request_context: Callable[..., Any]
    run_retrieval_and_qa_request_context: Callable[..., dict[str, Any]]
    run_retrieval_benchmark: Callable[..., dict[str, Any]]
    sha256_file: Callable[..., str]


def load_demo_stage_entrypoints() -> DemoStageEntrypoints:
    from demo.stages.claim_extraction import run_claim_and_mention_extraction_request_context
    from demo.stages.claim_participation import run_claim_participation_request_context
    from demo.stages.entity_resolution import run_entity_resolution_request_context
    from demo.stages.pdf_ingest import run_pdf_ingest_request_context, sha256_file
    from demo.stages.retrieval_and_qa import (
        _format_scope_label,
        run_interactive_qa_request_context,
        run_retrieval_and_qa_request_context,
    )
    from demo.stages.retrieval_benchmark import run_retrieval_benchmark
    from demo.stages.structured_ingest import (
        lint_and_clean_structured_csvs,
        run_structured_ingest_request_context,
    )

    return DemoStageEntrypoints(
        lint_and_clean_structured_csvs=lint_and_clean_structured_csvs,
        format_scope_label=_format_scope_label,
        run_claim_and_mention_extraction_request_context=run_claim_and_mention_extraction_request_context,
        run_claim_participation_request_context=run_claim_participation_request_context,
        run_entity_resolution_request_context=run_entity_resolution_request_context,
        run_pdf_ingest_request_context=run_pdf_ingest_request_context,
        run_structured_ingest_request_context=run_structured_ingest_request_context,
        run_interactive_qa_request_context=run_interactive_qa_request_context,
        run_retrieval_and_qa_request_context=run_retrieval_and_qa_request_context,
        run_retrieval_benchmark=run_retrieval_benchmark,
        sha256_file=sha256_file,
    )


__all__ = ["DemoStageEntrypoints", "load_demo_stage_entrypoints"]