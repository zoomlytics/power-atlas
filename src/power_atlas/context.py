from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from power_atlas.contracts.claim_extraction_policy import (
    ClaimExtractionPolicy,
    get_default_claim_extraction_policy,
)
from power_atlas.contracts.entity_type_normalization_policy import (
    EntityTypeNormalizationPolicy,
    get_default_entity_type_normalization_policy,
)
from power_atlas.contracts.pipeline import PipelineContractSnapshot, is_pipeline_contract_snapshot
from power_atlas.contracts.retrieval_policy import RetrievalPolicy, get_default_retrieval_policy
from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppPolicies:
    retrieval: RetrievalPolicy
    claim_extraction: ClaimExtractionPolicy
    entity_type_normalization: EntityTypeNormalizationPolicy


def build_default_app_policies(
    *,
    retrieval: RetrievalPolicy | None = None,
    claim_extraction: ClaimExtractionPolicy | None = None,
    entity_type_normalization: EntityTypeNormalizationPolicy | None = None,
) -> AppPolicies:
    return AppPolicies(
        retrieval=get_default_retrieval_policy() if retrieval is None else retrieval,
        claim_extraction=(
            get_default_claim_extraction_policy()
            if claim_extraction is None
            else claim_extraction
        ),
        entity_type_normalization=(
            get_default_entity_type_normalization_policy()
            if entity_type_normalization is None
            else entity_type_normalization
        ),
    )


@dataclass(frozen=True)
class AppContext:
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]
    policies: AppPolicies


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


__all__ = ["AppContext", "AppPolicies", "RequestContext", "build_default_app_policies"]