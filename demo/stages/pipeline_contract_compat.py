from __future__ import annotations

from typing import Any

from power_atlas.contracts.pipeline import PipelineContractSnapshot


def get_stage_pipeline_contract_value(
    name: str,
    snapshot_exports: dict[str, str],
    pipeline_contract: PipelineContractSnapshot,
) -> Any:
    return getattr(pipeline_contract, snapshot_exports[name])


__all__ = [
    "get_stage_pipeline_contract_value",
]