from importlib import import_module
from typing import Any

from demo.contracts.manifest import build_batch_manifest, build_stage_manifest, write_manifest, write_manifest_md
from demo.contracts.paths import ARTIFACTS_DIR, CONFIG_DIR, FIXTURES_DIR, PDF_PIPELINE_CONFIG_PATH
from demo.contracts.pipeline import (
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
from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE, PROMPT_IDS
from demo.contracts.resolution import ALIGNMENT_VERSION
from demo.contracts.retrieval_early_return_policy import (
    EarlyReturnRule,
    EARLY_RETURN_PRECEDENCE,
    EARLY_RETURN_RULE_BY_NAME,
)
from demo.contracts.retrieval_metadata_policy import (
    FieldSurfacePolicy,
    RetrievalMetadataSurface,
    RETRIEVAL_METADATA_SURFACE_POLICY,
)
from demo.contracts.runtime import Config, make_run_id, timestamp
from demo.contracts.structured import (
    COMMON_PREDICATE_LABELS,
    CSV_FIRST_DATA_ROW,
    ID_PATTERNS,
    STRUCTURED_FILE_HEADERS,
    VALUE_TYPES,
)

__all__ = [
    "ALIGNMENT_VERSION",
    "ARTIFACTS_DIR",
    "build_batch_manifest",
    "build_stage_manifest",
    "write_manifest",
    "write_manifest_md",
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
    "Config",
    "EARLY_RETURN_PRECEDENCE",
    "EARLY_RETURN_RULE_BY_NAME",
    "EarlyReturnRule",
    "EMBEDDER_MODEL_NAME",
    "ensure_pipeline_contract_loaded",
    "FIXTURES_DIR",
    "ID_PATTERNS",
    "make_run_id",
    "PDF_PIPELINE_CONFIG_PATH",
    "PIPELINE_CONFIG_DATA",
    "POWER_ATLAS_RAG_TEMPLATE",
    "PROMPT_IDS",
    "FieldSurfacePolicy",
    "RetrievalMetadataSurface",
    "RETRIEVAL_METADATA_SURFACE_POLICY",
    "STRUCTURED_FILE_HEADERS",
    "timestamp",
    "VALUE_TYPES",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import proxy
    if name in {"claim_extraction_lexical_config", "claim_extraction_schema"}:
        module = import_module("demo.contracts.claim_schema")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - thin import proxy
    return sorted(__all__)
