from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "lint_and_clean_structured_csvs",
    "load_csv_rows",
    "run_claim_participation",
    "run_graph_health_diagnostics",
    "run_structured_ingest",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import proxy
    if name in {"lint_and_clean_structured_csvs", "load_csv_rows", "run_structured_ingest"}:
        module = import_module("demo.stages.structured_ingest")
    elif name == "run_claim_participation":
        module = import_module("demo.stages.claim_participation")
    elif name == "run_graph_health_diagnostics":
        module = import_module("demo.stages.graph_health")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - thin import proxy
    return sorted(__all__)
