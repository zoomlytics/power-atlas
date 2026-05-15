from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str = "neo4j://localhost:7687"
    username: str = "neo4j"
    password: str = "CHANGE_ME_BEFORE_USE"
    database: str = "neo4j"


@dataclass(frozen=True)
class AppSettingsEnvNames:
    neo4j_uri: str = "NEO4J_URI"
    neo4j_username: str = "NEO4J_USERNAME"
    neo4j_password: str = "NEO4J_PASSWORD"
    neo4j_database: str = "NEO4J_DATABASE"
    openai_model: str = "OPENAI_MODEL"
    embedder_model_primary: str = "POWER_ATLAS_EMBEDDER_MODEL"
    embedder_model_fallback: str = "OPENAI_EMBEDDER_MODEL"
    output_dir: str = "POWER_ATLAS_OUTPUT_DIR"
    dataset_name_primary: str = "POWER_ATLAS_DATASET"
    dataset_name_fallback: str = "FIXTURE_DATASET"


DEFAULT_APP_SETTINGS_ENV_NAMES = AppSettingsEnvNames()


@dataclass(frozen=True)
class AppSettings:
    neo4j: Neo4jSettings
    openai_model: str = "gpt-5.4"
    embedder_model: str = "text-embedding-3-small"
    output_dir: Path = Path("artifacts")
    dataset_name: str | None = None

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        env_names: AppSettingsEnvNames | None = None,
    ) -> "AppSettings":
        env = dict(os.environ if environ is None else environ)
        resolved_env_names = (
            DEFAULT_APP_SETTINGS_ENV_NAMES if env_names is None else env_names
        )
        output_dir = Path(
            env.get(resolved_env_names.output_dir, "artifacts")
        ).expanduser()
        dataset_name = (
            env.get(resolved_env_names.dataset_name_primary)
            or env.get(resolved_env_names.dataset_name_fallback)
            or None
        )
        neo4j = Neo4jSettings(
            uri=env.get(resolved_env_names.neo4j_uri, Neo4jSettings.uri),
            username=env.get(resolved_env_names.neo4j_username, Neo4jSettings.username),
            password=env.get(resolved_env_names.neo4j_password, Neo4jSettings.password),
            database=env.get(resolved_env_names.neo4j_database, Neo4jSettings.database),
        )
        return cls(
            neo4j=neo4j,
            openai_model=env.get(resolved_env_names.openai_model, cls.openai_model),
            embedder_model=(
                env.get(resolved_env_names.embedder_model_primary)
                or env.get(resolved_env_names.embedder_model_fallback)
                or cls.embedder_model
            ),
            output_dir=output_dir,
            dataset_name=dataset_name,
        )


__all__ = [
    "AppSettings",
    "AppSettingsEnvNames",
    "DEFAULT_APP_SETTINGS_ENV_NAMES",
    "Neo4jSettings",
]
