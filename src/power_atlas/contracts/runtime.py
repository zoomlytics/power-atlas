from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from power_atlas.contracts.pipeline import (
    PipelineContractSnapshot,
    get_pipeline_contract_config_data,
    get_pipeline_contract_snapshot,
)


@dataclass(frozen=True)
class Config:
    dry_run: bool
    output_dir: Path
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    openai_model: str
    question: str | None = None
    resolution_mode: str = "unstructured_only"
    dataset_name: str | None = None
    pipeline_contract: PipelineContractSnapshot = field(default_factory=get_pipeline_contract_snapshot)
    pipeline_contract_config_data: dict[str, Any] = field(default_factory=get_pipeline_contract_config_data)


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def make_run_id(scope: str) -> str:
    return f"{scope}-{timestamp()}-{uuid4().hex[:8]}"


__all__ = ["Config", "make_run_id", "timestamp"]