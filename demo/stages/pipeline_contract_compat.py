from __future__ import annotations

from typing import Any

from power_atlas.contracts.pipeline import PipelineContractSnapshot, get_pipeline_contract_snapshot


def get_stage_pipeline_contract_value(
    name: str,
    snapshot_exports: dict[str, str],
    pipeline_contract: PipelineContractSnapshot | None = None,
) -> Any:
    snapshot = get_pipeline_contract_snapshot() if pipeline_contract is None else pipeline_contract
    return getattr(snapshot, snapshot_exports[name])


__all__ = [
    "get_stage_pipeline_contract_value",
]