from importlib import import_module
from typing import Any

from power_atlas.contracts.manifest import build_batch_manifest, build_stage_manifest, write_manifest, write_manifest_md
from power_atlas.contracts.paths import (
    ARTIFACTS_DIR,
    CONFIG_DIR,
    DATASETS_CONTAINER_DIR,
    DatasetRoot,
    FIXTURES_DIR,
    PDF_PIPELINE_CONFIG_PATH,
    list_available_datasets,
    resolve_dataset_root,
)
from power_atlas.contracts.pipeline import ensure_pipeline_contract_loaded
from power_atlas.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE, PROMPT_IDS
from power_atlas.contracts.resolution import ALIGNMENT_VERSION
from power_atlas.contracts.retrieval_early_return_policy import (
    EarlyReturnRule,
    EARLY_RETURN_PRECEDENCE,
    EARLY_RETURN_RULE_BY_NAME,
    resolve_early_return_rule,
)
from power_atlas.contracts.retrieval_metadata_policy import (
    FieldSurfacePolicy,
    RetrievalMetadataSurface,
    RETRIEVAL_METADATA_SURFACE_POLICY,
)
from power_atlas.contracts.runtime import Config, make_run_id, timestamp
from power_atlas.contracts.structured import (
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
    "DATASETS_CONTAINER_DIR",
    "DatasetRoot",
    "Config",
    "EARLY_RETURN_PRECEDENCE",
    "EARLY_RETURN_RULE_BY_NAME",
    "EarlyReturnRule",
    "resolve_early_return_rule",
    "EMBEDDER_MODEL_NAME",
    "ensure_pipeline_contract_loaded",
    "FIXTURES_DIR",
    "ID_PATTERNS",
    "list_available_datasets",
    "make_run_id",
    "PDF_PIPELINE_CONFIG_PATH",
    "PIPELINE_CONFIG_DATA",
    "POWER_ATLAS_RAG_TEMPLATE",
    "PROMPT_IDS",
    "FieldSurfacePolicy",
    "RetrievalMetadataSurface",
    "RETRIEVAL_METADATA_SURFACE_POLICY",
    "resolve_dataset_root",
    "STRUCTURED_FILE_HEADERS",
    "timestamp",
    "VALUE_TYPES",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import proxy
    if name in {"claim_extraction_lexical_config", "claim_extraction_schema"}:
        module = import_module("power_atlas.contracts.claim_schema")
        return getattr(module, name)
    if name in {
        "CHUNK_EMBEDDING_DIMENSIONS",
        "CHUNK_EMBEDDING_INDEX_NAME",
        "CHUNK_EMBEDDING_LABEL",
        "CHUNK_EMBEDDING_PROPERTY",
        "CHUNK_FALLBACK_STRIDE",
        "EMBEDDER_MODEL_NAME",
        "PIPELINE_CONFIG_DATA",
    }:
        module = import_module("power_atlas.contracts.pipeline")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - thin import proxy
    return sorted(__all__)
