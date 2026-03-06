from __future__ import annotations

from copy import deepcopy
import warnings

import pytest
import yaml

from demo.contracts import pipeline


@pytest.fixture(autouse=True)
def isolate_pipeline_contract(monkeypatch):
    original_path = pipeline.PDF_PIPELINE_CONFIG_PATH
    contract_was_loaded = pipeline._PIPELINE_CONTRACT_LOADED.is_set()
    original_state = {
        "PIPELINE_CONFIG_DATA": deepcopy(pipeline.PIPELINE_CONFIG_DATA),
        "CHUNK_EMBEDDING_INDEX_NAME": pipeline.CHUNK_EMBEDDING_INDEX_NAME,
        "CHUNK_EMBEDDING_LABEL": pipeline.CHUNK_EMBEDDING_LABEL,
        "CHUNK_EMBEDDING_PROPERTY": pipeline.CHUNK_EMBEDDING_PROPERTY,
        "CHUNK_EMBEDDING_DIMENSIONS": pipeline.CHUNK_EMBEDDING_DIMENSIONS,
        "EMBEDDER_MODEL_NAME": pipeline.EMBEDDER_MODEL_NAME,
        "CHUNK_FALLBACK_STRIDE": pipeline.CHUNK_FALLBACK_STRIDE,
        "DATASET_ID": pipeline.DATASET_ID,
    }
    try:
        yield
    finally:
        pipeline.PDF_PIPELINE_CONFIG_PATH = original_path
        pipeline.PIPELINE_CONFIG_DATA = deepcopy(original_state["PIPELINE_CONFIG_DATA"])
        pipeline.CHUNK_EMBEDDING_INDEX_NAME = original_state["CHUNK_EMBEDDING_INDEX_NAME"]
        pipeline.CHUNK_EMBEDDING_LABEL = original_state["CHUNK_EMBEDDING_LABEL"]
        pipeline.CHUNK_EMBEDDING_PROPERTY = original_state["CHUNK_EMBEDDING_PROPERTY"]
        pipeline.CHUNK_EMBEDDING_DIMENSIONS = original_state["CHUNK_EMBEDDING_DIMENSIONS"]
        pipeline.EMBEDDER_MODEL_NAME = original_state["EMBEDDER_MODEL_NAME"]
        pipeline.CHUNK_FALLBACK_STRIDE = original_state["CHUNK_FALLBACK_STRIDE"]
        pipeline.DATASET_ID = original_state["DATASET_ID"]
        if contract_was_loaded:
            pipeline._PIPELINE_CONTRACT_LOADED.set()
        else:
            pipeline._PIPELINE_CONTRACT_LOADED.clear()


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


def test_coerce_identifier_strips_and_accepts_valid():
    assert pipeline._coerce_identifier("  Foo_1 ", "default", "field") == "Foo_1"


def test_coerce_identifier_warns_and_falls_back(monkeypatch):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = pipeline._coerce_identifier("invalid space", "default", "field")
    assert result == "default"
    assert caught
    warning = caught[0]
    assert issubclass(warning.category, RuntimeWarning)
    assert warning.filename.endswith("test_pipeline_contract.py")
    assert "identifier-safe string" in str(warning.message)
