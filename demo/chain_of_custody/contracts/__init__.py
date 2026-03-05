from importlib import import_module
from typing import Any

from demo.chain_of_custody.contracts.manifest import build_batch_manifest, build_stage_manifest
from demo.chain_of_custody.contracts.paths import ARTIFACTS_DIR, CONFIG_DIR, FIXTURES_DIR, PDF_PIPELINE_CONFIG_PATH
from demo.chain_of_custody.contracts.pipeline import (
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
    CHUNK_FALLBACK_STRIDE,
    DATASET_ID,
    DEFAULT_DB,
    EMBEDDER_MODEL_NAME,
    PIPELINE_CONFIG_DATA,
    ensure_pipeline_contract_loaded,
)
from demo.chain_of_custody.contracts.prompts import PROMPT_IDS
from demo.chain_of_custody.contracts.runtime import DemoConfig, make_run_id, timestamp
from demo.chain_of_custody.contracts.structured import (
    COMMON_PREDICATE_LABELS,
    CSV_FIRST_DATA_ROW,
    ID_PATTERNS,
    STRUCTURED_FILE_HEADERS,
    VALUE_TYPES,
)

__all__ = [
    "ARTIFACTS_DIR",
    "build_batch_manifest",
    "build_stage_manifest",
    "claim_extraction_lexical_config",
    "claim_extraction_schema",
    "COMMON_PREDICATE_LABELS",
    "CONFIG_DIR",
    "CSV_FIRST_DATA_ROW",
    "CHUNK_EMBEDDING_DIMENSIONS",
    "CHUNK_EMBEDDING_INDEX_NAME",
    "CHUNK_EMBEDDING_LABEL",
    "CHUNK_EMBEDDING_PROPERTY",
    "CHUNK_FALLBACK_STRIDE",
    "DATASET_ID",
    "DEFAULT_DB",
    "DemoConfig",
    "EMBEDDER_MODEL_NAME",
    "ensure_pipeline_contract_loaded",
    "FIXTURES_DIR",
    "ID_PATTERNS",
    "make_run_id",
    "PDF_PIPELINE_CONFIG_PATH",
    "PIPELINE_CONFIG_DATA",
    "PROMPT_IDS",
    "STRUCTURED_FILE_HEADERS",
    "timestamp",
    "VALUE_TYPES",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import proxy
    if name in {"claim_extraction_lexical_config", "claim_extraction_schema"}:
        module = import_module("demo.chain_of_custody.contracts.claim_schema")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - thin import proxy
    return sorted(__all__)
