from __future__ import annotations

import yaml

from demo.chain_of_custody.contracts import pipeline


def _reset_contract_state() -> None:
    pipeline.PIPELINE_CONFIG_DATA = {}
    pipeline._PIPELINE_CONTRACT_LOADED.clear()
    pipeline.CHUNK_EMBEDDING_INDEX_NAME = pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
    pipeline.CHUNK_EMBEDDING_LABEL = pipeline._DEFAULT_CHUNK_EMBEDDING_LABEL
    pipeline.CHUNK_EMBEDDING_PROPERTY = pipeline._DEFAULT_CHUNK_EMBEDDING_PROPERTY
    pipeline.CHUNK_EMBEDDING_DIMENSIONS = pipeline._DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    pipeline.EMBEDDER_MODEL_NAME = pipeline._DEFAULT_EMBEDDER_MODEL_NAME
    pipeline.CHUNK_FALLBACK_STRIDE = max(pipeline._DEFAULT_CHUNK_SIZE - pipeline._DEFAULT_CHUNK_OVERLAP, 1)
    pipeline.DATASET_ID = pipeline._DEFAULT_DATASET_ID


def test_refresh_pipeline_contract_applies_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "demo_contract": {
                    "chunk_embedding": {
                        "index_name": "custom_index",
                        "label": "CustomLabel",
                        "embedding_property": "custom_prop",
                        "dimensions": "2048",
                    }
                },
                "embedder_config": {"params_": {"model": "text-embedding-3-large"}},
                "text_splitter": {"params_": {"chunk_size": 200, "chunk_overlap": 20}},
                "kg_writer": {"params_": {"dataset_id": "custom_dataset"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "PDF_PIPELINE_CONFIG_PATH", config_path)
    _reset_contract_state()

    pipeline.refresh_pipeline_contract()

    assert pipeline.CHUNK_EMBEDDING_INDEX_NAME == "custom_index"
    assert pipeline.CHUNK_EMBEDDING_LABEL == "CustomLabel"
    assert pipeline.CHUNK_EMBEDDING_PROPERTY == "custom_prop"
    assert pipeline.CHUNK_EMBEDDING_DIMENSIONS == 2048
    assert pipeline.EMBEDDER_MODEL_NAME == "text-embedding-3-large"
    assert pipeline.CHUNK_FALLBACK_STRIDE == 180
    assert pipeline.DATASET_ID == "custom_dataset"
    assert pipeline.PIPELINE_CONFIG_DATA["demo_contract"]["chunk_embedding"]["dimensions"] == "2048"


def test_refresh_pipeline_contract_falls_back_on_invalid_types(tmp_path, monkeypatch):
    config_path = tmp_path / "pipeline_invalid.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "demo_contract": {
                    "chunk_embedding": {
                        "index_name": None,
                        "label": 123,
                        "embedding_property": "",
                        "dimensions": "not-a-number",
                    }
                },
                "embedder_config": {"params_": {"model": 123}},
                "text_splitter": {"params_": {"chunk_size": "bad", "chunk_overlap": "bad"}},
                "kg_writer": {"params_": {"dataset_id": 0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "PDF_PIPELINE_CONFIG_PATH", config_path)
    _reset_contract_state()

    pipeline.refresh_pipeline_contract()

    assert pipeline.CHUNK_EMBEDDING_INDEX_NAME == pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
    assert pipeline.CHUNK_EMBEDDING_LABEL == pipeline._DEFAULT_CHUNK_EMBEDDING_LABEL
    assert pipeline.CHUNK_EMBEDDING_PROPERTY == pipeline._DEFAULT_CHUNK_EMBEDDING_PROPERTY
    assert pipeline.CHUNK_EMBEDDING_DIMENSIONS == pipeline._DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    assert pipeline.EMBEDDER_MODEL_NAME == pipeline._DEFAULT_EMBEDDER_MODEL_NAME
    assert pipeline.CHUNK_FALLBACK_STRIDE == max(pipeline._DEFAULT_CHUNK_SIZE - pipeline._DEFAULT_CHUNK_OVERLAP, 1)
    assert pipeline.DATASET_ID == pipeline._DEFAULT_DATASET_ID
