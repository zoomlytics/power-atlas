from __future__ import annotations

import os
import re
import threading
import warnings
from typing import Any

import yaml

from demo.contracts.paths import PDF_PIPELINE_CONFIG_PATH

DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")
_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 0
_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME = "chain_custody_chunk_embedding_index"
_DEFAULT_CHUNK_EMBEDDING_LABEL = "Chunk"
_DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS = 1536
_DEFAULT_EMBEDDER_MODEL_NAME = "text-embedding-3-small"
_DEFAULT_DATASET_ID = "chain_of_custody_dataset_v1"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PIPELINE_CONFIG_DATA: dict[str, Any] = {}
_PIPELINE_CONTRACT_LOADED = threading.Event()
_PIPELINE_CONTRACT_LOCK = threading.Lock()
CHUNK_EMBEDDING_INDEX_NAME = _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
CHUNK_EMBEDDING_LABEL = _DEFAULT_CHUNK_EMBEDDING_LABEL
CHUNK_EMBEDDING_PROPERTY = _DEFAULT_CHUNK_EMBEDDING_PROPERTY
CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
CHUNK_FALLBACK_STRIDE = max(_DEFAULT_CHUNK_SIZE - _DEFAULT_CHUNK_OVERLAP, 1)
DATASET_ID = _DEFAULT_DATASET_ID


def refresh_pipeline_contract() -> None:
    """Force a reload of the pipeline contract from disk, even if already loaded."""
    global PIPELINE_CONFIG_DATA, CHUNK_EMBEDDING_INDEX_NAME, CHUNK_EMBEDDING_LABEL, CHUNK_EMBEDDING_PROPERTY
    global CHUNK_EMBEDDING_DIMENSIONS, EMBEDDER_MODEL_NAME, CHUNK_FALLBACK_STRIDE, DATASET_ID
    with _PIPELINE_CONTRACT_LOCK:
        _load_pipeline_contract()
        _PIPELINE_CONTRACT_LOADED.set()


def ensure_pipeline_contract_loaded() -> None:
    """Load the pipeline contract once in a thread-safe way."""
    with _PIPELINE_CONTRACT_LOCK:
        if not _PIPELINE_CONTRACT_LOADED.is_set():
            _load_pipeline_contract()
            _PIPELINE_CONTRACT_LOADED.set()


def _load_pipeline_contract() -> None:
    """Internal helper that reads the pipeline contract from disk and updates globals."""
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

    CHUNK_EMBEDDING_INDEX_NAME = _coerce_identifier(
        chunk_embedding_contract.get("index_name"),
        _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME,
        "chunk_embedding.index_name",
    )
    CHUNK_EMBEDDING_LABEL = _coerce_identifier(
        chunk_embedding_contract.get("label"),
        _DEFAULT_CHUNK_EMBEDDING_LABEL,
        "chunk_embedding.label",
    )
    CHUNK_EMBEDDING_PROPERTY = _coerce_identifier(
        chunk_embedding_contract.get("embedding_property"),
        _DEFAULT_CHUNK_EMBEDDING_PROPERTY,
        "chunk_embedding.embedding_property",
    )

    dimensions_value = chunk_embedding_contract.get("dimensions")
    if dimensions_value is not None:
        try:
            CHUNK_EMBEDDING_DIMENSIONS = int(dimensions_value)
        except (TypeError, ValueError):
            CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    else:
        CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
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


def _coerce_identifier(value: Any, default: str, field_name: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and _IDENTIFIER_PATTERN.fullmatch(candidate):
            return candidate
        # stacklevel=2 surfaces warnings at the _coerce_identifier call sites while avoiding warnings module internals
        warnings.warn(
            f"Falling back to default for {field_name}; expected identifier-safe string, got {value!r}",
            RuntimeWarning,
            stacklevel=2,
        )
    return default


# Load once at import time so the exported constants reflect the configured contract.
# Module import is serialized by Python's import lock, so this one-time load is safe
# even when multiple threads import the package concurrently.
ensure_pipeline_contract_loaded()


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
    "ensure_pipeline_contract_loaded",
    "refresh_pipeline_contract",
]
