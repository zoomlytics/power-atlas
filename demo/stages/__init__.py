from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "lint_and_clean_structured_csvs",
    "load_csv_rows",
    "run_claim_and_mention_extraction",
    "run_claim_participation",
    "run_entity_resolution",
    "run_interactive_qa",
    "run_pdf_ingest",
    "run_retrieval_and_qa",
    "run_structured_ingest",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import proxy
    if name in {"lint_and_clean_structured_csvs", "load_csv_rows", "run_structured_ingest"}:
        module = import_module("demo.stages.structured_ingest")
    elif name == "run_pdf_ingest":
        module = import_module("demo.stages.pdf_ingest")
    elif name == "run_claim_and_mention_extraction":
        module = import_module("demo.stages.claim_extraction")
    elif name == "run_claim_participation":
        module = import_module("demo.stages.claim_participation")
    elif name == "run_entity_resolution":
        module = import_module("demo.stages.entity_resolution")
    elif name in {"run_retrieval_and_qa", "run_interactive_qa"}:
        module = import_module("demo.stages.retrieval_and_qa")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - thin import proxy
    return sorted(__all__)
