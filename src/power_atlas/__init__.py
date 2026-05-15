from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ALIGNMENT_VERSION": ("power_atlas.contracts", "ALIGNMENT_VERSION"),
    "ARTIFACTS_DIR": ("power_atlas.contracts", "ARTIFACTS_DIR"),
    "BASE_DIR": ("power_atlas.contracts", "BASE_DIR"),
    "AmbiguousDatasetError": ("power_atlas.contracts", "AmbiguousDatasetError"),
    "api": ("power_atlas.api", None),
    "AppBootstrap": ("power_atlas.bootstrap", "AppBootstrap"),
    "AppContext": ("power_atlas.context", "AppContext"),
    "AppPolicies": ("power_atlas.context", "AppPolicies"),
    "AppSettings": ("power_atlas.settings", "AppSettings"),
    "COMMON_PREDICATE_LABELS": ("power_atlas.contracts", "COMMON_PREDICATE_LABELS"),
    "ClaimExtractionOntology": ("power_atlas.contracts", "ClaimExtractionOntology"),
    "ClaimExtractionPolicy": ("power_atlas.contracts", "ClaimExtractionPolicy"),
    "CONFIG_DIR": ("power_atlas.contracts", "CONFIG_DIR"),
    "CSV_FIRST_DATA_ROW": ("power_atlas.contracts", "CSV_FIRST_DATA_ROW"),
    "Config": ("power_atlas.contracts", "Config"),
    "DatasetIdSelector": ("power_atlas.contracts", "DatasetIdSelector"),
    "DATASETS_CONTAINER_DIR": ("power_atlas.contracts", "DATASETS_CONTAINER_DIR"),
    "DatasetRoot": ("power_atlas.contracts", "DatasetRoot"),
    "RepoPaths": ("power_atlas.contracts", "RepoPaths"),
    "DomainPackDescriptor": ("power_atlas.bootstrap", "DomainPackDescriptor"),
    "EARLY_RETURN_PRECEDENCE": ("power_atlas.contracts", "EARLY_RETURN_PRECEDENCE"),
    "EARLY_RETURN_RULE_BY_NAME": ("power_atlas.contracts", "EARLY_RETURN_RULE_BY_NAME"),
    "EarlyReturnRule": ("power_atlas.contracts", "EarlyReturnRule"),
    "EntityResolutionAlignmentContract": (
        "power_atlas.contracts",
        "EntityResolutionAlignmentContract",
    ),
    "EntityResolutionAlignmentStep": (
        "power_atlas.contracts",
        "EntityResolutionAlignmentStep",
    ),
    "EntityResolutionCanonicalLookupContract": (
        "power_atlas.contracts",
        "EntityResolutionCanonicalLookupContract",
    ),
    "EntityResolutionDatasetSelectionContract": (
        "power_atlas.contracts",
        "EntityResolutionDatasetSelectionContract",
    ),
    "EntityResolutionGraphContract": (
        "power_atlas.contracts",
        "EntityResolutionGraphContract",
    ),
    "EntityTypeNormalizationPolicy": ("power_atlas.contracts", "EntityTypeNormalizationPolicy"),
    "FIXTURES_DIR": ("power_atlas.contracts", "FIXTURES_DIR"),
    "FieldSurfacePolicy": ("power_atlas.contracts", "FieldSurfacePolicy"),
    "ID_PATTERNS": ("power_atlas.contracts", "ID_PATTERNS"),
    "Neo4jSettings": ("power_atlas.settings", "Neo4jSettings"),
    "PDF_PIPELINE_CONFIG_PATH": ("power_atlas.contracts", "PDF_PIPELINE_CONFIG_PATH"),
    "POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY": ("power_atlas.contracts", "POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY"),
    "POWER_ATLAS_CLAIM_EXTRACTION_POLICY": ("power_atlas.contracts", "POWER_ATLAS_CLAIM_EXTRACTION_POLICY"),
    "POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT",
    ),
    "POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT",
    ),
    "POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT",
    ),
    "POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT",
    ),
    "POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY": ("power_atlas.contracts", "POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY"),
    "POWER_ATLAS_RAG_TEMPLATE": ("power_atlas.contracts", "POWER_ATLAS_RAG_TEMPLATE"),
    "POWER_ATLAS_RETRIEVAL_ONTOLOGY": ("power_atlas.contracts", "POWER_ATLAS_RETRIEVAL_ONTOLOGY"),
    "POWER_ATLAS_RETRIEVAL_POLICY": ("power_atlas.contracts", "POWER_ATLAS_RETRIEVAL_POLICY"),
    "POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT",
    ),
    "POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT": (
        "power_atlas.contracts",
        "POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT",
    ),
    "PipelineContractLoadResult": ("power_atlas.contracts", "PipelineContractLoadResult"),
    "PipelineContractSnapshot": ("power_atlas.contracts", "PipelineContractSnapshot"),
    "PipelineContractSource": ("power_atlas.contracts", "PipelineContractSource"),
    "PROMPT_IDS": ("power_atlas.contracts", "PROMPT_IDS"),
    "RETRIEVAL_METADATA_SURFACE_POLICY": ("power_atlas.contracts", "RETRIEVAL_METADATA_SURFACE_POLICY"),
    "RequestContext": ("power_atlas.context", "RequestContext"),
    "RetrievalMetadataSurface": ("power_atlas.contracts", "RetrievalMetadataSurface"),
    "RetrievalOntology": ("power_atlas.contracts", "RetrievalOntology"),
    "RetrievalPolicy": ("power_atlas.contracts", "RetrievalPolicy"),
    "STRUCTURED_FILE_HEADERS": ("power_atlas.contracts", "STRUCTURED_FILE_HEADERS"),
    "StructuredGraphShapeContract": (
        "power_atlas.contracts",
        "StructuredGraphShapeContract",
    ),
    "StructuredSchemaContract": ("power_atlas.contracts", "StructuredSchemaContract"),
    "VALUE_TYPES": ("power_atlas.contracts", "VALUE_TYPES"),
    "bootstrap_app": ("power_atlas.bootstrap", "bootstrap_app"),
    "build_app_context": ("power_atlas.bootstrap", "build_app_context"),
    "build_default_app_policies": ("power_atlas.context", "build_default_app_policies"),
    "build_entity_type_cypher_case": ("power_atlas.contracts", "build_entity_type_cypher_case"),
    "build_batch_manifest": ("power_atlas.contracts", "build_batch_manifest"),
    "build_embedder_for_settings": ("power_atlas.bootstrap", "build_embedder_for_settings"),
    "build_llm_for_settings": ("power_atlas.bootstrap", "build_llm_for_settings"),
    "build_openai_llm": ("power_atlas.llm_utils", "build_openai_llm"),
    "build_request_context": ("power_atlas.bootstrap", "build_request_context"),
    "build_settings": ("power_atlas.bootstrap", "build_settings"),
    "build_stage_manifest": ("power_atlas.contracts", "build_stage_manifest"),
    "claim_extraction_lexical_config": ("power_atlas.contracts", "claim_extraction_lexical_config"),
    "claim_extraction_diagnostics": ("power_atlas.claim_extraction_diagnostics", None),
    "claim_extraction_schema": ("power_atlas.contracts", "claim_extraction_schema"),
    "claim_extraction_entrypoint": ("power_atlas.claim_extraction_entrypoint", None),
    "claim_extraction_runner": ("power_atlas.claim_extraction_runner", None),
    "create_neo4j_driver": ("power_atlas.bootstrap", "create_neo4j_driver"),
    "entity_resolution_entrypoint": ("power_atlas.entity_resolution_entrypoint", None),
    "entity_resolution_runner": ("power_atlas.entity_resolution_runner", None),
    "get_default_claim_extraction_policy": ("power_atlas.contracts", "get_default_claim_extraction_policy"),
    "get_default_entity_resolution_alignment_contract": (
        "power_atlas.contracts",
        "get_default_entity_resolution_alignment_contract",
    ),
    "get_default_entity_resolution_canonical_lookup_contract": (
        "power_atlas.contracts",
        "get_default_entity_resolution_canonical_lookup_contract",
    ),
    "get_default_entity_resolution_dataset_selection_contract": (
        "power_atlas.contracts",
        "get_default_entity_resolution_dataset_selection_contract",
    ),
    "get_default_entity_resolution_graph_contract": (
        "power_atlas.contracts",
        "get_default_entity_resolution_graph_contract",
    ),
    "get_default_entity_type_normalization_policy": ("power_atlas.contracts", "get_default_entity_type_normalization_policy"),
    "get_pipeline_contract_config_data": ("power_atlas.contracts", "get_pipeline_contract_config_data"),
    "get_pipeline_contract_snapshot": ("power_atlas.contracts", "get_pipeline_contract_snapshot"),
    "graph_health_diagnostics": ("power_atlas.graph_health_diagnostics", None),
    "is_pipeline_contract_snapshot": ("power_atlas.contracts", "is_pipeline_contract_snapshot"),
    "list_available_datasets": ("power_atlas.contracts", "list_available_datasets"),
    "load_pipeline_contract": ("power_atlas.contracts", "load_pipeline_contract"),
    "make_run_id": ("power_atlas.contracts", "make_run_id"),
    "normalize_entity_type": ("power_atlas.contracts", "normalize_entity_type"),
    "normalize_mention_text": ("power_atlas.text_utils", "normalize_mention_text"),
    "pdf_ingest_entrypoint": ("power_atlas.pdf_ingest_entrypoint", None),
    "pdf_ingest_runner": ("power_atlas.pdf_ingest_runner", None),
    "resolve_dataset_root": ("power_atlas.contracts", "resolve_dataset_root"),
    "resolve_pipeline_contract_source": ("power_atlas.contracts", "resolve_pipeline_contract_source"),
    "resolve_repo_paths": ("power_atlas.contracts", "resolve_repo_paths"),
    "resolve_early_return_rule": ("power_atlas.contracts", "resolve_early_return_rule"),
    "refresh_pipeline_contract": ("power_atlas.contracts", "refresh_pipeline_contract"),
    "get_default_retrieval_policy": ("power_atlas.contracts", "get_default_retrieval_policy"),
    "get_default_structured_graph_shape_contract": (
        "power_atlas.contracts",
        "get_default_structured_graph_shape_contract",
    ),
    "get_default_structured_schema_contract": (
        "power_atlas.contracts",
        "get_default_structured_schema_contract",
    ),
    "retrieval_benchmark_entrypoint": ("power_atlas.retrieval_benchmark_entrypoint", None),
    "retrieval_benchmark_runner": ("power_atlas.retrieval_benchmark_runner", None),
    "retrieval_request_context_adapters": (
        "power_atlas.retrieval_request_context_adapters",
        None,
    ),
    "resolution_layer_schema": ("power_atlas.contracts", "resolution_layer_schema"),
    "structured_ingest_entrypoint": ("power_atlas.structured_ingest_entrypoint", None),
    "structured_ingest_runner": ("power_atlas.structured_ingest_runner", None),
    "timestamp": ("power_atlas.contracts", "timestamp"),
    "write_manifest": ("power_atlas.contracts", "write_manifest"),
    "write_manifest_md": ("power_atlas.contracts", "write_manifest_md"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        module = import_module(module_name)
        value = module if attr_name is None else getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
