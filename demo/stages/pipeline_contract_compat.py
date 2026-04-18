from __future__ import annotations

from typing import Any

from power_atlas.contracts.pipeline import get_pipeline_contract_snapshot


def get_stage_pipeline_contract_value(
    name: str,
    snapshot_exports: dict[str, str],
) -> Any:
    snapshot = get_pipeline_contract_snapshot()
    return getattr(snapshot, snapshot_exports[name])


def get_stage_pipeline_contract_attr(
    module_name: str,
    name: str,
    snapshot_exports: dict[str, str],
) -> Any:
    if name in snapshot_exports:
        return get_stage_pipeline_contract_value(name, snapshot_exports)
    raise AttributeError(f"module {module_name!r} has no attribute {name!r}")


__all__ = [
    "get_stage_pipeline_contract_attr",
    "get_stage_pipeline_contract_value",
]