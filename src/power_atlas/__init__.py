from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ALIGNMENT_VERSION": ("power_atlas.contracts", "ALIGNMENT_VERSION"),
    "ARTIFACTS_DIR": ("power_atlas.contracts", "ARTIFACTS_DIR"),
    "AmbiguousDatasetError": ("power_atlas.contracts", "AmbiguousDatasetError"),
    "AppBootstrap": ("power_atlas.bootstrap", "AppBootstrap"),
    "AppContext": ("power_atlas.context", "AppContext"),
    "AppSettings": ("power_atlas.settings", "AppSettings"),
    "COMMON_PREDICATE_LABELS": ("power_atlas.contracts", "COMMON_PREDICATE_LABELS"),
    "CONFIG_DIR": ("power_atlas.contracts", "CONFIG_DIR"),
    "CSV_FIRST_DATA_ROW": ("power_atlas.contracts", "CSV_FIRST_DATA_ROW"),
    "Config": ("power_atlas.contracts", "Config"),
    "DATASETS_CONTAINER_DIR": ("power_atlas.contracts", "DATASETS_CONTAINER_DIR"),
    "DatasetRoot": ("power_atlas.contracts", "DatasetRoot"),
    "EARLY_RETURN_PRECEDENCE": ("power_atlas.contracts", "EARLY_RETURN_PRECEDENCE"),
    "EARLY_RETURN_RULE_BY_NAME": ("power_atlas.contracts", "EARLY_RETURN_RULE_BY_NAME"),
    "EarlyReturnRule": ("power_atlas.contracts", "EarlyReturnRule"),
    "FIXTURES_DIR": ("power_atlas.contracts", "FIXTURES_DIR"),
    "FieldSurfacePolicy": ("power_atlas.contracts", "FieldSurfacePolicy"),
    "ID_PATTERNS": ("power_atlas.contracts", "ID_PATTERNS"),
    "Neo4jSettings": ("power_atlas.settings", "Neo4jSettings"),
    "PDF_PIPELINE_CONFIG_PATH": ("power_atlas.contracts", "PDF_PIPELINE_CONFIG_PATH"),
    "POWER_ATLAS_RAG_TEMPLATE": ("power_atlas.contracts", "POWER_ATLAS_RAG_TEMPLATE"),
    "PROMPT_IDS": ("power_atlas.contracts", "PROMPT_IDS"),
    "RETRIEVAL_METADATA_SURFACE_POLICY": ("power_atlas.contracts", "RETRIEVAL_METADATA_SURFACE_POLICY"),
    "RequestContext": ("power_atlas.context", "RequestContext"),
    "RetrievalMetadataSurface": ("power_atlas.contracts", "RetrievalMetadataSurface"),
    "STRUCTURED_FILE_HEADERS": ("power_atlas.contracts", "STRUCTURED_FILE_HEADERS"),
    "VALUE_TYPES": ("power_atlas.contracts", "VALUE_TYPES"),
    "bootstrap_app": ("power_atlas.bootstrap", "bootstrap_app"),
    "build_app_context": ("power_atlas.bootstrap", "build_app_context"),
    "build_batch_manifest": ("power_atlas.contracts", "build_batch_manifest"),
    "build_embedder_for_settings": ("power_atlas.bootstrap", "build_embedder_for_settings"),
    "build_llm_for_settings": ("power_atlas.bootstrap", "build_llm_for_settings"),
    "build_openai_llm": ("power_atlas.llm_utils", "build_openai_llm"),
    "build_request_context": ("power_atlas.bootstrap", "build_request_context"),
    "build_settings": ("power_atlas.bootstrap", "build_settings"),
    "build_stage_manifest": ("power_atlas.contracts", "build_stage_manifest"),
    "claim_extraction_lexical_config": ("power_atlas.contracts", "claim_extraction_lexical_config"),
    "claim_extraction_schema": ("power_atlas.contracts", "claim_extraction_schema"),
    "create_neo4j_driver": ("power_atlas.bootstrap", "create_neo4j_driver"),
    "list_available_datasets": ("power_atlas.contracts", "list_available_datasets"),
    "make_run_id": ("power_atlas.contracts", "make_run_id"),
    "normalize_mention_text": ("power_atlas.text_utils", "normalize_mention_text"),
    "resolve_dataset_root": ("power_atlas.contracts", "resolve_dataset_root"),
    "resolve_early_return_rule": ("power_atlas.contracts", "resolve_early_return_rule"),
    "resolution_layer_schema": ("power_atlas.contracts", "resolution_layer_schema"),
    "timestamp": ("power_atlas.contracts", "timestamp"),
    "write_manifest": ("power_atlas.contracts", "write_manifest"),
    "write_manifest_md": ("power_atlas.contracts", "write_manifest_md"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        module = import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
