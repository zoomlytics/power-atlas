from __future__ import annotations

import os
import warnings
from typing import Any

import yaml

from demo.chain_of_custody.contracts.paths import PDF_PIPELINE_CONFIG_PATH

DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")
_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 0
_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME = "chain_custody_chunk_embedding_index"
_DEFAULT_CHUNK_EMBEDDING_LABEL = "Chunk"
_DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS = 1536
_DEFAULT_EMBEDDER_MODEL_NAME = "text-embedding-3-small"
_DEFAULT_DATASET_ID = "chain_of_custody_dataset_v1"

PIPELINE_CONFIG_DATA: dict[str, Any] = {}
CHUNK_EMBEDDING_INDEX_NAME = _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
CHUNK_EMBEDDING_LABEL = _DEFAULT_CHUNK_EMBEDDING_LABEL
CHUNK_EMBEDDING_PROPERTY = _DEFAULT_CHUNK_EMBEDDING_PROPERTY
CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
CHUNK_FALLBACK_STRIDE = max(_DEFAULT_CHUNK_SIZE - _DEFAULT_CHUNK_OVERLAP, 1)
DATASET_ID = _DEFAULT_DATASET_ID


def refresh_pipeline_contract() -> None:
    global PIPELINE_CONFIG_DATA, CHUNK_EMBEDDING_INDEX_NAME, CHUNK_EMBEDDING_LABEL, CHUNK_EMBEDDING_PROPERTY
    global CHUNK_EMBEDDING_DIMENSIONS, EMBEDDER_MODEL_NAME, CHUNK_FALLBACK_STRIDE, DATASET_ID

    PIPELINE_CONFIG_DATA = {}
    if PDF_PIPELINE_CONFIG_PATH.is_file():
        cfg_data: Any = {}
        try:
            with PDF_PIPELINE_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                cfg_data = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - defensive logging
            warnings.warn(
                f"Falling back to default chunk embedding contract; unable to load {PDF_PIPELINE_CONFIG_PATH}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            cfg_data = {}
        cfg_is_mapping = isinstance(cfg_data, dict)
        if not cfg_is_mapping:  # pragma: no cover - defensive logging
            warnings.warn(
                f"Falling back to default chunk embedding contract; expected mapping at top-level in {PDF_PIPELINE_CONFIG_PATH}, "
                f"got {type(cfg_data).__name__}",
                RuntimeWarning,
                stacklevel=2,
            )
            cfg_data = {}
        PIPELINE_CONFIG_DATA = cfg_data if cfg_is_mapping else {}

    demo_contract = PIPELINE_CONFIG_DATA.get("demo_contract") if isinstance(PIPELINE_CONFIG_DATA, dict) else {}
    if demo_contract is None:
        demo_contract = {}
    elif not isinstance(demo_contract, dict):  # pragma: no cover - defensive logging
        warnings.warn(
            f"Falling back to default chunk embedding contract; expected mapping for demo_contract in {PDF_PIPELINE_CONFIG_PATH}, "
            f"got {type(demo_contract).__name__}",
            RuntimeWarning,
            stacklevel=2,
        )
        demo_contract = {}

    chunk_embedding_contract = demo_contract.get("chunk_embedding")
    if chunk_embedding_contract is None:
        chunk_embedding_contract = {}
    elif not isinstance(chunk_embedding_contract, dict):  # pragma: no cover - defensive logging
        warnings.warn(
            f"Falling back to default chunk embedding contract; expected mapping for demo_contract.chunk_embedding in "
            f"{PDF_PIPELINE_CONFIG_PATH}, got {type(chunk_embedding_contract).__name__}",
            RuntimeWarning,
            stacklevel=2,
        )
        chunk_embedding_contract = {}

    CHUNK_EMBEDDING_INDEX_NAME = chunk_embedding_contract.get("index_name", _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME)
    CHUNK_EMBEDDING_LABEL = chunk_embedding_contract.get("label", _DEFAULT_CHUNK_EMBEDDING_LABEL)
    CHUNK_EMBEDDING_PROPERTY = chunk_embedding_contract.get("embedding_property", _DEFAULT_CHUNK_EMBEDDING_PROPERTY)
    CHUNK_EMBEDDING_DIMENSIONS = chunk_embedding_contract.get("dimensions", _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS)

    EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
    embedder_config = PIPELINE_CONFIG_DATA.get("embedder_config", {})
    if isinstance(embedder_config, dict):
        embedder_params = embedder_config.get("params_")
        if isinstance(embedder_params, dict):
            embedder_model = embedder_params.get("model")
            if isinstance(embedder_model, str):
                EMBEDDER_MODEL_NAME = embedder_model

    text_splitter_config = PIPELINE_CONFIG_DATA.get("text_splitter", {})
    chunk_size = _DEFAULT_CHUNK_SIZE
    chunk_overlap = _DEFAULT_CHUNK_OVERLAP
    if isinstance(text_splitter_config, dict):
        text_splitter_params = text_splitter_config.get("params_")
        if isinstance(text_splitter_params, dict):
            try:
                chunk_size = int(text_splitter_params.get("chunk_size"))
            except (TypeError, ValueError):
                chunk_size = _DEFAULT_CHUNK_SIZE
            try:
                chunk_overlap = int(text_splitter_params.get("chunk_overlap"))
            except (TypeError, ValueError):
                chunk_overlap = _DEFAULT_CHUNK_OVERLAP
    CHUNK_FALLBACK_STRIDE = max(chunk_size - chunk_overlap, 1)

    DATASET_ID = _DEFAULT_DATASET_ID
    kg_writer_config = PIPELINE_CONFIG_DATA.get("kg_writer")
    kg_writer_params = kg_writer_config.get("params_") if isinstance(kg_writer_config, dict) else {}
    cfg_dataset_id = kg_writer_params.get("dataset_id") if isinstance(kg_writer_params, dict) else None
    if isinstance(cfg_dataset_id, str) and cfg_dataset_id:
        DATASET_ID = cfg_dataset_id


__all__ = [
    "CHUNK_EMBEDDING_DIMENSIONS",
    "CHUNK_EMBEDDING_INDEX_NAME",
    "CHUNK_EMBEDDING_LABEL",
    "CHUNK_EMBEDDING_PROPERTY",
    "CHUNK_FALLBACK_STRIDE",
    "DATASET_ID",
    "DEFAULT_DB",
    "EMBEDDER_MODEL_NAME",
    "PIPELINE_CONFIG_DATA",
    "refresh_pipeline_contract",
]
