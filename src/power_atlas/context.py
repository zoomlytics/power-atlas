from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from power_atlas.contracts.pipeline import PipelineContractSnapshot, is_pipeline_contract_snapshot
from power_atlas.contracts.runtime import Config
from power_atlas.runtime_carriers import (
    AppPolicies,
    AppRuntime,
    RequestRuntime,
    build_default_app_policies,
)
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppContext:
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]
    policies: AppPolicies

    @property
    def runtime(self) -> AppRuntime:
        return AppRuntime(
            settings=self.settings,
            pipeline_contract=self.pipeline_contract,
            pipeline_contract_config_data=self.pipeline_contract_config_data,
            policies=self.policies,
        )


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
        app_pipeline_contract = getattr(self.app, "pipeline_contract", None)
        if is_pipeline_contract_snapshot(app_pipeline_contract):
            return app_pipeline_contract
        config_pipeline_contract = getattr(self.config, "pipeline_contract", None)
        if is_pipeline_contract_snapshot(config_pipeline_contract):
            return config_pipeline_contract
        raise ValueError(
            "RequestContext requires a pipeline contract on app or config runtime state"
        )

    @property
    def policies(self) -> AppPolicies:
        return self.app.policies

    @property
    def runtime(self) -> RequestRuntime:
        return RequestRuntime(
            config=self.config,
            settings=self.settings,
            pipeline_contract=self.pipeline_contract,
            pipeline_contract_config_data=self.app.pipeline_contract_config_data,
            policies=self.policies,
            run_id=self.run_id,
            all_runs=self.all_runs,
            source_uri=self.source_uri,
        )


__all__ = [
    "AppContext",
    "AppPolicies",
    "AppRuntime",
    "RequestContext",
    "RequestRuntime",
    "build_default_app_policies",
]