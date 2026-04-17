from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
import re
import sys
import threading
from types import ModuleType
from typing import Any
import warnings

import yaml

from power_atlas.contracts.paths import PDF_PIPELINE_CONFIG_PATH

_logger = logging.getLogger("demo.contracts.pipeline")

_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 0
_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME = "demo_chunk_embedding_index"
_DEFAULT_CHUNK_EMBEDDING_LABEL = "Chunk"
_DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS = 1536
_DEFAULT_EMBEDDER_MODEL_NAME = "text-embedding-3-small"
_DEFAULT_DATASET_ID = "demo_dataset_v1"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_PIPELINE_CONFIG_DATA: dict[str, Any] = {}
_PIPELINE_CONTRACT_LOADED = threading.Event()
_PIPELINE_CONTRACT_LOCK = threading.Lock()
_CHUNK_EMBEDDING_INDEX_NAME = _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
_CHUNK_EMBEDDING_LABEL = _DEFAULT_CHUNK_EMBEDDING_LABEL
_CHUNK_EMBEDDING_PROPERTY = _DEFAULT_CHUNK_EMBEDDING_PROPERTY
_CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
_EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
_CHUNK_FALLBACK_STRIDE = max(_DEFAULT_CHUNK_SIZE - _DEFAULT_CHUNK_OVERLAP, 1)
_DATASET_ID = _DEFAULT_DATASET_ID
_DATASET_STATE_DEPRECATION_MESSAGE = (
    "power_atlas.contracts.pipeline DATASET_ID/get_dataset_id()/set_dataset_id() are deprecated; "
    "pass dataset scope explicitly via stage/orchestrator arguments or injected context instead."
)
_PIPELINE_STATE_DEPRECATION_MESSAGE = (
    "Mutable pipeline contract globals are deprecated; use get_pipeline_contract_snapshot() for "
    "embedding/index settings or get_pipeline_contract_config_data() for raw config inspection instead."
)
_PIPELINE_COMPAT_ATTRS = {
    "PIPELINE_CONFIG_DATA": "_PIPELINE_CONFIG_DATA",
    "CHUNK_EMBEDDING_INDEX_NAME": "_CHUNK_EMBEDDING_INDEX_NAME",
    "CHUNK_EMBEDDING_LABEL": "_CHUNK_EMBEDDING_LABEL",
    "CHUNK_EMBEDDING_PROPERTY": "_CHUNK_EMBEDDING_PROPERTY",
    "CHUNK_EMBEDDING_DIMENSIONS": "_CHUNK_EMBEDDING_DIMENSIONS",
    "EMBEDDER_MODEL_NAME": "_EMBEDDER_MODEL_NAME",
    "CHUNK_FALLBACK_STRIDE": "_CHUNK_FALLBACK_STRIDE",
}


@dataclass(frozen=True)
class PipelineContractSnapshot:
    chunk_embedding_index_name: str
    chunk_embedding_label: str
    chunk_embedding_property: str
    chunk_embedding_dimensions: int
    embedder_model_name: str
    chunk_fallback_stride: int


def refresh_pipeline_contract() -> None:
    """Force a reload of the pipeline contract from disk, even if already loaded."""
    global _PIPELINE_CONFIG_DATA, _CHUNK_EMBEDDING_INDEX_NAME, _CHUNK_EMBEDDING_LABEL, _CHUNK_EMBEDDING_PROPERTY
    global _CHUNK_EMBEDDING_DIMENSIONS, _EMBEDDER_MODEL_NAME, _CHUNK_FALLBACK_STRIDE, _DATASET_ID
    with _PIPELINE_CONTRACT_LOCK:
        _load_pipeline_contract()
        _PIPELINE_CONTRACT_LOADED.set()


def set_dataset_id(dataset_id: str) -> None:
    """Deprecated compatibility shim for overriding the active dataset identifier."""
    global _DATASET_ID
    _warn_deprecated_dataset_state("set_dataset_id()")
    if isinstance(dataset_id, str) and dataset_id:
        with _PIPELINE_CONTRACT_LOCK:
            _DATASET_ID = dataset_id


def get_dataset_id() -> str:
    """Deprecated compatibility shim for reading the active dataset identifier."""
    _warn_deprecated_dataset_state("get_dataset_id()")
    return _DATASET_ID


def ensure_pipeline_contract_loaded() -> None:
    """Load the pipeline contract once in a thread-safe way."""
    with _PIPELINE_CONTRACT_LOCK:
        if not _PIPELINE_CONTRACT_LOADED.is_set():
            _load_pipeline_contract()
            _PIPELINE_CONTRACT_LOADED.set()


def get_pipeline_contract_snapshot() -> PipelineContractSnapshot:
    """Return an immutable snapshot of the current non-dataset pipeline contract values."""
    return PipelineContractSnapshot(
        chunk_embedding_index_name=_CHUNK_EMBEDDING_INDEX_NAME,
        chunk_embedding_label=_CHUNK_EMBEDDING_LABEL,
        chunk_embedding_property=_CHUNK_EMBEDDING_PROPERTY,
        chunk_embedding_dimensions=_CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model_name=_EMBEDDER_MODEL_NAME,
        chunk_fallback_stride=_CHUNK_FALLBACK_STRIDE,
    )


def get_pipeline_contract_config_data() -> dict[str, Any]:
    """Return a defensive copy of the loaded raw pipeline contract config data."""
    return deepcopy(_PIPELINE_CONFIG_DATA)


def _load_pipeline_contract() -> None:
    """Internal helper that reads the pipeline contract from disk and updates globals."""
    global _PIPELINE_CONFIG_DATA, _CHUNK_EMBEDDING_INDEX_NAME, _CHUNK_EMBEDDING_LABEL, _CHUNK_EMBEDDING_PROPERTY
    global _CHUNK_EMBEDDING_DIMENSIONS, _EMBEDDER_MODEL_NAME, _CHUNK_FALLBACK_STRIDE, _DATASET_ID

    _PIPELINE_CONFIG_DATA = {}
    if PDF_PIPELINE_CONFIG_PATH.is_file():
        cfg_data: Any = {}
        try:
            with PDF_PIPELINE_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                cfg_data = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError) as exc:
            _logger.warning(
                "Falling back to default chunk embedding contract; unable to load %s: %s",
                PDF_PIPELINE_CONFIG_PATH,
                exc,
            )
            cfg_data = {}
        cfg_is_mapping = isinstance(cfg_data, dict)
        if not cfg_is_mapping:
            _logger.warning(
                "Falling back to default chunk embedding contract; expected mapping at top-level in %s, got %s",
                PDF_PIPELINE_CONFIG_PATH,
                type(cfg_data).__name__,
            )
            cfg_data = {}
        _PIPELINE_CONFIG_DATA = cfg_data if cfg_is_mapping else {}

    pipeline_contract = _PIPELINE_CONFIG_DATA.get("contract") if isinstance(_PIPELINE_CONFIG_DATA, dict) else {}
    if pipeline_contract is None:
        pipeline_contract = {}
    elif not isinstance(pipeline_contract, dict):
        _logger.warning(
            "Falling back to default chunk embedding contract; expected mapping for contract in %s, got %s",
            PDF_PIPELINE_CONFIG_PATH,
            type(pipeline_contract).__name__,
        )
        pipeline_contract = {}

    chunk_embedding_contract = pipeline_contract.get("chunk_embedding")
    if chunk_embedding_contract is None:
        chunk_embedding_contract = {}
    elif not isinstance(chunk_embedding_contract, dict):
        _logger.warning(
            "Falling back to default chunk embedding contract; expected mapping for contract.chunk_embedding in %s, got %s",
            PDF_PIPELINE_CONFIG_PATH,
            type(chunk_embedding_contract).__name__,
        )
        chunk_embedding_contract = {}

    _CHUNK_EMBEDDING_INDEX_NAME = _coerce_identifier(
        chunk_embedding_contract.get("index_name"),
        _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME,
        "chunk_embedding.index_name",
    )
    _CHUNK_EMBEDDING_LABEL = _coerce_identifier(
        chunk_embedding_contract.get("label"),
        _DEFAULT_CHUNK_EMBEDDING_LABEL,
        "chunk_embedding.label",
    )
    _CHUNK_EMBEDDING_PROPERTY = _coerce_identifier(
        chunk_embedding_contract.get("embedding_property"),
        _DEFAULT_CHUNK_EMBEDDING_PROPERTY,
        "chunk_embedding.embedding_property",
    )

    dimensions_value = chunk_embedding_contract.get("dimensions")
    if dimensions_value is not None:
        try:
            _CHUNK_EMBEDDING_DIMENSIONS = int(dimensions_value)
        except (TypeError, ValueError):
            _CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    else:
        _CHUNK_EMBEDDING_DIMENSIONS = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    _EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
    embedder_config = _PIPELINE_CONFIG_DATA.get("embedder_config", {})
    if isinstance(embedder_config, dict):
        embedder_params = embedder_config.get("params_")
        if isinstance(embedder_params, dict):
            embedder_model = embedder_params.get("model")
            if isinstance(embedder_model, str):
                _EMBEDDER_MODEL_NAME = embedder_model

    text_splitter_config = _PIPELINE_CONFIG_DATA.get("text_splitter", {})
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
    _CHUNK_FALLBACK_STRIDE = max(chunk_size - chunk_overlap, 1)

    _DATASET_ID = _DEFAULT_DATASET_ID
    kg_writer_config = _PIPELINE_CONFIG_DATA.get("kg_writer")
    kg_writer_params = kg_writer_config.get("params_") if isinstance(kg_writer_config, dict) else {}
    cfg_dataset_id = kg_writer_params.get("dataset_id") if isinstance(kg_writer_params, dict) else None
    if isinstance(cfg_dataset_id, str) and cfg_dataset_id:
        _DATASET_ID = cfg_dataset_id


def _warn_deprecated_dataset_state(symbol_name: str) -> None:
    warnings.warn(
        f"{symbol_name} is deprecated. {_DATASET_STATE_DEPRECATION_MESSAGE}",
        DeprecationWarning,
        stacklevel=3,
    )


def _warn_deprecated_pipeline_state(symbol_name: str) -> None:
    warnings.warn(
        f"{symbol_name} is deprecated. {_PIPELINE_STATE_DEPRECATION_MESSAGE}",
        DeprecationWarning,
        stacklevel=3,
    )


class _PipelineModule(ModuleType):
    def __getattribute__(self, name: str) -> Any:
        if name == "DATASET_ID":
            _warn_deprecated_dataset_state("DATASET_ID")
            return super().__getattribute__("_DATASET_ID")
        if name in _PIPELINE_COMPAT_ATTRS:
            _warn_deprecated_pipeline_state(name)
            return super().__getattribute__(_PIPELINE_COMPAT_ATTRS[name])
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "DATASET_ID":
            _warn_deprecated_dataset_state("DATASET_ID")
            name = "_DATASET_ID"
        elif name in _PIPELINE_COMPAT_ATTRS:
            _warn_deprecated_pipeline_state(name)
            name = _PIPELINE_COMPAT_ATTRS[name]
        super().__setattr__(name, value)


def _coerce_identifier(value: Any, default: str, field_name: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and _IDENTIFIER_PATTERN.fullmatch(candidate):
            return candidate
        _logger.warning(
            "Falling back to default for %s; expected identifier-safe string, got %r",
            field_name,
            value,
        )
    return default


ensure_pipeline_contract_loaded()
sys.modules[__name__].__class__ = _PipelineModule


__all__ = [
    "CHUNK_EMBEDDING_DIMENSIONS",
    "CHUNK_EMBEDDING_INDEX_NAME",
    "CHUNK_EMBEDDING_LABEL",
    "CHUNK_EMBEDDING_PROPERTY",
    "CHUNK_FALLBACK_STRIDE",
    "DATASET_ID",
    "EMBEDDER_MODEL_NAME",
    "PipelineContractSnapshot",
    "PIPELINE_CONFIG_DATA",
    "ensure_pipeline_contract_loaded",
    "get_pipeline_contract_config_data",
    "get_pipeline_contract_snapshot",
    "refresh_pipeline_contract",
    "get_dataset_id",
    "set_dataset_id",
]