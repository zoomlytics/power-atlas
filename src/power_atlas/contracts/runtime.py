from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.settings import AppSettings, Neo4jSettings


@dataclass(frozen=True)
class Config:
    dry_run: bool
    output_dir: Path
    settings: AppSettings
    pipeline_contract: PipelineContractSnapshot
    pipeline_contract_config_data: dict[str, Any]
    question: str | None = None
    resolution_mode: str = "unstructured_only"
    dataset_name: str | None = None

    def __init__(
        self,
        *,
        dry_run: bool,
        output_dir: Path,
        pipeline_contract: PipelineContractSnapshot,
        pipeline_contract_config_data: dict[str, Any],
        settings: AppSettings | None = None,
        neo4j_uri: str | None = None,
        neo4j_username: str | None = None,
        neo4j_password: str | None = None,
        neo4j_database: str | None = None,
        openai_model: str | None = None,
        question: str | None = None,
        resolution_mode: str = "unstructured_only",
        dataset_name: str | None = None,
    ) -> None:
        resolved_settings = settings
        if resolved_settings is None:
            if None in (
                neo4j_uri,
                neo4j_username,
                neo4j_password,
                neo4j_database,
                openai_model,
            ):
                raise TypeError(
                    "Config requires settings or explicit neo4j/openai runtime values"
                )
            resolved_settings = AppSettings(
                neo4j=Neo4jSettings(
                    uri=neo4j_uri,
                    username=neo4j_username,
                    password=neo4j_password,
                    database=neo4j_database,
                ),
                openai_model=openai_model,
                output_dir=output_dir,
                dataset_name=dataset_name,
            )
        resolved_dataset_name = (
            resolved_settings.dataset_name if dataset_name is None else dataset_name
        )
        resolved_settings = replace(
            resolved_settings,
            output_dir=output_dir,
            dataset_name=resolved_dataset_name,
        )
        object.__setattr__(self, "dry_run", dry_run)
        object.__setattr__(self, "output_dir", output_dir)
        object.__setattr__(self, "settings", resolved_settings)
        object.__setattr__(self, "pipeline_contract", pipeline_contract)
        object.__setattr__(
            self,
            "pipeline_contract_config_data",
            dict(pipeline_contract_config_data),
        )
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "resolution_mode", resolution_mode)
        object.__setattr__(self, "dataset_name", resolved_dataset_name)

    @property
    def neo4j_uri(self) -> str:
        return self.settings.neo4j.uri

    @property
    def neo4j_username(self) -> str:
        return self.settings.neo4j.username

    @property
    def neo4j_password(self) -> str:
        return self.settings.neo4j.password

    @property
    def neo4j_database(self) -> str:
        return self.settings.neo4j.database

    @property
    def openai_model(self) -> str:
        return self.settings.openai_model


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def make_run_id(scope: str) -> str:
    return f"{scope}-{timestamp()}-{uuid4().hex[:8]}"


__all__ = ["Config", "make_run_id", "timestamp"]