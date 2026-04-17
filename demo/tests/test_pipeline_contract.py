from __future__ import annotations

from copy import deepcopy
import logging

import pytest
import yaml

import power_atlas.contracts.pipeline as pipeline


@pytest.fixture(autouse=True)
def isolate_pipeline_contract(monkeypatch):
    original_path = pipeline.PDF_PIPELINE_CONFIG_PATH
    contract_was_loaded = pipeline._PIPELINE_CONTRACT_LOADED.is_set()
    original_state = {
        "PIPELINE_CONFIG_DATA": deepcopy(pipeline._PIPELINE_CONFIG_DATA),
        "CHUNK_EMBEDDING_INDEX_NAME": pipeline._CHUNK_EMBEDDING_INDEX_NAME,
        "CHUNK_EMBEDDING_LABEL": pipeline._CHUNK_EMBEDDING_LABEL,
        "CHUNK_EMBEDDING_PROPERTY": pipeline._CHUNK_EMBEDDING_PROPERTY,
        "CHUNK_EMBEDDING_DIMENSIONS": pipeline._CHUNK_EMBEDDING_DIMENSIONS,
        "EMBEDDER_MODEL_NAME": pipeline._EMBEDDER_MODEL_NAME,
        "CHUNK_FALLBACK_STRIDE": pipeline._CHUNK_FALLBACK_STRIDE,
        "DATASET_ID": pipeline._DATASET_ID,
    }
    try:
        yield
    finally:
        pipeline.PDF_PIPELINE_CONFIG_PATH = original_path
        pipeline._PIPELINE_CONFIG_DATA = deepcopy(original_state["PIPELINE_CONFIG_DATA"])
        pipeline._CHUNK_EMBEDDING_INDEX_NAME = original_state["CHUNK_EMBEDDING_INDEX_NAME"]
        pipeline._CHUNK_EMBEDDING_LABEL = original_state["CHUNK_EMBEDDING_LABEL"]
        pipeline._CHUNK_EMBEDDING_PROPERTY = original_state["CHUNK_EMBEDDING_PROPERTY"]
        pipeline._CHUNK_EMBEDDING_DIMENSIONS = original_state["CHUNK_EMBEDDING_DIMENSIONS"]
        pipeline._EMBEDDER_MODEL_NAME = original_state["EMBEDDER_MODEL_NAME"]
        pipeline._CHUNK_FALLBACK_STRIDE = original_state["CHUNK_FALLBACK_STRIDE"]
        pipeline._DATASET_ID = original_state["DATASET_ID"]
        if contract_was_loaded:
            pipeline._PIPELINE_CONTRACT_LOADED.set()
        else:
            pipeline._PIPELINE_CONTRACT_LOADED.clear()


def _reset_contract_state() -> None:
    pipeline._PIPELINE_CONFIG_DATA = {}
    pipeline._PIPELINE_CONTRACT_LOADED.clear()
    pipeline._CHUNK_EMBEDDING_INDEX_NAME = pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
    pipeline._CHUNK_EMBEDDING_LABEL = pipeline._DEFAULT_CHUNK_EMBEDDING_LABEL
    pipeline._CHUNK_EMBEDDING_PROPERTY = pipeline._DEFAULT_CHUNK_EMBEDDING_PROPERTY
    pipeline._CHUNK_EMBEDDING_DIMENSIONS = pipeline._DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    pipeline._EMBEDDER_MODEL_NAME = pipeline._DEFAULT_EMBEDDER_MODEL_NAME
    pipeline._CHUNK_FALLBACK_STRIDE = max(pipeline._DEFAULT_CHUNK_SIZE - pipeline._DEFAULT_CHUNK_OVERLAP, 1)
    pipeline._DATASET_ID = pipeline._DEFAULT_DATASET_ID


def test_refresh_pipeline_contract_applies_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "contract": {
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

    assert pipeline._CHUNK_EMBEDDING_INDEX_NAME == "custom_index"
    assert pipeline._CHUNK_EMBEDDING_LABEL == "CustomLabel"
    assert pipeline._CHUNK_EMBEDDING_PROPERTY == "custom_prop"
    assert pipeline._CHUNK_EMBEDDING_DIMENSIONS == 2048
    assert pipeline._EMBEDDER_MODEL_NAME == "text-embedding-3-large"
    assert pipeline._CHUNK_FALLBACK_STRIDE == 180
    assert pipeline._DATASET_ID == "custom_dataset"
    assert pipeline._PIPELINE_CONFIG_DATA["contract"]["chunk_embedding"]["dimensions"] == "2048"


def test_refresh_pipeline_contract_falls_back_on_invalid_types(tmp_path, monkeypatch):
    config_path = tmp_path / "pipeline_invalid.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "contract": {
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

    assert pipeline._CHUNK_EMBEDDING_INDEX_NAME == pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
    assert pipeline._CHUNK_EMBEDDING_LABEL == pipeline._DEFAULT_CHUNK_EMBEDDING_LABEL
    assert pipeline._CHUNK_EMBEDDING_PROPERTY == pipeline._DEFAULT_CHUNK_EMBEDDING_PROPERTY
    assert pipeline._CHUNK_EMBEDDING_DIMENSIONS == pipeline._DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    assert pipeline._EMBEDDER_MODEL_NAME == pipeline._DEFAULT_EMBEDDER_MODEL_NAME
    assert pipeline._CHUNK_FALLBACK_STRIDE == max(pipeline._DEFAULT_CHUNK_SIZE - pipeline._DEFAULT_CHUNK_OVERLAP, 1)
    assert pipeline._DATASET_ID == pipeline._DEFAULT_DATASET_ID


def test_coerce_identifier_strips_and_accepts_valid():
    assert pipeline._coerce_identifier("  Foo_1 ", "default", "field") == "Foo_1"


def test_coerce_identifier_warns_and_falls_back(
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.WARNING, logger="demo.contracts.pipeline"):
        result = pipeline._coerce_identifier("invalid space", "default", "field")
    assert result == "default"
    assert caplog.records
    assert any(
        record.levelno == logging.WARNING
        and record.name == "demo.contracts.pipeline"
        and "identifier-safe string" in record.getMessage()
        for record in caplog.records
    )


def test_dataset_state_accessors_emit_deprecation_warnings() -> None:
    _reset_contract_state()

    with pytest.deprecated_call(match=r"get_dataset_id\(\) is deprecated"):
        assert pipeline.get_dataset_id() == pipeline._DEFAULT_DATASET_ID

    with pytest.deprecated_call(match=r"set_dataset_id\(\) is deprecated"):
        pipeline.set_dataset_id("compat_dataset")

    assert pipeline._DATASET_ID == "compat_dataset"


def test_dataset_id_module_attribute_emits_deprecation_warnings() -> None:
    _reset_contract_state()

    with pytest.deprecated_call(match="DATASET_ID is deprecated"):
        assert pipeline.DATASET_ID == pipeline._DEFAULT_DATASET_ID

    with pytest.deprecated_call(match="DATASET_ID is deprecated"):
        pipeline.DATASET_ID = "compat_dataset"

    assert pipeline._DATASET_ID == "compat_dataset"


def test_pipeline_contract_snapshot_reflects_current_values() -> None:
    _reset_contract_state()
    pipeline._CHUNK_EMBEDDING_INDEX_NAME = "snapshot_index"
    pipeline._CHUNK_EMBEDDING_LABEL = "SnapshotChunk"
    pipeline._CHUNK_EMBEDDING_PROPERTY = "snapshot_embedding"
    pipeline._CHUNK_EMBEDDING_DIMENSIONS = 3072
    pipeline._EMBEDDER_MODEL_NAME = "text-embedding-3-large"
    pipeline._CHUNK_FALLBACK_STRIDE = 256

    snapshot = pipeline.get_pipeline_contract_snapshot()

    assert snapshot.chunk_embedding_index_name == "snapshot_index"
    assert snapshot.chunk_embedding_label == "SnapshotChunk"
    assert snapshot.chunk_embedding_property == "snapshot_embedding"
    assert snapshot.chunk_embedding_dimensions == 3072
    assert snapshot.embedder_model_name == "text-embedding-3-large"
    assert snapshot.chunk_fallback_stride == 256


def test_pipeline_contract_config_data_getter_returns_copy() -> None:
    _reset_contract_state()
    pipeline._PIPELINE_CONFIG_DATA = {"contract": {"chunk_embedding": {"index_name": "demo_index"}}}

    result = pipeline.get_pipeline_contract_config_data()

    assert result == {"contract": {"chunk_embedding": {"index_name": "demo_index"}}}
    assert result is not pipeline._PIPELINE_CONFIG_DATA


def test_non_dataset_pipeline_compat_exports_emit_deprecation_warnings() -> None:
    _reset_contract_state()

    with pytest.deprecated_call(match="CHUNK_EMBEDDING_INDEX_NAME is deprecated"):
        assert pipeline.CHUNK_EMBEDDING_INDEX_NAME == pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME

    with pytest.deprecated_call(match="PIPELINE_CONFIG_DATA is deprecated"):
        assert pipeline.PIPELINE_CONFIG_DATA == {}

    with pytest.deprecated_call(match="EMBEDDER_MODEL_NAME is deprecated"):
        pipeline.EMBEDDER_MODEL_NAME = "compat-model"

    assert pipeline._EMBEDDER_MODEL_NAME == "compat-model"
