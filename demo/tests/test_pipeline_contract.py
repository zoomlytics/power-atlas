from __future__ import annotations

from copy import deepcopy
import importlib
import logging

import pytest
import yaml

import power_atlas.contracts.pipeline as pipeline


@pytest.fixture(autouse=True)
def isolate_pipeline_contract(monkeypatch):
    original_path = pipeline.PDF_PIPELINE_CONFIG_PATH
    contract_was_loaded = pipeline._PIPELINE_CONTRACT_LOADED.is_set()
    original_state = pipeline._get_pipeline_contract_state_for_test()
    try:
        yield
    finally:
        pipeline.PDF_PIPELINE_CONFIG_PATH = original_path
        pipeline._set_pipeline_contract_state_for_test(
            config_data=original_state.config_data,
            chunk_embedding_index_name=original_state.snapshot.chunk_embedding_index_name,
            chunk_embedding_label=original_state.snapshot.chunk_embedding_label,
            chunk_embedding_property=original_state.snapshot.chunk_embedding_property,
            chunk_embedding_dimensions=original_state.snapshot.chunk_embedding_dimensions,
            embedder_model_name=original_state.snapshot.embedder_model_name,
            chunk_fallback_stride=original_state.snapshot.chunk_fallback_stride,
        )
        if contract_was_loaded:
            pipeline._PIPELINE_CONTRACT_LOADED.set()
        else:
            pipeline._PIPELINE_CONTRACT_LOADED.clear()


def _reset_contract_state() -> None:
    pipeline._reset_pipeline_contract_state_for_test()
    pipeline._PIPELINE_CONTRACT_LOADED.clear()


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
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "PDF_PIPELINE_CONFIG_PATH", config_path)
    _reset_contract_state()

    pipeline.refresh_pipeline_contract()

    snapshot = pipeline.get_pipeline_contract_snapshot()
    assert snapshot.chunk_embedding_index_name == "custom_index"
    assert snapshot.chunk_embedding_label == "CustomLabel"
    assert snapshot.chunk_embedding_property == "custom_prop"
    assert snapshot.chunk_embedding_dimensions == 2048
    assert snapshot.embedder_model_name == "text-embedding-3-large"
    assert snapshot.chunk_fallback_stride == 180
    assert pipeline.get_pipeline_contract_config_data()["contract"]["chunk_embedding"]["dimensions"] == "2048"


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
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "PDF_PIPELINE_CONFIG_PATH", config_path)
    _reset_contract_state()

    pipeline.refresh_pipeline_contract()

    snapshot = pipeline.get_pipeline_contract_snapshot()
    assert snapshot.chunk_embedding_index_name == pipeline._DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
    assert snapshot.chunk_embedding_label == pipeline._DEFAULT_CHUNK_EMBEDDING_LABEL
    assert snapshot.chunk_embedding_property == pipeline._DEFAULT_CHUNK_EMBEDDING_PROPERTY
    assert snapshot.chunk_embedding_dimensions == pipeline._DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    assert snapshot.embedder_model_name == pipeline._DEFAULT_EMBEDDER_MODEL_NAME
    assert snapshot.chunk_fallback_stride == max(pipeline._DEFAULT_CHUNK_SIZE - pipeline._DEFAULT_CHUNK_OVERLAP, 1)


def test_pipeline_contract_module_import_is_lazy(monkeypatch):
    safe_load_calls = 0
    original_path = pipeline.PDF_PIPELINE_CONFIG_PATH
    real_safe_load = yaml.safe_load

    def tracking_safe_load(*args, **kwargs):
        nonlocal safe_load_calls
        safe_load_calls += 1
        return real_safe_load(*args, **kwargs)

    monkeypatch.setattr(yaml, "safe_load", tracking_safe_load)
    pipeline.PDF_PIPELINE_CONFIG_PATH = original_path
    _reset_contract_state()

    try:
        importlib.reload(pipeline)

        assert not pipeline._PIPELINE_CONTRACT_LOADED.is_set()
        assert safe_load_calls == 0

        snapshot = pipeline.get_pipeline_contract_snapshot()

        assert pipeline._PIPELINE_CONTRACT_LOADED.is_set()
        assert safe_load_calls == 1
        assert snapshot.chunk_embedding_index_name
    finally:
        monkeypatch.setattr(yaml, "safe_load", real_safe_load)
        importlib.reload(pipeline)


def test_coerce_identifier_strips_and_accepts_valid():
    assert pipeline._coerce_identifier("  Foo_1 ", "default", "field") == "Foo_1"


def test_coerce_identifier_warns_and_falls_back(
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.WARNING, logger="power_atlas.contracts.pipeline"):
        result = pipeline._coerce_identifier("invalid space", "default", "field")
    assert result == "default"
    assert caplog.records
    assert any(
        record.levelno == logging.WARNING
        and record.name == "power_atlas.contracts.pipeline"
        and "identifier-safe string" in record.getMessage()
        for record in caplog.records
    )


def test_dataset_state_compat_api_is_removed() -> None:
    assert not hasattr(pipeline, "DATASET_ID")
    assert not hasattr(pipeline, "get_dataset_id")
    assert not hasattr(pipeline, "set_dataset_id")


def test_pipeline_contract_snapshot_reflects_current_values() -> None:
    _reset_contract_state()
    pipeline._set_pipeline_contract_state_for_test(
        chunk_embedding_index_name="snapshot_index",
        chunk_embedding_label="SnapshotChunk",
        chunk_embedding_property="snapshot_embedding",
        chunk_embedding_dimensions=3072,
        embedder_model_name="text-embedding-3-large",
        chunk_fallback_stride=256,
    )

    snapshot = pipeline.get_pipeline_contract_snapshot()

    assert snapshot.chunk_embedding_index_name == "snapshot_index"
    assert snapshot.chunk_embedding_label == "SnapshotChunk"
    assert snapshot.chunk_embedding_property == "snapshot_embedding"
    assert snapshot.chunk_embedding_dimensions == 3072
    assert snapshot.embedder_model_name == "text-embedding-3-large"
    assert snapshot.chunk_fallback_stride == 256


def test_pipeline_contract_config_data_getter_returns_copy() -> None:
    _reset_contract_state()
    pipeline._set_pipeline_contract_state_for_test(
        config_data={"contract": {"chunk_embedding": {"index_name": "demo_index"}}}
    )

    result = pipeline.get_pipeline_contract_config_data()

    assert result == {"contract": {"chunk_embedding": {"index_name": "demo_index"}}}
    assert result is not pipeline.get_pipeline_contract_config_data()


def test_non_dataset_pipeline_compat_exports_are_removed() -> None:
    assert not hasattr(pipeline, "PIPELINE_CONFIG_DATA")
    assert not hasattr(pipeline, "CHUNK_EMBEDDING_INDEX_NAME")
    assert not hasattr(pipeline, "CHUNK_EMBEDDING_LABEL")
    assert not hasattr(pipeline, "CHUNK_EMBEDDING_PROPERTY")
    assert not hasattr(pipeline, "CHUNK_EMBEDDING_DIMENSIONS")
    assert not hasattr(pipeline, "EMBEDDER_MODEL_NAME")
    assert not hasattr(pipeline, "CHUNK_FALLBACK_STRIDE")


def test_private_pipeline_compat_exports_are_removed() -> None:
    assert not hasattr(pipeline, "_PIPELINE_CONFIG_DATA")
    assert not hasattr(pipeline, "_CHUNK_EMBEDDING_INDEX_NAME")
    assert not hasattr(pipeline, "_CHUNK_EMBEDDING_LABEL")
    assert not hasattr(pipeline, "_CHUNK_EMBEDDING_PROPERTY")
    assert not hasattr(pipeline, "_CHUNK_EMBEDDING_DIMENSIONS")
    assert not hasattr(pipeline, "_EMBEDDER_MODEL_NAME")
    assert not hasattr(pipeline, "_CHUNK_FALLBACK_STRIDE")
