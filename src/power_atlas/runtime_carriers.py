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
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.contracts.retrieval_policy import RetrievalPolicy, get_default_retrieval_policy
from power_atlas.contracts.runtime import Config
from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppPolicies:
    retrieval: RetrievalPolicy
    claim_extraction: ClaimExtractionPolicy
    entity_type_normalization: EntityTypeNormalizationPolicy


@dataclass(frozen=True)
class AppRuntime:
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]
    policies: AppPolicies


@dataclass(frozen=True)
class RequestRuntime:
    config: Config
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]
    policies: AppPolicies
    run_id: str | None = None
    all_runs: bool = False
    source_uri: str | None = None


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


__all__ = [
    "AppPolicies",
    "AppRuntime",
    "RequestRuntime",
    "build_default_app_policies",
]
