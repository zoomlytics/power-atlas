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
class AppSettings:
    neo4j: Neo4jSettings
    openai_model: str = "gpt-5.4"
    output_dir: Path = Path("artifacts")
    dataset_name: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AppSettings":
        env = dict(os.environ if environ is None else environ)
        output_dir = Path(env.get("POWER_ATLAS_OUTPUT_DIR", "artifacts")).expanduser()
        dataset_name = env.get("POWER_ATLAS_DATASET") or env.get("FIXTURE_DATASET") or None
        neo4j = Neo4jSettings(
            uri=env.get("NEO4J_URI", Neo4jSettings.uri),
            username=env.get("NEO4J_USERNAME", Neo4jSettings.username),
            password=env.get("NEO4J_PASSWORD", Neo4jSettings.password),
            database=env.get("NEO4J_DATABASE", Neo4jSettings.database),
        )
        return cls(
            neo4j=neo4j,
            openai_model=env.get("OPENAI_MODEL", cls.openai_model),
            output_dir=output_dir,
            dataset_name=dataset_name,
        )


__all__ = ["AppSettings", "Neo4jSettings"]
