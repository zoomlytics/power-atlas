from __future__ import annotations

from typing import Any

from power_atlas.contracts.pipeline import get_pipeline_contract_snapshot


def get_stage_pipeline_contract_value(
    name: str,
    snapshot_exports: dict[str, str],
) -> Any:
    snapshot = get_pipeline_contract_snapshot()
    return getattr(snapshot, snapshot_exports[name])


__all__ = [
    "get_stage_pipeline_contract_value",
]