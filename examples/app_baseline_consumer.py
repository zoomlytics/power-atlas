from __future__ import annotations

import json
import tempfile
from pathlib import Path

from power_atlas.bootstrap import (
    AppSettingsEnvNames,
    bootstrap_app,
    build_request_context,
    resolve_app_baseline,
)
from power_atlas.contracts import RepoPaths


def build_example_payload() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        host_app_root = Path(tmp_dir) / "host_app"
        pipeline_config_path = host_app_root / "config" / "pipeline.yaml"
        pipeline_config_path.parent.mkdir(parents=True)
        pipeline_config_path.write_text(
            """
contract:
  chunk_embedding:
    index_name: host_app_chunk_index
    label: HostChunk
    embedding_property: host_embedding
    dimensions: 1024
embedder_config:
  params_:
    model: text-embedding-3-large
text_splitter:
  params_:
    chunk_size: 900
    chunk_overlap: 150
""".strip(),
            encoding="utf-8",
        )

        repo_paths = RepoPaths(
            base_dir=host_app_root,
            fixtures_dir=host_app_root / "fixtures",
            artifacts_dir=host_app_root / "artifacts",
            config_dir=host_app_root / "config",
            pdf_pipeline_config_path=pipeline_config_path,
            datasets_container_dir=host_app_root / "fixtures" / "datasets",
        )
        env_names = AppSettingsEnvNames(
            neo4j_uri="HOSTAPP_NEO4J_URI",
            neo4j_username="HOSTAPP_NEO4J_USERNAME",
            neo4j_password="HOSTAPP_NEO4J_PASSWORD",
            neo4j_database="HOSTAPP_NEO4J_DATABASE",
            openai_model="HOSTAPP_OPENAI_MODEL",
            embedder_model_primary="HOSTAPP_EMBEDDER_MODEL",
            output_dir="HOSTAPP_OUTPUT_DIR",
            dataset_name_primary="HOSTAPP_DATASET",
            dataset_name_fallback="HOSTAPP_LEGACY_DATASET",
        )
        baseline = resolve_app_baseline(env_names=env_names, repo_paths=repo_paths)

        app = bootstrap_app(
            {
                "HOSTAPP_NEO4J_URI": "bolt://host-app.test:7687",
                "HOSTAPP_NEO4J_USERNAME": "host-user",
                "HOSTAPP_NEO4J_PASSWORD": "host-secret",
                "HOSTAPP_NEO4J_DATABASE": "host-db",
                "HOSTAPP_OPENAI_MODEL": "gpt-5.4",
                "HOSTAPP_EMBEDDER_MODEL": "text-embedding-3-large",
                "HOSTAPP_OUTPUT_DIR": str(host_app_root / "build"),
                "HOSTAPP_DATASET": "host_dataset_v1",
            },
            app_baseline=baseline,
        )
        request_context = build_request_context(
            app.app_context,
            command="ask",
            dry_run=True,
            question="Which host-app baseline was applied?",
            run_id="host-app-run-id",
            source_uri="file:///host-app/source.pdf",
        )

        return {
            "consumer": "app_baseline_consumer",
            "baseline": {
                "dataset_env": baseline.env_names.dataset_name_primary,
                "legacy_dataset_env": baseline.env_names.dataset_name_fallback,
                "config_dir": str(baseline.repo_paths.config_dir),
                "pipeline_config_path": str(baseline.pipeline_contract_source.config_path),
            },
            "settings": {
                "neo4j_uri": app.settings.neo4j.uri,
                "output_dir": str(app.settings.output_dir),
                "dataset_name": app.settings.dataset_name,
            },
            "pipeline_contract": {
                "chunk_embedding_index_name": app.app_context.pipeline_contract.chunk_embedding_index_name,
                "chunk_embedding_label": app.app_context.pipeline_contract.chunk_embedding_label,
                "chunk_embedding_property": app.app_context.pipeline_contract.chunk_embedding_property,
                "chunk_embedding_dimensions": app.app_context.pipeline_contract.chunk_embedding_dimensions,
                "embedder_model_name": app.app_context.pipeline_contract.embedder_model_name,
                "chunk_fallback_stride": app.app_context.pipeline_contract.chunk_fallback_stride,
            },
            "request_context": {
                "command": request_context.command,
                "question": request_context.config.question,
                "run_id": request_context.run_id,
                "dataset_name": request_context.config.dataset_name,
                "source_uri": request_context.source_uri,
            },
        }


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))