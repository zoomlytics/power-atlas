from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppContext:
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]


@dataclass(frozen=True)
class RequestContext:
    app: AppContext
    config: Config
    command: str | None = None
    run_id: str | None = None
    all_runs: bool = False
    source_uri: str | None = None

    @property
    def settings(self) -> AppSettings:
        return self.app.settings

    @property
    def pipeline_contract(self) -> PipelineContractSnapshot:
        return self.app.pipeline_contract


__all__ = ["AppContext", "RequestContext"]