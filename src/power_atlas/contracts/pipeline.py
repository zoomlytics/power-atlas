from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
import re
import threading
from typing import Any

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
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_PIPELINE_CONTRACT_LOADED = threading.Event()
_PIPELINE_CONTRACT_LOCK = threading.Lock()


@dataclass(frozen=True)
class PipelineContractSnapshot:
    chunk_embedding_index_name: str
    chunk_embedding_label: str
    chunk_embedding_property: str
    chunk_embedding_dimensions: int
    embedder_model_name: str
    chunk_fallback_stride: int


@dataclass(frozen=True)
class _PipelineContractState:
    config_data: dict[str, Any]
    snapshot: PipelineContractSnapshot


_UNSET = object()


def _default_pipeline_contract_snapshot() -> PipelineContractSnapshot:
    return PipelineContractSnapshot(
        chunk_embedding_index_name=_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME,
        chunk_embedding_label=_DEFAULT_CHUNK_EMBEDDING_LABEL,
        chunk_embedding_property=_DEFAULT_CHUNK_EMBEDDING_PROPERTY,
        chunk_embedding_dimensions=_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS,
        embedder_model_name=_DEFAULT_EMBEDDER_MODEL_NAME,
        chunk_fallback_stride=max(_DEFAULT_CHUNK_SIZE - _DEFAULT_CHUNK_OVERLAP, 1),
    )


_PIPELINE_CONTRACT_STATE = _PipelineContractState(
    config_data={},
    snapshot=_default_pipeline_contract_snapshot(),
)


def _get_pipeline_contract_state_for_test() -> _PipelineContractState:
    return deepcopy(_PIPELINE_CONTRACT_STATE)


def _set_pipeline_contract_state_for_test(
    *,
    config_data: dict[str, Any] | object = _UNSET,
    chunk_embedding_index_name: str | object = _UNSET,
    chunk_embedding_label: str | object = _UNSET,
    chunk_embedding_property: str | object = _UNSET,
    chunk_embedding_dimensions: int | object = _UNSET,
    embedder_model_name: str | object = _UNSET,
    chunk_fallback_stride: int | object = _UNSET,
) -> None:
    global _PIPELINE_CONTRACT_STATE
    current_snapshot = _PIPELINE_CONTRACT_STATE.snapshot
    _PIPELINE_CONTRACT_STATE = _PipelineContractState(
        config_data=(
            deepcopy(_PIPELINE_CONTRACT_STATE.config_data)
            if config_data is _UNSET
            else deepcopy(config_data)
        ),
        snapshot=PipelineContractSnapshot(
            chunk_embedding_index_name=(
                current_snapshot.chunk_embedding_index_name
                if chunk_embedding_index_name is _UNSET
                else str(chunk_embedding_index_name)
            ),
            chunk_embedding_label=(
                current_snapshot.chunk_embedding_label
                if chunk_embedding_label is _UNSET
                else str(chunk_embedding_label)
            ),
            chunk_embedding_property=(
                current_snapshot.chunk_embedding_property
                if chunk_embedding_property is _UNSET
                else str(chunk_embedding_property)
            ),
            chunk_embedding_dimensions=(
                current_snapshot.chunk_embedding_dimensions
                if chunk_embedding_dimensions is _UNSET
                else int(chunk_embedding_dimensions)
            ),
            embedder_model_name=(
                current_snapshot.embedder_model_name
                if embedder_model_name is _UNSET
                else str(embedder_model_name)
            ),
            chunk_fallback_stride=(
                current_snapshot.chunk_fallback_stride
                if chunk_fallback_stride is _UNSET
                else int(chunk_fallback_stride)
            ),
        ),
    )


def _reset_pipeline_contract_state_for_test() -> None:
    global _PIPELINE_CONTRACT_STATE
    _PIPELINE_CONTRACT_STATE = _PipelineContractState(
        config_data={},
        snapshot=_default_pipeline_contract_snapshot(),
    )


def refresh_pipeline_contract() -> None:
    """Force a reload of the pipeline contract from disk, even if already loaded."""
    global _PIPELINE_CONTRACT_STATE
    with _PIPELINE_CONTRACT_LOCK:
        _PIPELINE_CONTRACT_STATE = _load_pipeline_contract()
        _PIPELINE_CONTRACT_LOADED.set()


def ensure_pipeline_contract_loaded() -> None:
    """Load the pipeline contract once in a thread-safe way."""
    global _PIPELINE_CONTRACT_STATE
    with _PIPELINE_CONTRACT_LOCK:
        if not _PIPELINE_CONTRACT_LOADED.is_set():
            _PIPELINE_CONTRACT_STATE = _load_pipeline_contract()
            _PIPELINE_CONTRACT_LOADED.set()


def get_pipeline_contract_snapshot() -> PipelineContractSnapshot:
    """Return an immutable snapshot of the current non-dataset pipeline contract values."""
    return _PIPELINE_CONTRACT_STATE.snapshot


def get_pipeline_contract_config_data() -> dict[str, Any]:
    """Return a defensive copy of the loaded raw pipeline contract config data."""
    return deepcopy(_PIPELINE_CONTRACT_STATE.config_data)


def _load_pipeline_contract() -> _PipelineContractState:
    """Internal helper that reads the pipeline contract from disk and returns a new cached state."""
    config_data: dict[str, Any] = {}
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
        config_data = cfg_data if cfg_is_mapping else {}

    pipeline_contract = config_data.get("contract") if isinstance(config_data, dict) else {}
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

    chunk_embedding_index_name = _coerce_identifier(
        chunk_embedding_contract.get("index_name"),
        _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME,
        "chunk_embedding.index_name",
    )
    chunk_embedding_label = _coerce_identifier(
        chunk_embedding_contract.get("label"),
        _DEFAULT_CHUNK_EMBEDDING_LABEL,
        "chunk_embedding.label",
    )
    chunk_embedding_property = _coerce_identifier(
        chunk_embedding_contract.get("embedding_property"),
        _DEFAULT_CHUNK_EMBEDDING_PROPERTY,
        "chunk_embedding.embedding_property",
    )

    dimensions_value = chunk_embedding_contract.get("dimensions")
    if dimensions_value is not None:
        try:
            chunk_embedding_dimensions = int(dimensions_value)
        except (TypeError, ValueError):
            chunk_embedding_dimensions = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    else:
        chunk_embedding_dimensions = _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
    embedder_model_name = _DEFAULT_EMBEDDER_MODEL_NAME
    embedder_config = config_data.get("embedder_config", {})
    if isinstance(embedder_config, dict):
        embedder_params = embedder_config.get("params_")
        if isinstance(embedder_params, dict):
            embedder_model = embedder_params.get("model")
            if isinstance(embedder_model, str):
                embedder_model_name = embedder_model

    text_splitter_config = config_data.get("text_splitter", {})
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
    return _PipelineContractState(
        config_data=config_data,
        snapshot=PipelineContractSnapshot(
            chunk_embedding_index_name=chunk_embedding_index_name,
            chunk_embedding_label=chunk_embedding_label,
            chunk_embedding_property=chunk_embedding_property,
            chunk_embedding_dimensions=chunk_embedding_dimensions,
            embedder_model_name=embedder_model_name,
            chunk_fallback_stride=max(chunk_size - chunk_overlap, 1),
        ),
    )


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

__all__ = [
    "PipelineContractSnapshot",
    "ensure_pipeline_contract_loaded",
    "get_pipeline_contract_config_data",
    "get_pipeline_contract_snapshot",
    "refresh_pipeline_contract",
]