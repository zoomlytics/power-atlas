from __future__ import annotations

import asyncio
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest


def test_package_modules_import() -> None:
    package = importlib.import_module("power_atlas")
    api_module = importlib.import_module("power_atlas.api")
    backend_app_module = importlib.import_module("power_atlas.backend_app")
    backend_graph_module = importlib.import_module("power_atlas.backend_graph")
    context_module = importlib.import_module("power_atlas.context")
    policy_packs_module = importlib.import_module("power_atlas.policy_packs")
    market_trade_policy_module = importlib.import_module(
        "power_atlas.policy_packs.market_trade"
    )
    contracts_module = importlib.import_module("power_atlas.contracts")
    pipeline_module = importlib.import_module("power_atlas.contracts.pipeline")
    orchestration_module = importlib.import_module("power_atlas.orchestration")
    settings_module = importlib.import_module("power_atlas.settings")
    bootstrap_module = importlib.import_module("power_atlas.bootstrap")
    claim_extraction_diagnostics_module = importlib.import_module(
        "power_atlas.claim_extraction_diagnostics"
    )
    claim_extraction_entrypoint_module = importlib.import_module(
        "power_atlas.claim_extraction_entrypoint"
    )
    claim_extraction_query_specs_module = importlib.import_module(
        "power_atlas.claim_extraction_query_specs"
    )
    claim_extraction_runner_module = importlib.import_module(
        "power_atlas.claim_extraction_runner"
    )
    claim_extraction_runtime_module = importlib.import_module(
        "power_atlas.claim_extraction_runtime"
    )
    claim_participation_edges_module = importlib.import_module(
        "power_atlas.claim_participation_edges"
    )
    claim_participation_runner_module = importlib.import_module(
        "power_atlas.claim_participation_runner"
    )
    entity_resolution_alignment_module = importlib.import_module(
        "power_atlas.entity_resolution_alignment"
    )
    entity_resolution_entrypoint_module = importlib.import_module(
        "power_atlas.entity_resolution_entrypoint"
    )
    entity_resolution_reporting_module = importlib.import_module(
        "power_atlas.entity_resolution_reporting"
    )
    entity_resolution_runner_module = importlib.import_module(
        "power_atlas.entity_resolution_runner"
    )
    llm_utils_module = importlib.import_module("power_atlas.llm_utils")
    pdf_ingest_entrypoint_module = importlib.import_module(
        "power_atlas.pdf_ingest_entrypoint"
    )
    pdf_ingest_runner_module = importlib.import_module(
        "power_atlas.pdf_ingest_runner"
    )
    retrieval_benchmark_entrypoint_module = importlib.import_module(
        "power_atlas.retrieval_benchmark_entrypoint"
    )
    claim_extraction_diagnostics_cli_module = importlib.import_module(
        "power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint"
    )
    claim_extraction_diagnostics_package_cli_module = importlib.import_module(
        "power_atlas.cli.claim_extraction_diagnostics_report"
    )
    claim_extraction_diagnostics_report_support_module = importlib.import_module(
        "power_atlas.interfaces.cli.claim_extraction_diagnostics_report_support"
    )
    retrieval_benchmark_runner_module = importlib.import_module(
        "power_atlas.retrieval_benchmark_runner"
    )
    retrieval_request_context_adapters_module = importlib.import_module(
        "power_atlas.retrieval_request_context_adapters"
    )
    structured_ingest_runner_module = importlib.import_module(
        "power_atlas.structured_ingest_runner"
    )
    structured_ingest_entrypoint_module = importlib.import_module(
        "power_atlas.structured_ingest_entrypoint"
    )
    text_utils_module = importlib.import_module("power_atlas.text_utils")

    assert package.ALIGNMENT_VERSION is contracts_module.ALIGNMENT_VERSION
    assert package.AmbiguousDatasetError is contracts_module.AmbiguousDatasetError
    assert package.ARTIFACTS_DIR == contracts_module.ARTIFACTS_DIR
    assert package.api is api_module
    assert package.build_batch_manifest is contracts_module.build_batch_manifest
    assert package.build_stage_manifest is contracts_module.build_stage_manifest
    assert package.claim_extraction_lexical_config is contracts_module.claim_extraction_lexical_config
    assert package.claim_extraction_schema is contracts_module.claim_extraction_schema
    assert package.EarlyReturnRule is contracts_module.EarlyReturnRule
    assert package.EARLY_RETURN_PRECEDENCE is contracts_module.EARLY_RETURN_PRECEDENCE
    assert package.EARLY_RETURN_RULE_BY_NAME is contracts_module.EARLY_RETURN_RULE_BY_NAME
    assert package.DatasetIdSelector is contracts_module.DatasetIdSelector
    assert package.DomainPackDescriptor is bootstrap_module.DomainPackDescriptor
    assert (
        package.EntityResolutionAlignmentContract
        is contracts_module.EntityResolutionAlignmentContract
    )
    assert (
        package.EntityResolutionAlignmentStep
        is contracts_module.EntityResolutionAlignmentStep
    )
    assert (
        package.EntityResolutionCanonicalLookupContract
        is contracts_module.EntityResolutionCanonicalLookupContract
    )
    assert (
        package.EntityResolutionDatasetSelectionContract
        is contracts_module.EntityResolutionDatasetSelectionContract
    )
    assert package.EntityResolutionGraphContract is contracts_module.EntityResolutionGraphContract
    assert package.EntityTypeNormalizationPolicy is contracts_module.EntityTypeNormalizationPolicy
    assert package.CONFIG_DIR == contracts_module.CONFIG_DIR
    assert package.PROMPT_IDS is contracts_module.PROMPT_IDS
    assert package.POWER_ATLAS_RAG_TEMPLATE is contracts_module.POWER_ATLAS_RAG_TEMPLATE
    assert package.POWER_ATLAS_RETRIEVAL_ONTOLOGY is contracts_module.POWER_ATLAS_RETRIEVAL_ONTOLOGY
    assert package.POWER_ATLAS_RETRIEVAL_POLICY is contracts_module.POWER_ATLAS_RETRIEVAL_POLICY
    assert (
        package.POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT
        is contracts_module.POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT
    )
    assert (
        package.POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT
        is contracts_module.POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT
    )
    assert package.Config is contracts_module.Config
    assert package.COMMON_PREDICATE_LABELS is contracts_module.COMMON_PREDICATE_LABELS
    assert package.ClaimExtractionOntology is contracts_module.ClaimExtractionOntology
    assert package.ClaimExtractionPolicy is contracts_module.ClaimExtractionPolicy
    assert package.CSV_FIRST_DATA_ROW is contracts_module.CSV_FIRST_DATA_ROW
    assert package.DATASETS_CONTAINER_DIR == contracts_module.DATASETS_CONTAINER_DIR
    assert package.DatasetRoot is contracts_module.DatasetRoot
    assert package.FieldSurfacePolicy is contracts_module.FieldSurfacePolicy
    assert package.FIXTURES_DIR == contracts_module.FIXTURES_DIR
    assert package.ID_PATTERNS is contracts_module.ID_PATTERNS
    assert package.AppContext is context_module.AppContext
    assert package.AppPolicies is context_module.AppPolicies
    assert package.PDF_PIPELINE_CONFIG_PATH == contracts_module.PDF_PIPELINE_CONFIG_PATH
    assert package.POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY is contracts_module.POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY
    assert package.POWER_ATLAS_CLAIM_EXTRACTION_POLICY is contracts_module.POWER_ATLAS_CLAIM_EXTRACTION_POLICY
    assert (
        package.POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT
        is contracts_module.POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT
    )
    assert (
        package.POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT
        is contracts_module.POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT
    )
    assert (
        package.POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT
        is contracts_module.POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT
    )
    assert (
        package.POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT
        is contracts_module.POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT
    )
    assert package.POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY is contracts_module.POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY
    assert package.RETRIEVAL_METADATA_SURFACE_POLICY is contracts_module.RETRIEVAL_METADATA_SURFACE_POLICY
    assert package.RequestContext is context_module.RequestContext
    assert package.RetrievalMetadataSurface is contracts_module.RetrievalMetadataSurface
    assert package.RetrievalOntology is contracts_module.RetrievalOntology
    assert package.RetrievalPolicy is contracts_module.RetrievalPolicy
    assert package.StructuredGraphShapeContract is contracts_module.StructuredGraphShapeContract
    assert package.STRUCTURED_FILE_HEADERS is contracts_module.STRUCTURED_FILE_HEADERS
    assert package.StructuredSchemaContract is contracts_module.StructuredSchemaContract
    assert package.VALUE_TYPES is contracts_module.VALUE_TYPES
    assert package.list_available_datasets is contracts_module.list_available_datasets
    assert package.make_run_id is contracts_module.make_run_id
    assert package.resolve_dataset_root is contracts_module.resolve_dataset_root
    assert package.resolve_early_return_rule is contracts_module.resolve_early_return_rule
    assert package.get_default_retrieval_policy is contracts_module.get_default_retrieval_policy
    assert (
        package.get_default_entity_resolution_alignment_contract
        is contracts_module.get_default_entity_resolution_alignment_contract
    )
    assert (
        package.get_default_entity_resolution_canonical_lookup_contract
        is contracts_module.get_default_entity_resolution_canonical_lookup_contract
    )
    assert (
        package.get_default_entity_resolution_dataset_selection_contract
        is contracts_module.get_default_entity_resolution_dataset_selection_contract
    )
    assert (
        package.get_default_entity_resolution_graph_contract
        is contracts_module.get_default_entity_resolution_graph_contract
    )
    assert (
        package.get_default_structured_graph_shape_contract
        is contracts_module.get_default_structured_graph_shape_contract
    )
    assert (
        package.get_default_structured_schema_contract
        is contracts_module.get_default_structured_schema_contract
    )
    assert package.get_default_claim_extraction_policy is contracts_module.get_default_claim_extraction_policy
    assert package.get_default_entity_type_normalization_policy is contracts_module.get_default_entity_type_normalization_policy
    assert package.build_entity_type_cypher_case is contracts_module.build_entity_type_cypher_case
    assert package.normalize_entity_type is contracts_module.normalize_entity_type
    assert package.resolution_layer_schema is contracts_module.resolution_layer_schema
    assert package.timestamp is contracts_module.timestamp
    assert package.write_manifest is contracts_module.write_manifest
    assert package.write_manifest_md is contracts_module.write_manifest_md
    assert (
        policy_packs_module.MARKET_TRADE_DOMAIN_PACK
        is market_trade_policy_module.MARKET_TRADE_DOMAIN_PACK
    )
    assert (
        policy_packs_module.MARKET_TRADE_RETRIEVAL_POLICY
        is market_trade_policy_module.MARKET_TRADE_RETRIEVAL_POLICY
    )
    assert (
        policy_packs_module.MARKET_TRADE_RETRIEVAL_ONTOLOGY
        is market_trade_policy_module.MARKET_TRADE_RETRIEVAL_ONTOLOGY
    )
    assert (
        policy_packs_module.get_market_trade_retrieval_policy()
        is market_trade_policy_module.MARKET_TRADE_RETRIEVAL_POLICY
    )
    assert market_trade_policy_module.MARKET_TRADE_DOMAIN_PACK == bootstrap_module.DomainPackDescriptor(
        name="market_trade",
        version="v1",
        provides=(
            "retrieval_policy",
            "entity_resolution_graph_contract",
            "entity_resolution_canonical_lookup_contract",
            "entity_resolution_alignment_contract",
            "entity_resolution_dataset_selection_contract",
        ),
        examples=(
            "examples/market_trade_retrieval_policy_consumer.py",
            "examples/market_trade_entity_resolution_consumer.py",
        ),
    )
    assert package.AppSettings is settings_module.AppSettings
    assert package.build_settings is bootstrap_module.build_settings
    assert package.build_app_context is bootstrap_module.build_app_context
    assert package.build_request_context is bootstrap_module.build_request_context
    assert package.build_default_app_policies is context_module.build_default_app_policies
    assert package.build_openai_llm is llm_utils_module.build_openai_llm
    assert package.normalize_mention_text is text_utils_module.normalize_mention_text
    assert package.claim_extraction_diagnostics is claim_extraction_diagnostics_module
    assert package.claim_extraction_entrypoint is claim_extraction_entrypoint_module
    assert package.claim_extraction_runner is claim_extraction_runner_module
    assert package.entity_resolution_entrypoint is entity_resolution_entrypoint_module
    assert package.entity_resolution_runner is entity_resolution_runner_module
    assert package.pdf_ingest_entrypoint is pdf_ingest_entrypoint_module
    assert package.pdf_ingest_runner is pdf_ingest_runner_module
    assert package.retrieval_benchmark_entrypoint is retrieval_benchmark_entrypoint_module
    assert package.retrieval_benchmark_runner is retrieval_benchmark_runner_module
    assert (
        package.retrieval_request_context_adapters
        is retrieval_request_context_adapters_module
    )
    assert package.structured_ingest_entrypoint is structured_ingest_entrypoint_module
    assert package.structured_ingest_runner is structured_ingest_runner_module
    assert not hasattr(package, "run_claim_extraction")
    assert not hasattr(package, "run_claim_extraction_request_context")
    assert not hasattr(package, "run_entity_resolution")
    assert not hasattr(package, "run_entity_resolution_request_context")
    assert not hasattr(package, "run_pdf_ingest")
    assert not hasattr(package, "run_pdf_ingest_request_context")
    assert not hasattr(package, "run_structured_ingest")
    assert not hasattr(package, "run_structured_ingest_request_context")
    assert not hasattr(package, "run_retrieval_benchmark")
    assert not hasattr(package, "run_retrieval_benchmark_request_context")
    assert not hasattr(package, "run_retrieval_request_context")
    assert not hasattr(package, "run_interactive_request_context")
    assert not hasattr(package, "run_demo_entrypoint")
    assert not hasattr(package, "retrieval_benchmark_cli_entrypoint")
    assert not hasattr(package, "graph_health_diagnostics_entrypoint")
    assert not hasattr(package, "narrative_extraction_cli_entrypoint")
    assert not hasattr(package, "reset_demo_entrypoint")
    assert not hasattr(package, "smoke_test_entrypoint")
    assert not hasattr(package, "sync_vendor_version_entrypoint")
    assert not hasattr(package, "create_backend_app")
    assert not hasattr(package, "backend_router")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("power_atlas.interfaces.api")
    assert api_module.BackendAppOptions.__name__ == "BackendAppOptions"
    assert api_module.BackendGraphQueryService.__name__ == "BackendGraphQueryService"
    assert api_module.BackendRuntime.__name__ == "BackendRuntime"
    assert api_module.CurrentRunDetailResponse.__name__ == "CurrentRunDetailResponse"
    assert api_module.CurrentRunsResponse.__name__ == "CurrentRunsResponse"
    assert api_module.DatasetResponse.__name__ == "DatasetResponse"
    assert api_module.DatasetsResponse.__name__ == "DatasetsResponse"
    assert api_module.RunDetailResponse.__name__ == "RunDetailResponse"
    assert api_module.RunResponse.__name__ == "RunResponse"
    assert api_module.RunStageResponse.__name__ == "RunStageResponse"
    assert api_module.RunsResponse.__name__ == "RunsResponse"
    assert api_module.GraphHealthSummaryRequestBody.__name__ == "GraphHealthSummaryRequestBody"
    assert api_module.GraphHealthSummaryResponse.__name__ == "GraphHealthSummaryResponse"
    assert api_module.RunScopedGraphCountsRequestBody.__name__ == "RunScopedGraphCountsRequestBody"
    assert api_module.RunScopedGraphCountsResponse.__name__ == "RunScopedGraphCountsResponse"
    assert callable(backend_app_module.build_backend_runtime)
    assert callable(backend_app_module.create_backend_app)
    assert callable(backend_graph_module.build_backend_graph_query_service)
    assert callable(api_module.build_backend_graph_query_service)
    assert api_module.build_backend_graph_query_service is backend_graph_module.build_backend_graph_query_service
    assert callable(api_module.build_backend_runtime)
    assert api_module.build_backend_runtime is backend_app_module.build_backend_runtime
    assert callable(api_module.build_backend_router)
    assert api_module.build_backend_router is backend_app_module.build_backend_router
    assert callable(api_module.create_backend_app)
    assert api_module.create_backend_app is backend_app_module.create_backend_app
    assert callable(api_module.get_backend_runtime)
    assert api_module.get_backend_runtime is backend_app_module.get_backend_runtime
    assert api_module.backend_router is not None
    assert callable(claim_extraction_diagnostics_module.neo4j_settings_from_config)
    assert callable(claim_extraction_diagnostics_module.neo4j_settings_from_request_context)
    assert callable(claim_extraction_diagnostics_module.run_claim_extraction_diagnostics)
    assert callable(
        claim_extraction_diagnostics_module.run_claim_extraction_diagnostics_request_context
    )
    assert callable(
        claim_extraction_diagnostics_cli_module.run_claim_extraction_diagnostics_report_main
    )
    assert callable(claim_extraction_diagnostics_package_cli_module.main)
    assert callable(
        claim_extraction_diagnostics_report_support_module.build_claim_extraction_diagnostics_report_settings
    )
    assert callable(
        claim_extraction_diagnostics_report_support_module.parse_claim_extraction_diagnostics_report_args
    )
    assert callable(claim_extraction_entrypoint_module.resolve_claim_extraction_policy)
    assert callable(claim_extraction_entrypoint_module.resolve_pipeline_contract)
    assert callable(claim_extraction_entrypoint_module.neo4j_settings_from_config)
    assert callable(claim_extraction_entrypoint_module.openai_model_from_config)
    assert callable(claim_extraction_entrypoint_module.run_claim_extraction)
    assert callable(claim_extraction_entrypoint_module.run_claim_extraction_request_context)
    assert callable(
        claim_extraction_query_specs_module.build_claim_extraction_diagnostic_query_specs
    )
    assert callable(
        claim_extraction_query_specs_module.fetch_claim_extraction_diagnostic_rows
    )
    assert callable(claim_extraction_runner_module.read_chunks_and_extract)
    assert callable(claim_extraction_runner_module.run_claim_extraction_runtime)
    assert callable(claim_extraction_runner_module.run_claim_extraction_runtime_default)
    assert callable(claim_extraction_runtime_module.run_claim_extraction_live)
    assert claim_participation_edges_module.EDGE_TYPE_HAS_PARTICIPANT == "HAS_PARTICIPANT"
    assert claim_participation_edges_module.ROLE_SUBJECT == "subject"
    assert claim_participation_edges_module.ROLE_OBJECT == "object"
    assert callable(claim_participation_edges_module.split_slot_text)
    assert callable(claim_participation_edges_module.match_slot_to_mention)
    assert callable(claim_participation_edges_module.build_participation_edges)
    assert callable(claim_participation_edges_module.build_participation_edges_with_metrics)
    assert callable(claim_participation_runner_module.neo4j_settings_from_config)
    assert callable(claim_participation_runner_module.write_participation_edges)
    assert callable(claim_participation_runner_module.run_claim_participation_request_context)
    assert callable(entity_resolution_alignment_module.align_clusters_to_canonical)
    assert callable(entity_resolution_entrypoint_module.neo4j_settings_from_config)
    assert callable(entity_resolution_entrypoint_module.resolve_effective_dataset_id)
    assert callable(entity_resolution_entrypoint_module.run_entity_resolution)
    assert callable(entity_resolution_entrypoint_module.run_entity_resolution_request_context)
    assert (
        entity_resolution_entrypoint_module.RESOLUTION_MODE_STRUCTURED_ANCHOR
        == "structured_anchor"
    )
    assert (
        entity_resolution_entrypoint_module.RESOLUTION_MODE_UNSTRUCTURED_ONLY
        == "unstructured_only"
    )
    assert entity_resolution_entrypoint_module.RESOLUTION_MODE_HYBRID == "hybrid"
    assert callable(entity_resolution_reporting_module.build_entity_type_report)
    assert (
        entity_resolution_reporting_module.ENTITY_TYPE_NULL_SENTINEL
        == contracts_module.POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY.null_sentinel
    )
    assert callable(entity_resolution_runner_module.write_cluster_memberships)
    assert callable(entity_resolution_runner_module.write_resolution_results)
    assert callable(entity_resolution_runner_module.run_entity_resolution_runtime)
    assert callable(pdf_ingest_entrypoint_module.resolve_pipeline_contract)
    assert callable(pdf_ingest_entrypoint_module.neo4j_settings_from_config)
    assert callable(pdf_ingest_entrypoint_module.openai_model_from_config)
    assert callable(pdf_ingest_entrypoint_module.run_pdf_ingest)
    assert callable(pdf_ingest_entrypoint_module.run_pdf_ingest_request_context)
    assert callable(pdf_ingest_runner_module.resolve_pdf_dataset)
    assert callable(pdf_ingest_runner_module.sha256_file)
    assert callable(pdf_ingest_runner_module.require_positive_int)
    assert callable(pdf_ingest_runner_module.run_pipeline_with_cleanup)
    assert callable(pdf_ingest_runner_module.run_pdf_ingest_runtime)
    assert callable(pdf_ingest_runner_module.run_pdf_ingest_runtime_default)
    assert callable(retrieval_benchmark_entrypoint_module.neo4j_settings_from_config)
    assert callable(retrieval_benchmark_entrypoint_module.neo4j_settings_from_request_context)
    assert callable(retrieval_benchmark_entrypoint_module.run_retrieval_benchmark)
    assert callable(retrieval_benchmark_entrypoint_module.run_retrieval_benchmark_request_context)
    assert retrieval_benchmark_runner_module.BENCHMARK_CASES
    assert callable(retrieval_benchmark_runner_module.build_benchmark_case_result)
    assert callable(retrieval_benchmark_runner_module.build_benchmark_artifact)
    assert callable(retrieval_benchmark_runner_module.run_retrieval_benchmark_runtime)
    assert callable(retrieval_benchmark_runner_module.run_retrieval_benchmark_runtime_default)
    assert callable(retrieval_request_context_adapters_module.run_retrieval_request_context)
    assert callable(retrieval_request_context_adapters_module.run_interactive_request_context)
    assert callable(structured_ingest_entrypoint_module.neo4j_settings_from_config)
    assert callable(structured_ingest_entrypoint_module.run_structured_ingest)
    assert callable(structured_ingest_entrypoint_module.run_structured_ingest_request_context)
    assert callable(structured_ingest_runner_module.load_csv_rows)
    assert callable(structured_ingest_runner_module.lint_and_clean_structured_csvs)
    assert callable(structured_ingest_runner_module.run_structured_ingest_runtime)
    assert callable(structured_ingest_runner_module.run_structured_ingest_runtime_default)
    assert not hasattr(pipeline_module, "DATASET_ID")
    assert not hasattr(pipeline_module, "get_dataset_id")
    assert not hasattr(pipeline_module, "set_dataset_id")
    assert not hasattr(pipeline_module, "PIPELINE_CONFIG_DATA")
    assert not hasattr(pipeline_module, "CHUNK_EMBEDDING_INDEX_NAME")
    assert not hasattr(pipeline_module, "CHUNK_EMBEDDING_LABEL")
    assert not hasattr(pipeline_module, "CHUNK_EMBEDDING_PROPERTY")
    assert not hasattr(pipeline_module, "CHUNK_EMBEDDING_DIMENSIONS")
    assert not hasattr(pipeline_module, "EMBEDDER_MODEL_NAME")
    assert not hasattr(pipeline_module, "CHUNK_FALLBACK_STRIDE")
    assert not hasattr(orchestration_module, "lint_and_clean_structured_csvs_legacy")
    assert not hasattr(orchestration_module, "run_structured_ingest_legacy")
    assert not hasattr(orchestration_module, "run_pdf_ingest_legacy")
    assert not hasattr(orchestration_module, "run_claim_and_mention_extraction_legacy")
    assert not hasattr(orchestration_module, "run_entity_resolution_legacy")
    assert not hasattr(orchestration_module, "run_retrieval_and_qa_legacy")


def test_build_settings_from_env_mapping() -> None:
    from power_atlas.bootstrap import bootstrap_app

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_EMBEDDER_MODEL": "text-embedding-3-large",
            "POWER_ATLAS_OUTPUT_DIR": "build/power-atlas",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )

    assert app.settings.neo4j.uri == "bolt://example.test:7687"
    assert app.settings.neo4j.username == "atlas"
    assert app.settings.neo4j.password == "secret"
    assert app.settings.neo4j.database == "analytics"
    assert app.settings.openai_model == "gpt-5.4"
    assert app.settings.embedder_model == "text-embedding-3-large"
    assert app.settings.output_dir == Path("build/power-atlas")
    assert app.settings.dataset_name == "demo_dataset_v1"


def test_public_api_facade_supports_filtered_run_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from power_atlas.api import BackendAppOptions, create_backend_app

    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_pdf_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
    newer_pdf_manifest_path.parent.mkdir(parents=True)
    newer_pdf_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_claim_manifest_path.parent.mkdir(parents=True)
    newer_claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "resolved-demo-dataset",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "power_atlas.backend_run_catalog.resolve_backend_dataset_catalog",
        lambda settings: importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogResult(
            datasets=[],
            selected_dataset=importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogEntry(
                name="demo_dataset_v1",
                dataset_id="resolved-demo-dataset",
                pdf_filename="example.pdf",
                manifest_path="/tmp/manifest.json",
                root_path="/tmp/dataset",
            ),
            selection_mode="configured",
        ),
    )

    app = create_backend_app(
        BackendAppOptions(version="4.0.0-run-filters"),
        environ={
            "POWER_ATLAS_OUTPUT_DIR": str(tmp_path),
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        },
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            current_runs = await client.get(
                "/runs/current",
            )
            assert current_runs.status_code == 200
            current_runs_payload = current_runs.json()
            assert [run["run_id"] for run in current_runs_payload["runs"]] == [
                newer_run_root.name
            ]
            assert current_runs_payload["inferred_dataset_id"] == "resolved-demo-dataset"

            current_run_detail = await client.get(
                "/runs/current/unstructured_ingest",
                params={"stage_name": "claim_extraction"},
            )
            assert current_run_detail.status_code == 200
            detail_payload = current_run_detail.json()
            assert detail_payload["run"]["run_id"] == newer_run_root.name
            assert detail_payload["inferred_dataset_id"] == "resolved-demo-dataset"
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

            latest_per_prefix = await client.get(
                "/runs",
                params={
                    "dataset_id": "resolved-demo-dataset",
                    "latest_per_stage_prefix": "true",
                },
            )
            assert latest_per_prefix.status_code == 200
            assert [run["run_id"] for run in latest_per_prefix.json()["runs"]] == [
                newer_run_root.name
            ]

            detail_by_stage = await client.get(
                f"/runs/{newer_run_root.name}",
                params={"stage_name": "claim_extraction"},
            )
            assert detail_by_stage.status_code == 200
            detail_payload = detail_by_stage.json()
            assert detail_payload["run"]["run_id"] == newer_run_root.name
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

    asyncio.run(_exercise_app())


def test_claim_extraction_entrypoint_uses_package_default_runtime_runner() -> None:
    from power_atlas import entity_resolution_entrypoint  # noqa: F401
    from power_atlas.claim_extraction_entrypoint import (
        _default_runtime_runner,
        run_claim_extraction,
    )
    from power_atlas.contracts import get_default_claim_extraction_policy
    from power_atlas.contracts.pipeline import PipelineContractSnapshot
    from power_atlas.settings import Neo4jSettings

    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.claim_extraction_entrypoint._default_runtime_runner"
    ) as default_runtime_runner:
        default_runtime_runner.return_value = mock.Mock(return_value=result_payload)

        result = run_claim_extraction(
            object(),
            run_id="run-123",
            source_uri="file:///example/doc.pdf",
            pipeline_contract=PipelineContractSnapshot(
                chunk_embedding_index_name="ignored_index",
                chunk_embedding_label="Chunk",
                chunk_embedding_property="embedding",
                chunk_embedding_dimensions=1536,
                embedder_model_name="text-embedding-3-small",
                chunk_fallback_stride=1000,
            ),
            claim_extraction_policy=get_default_claim_extraction_policy(),
            neo4j_settings=Neo4jSettings(),
            model_name="gpt-5.4",
        )

    assert result == result_payload
    default_runtime_runner.assert_called_once_with()


def test_run_entity_resolution_accepts_custom_dataset_selection_contract() -> None:
    from power_atlas import entity_resolution_entrypoint
    from power_atlas.contracts import EntityResolutionDatasetSelectionContract
    from power_atlas.settings import Neo4jSettings

    dataset_selection = EntityResolutionDatasetSelectionContract(
        select_dataset_id=lambda config, dataset_id, dataset_name: (
            f"market::{dataset_name or getattr(config, 'dataset_name', 'missing')}::canonicals"
        )
    )
    runtime_runner = mock.Mock(return_value={"status": "ok"})
    config = SimpleNamespace(dataset_name="demo_dataset_v1")

    result = entity_resolution_entrypoint.run_entity_resolution(
        config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        resolution_mode=entity_resolution_entrypoint.RESOLUTION_MODE_HYBRID,
        dataset_name="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        entity_resolution_dataset_selection=dataset_selection,
        runtime_runner=runtime_runner,
    )

    assert result == {"status": "ok"}
    assert runtime_runner.call_args.kwargs["effective_dataset_id"] == (
        "market::market_trade_dataset_v1::canonicals"
    )


def test_claim_extraction_request_context_uses_package_default_config_runner() -> None:
    from power_atlas.bootstrap import bootstrap_app, build_request_context
    from power_atlas.claim_extraction_entrypoint import run_claim_extraction_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="extract-claims",
        dry_run=False,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
    )
    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.claim_extraction_entrypoint._default_config_runner",
        return_value=result_payload,
    ) as default_config_runner:
        result = run_claim_extraction_request_context(request_context)

    assert result == result_payload
    default_config_runner.assert_called_once_with(
        request_context.config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        pipeline_contract=request_context.pipeline_contract,
        claim_extraction_policy=request_context.policies.claim_extraction,
        neo4j_settings=request_context.settings.neo4j,
        model_name=request_context.settings.openai_model,
    )


def test_structured_ingest_entrypoint_uses_package_default_runtime_runner() -> None:
    from power_atlas.structured_ingest_entrypoint import run_structured_ingest
    from power_atlas.settings import Neo4jSettings

    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.structured_ingest_entrypoint._default_runtime_runner"
    ) as default_runtime_runner:
        default_runtime_runner.return_value = mock.Mock(return_value=result_payload)

        result = run_structured_ingest(
            object(),
            run_id="run-123",
            dataset_id="demo_dataset_v1",
            neo4j_settings=Neo4jSettings(),
        )

    assert result == result_payload
    default_runtime_runner.assert_called_once_with()


def test_structured_ingest_request_context_uses_package_default_config_runner() -> None:
    from power_atlas.bootstrap import bootstrap_app, build_request_context
    from power_atlas.structured_ingest_entrypoint import run_structured_ingest_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="ingest-structured",
        dry_run=False,
        run_id="run-123",
    )
    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.structured_ingest_entrypoint._default_config_runner",
        return_value=result_payload,
    ) as default_config_runner:
        result = run_structured_ingest_request_context(request_context)

    assert result == result_payload
    default_config_runner.assert_called_once_with(
        request_context.config,
        run_id="run-123",
        fixtures_dir=None,
        dataset_id=None,
        neo4j_settings=request_context.settings.neo4j,
        structured_graph_shape=None,
        structured_schema=None,
    )


def test_write_structured_ingest_graph_accepts_custom_graph_shape_contract() -> None:
    from power_atlas.contracts import StructuredGraphShapeContract
    from power_atlas.structured_ingest_writes import write_structured_ingest_graph

    graph_shape = StructuredGraphShapeContract(
        source_label="ResearchSource",
        entity_label="Security",
        fact_label="SecurityFact",
        relationship_label="MarketRelationship",
        claim_label="MarketClaim",
        asserted_in_relationship="RECORDED_IN",
        cited_from_relationship="CITED_MARKET_SOURCE",
        about_relationship="ABOUT_SECURITY",
        targets_relationship="TARGETS_SECURITY",
        supported_by_relationship="SUPPORTED_BY_RECORD",
        subject_relationship="MARKET_SUBJECT",
        object_relationship="MARKET_OBJECT",
    )

    session = mock.Mock()
    session.run.return_value.consume.return_value = None

    write_structured_ingest_graph(
        session,
        run_id="run-123",
        source_uri="file:///market/trade/source.csv",
        dataset_id="market_trade_dataset_v1",
        ingested_at="2026-05-12T00:00:00+00:00",
        entities_rows=[],
        facts_rows=[],
        relationship_rows=[],
        claims_rows=[],
        graph_shape=graph_shape,
    )

    rendered_queries = "\n".join(call.args[0] for call in session.run.call_args_list)
    assert "`ResearchSource`" in rendered_queries
    assert "`Security`" in rendered_queries
    assert "`SecurityFact`" in rendered_queries
    assert "`MarketRelationship`" in rendered_queries
    assert "`MarketClaim`" in rendered_queries
    assert "`RECORDED_IN`" in rendered_queries
    assert "`CITED_MARKET_SOURCE`" in rendered_queries
    assert "`ABOUT_SECURITY`" in rendered_queries
    assert "`TARGETS_SECURITY`" in rendered_queries
    assert "`SUPPORTED_BY_RECORD`" in rendered_queries
    assert "`MARKET_SUBJECT`" in rendered_queries
    assert "`MARKET_OBJECT`" in rendered_queries


def test_structured_ingest_runtime_forwards_custom_graph_shape_contract() -> None:
    from power_atlas.contracts import StructuredGraphShapeContract
    from power_atlas.settings import Neo4jSettings
    from power_atlas.structured_ingest_runner import run_structured_ingest_runtime

    graph_shape = StructuredGraphShapeContract(entity_label="Security")
    config = mock.Mock(output_dir=Path("build/test-structured-graph-shape"), dry_run=False)
    live_runner = mock.Mock()

    result = run_structured_ingest_runtime(
        config=config,
        run_id="run-123",
        dataset_id="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        structured_graph_shape=graph_shape,
        resolve_dataset=mock.Mock(
            return_value=(Path("fixtures/market_trade"), "market_trade_dataset_v1")
        ),
        lint_and_clean=mock.Mock(
            return_value={
                "structured_clean_dir": "build/test-structured-graph-shape/runs/run-123/structured_clean",
                "lint_report_path": "build/test-structured-graph-shape/runs/run-123/lint_report.json",
                "lint_summary": {"status": "ok", "issue_count": 0},
                "files": {},
            }
        ),
        read_csv_rows=mock.Mock(return_value=[]),
        timestamp_factory=mock.Mock(return_value="2026-05-12T00:00:00+00:00"),
        live_runner=live_runner,
    )

    assert result["status"] == "live"
    live_runner.assert_called_once()
    assert live_runner.call_args.kwargs["graph_shape"] is graph_shape



def test_structured_ingest_runtime_accepts_custom_structured_schema_contract(
    tmp_path: Path,
) -> None:
    from power_atlas.contracts import StructuredSchemaContract
    from power_atlas.settings import Neo4jSettings
    from power_atlas.structured_ingest_runner import run_structured_ingest_runtime

    fixtures_dir = tmp_path / "fixtures"
    structured_dir = fixtures_dir / "structured"
    structured_dir.mkdir(parents=True)

    schema = StructuredSchemaContract(
        entity_file_name="securities.csv",
        fact_file_name="security_facts.csv",
        relationship_file_name="security_relationships.csv",
        claim_file_name="security_claims.csv",
        file_headers={
            "securities.csv": (
                "entity_id",
                "name",
                "entity_type",
                "aliases",
                "description",
                "wikidata_url",
            ),
            "security_facts.csv": (
                "fact_id",
                "subject_id",
                "subject_label",
                "predicate_pid",
                "predicate_label",
                "value",
                "value_type",
                "source",
                "source_url",
                "retrieved_at",
            ),
            "security_relationships.csv": (
                "rel_id",
                "subject_id",
                "subject_label",
                "predicate_pid",
                "predicate_label",
                "object_id",
                "object_label",
                "object_entity_type",
                "source",
                "source_url",
                "retrieved_at",
            ),
            "security_claims.csv": (
                "claim_id",
                "claim_type",
                "subject_id",
                "subject_label",
                "predicate_pid",
                "predicate_label",
                "object_id",
                "object_label",
                "value",
                "value_type",
                "claim_text",
                "confidence",
                "source",
                "source_url",
                "retrieved_at",
                "source_row_id",
            ),
        },
        id_patterns={
            "entity_id": re.compile(r"^SEC\d+$"),
            "fact_id": re.compile(r"^FACT\d+$"),
            "rel_id": re.compile(r"^REL\d+$"),
            "claim_id": re.compile(r"^CLM\d+$"),
            "predicate_pid": re.compile(r"^MP\d+$"),
        },
    )

    (structured_dir / schema.entity_file_name).write_text(
        "entity_id,name,entity_type,aliases,description,wikidata_url\n"
        "SEC1,Acme Corp,Security,ACME,Example issuer,https://example.test/sec1\n"
        "SEC2,Example Exchange,Exchange,EXCH,Example venue,https://example.test/sec2\n",
        encoding="utf-8",
    )
    (structured_dir / schema.fact_file_name).write_text(
        "fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at\n"
        "FACT1,SEC1,Acme Corp,MP100,ticker,ACME,string,filing,https://example.test/fact,2026-01-01\n",
        encoding="utf-8",
    )
    (structured_dir / schema.relationship_file_name).write_text(
        "rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at\n"
        "REL1,SEC1,Acme Corp,MP200,listed_on,SEC2,Example Exchange,Exchange,filing,https://example.test/rel,2026-01-01\n",
        encoding="utf-8",
    )
    (structured_dir / schema.claim_file_name).write_text(
        "claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id\n"
        "CLM1,relationship,SEC1,Acme Corp,MP200,listed_on,SEC2,Example Exchange,,string,Acme Corp is listed on Example Exchange,0.9,filing,https://example.test/claim,2026-01-01,REL1\n",
        encoding="utf-8",
    )

    config = mock.Mock(output_dir=tmp_path / "artifacts", dry_run=True)

    result = run_structured_ingest_runtime(
        config=config,
        run_id="run-123",
        fixtures_dir=fixtures_dir,
        dataset_id="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        structured_schema=schema,
    )

    clean_dir = Path(result["structured_clean_dir"])
    assert result["status"] == "dry_run"
    assert result["entities"] == 2
    assert result["facts"] == 1
    assert result["relationships"] == 1
    assert result["claims"] == 1
    assert (clean_dir / "securities.csv").is_file()
    assert (clean_dir / "security_facts.csv").is_file()
    assert (clean_dir / "security_relationships.csv").is_file()
    assert (clean_dir / "security_claims.csv").is_file()
    assert not (clean_dir / "entities.csv").exists()


def test_pdf_ingest_entrypoint_uses_package_default_runtime_runner() -> None:
    from power_atlas.contracts.pipeline import PipelineContractSnapshot
    from power_atlas.pdf_ingest_entrypoint import run_pdf_ingest
    from power_atlas.settings import Neo4jSettings

    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.pdf_ingest_entrypoint._default_runtime_runner"
    ) as default_runtime_runner:
        default_runtime_runner.return_value = mock.Mock(return_value=result_payload)

        result = run_pdf_ingest(
            object(),
            "run-123",
            pipeline_contract=PipelineContractSnapshot(
                chunk_embedding_index_name="pdf_index",
                chunk_embedding_label="Chunk",
                chunk_embedding_property="embedding",
                chunk_embedding_dimensions=1536,
                embedder_model_name="text-embedding-3-small",
                chunk_fallback_stride=1000,
            ),
            neo4j_settings=Neo4jSettings(),
            openai_model="gpt-5.4",
            dataset_name="demo_dataset_v1",
        )

    assert result == result_payload
    default_runtime_runner.assert_called_once_with()


def test_pdf_ingest_request_context_uses_package_default_config_runner() -> None:
    from power_atlas.bootstrap import bootstrap_app, build_request_context
    from power_atlas.pdf_ingest_entrypoint import run_pdf_ingest_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="ingest-pdf",
        dry_run=False,
        run_id="run-123",
    )
    result_payload = {"status": "ok"}

    with mock.patch(
        "power_atlas.pdf_ingest_entrypoint._default_config_runner",
        return_value=result_payload,
    ) as default_config_runner:
        result = run_pdf_ingest_request_context(request_context)

    assert result == result_payload
    default_config_runner.assert_called_once_with(
        request_context.config,
        "run-123",
        fixtures_dir=None,
        pdf_filename=None,
        dataset_id=None,
        index_name=request_context.pipeline_contract.chunk_embedding_index_name,
        chunk_label=request_context.pipeline_contract.chunk_embedding_label,
        embedding_property=request_context.pipeline_contract.chunk_embedding_property,
        embedding_dimensions=request_context.pipeline_contract.chunk_embedding_dimensions,
        embedder_model=request_context.pipeline_contract.embedder_model_name,
        chunk_stride=request_context.pipeline_contract.chunk_fallback_stride,
        pipeline_contract=request_context.pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
        openai_model=request_context.settings.openai_model,
        dataset_name=request_context.settings.dataset_name,
    )


def test_retrieval_benchmark_entrypoint_uses_package_default_impl_runner() -> None:
    from power_atlas.retrieval_benchmark_entrypoint import run_retrieval_benchmark

    output_root = Path("build/test-retrieval-benchmark")
    config = mock.Mock(output_dir=output_root, dry_run=True)

    result = run_retrieval_benchmark(
        config,
        run_id="run-123",
        dataset_id="demo_dataset_v1",
        alignment_version="v1.0",
    )

    assert result["status"] == "dry_run"
    assert result["run_id"] == "run-123"
    assert result["dataset_id"] == "demo_dataset_v1"
    assert result["alignment_version"] == "v1.0"
    assert result["artifact_path"].endswith(
        "build/test-retrieval-benchmark/runs/run-123/retrieval_benchmark/retrieval_benchmark.json"
    )


def test_retrieval_benchmark_request_context_uses_package_default_impl_runner() -> None:
    from power_atlas.bootstrap import bootstrap_app, build_request_context
    from power_atlas.retrieval_benchmark_entrypoint import run_retrieval_benchmark_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_OUTPUT_DIR": "build/test-retrieval-benchmark-context",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="retrieval-benchmark",
        dry_run=True,
        run_id="run-123",
    )

    result = run_retrieval_benchmark_request_context(
        request_context,
        alignment_version="v1.0",
    )

    assert result["status"] == "dry_run"
    assert result["run_id"] == "run-123"
    assert result["dataset_id"] == "demo_dataset_v1"
    assert result["alignment_version"] == "v1.0"
    assert result["artifact_path"].endswith(
        "build/test-retrieval-benchmark-context/runs/run-123/retrieval_benchmark/retrieval_benchmark.json"
    )


def test_claim_extraction_diagnostics_entrypoint_uses_package_default_impl_runner() -> None:
    from power_atlas import claim_extraction_diagnostics

    output_root = Path("build/test-claim-extraction-diagnostics")
    config = mock.Mock(output_dir=output_root, dry_run=True)
    result_payload = {"status": "ok"}

    with mock.patch.object(
        claim_extraction_diagnostics,
        "_default_impl_runner",
    ) as default_impl_runner:
        default_impl_runner.return_value = mock.Mock(return_value=result_payload)

        result = claim_extraction_diagnostics.run_claim_extraction_diagnostics(
            config,
            run_id="run-123",
            source_uri="file:///example/doc.pdf",
        )

    assert result == result_payload
    default_impl_runner.assert_called_once_with()


def test_claim_extraction_diagnostics_request_context_uses_package_default_impl_runner() -> None:
    from power_atlas import claim_extraction_diagnostics
    from power_atlas.bootstrap import bootstrap_app, build_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_OUTPUT_DIR": "build/test-claim-extraction-diagnostics-context",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="claim-extraction-diagnostics",
        dry_run=True,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
    )

    result = claim_extraction_diagnostics.run_claim_extraction_diagnostics_request_context(
        request_context,
    )

    assert result["status"] == "dry_run"
    assert result["run_id"] == "run-123"
    assert result["source_uri"] == "file:///example/doc.pdf"
    assert result["artifact_path"].endswith(
        "build/test-claim-extraction-diagnostics-context/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json"
    )


def test_claim_extraction_diagnostics_runtime_writes_stable_dry_run_artifact(tmp_path: Path) -> None:
    from power_atlas.claim_extraction_diagnostics_runner import (
        run_claim_extraction_diagnostics_runtime_default,
    )

    result = run_claim_extraction_diagnostics_runtime_default(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_settings=None,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
    )

    artifact_path = (
        tmp_path
        / "runs"
        / "run-123"
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert result["status"] == "dry_run"
    assert artifact["status"] == "dry_run"
    assert artifact["run_id"] == "run-123"
    assert artifact["source_uri"] == "file:///example/doc.pdf"
    assert artifact["participation_summary"] == {
        "total_edges": 0,
        "edges_by_role": {},
        "total_claims": 0,
        "claims_with_zero_edges": 0,
        "claim_coverage_pct": None,
    }
    assert artifact["match_summary"] == {
        "total_edges_with_match_method": 0,
        "edges_by_match_method": {},
    }
    assert artifact["warnings"] == [
        "claim extraction diagnostics skipped in dry_run mode"
    ]


def test_claim_extraction_diagnostics_runtime_computes_live_summary_from_query_rows(tmp_path: Path) -> None:
    from power_atlas.claim_extraction_diagnostics_runner import (
        run_claim_extraction_diagnostics_runtime_default,
    )
    from power_atlas.settings import Neo4jSettings

    result = run_claim_extraction_diagnostics_runtime_default(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_settings=Neo4jSettings(),
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        query_specs_builder=lambda: [("role_dist", "role dist", "RETURN 1")],
        query_rows_fetcher=lambda *args, **kwargs: {
            "role_dist": [
                {"role": "subject", "total": 3},
                {"role": "object", "total": 1},
            ],
            "edge_coverage": [
                {"participant_edges": 0, "claim_count": 1},
                {"participant_edges": 2, "claim_count": 4},
            ],
            "match_method_dist": [
                {"match_method": "normalized_exact", "total": 2},
                {"match_method": "list_split", "total": 1},
            ],
        },
    )

    assert result["status"] == "live"
    assert result["participation_summary"] == {
        "total_edges": 4,
        "edges_by_role": {"subject": 3, "object": 1},
        "total_claims": 5,
        "claims_with_zero_edges": 1,
        "claim_coverage_pct": 80.0,
    }
    assert result["match_summary"] == {
        "total_edges_with_match_method": 3,
        "edges_by_match_method": {
            "normalized_exact": 2,
            "list_split": 1,
        },
    }


def test_claim_extraction_diagnostics_report_main_emits_run_scoped_report() -> None:
    from argparse import Namespace

    from power_atlas.claim_extraction_diagnostics_artifact import (
        ClaimExtractionDiagnosticsArtifactResult,
        ClaimExtractionDiagnosticsMatchSummary,
        ClaimExtractionDiagnosticsParticipationSummary,
    )
    from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (
        run_claim_extraction_diagnostics_report_main,
    )

    lines: list[str] = []
    warnings: list[str] = []

    run_claim_extraction_diagnostics_report_main(
        parse_args=lambda argv: Namespace(current=False, run_id="run-123"),
        build_settings=lambda args: object(),
        resolve_artifact=lambda settings, run_id: ClaimExtractionDiagnosticsArtifactResult(
            status="live",
            detail="ok",
            run_id=run_id,
            generated_at="2026-05-13T12:00:00+00:00",
            source_uri="file:///example/doc.pdf",
            artifact_path="/tmp/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
            participation_summary=ClaimExtractionDiagnosticsParticipationSummary(
                total_edges=4,
                edges_by_role={"subject": 3, "object": 1},
                total_claims=5,
                claims_with_zero_edges=1,
                claim_coverage_pct=80.0,
            ),
            match_summary=ClaimExtractionDiagnosticsMatchSummary(
                total_edges_with_match_method=3,
                edges_by_match_method={"normalized_exact": 2, "list_split": 1},
            ),
            warnings=["warn-1"],
        ),
        resolve_current_artifact=lambda *args, **kwargs: None,
        warn=warnings.append,
        emit=lines.append,
    )

    assert any("Status        : live" == line for line in lines)
    assert any("Run ID        : run-123" == line for line in lines)
    assert any("Artifact path : /tmp/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json" == line for line in lines)
    assert warnings == ["warn-1"]
    assert json.loads(lines[-1]) == {
        "run_id": "run-123",
        "artifact_path": "/tmp/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
        "status": "live",
    }


def test_claim_extraction_diagnostics_report_main_emits_current_run_report() -> None:
    from argparse import Namespace

    from power_atlas.claim_extraction_diagnostics_artifact import (
        ClaimExtractionDiagnosticsMatchSummary,
        ClaimExtractionDiagnosticsParticipationSummary,
        CurrentClaimExtractionDiagnosticsArtifactResult,
    )
    from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (
        run_claim_extraction_diagnostics_report_main,
    )

    lines: list[str] = []

    run_claim_extraction_diagnostics_report_main(
        parse_args=lambda argv: Namespace(
            current=True,
            stage_prefix="unstructured_ingest",
            dataset_id="demo_dataset_v1",
        ),
        build_settings=lambda args: object(),
        resolve_artifact=lambda *args, **kwargs: None,
        resolve_current_artifact=lambda settings, stage_prefix, dataset_id=None: CurrentClaimExtractionDiagnosticsArtifactResult(
            status="dry_run",
            detail="ok",
            run_id="unstructured_ingest-20260512T000100Z-b",
            generated_at="2026-05-13T12:00:00+00:00",
            source_uri="file:///example/doc.pdf",
            artifact_path="/tmp/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
            participation_summary=ClaimExtractionDiagnosticsParticipationSummary(
                total_edges=0,
                edges_by_role={},
                total_claims=0,
                claims_with_zero_edges=0,
                claim_coverage_pct=None,
            ),
            match_summary=ClaimExtractionDiagnosticsMatchSummary(
                total_edges_with_match_method=0,
                edges_by_match_method={},
            ),
            warnings=[],
            inferred_dataset_id="resolved-demo-dataset",
        ),
        warn=lambda warning: None,
        emit=lines.append,
    )

    assert any("Status        : dry_run" == line for line in lines)
    assert json.loads(lines[-1]) == {
        "run_id": "unstructured_ingest-20260512T000100Z-b",
        "artifact_path": "/tmp/runs/run-123/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
        "status": "dry_run",
        "inferred_dataset_id": "resolved-demo-dataset",
    }


def test_claim_extraction_diagnostics_report_main_rejects_missing_run_selector() -> None:
    from argparse import Namespace

    from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (
        run_claim_extraction_diagnostics_report_main,
    )

    errors: list[str] = []

    with pytest.raises(SystemExit) as exc_info:
        run_claim_extraction_diagnostics_report_main(
            parse_args=lambda argv: Namespace(current=False, run_id=None),
            build_settings=lambda args: object(),
            resolve_artifact=lambda *args, **kwargs: None,
            resolve_current_artifact=lambda *args, **kwargs: None,
            warn=lambda warning: None,
            emit=lambda *args, **kwargs: errors.append(str(args[0])),
        )

    assert exc_info.value.code == 1
    assert errors == ["ERROR: run_id is required unless --current is used."]


def test_claim_extraction_diagnostics_report_package_cli_main_delegates_to_entrypoint() -> None:
    from power_atlas.cli import claim_extraction_diagnostics_report

    argv = ["--run-id", "run-123"]

    with mock.patch.object(
        claim_extraction_diagnostics_report,
        "run_claim_extraction_diagnostics_report_main",
    ) as run_main:
        claim_extraction_diagnostics_report.main(argv)

    run_main.assert_called_once_with(
        parse_args=claim_extraction_diagnostics_report._parse_args,
        build_settings=claim_extraction_diagnostics_report.build_claim_extraction_diagnostics_report_settings,
        resolve_artifact=claim_extraction_diagnostics_report.resolve_claim_extraction_diagnostics_artifact,
        resolve_current_artifact=claim_extraction_diagnostics_report.resolve_current_claim_extraction_diagnostics_artifact,
        warn=mock.ANY,
        argv=argv,
    )


def test_entity_resolution_entrypoint_uses_package_default_runtime_runner() -> None:
    from power_atlas import entity_resolution_entrypoint
    from power_atlas.settings import Neo4jSettings

    result_payload = {"status": "ok"}

    with mock.patch.object(
        entity_resolution_entrypoint,
        "_default_runtime_runner",
    ) as default_runtime_runner:
        default_runtime_runner.return_value = mock.Mock(return_value=result_payload)

        result = entity_resolution_entrypoint.run_entity_resolution(
            object(),
            run_id="run-123",
            source_uri="file:///example/doc.pdf",
            resolution_mode=entity_resolution_entrypoint.RESOLUTION_MODE_HYBRID,
            dataset_id="demo_dataset_v1",
            neo4j_settings=Neo4jSettings(),
        )

    assert result == result_payload
    default_runtime_runner.assert_called_once_with()


def test_entity_resolution_request_context_uses_package_default_config_runner() -> None:
    from power_atlas import entity_resolution_entrypoint
    from power_atlas.bootstrap import bootstrap_app, build_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )
    request_context = build_request_context(
        app.app_context,
        command="resolve",
        dry_run=False,
        resolution_mode="hybrid",
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
    )
    result_payload = {"status": "ok"}

    with mock.patch.object(
        entity_resolution_entrypoint,
        "_default_config_runner",
        return_value=result_payload,
    ) as default_config_runner:
        result = entity_resolution_entrypoint.run_entity_resolution_request_context(
            request_context,
            resolution_mode="hybrid",
        )

    assert result == result_payload
    default_config_runner.assert_called_once_with(
        request_context.config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution",
        dataset_id=None,
        neo4j_settings=request_context.settings.neo4j,
        dataset_name="demo_dataset_v1",
        entity_type_policy=request_context.policies.entity_type_normalization,
        entity_resolution_dataset_selection=None,
        entity_resolution_alignment=None,
        entity_resolution_canonical_lookup=None,
        entity_resolution_graph=None,
    )


def test_resolve_effective_dataset_id_accepts_custom_dataset_selection_contract() -> None:
    from power_atlas.contracts import EntityResolutionDatasetSelectionContract
    from power_atlas.entity_resolution_entrypoint import resolve_effective_dataset_id

    dataset_selection = EntityResolutionDatasetSelectionContract(
        select_dataset_id=lambda config, dataset_id, dataset_name: (
            f"custom::{dataset_name or getattr(config, 'dataset_name', 'missing')}"
        )
    )

    result = resolve_effective_dataset_id(
        SimpleNamespace(dataset_name="demo_dataset_v1"),
        None,
        dataset_name="market_trade_dataset_v1",
        entity_resolution_dataset_selection=dataset_selection,
    )

    assert result == "custom::market_trade_dataset_v1"


def test_fetch_canonical_entities_accepts_custom_entity_resolution_canonical_lookup_contract() -> None:
    from power_atlas.contracts import EntityResolutionCanonicalLookupContract
    from power_atlas.entity_resolution_queries import fetch_canonical_entities

    lookup_contract = EntityResolutionCanonicalLookupContract(
        canonical_entity_id_field="security_id",
        canonical_run_id_field="security_run_id",
        canonical_name_field="security_name",
        canonical_aliases_field="ticker_aliases",
    )
    driver = mock.Mock()
    driver.execute_query.return_value = (
        [
            {
                "security_id": "SEC1",
                "security_run_id": "structured-1",
                "security_name": "Acme Corp",
                "ticker_aliases": "ACME|ACM",
            }
        ],
        None,
        None,
    )

    result = fetch_canonical_entities(
        driver,
        dataset_id="market_trade_dataset_v1",
        neo4j_database="neo4j",
        entity_resolution_canonical_lookup=lookup_contract,
    )

    rendered_query = driver.execute_query.call_args.args[0]
    assert result == [
        {
            "security_id": "SEC1",
            "security_run_id": "structured-1",
            "security_name": "Acme Corp",
            "ticker_aliases": "ACME|ACM",
        }
    ]
    assert "`security_id`" in rendered_query
    assert "`security_run_id`" in rendered_query
    assert "`security_name`" in rendered_query
    assert "`ticker_aliases`" in rendered_query


def test_resolve_mention_accepts_custom_entity_resolution_canonical_lookup_contract() -> None:
    from power_atlas.contracts import EntityResolutionCanonicalLookupContract
    from power_atlas.entity_resolution_resolver import _build_lookup_tables, _resolve_mention

    lookup_contract = EntityResolutionCanonicalLookupContract(
        canonical_entity_id_field="security_id",
        canonical_run_id_field="security_run_id",
        canonical_name_field="security_name",
        canonical_aliases_field="ticker_aliases",
        qid_pattern=re.compile(r"^SEC\d+$"),
        qid_exact_method="security_id_exact",
        unresolved_method="security_cluster",
    )
    by_qid, by_label, by_alias = _build_lookup_tables(
        [
            {
                "security_id": "SEC1",
                "security_run_id": "structured-1",
                "security_name": "Acme Corp",
                "ticker_aliases": "ACME|ACM",
            }
        ],
        canonical_lookup_contract=lookup_contract,
    )

    resolved = _resolve_mention(
        {"mention_id": "m-1", "name": "SEC1", "entity_type": "Company"},
        by_qid,
        by_label,
        by_alias,
        canonical_lookup_contract=lookup_contract,
    )
    aligned = _resolve_mention(
        {"mention_id": "m-2", "name": "ACME", "entity_type": "Company"},
        by_qid,
        by_label,
        by_alias,
        canonical_lookup_contract=lookup_contract,
    )

    assert resolved["canonical_entity_id"] == "SEC1"
    assert resolved["canonical_run_id"] == "structured-1"
    assert resolved["resolution_method"] == "security_id_exact"
    assert aligned["resolution_method"] == lookup_contract.alias_exact_method


def test_align_clusters_to_canonical_accepts_custom_entity_resolution_alignment_contract() -> None:
    from power_atlas.contracts import (
        EntityResolutionAlignmentContract,
        EntityResolutionAlignmentStep,
    )
    from power_atlas.entity_resolution_alignment import align_clusters_to_canonical

    alignment_contract = EntityResolutionAlignmentContract(
        steps=(
            EntityResolutionAlignmentStep(
                lookup_table="alias",
                cluster_keys=lambda cluster: (cluster["normalized_text"].lstrip("$"),),
                method="symbol_alias",
                score=0.97,
                status="tentative",
            ),
        )
    )

    aligned = align_clusters_to_canonical(
        [{"cluster_id": "cluster-1", "normalized_text": "$acme"}],
        by_label={},
        by_alias={
            "acme": {
                "entity_id": "SEC1",
                "run_id": "structured-1",
            }
        },
        entity_resolution_alignment=alignment_contract,
    )

    assert aligned == [
        {
            "cluster_id": "cluster-1",
            "canonical_entity_id": "SEC1",
            "canonical_run_id": "structured-1",
            "alignment_method": "symbol_alias",
            "alignment_score": 0.97,
            "alignment_status": "tentative",
            "source_uri": None,
        }
    ]


def test_entity_resolution_runtime_forwards_custom_canonical_lookup_contract() -> None:
    from power_atlas.contracts import EntityResolutionCanonicalLookupContract
    from power_atlas.entity_resolution_runner import run_entity_resolution_runtime
    from power_atlas.settings import Neo4jSettings

    lookup_contract = EntityResolutionCanonicalLookupContract(
        canonical_entity_id_field="security_id"
    )
    config = mock.Mock(output_dir=Path("build/test-entity-resolution-lookup"), dry_run=False)
    live_runner = mock.Mock(
        return_value=SimpleNamespace(
            mentions=[],
            resolved_rows=[],
            unresolved_rows=[],
            resolution_breakdown={},
            graph_mentions_clustered=0,
            graph_mentions_unclustered=0,
            graph_total_clusters=0,
            graph_aligned_clusters=0,
            graph_distinct_canonical_entities=0,
            graph_mentions_in_aligned=0,
            graph_alignment_breakdown={},
            warnings=[],
        )
    )

    result = run_entity_resolution_runtime(
        config=config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution",
        effective_dataset_id="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        entity_resolution_canonical_lookup=lookup_contract,
        resolver_version="v1",
        cluster_version="v1",
        alignment_version="v1",
        build_entity_type_report=mock.Mock(return_value={}),
        cluster_mentions=mock.Mock(return_value=[]),
        fetch_mentions=mock.Mock(return_value=[]),
        fetch_canonicals=mock.Mock(return_value=[]),
        build_lookup_tables=mock.Mock(return_value=({}, {}, {})),
        make_cluster_id=mock.Mock(return_value="cluster-1"),
        align_clusters_to_canonical=mock.Mock(return_value=[]),
        resolve_mention=mock.Mock(),
        write_resolution_results=mock.Mock(),
        write_alignment_results=mock.Mock(),
        fetch_member_of_coverage=mock.Mock(
            return_value=SimpleNamespace(mentions_clustered=0, mentions_unclustered=0)
        ),
        fetch_alignment_coverage=mock.Mock(
            return_value=SimpleNamespace(
                total_clusters=0,
                aligned_clusters=0,
                distinct_canonical_entities_aligned=0,
                mentions_in_aligned=0,
                alignment_breakdown={},
            )
        ),
        resolution_mode_structured_anchor="structured_anchor",
        resolution_mode_unstructured_only="unstructured_only",
        resolution_mode_hybrid="hybrid",
        live_runner=live_runner,
    )

    assert result["status"] == "live"
    live_runner.assert_called_once()
    assert (
        live_runner.call_args.kwargs["entity_resolution_canonical_lookup"]
        is lookup_contract
    )


def test_entity_resolution_runtime_forwards_custom_alignment_contract() -> None:
    from power_atlas.contracts import EntityResolutionAlignmentContract
    from power_atlas.contracts import EntityResolutionAlignmentStep
    from power_atlas.entity_resolution_runner import run_entity_resolution_runtime
    from power_atlas.settings import Neo4jSettings

    alignment_contract = EntityResolutionAlignmentContract(
        steps=(EntityResolutionAlignmentStep(lookup_table="alias"),)
    )
    config = mock.Mock(output_dir=Path("build/test-entity-resolution-alignment"), dry_run=False)
    live_runner = mock.Mock(
        return_value=SimpleNamespace(
            mentions=[],
            resolved_rows=[],
            unresolved_rows=[],
            resolution_breakdown={},
            graph_mentions_clustered=0,
            graph_mentions_unclustered=0,
            graph_total_clusters=0,
            graph_aligned_clusters=0,
            graph_distinct_canonical_entities=0,
            graph_mentions_in_aligned=0,
            graph_alignment_breakdown={},
            warnings=[],
        )
    )

    result = run_entity_resolution_runtime(
        config=config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution",
        effective_dataset_id="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        entity_resolution_alignment=alignment_contract,
        resolver_version="v1",
        cluster_version="v1",
        alignment_version="v1",
        build_entity_type_report=mock.Mock(return_value={}),
        cluster_mentions=mock.Mock(return_value=[]),
        fetch_mentions=mock.Mock(return_value=[]),
        fetch_canonicals=mock.Mock(return_value=[]),
        build_lookup_tables=mock.Mock(return_value=({}, {}, {})),
        make_cluster_id=mock.Mock(return_value="cluster-1"),
        align_clusters_to_canonical=mock.Mock(return_value=[]),
        resolve_mention=mock.Mock(),
        write_resolution_results=mock.Mock(),
        write_alignment_results=mock.Mock(),
        fetch_member_of_coverage=mock.Mock(
            return_value=SimpleNamespace(mentions_clustered=0, mentions_unclustered=0)
        ),
        fetch_alignment_coverage=mock.Mock(
            return_value=SimpleNamespace(
                total_clusters=0,
                aligned_clusters=0,
                distinct_canonical_entities_aligned=0,
                mentions_in_aligned=0,
                alignment_breakdown={},
            )
        ),
        resolution_mode_structured_anchor="structured_anchor",
        resolution_mode_unstructured_only="unstructured_only",
        resolution_mode_hybrid="hybrid",
        live_runner=live_runner,
    )

    assert result["status"] == "live"
    live_runner.assert_called_once()
    assert live_runner.call_args.kwargs["entity_resolution_alignment"] is alignment_contract


def test_fetch_alignment_coverage_accepts_custom_entity_resolution_graph_contract() -> None:
    from power_atlas.contracts import EntityResolutionGraphContract
    from power_atlas.entity_resolution_queries import fetch_alignment_coverage

    graph_contract = EntityResolutionGraphContract(
        mention_label="SecurityMention",
        canonical_label="Security",
        cluster_label="SecurityCluster",
        member_of_relationship="MEMBER_OF_SECURITY_CLUSTER",
        aligned_with_relationship="ALIGNED_WITH_SECURITY",
    )
    driver = mock.Mock()
    driver.execute_query.side_effect = [
        ([{"total_clusters": 3}], None, None),
        ([{"aligned_clusters": 2, "distinct_canonical_entities_aligned": 2}], None, None),
        ([{"alignment_method": "label_exact", "method_count": 2}], None, None),
        ([{"mentions_in_aligned": 5}], None, None),
    ]

    result = fetch_alignment_coverage(
        driver,
        run_id="run-123",
        alignment_version="v1",
        neo4j_database="neo4j",
        entity_resolution_graph=graph_contract,
    )

    rendered_queries = "\n".join(call.args[0] for call in driver.execute_query.call_args_list)
    assert result.total_clusters == 3
    assert result.aligned_clusters == 2
    assert "`SecurityMention`" in rendered_queries
    assert "`SecurityCluster`" in rendered_queries
    assert "`Security`" in rendered_queries
    assert "`MEMBER_OF_SECURITY_CLUSTER`" in rendered_queries
    assert "`ALIGNED_WITH_SECURITY`" in rendered_queries


def test_write_alignment_results_accepts_custom_entity_resolution_graph_contract() -> None:
    from power_atlas.contracts import EntityResolutionGraphContract
    from power_atlas.entity_resolution_writes import write_alignment_results

    graph_contract = EntityResolutionGraphContract(
        canonical_label="Security",
        cluster_label="SecurityCluster",
        aligned_with_relationship="ALIGNED_WITH_SECURITY",
    )
    driver = mock.Mock()

    write_alignment_results(
        driver,
        run_id="run-123",
        source_uri="file:///market/trade/source.pdf",
        alignment_rows=[
            {
                "cluster_id": "cluster-1",
                "canonical_entity_id": "SEC1",
                "canonical_run_id": "structured-1",
                "alignment_method": "label_exact",
                "alignment_score": 0.9,
                "alignment_status": "aligned",
                "source_uri": "file:///market/trade/source.pdf",
            }
        ],
        neo4j_database="neo4j",
        alignment_version="v1",
        entity_resolution_graph=graph_contract,
    )

    rendered_query = driver.execute_query.call_args.args[0]
    assert "`SecurityCluster`" in rendered_query
    assert "`Security`" in rendered_query
    assert "`ALIGNED_WITH_SECURITY`" in rendered_query


def test_entity_resolution_runtime_forwards_custom_graph_contract() -> None:
    from power_atlas.contracts import EntityResolutionGraphContract
    from power_atlas.entity_resolution_runner import run_entity_resolution_runtime
    from power_atlas.settings import Neo4jSettings

    graph_contract = EntityResolutionGraphContract(canonical_label="Security")
    config = mock.Mock(output_dir=Path("build/test-entity-resolution-graph"), dry_run=False)
    live_runner = mock.Mock(
        return_value=SimpleNamespace(
            mentions=[],
            resolved_rows=[],
            unresolved_rows=[],
            resolution_breakdown={},
            graph_mentions_clustered=0,
            graph_mentions_unclustered=0,
            graph_total_clusters=0,
            graph_aligned_clusters=0,
            graph_distinct_canonical_entities=0,
            graph_mentions_in_aligned=0,
            graph_alignment_breakdown={},
            warnings=[],
        )
    )

    result = run_entity_resolution_runtime(
        config=config,
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
        resolution_mode="hybrid",
        artifact_subdir="entity_resolution",
        effective_dataset_id="market_trade_dataset_v1",
        neo4j_settings=Neo4jSettings(),
        entity_resolution_graph=graph_contract,
        resolver_version="v1",
        cluster_version="v1",
        alignment_version="v1",
        build_entity_type_report=mock.Mock(return_value={}),
        cluster_mentions=mock.Mock(return_value=[]),
        fetch_mentions=mock.Mock(return_value=[]),
        fetch_canonicals=mock.Mock(return_value=[]),
        build_lookup_tables=mock.Mock(return_value=({}, {}, {})),
        make_cluster_id=mock.Mock(return_value="cluster-1"),
        align_clusters_to_canonical=mock.Mock(return_value=[]),
        resolve_mention=mock.Mock(),
        write_resolution_results=mock.Mock(),
        write_alignment_results=mock.Mock(),
        fetch_member_of_coverage=mock.Mock(
            return_value=SimpleNamespace(mentions_clustered=0, mentions_unclustered=0)
        ),
        fetch_alignment_coverage=mock.Mock(
            return_value=SimpleNamespace(
                total_clusters=0,
                aligned_clusters=0,
                distinct_canonical_entities_aligned=0,
                mentions_in_aligned=0,
                alignment_breakdown={},
            )
        ),
        resolution_mode_structured_anchor="structured_anchor",
        resolution_mode_unstructured_only="unstructured_only",
        resolution_mode_hybrid="hybrid",
        live_runner=live_runner,
    )

    assert result["status"] == "live"
    live_runner.assert_called_once()
    assert live_runner.call_args.kwargs["entity_resolution_graph"] is graph_contract


def test_default_retrieval_policy_matches_existing_power_atlas_defaults() -> None:
    from power_atlas.contracts import (
        POWER_ATLAS_RAG_TEMPLATE,
        POWER_ATLAS_RETRIEVAL_POLICY,
        PROMPT_IDS,
        get_default_retrieval_policy,
    )

    retrieval_policy = get_default_retrieval_policy()

    assert retrieval_policy is POWER_ATLAS_RETRIEVAL_POLICY
    assert retrieval_policy.qa_prompt_id == PROMPT_IDS["qa"]
    assert retrieval_policy.rag_template is POWER_ATLAS_RAG_TEMPLATE
    assert retrieval_policy.ontology.claim_label == "ExtractedClaim"
    assert retrieval_policy.ontology.aligned_with_relationship == "ALIGNED_WITH"
    assert retrieval_policy.default_expand_graph is False
    assert retrieval_policy.default_cluster_aware is False


def test_default_claim_extraction_policy_matches_existing_power_atlas_defaults() -> None:
    from power_atlas.contracts import (
        POWER_ATLAS_CLAIM_EXTRACTION_POLICY,
        PROMPT_IDS,
        get_default_claim_extraction_policy,
    )

    claim_extraction_policy = get_default_claim_extraction_policy()

    assert claim_extraction_policy is POWER_ATLAS_CLAIM_EXTRACTION_POLICY
    assert claim_extraction_policy.prompt_id == PROMPT_IDS["claim_extraction"]
    assert claim_extraction_policy.ontology.claim_label == "ExtractedClaim"
    assert claim_extraction_policy.ontology.mentioned_in_relationship == "MENTIONED_IN"


def test_claim_extraction_schema_accepts_policy_ontology_override() -> None:
    from power_atlas.contracts import ClaimExtractionOntology, claim_extraction_schema

    schema = claim_extraction_schema(
        ClaimExtractionOntology(
            claim_label="ResearchClaim",
            mention_label="ResearchMention",
            mentions_relationship="ASSERTS",
            supported_by_relationship="EVIDENCED_BY",
            mentioned_in_relationship="FOUND_IN",
            has_participant_relationship="HAS_ROLE",
            chunk_text_property="body_text",
        )
    )

    node_labels = {node_type.label for node_type in schema.node_types}
    relationship_labels = {relationship_type.label for relationship_type in schema.relationship_types}
    assert node_labels == {"ResearchClaim", "ResearchMention"}
    assert relationship_labels == {"ASSERTS", "EVIDENCED_BY", "FOUND_IN", "HAS_ROLE"}


def test_build_runtime_config_from_settings() -> None:
    from power_atlas.bootstrap import build_runtime_config
    from power_atlas.settings import AppSettings, Neo4jSettings

    settings = AppSettings(
        neo4j=Neo4jSettings(
            uri="bolt://example.test:7687",
            username="atlas",
            password="secret",
            database="analytics",
        ),
        openai_model="gpt-5.4",
        embedder_model="text-embedding-3-large",
        output_dir=Path("build/power-atlas"),
        dataset_name="demo_dataset_v1",
    )

    config = build_runtime_config(
        settings,
        dry_run=False,
        question="Who acquired Xapo?",
        resolution_mode="hybrid",
    )

    assert config.dry_run is False
    assert config.output_dir == Path("build/power-atlas")
    assert config.settings == settings
    assert "settings" in config.__dict__
    assert "neo4j_uri" not in config.__dict__
    assert "neo4j_username" not in config.__dict__
    assert "neo4j_password" not in config.__dict__
    assert "neo4j_database" not in config.__dict__
    assert "openai_model" not in config.__dict__
    assert config.neo4j_uri == "bolt://example.test:7687"
    assert config.neo4j_username == "atlas"
    assert config.neo4j_password == "secret"
    assert config.neo4j_database == "analytics"
    assert config.openai_model == "gpt-5.4"
    assert config.question == "Who acquired Xapo?"
    assert config.resolution_mode == "hybrid"
    assert config.dataset_name == "demo_dataset_v1"


def test_bootstrap_app_exposes_app_context_and_request_context() -> None:
    from power_atlas.bootstrap import bootstrap_app, build_request_context

    app = bootstrap_app(
        {
            "NEO4J_URI": "bolt://example.test:7687",
            "NEO4J_USERNAME": "atlas",
            "NEO4J_PASSWORD": "secret",
            "NEO4J_DATABASE": "analytics",
            "OPENAI_MODEL": "gpt-5.4",
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        }
    )

    request_context = build_request_context(
        app.app_context,
        command="ask",
        dry_run=False,
        question="Who acquired Xapo?",
        resolution_mode="hybrid",
        run_id="run-123",
        source_uri="file:///example/doc.pdf",
    )

    assert app.app_context.settings is app.settings
    assert request_context.policies is app.app_context.policies
    assert request_context.app is app.app_context
    assert request_context.settings is app.settings
    assert request_context.command == "ask"
    assert request_context.run_id == "run-123"
    assert request_context.source_uri == "file:///example/doc.pdf"
    assert request_context.config.question == "Who acquired Xapo?"
    assert request_context.config.resolution_mode == "hybrid"
    assert request_context.config.dataset_name == "demo_dataset_v1"


def test_default_app_policies_expose_default_stage_policies() -> None:
    from power_atlas.context import build_default_app_policies
    from power_atlas.contracts import (
        POWER_ATLAS_CLAIM_EXTRACTION_POLICY,
        POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY,
        POWER_ATLAS_RETRIEVAL_POLICY,
    )

    policies = build_default_app_policies()

    assert policies.retrieval is POWER_ATLAS_RETRIEVAL_POLICY
    assert policies.claim_extraction is POWER_ATLAS_CLAIM_EXTRACTION_POLICY
    assert policies.entity_type_normalization is POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY


def test_run_retrieval_request_context_forwards_request_owned_retrieval_policy() -> None:
    from dataclasses import replace

    from neo4j_graphrag.generation import RagTemplate

    from power_atlas.bootstrap import build_app_context, build_request_context
    from power_atlas.contracts import RetrievalOntology, RetrievalPolicy
    from power_atlas.retrieval_request_context_adapters import run_retrieval_request_context

    alternate_policy = RetrievalPolicy(
        ontology=RetrievalOntology(
            claim_label="ResearchClaim",
            mention_label="ResearchMention",
            cluster_label="ResearchCluster",
            canonical_label="ResearchCanonical",
            supported_by_relationship="BACKED_BY",
            mentioned_in_relationship="LOCATED_IN",
            has_participant_relationship="HAS_ROLE",
            resolves_to_relationship="MAPS_TO",
            member_of_relationship="BELONGS_TO",
            aligned_with_relationship="LINKED_TO",
        ),
        qa_prompt_id="alt_qa_v1",
        rag_template=RagTemplate(
            template="Context:\n{context}\nExamples:\n{examples}\nQuestion:\n{query_text}\nAnswer:",
            system_instructions="Alternate retrieval policy prompt",
        ),
        default_expand_graph=True,
        default_cluster_aware=True,
    )
    request_context = build_request_context(
        replace(
            build_app_context(environ={}),
            policies=replace(build_app_context(environ={}).policies, retrieval=alternate_policy),
        ),
        command="ask",
        dry_run=True,
        question="Which policy was forwarded?",
        run_id="forwarded-policy-run",
        source_uri="file:///forwarded-policy.pdf",
    )
    captured: dict[str, object] = {}

    def _fake_run_impl(config: object, **kwargs: object) -> dict[str, object]:
        captured["config"] = config
        captured.update(kwargs)
        return {"status": "ok"}

    result = run_retrieval_request_context(
        request_context,
        top_k=7,
        index_name=None,
        question=None,
        expand_graph=None,
        cluster_aware=None,
        message_history=[{"role": "user", "content": "Earlier turn"}],
        interactive=True,
        run_impl=_fake_run_impl,
    )

    assert result == {"status": "ok"}
    assert captured["config"] is request_context.config
    assert captured["retrieval_policy"] is alternate_policy
    assert captured["pipeline_contract"] is request_context.pipeline_contract
    assert captured["neo4j_settings"] is request_context.settings.neo4j
    assert captured["index_name"] == request_context.pipeline_contract.chunk_embedding_index_name
    assert captured["question"] == "Which policy was forwarded?"
    assert captured["run_id"] == "forwarded-policy-run"
    assert captured["source_uri"] == "file:///forwarded-policy.pdf"
    assert captured["all_runs"] is False
    assert captured["interactive"] is True


def test_run_interactive_request_context_forwards_request_owned_retrieval_policy() -> None:
    from dataclasses import replace

    from neo4j_graphrag.generation import RagTemplate

    from power_atlas.bootstrap import build_app_context, build_request_context
    from power_atlas.contracts import RetrievalOntology, RetrievalPolicy
    from power_atlas.retrieval_request_context_adapters import run_interactive_request_context

    alternate_policy = RetrievalPolicy(
        ontology=RetrievalOntology(
            claim_label="InteractiveClaim",
            mention_label="InteractiveMention",
            cluster_label="InteractiveCluster",
            canonical_label="InteractiveCanonical",
            supported_by_relationship="CONFIRMED_BY",
            mentioned_in_relationship="OBSERVED_IN",
            has_participant_relationship="HAS_ACTOR",
            resolves_to_relationship="POINTS_TO",
            member_of_relationship="GROUPED_WITH",
            aligned_with_relationship="CROSSWALKS_TO",
        ),
        qa_prompt_id="interactive_alt_qa_v1",
        rag_template=RagTemplate(
            template="Context:\n{context}\nExamples:\n{examples}\nQuestion:\n{query_text}\nAnswer:",
            system_instructions="Interactive alternate retrieval policy prompt",
        ),
    )
    request_context = build_request_context(
        replace(
            build_app_context(environ={}),
            policies=replace(build_app_context(environ={}).policies, retrieval=alternate_policy),
        ),
        command="ask",
        dry_run=True,
        run_id="interactive-policy-run",
        all_runs=False,
        source_uri="file:///interactive-policy.pdf",
    )
    captured: dict[str, object] = {}

    def _fake_run_impl(config: object, **kwargs: object) -> str:
        captured["config"] = config
        captured.update(kwargs)
        return "interactive-ok"

    result = run_interactive_request_context(
        request_context,
        top_k=5,
        index_name=None,
        expand_graph=None,
        cluster_aware=None,
        all_runs=True,
        debug=True,
        run_impl=_fake_run_impl,
    )

    assert result == "interactive-ok"
    assert captured["config"] is request_context.config
    assert captured["retrieval_policy"] is alternate_policy
    assert captured["pipeline_contract"] is request_context.pipeline_contract
    assert captured["neo4j_settings"] is request_context.settings.neo4j
    assert captured["index_name"] == request_context.pipeline_contract.chunk_embedding_index_name
    assert captured["run_id"] == "interactive-policy-run"
    assert captured["source_uri"] == "file:///interactive-policy.pdf"
    assert captured["all_runs"] is True
    assert captured["debug"] is True


def test_package_cli_ask_prep_preserves_retrieval_policy_for_retrieval_adapter() -> None:
    from argparse import Namespace
    from dataclasses import replace

    from neo4j_graphrag.generation import RagTemplate

    from power_atlas.bootstrap import build_app_context, build_request_context
    from power_atlas.contracts import RetrievalOntology, RetrievalPolicy
    from power_atlas.interfaces.cli.run_demo_entrypoint import (
        prepare_run_demo_ask_request_context,
    )
    from power_atlas.retrieval_request_context_adapters import run_retrieval_request_context

    alternate_policy = RetrievalPolicy(
        ontology=RetrievalOntology(
            claim_label="CliPreparedClaim",
            mention_label="CliPreparedMention",
            cluster_label="CliPreparedCluster",
            canonical_label="CliPreparedCanonical",
            supported_by_relationship="SUPPORTED_EXTERNALLY_BY",
            mentioned_in_relationship="OBSERVED_WITHIN",
            has_participant_relationship="HAS_INTERACTOR",
            resolves_to_relationship="NORMALIZES_TO",
            member_of_relationship="CLUSTERED_IN",
            aligned_with_relationship="ALIGNS_EXTERNALLY_WITH",
        ),
        qa_prompt_id="cli_prepared_alt_qa_v1",
        rag_template=RagTemplate(
            template="Context:\n{context}\nExamples:\n{examples}\nQuestion:\n{query_text}\nAnswer:",
            system_instructions="CLI ask-prep alternate retrieval policy prompt",
        ),
    )
    app_context = build_app_context(environ={})
    app_context = replace(
        app_context,
        policies=replace(app_context.policies, retrieval=alternate_policy),
    )
    request_context = build_request_context(
        app_context,
        command="ask",
        dry_run=True,
        question="Which prepared policy survives?",
        run_id="seed-run-id",
        source_uri="file:///seed-source.pdf",
    )

    prepared_request_context = prepare_run_demo_ask_request_context(
        Namespace(command="ask"),
        request_context,
        resolve_ask_scope=lambda args, request_context: ("prepared-run-id", True),
        resolve_ask_source_uri=lambda request_context: (
            f"file:///prepared/{request_context.run_id}.pdf"
        ),
    )
    captured: dict[str, object] = {}

    def _fake_run_impl(config: object, **kwargs: object) -> dict[str, object]:
        captured["config"] = config
        captured.update(kwargs)
        return {"status": "prepared-ok"}

    result = run_retrieval_request_context(
        prepared_request_context,
        top_k=3,
        index_name=None,
        question=None,
        expand_graph=False,
        cluster_aware=False,
        message_history=None,
        interactive=False,
        run_impl=_fake_run_impl,
    )

    assert result == {"status": "prepared-ok"}
    assert prepared_request_context.app is request_context.app
    assert prepared_request_context.policies.retrieval is alternate_policy
    assert prepared_request_context.run_id == "prepared-run-id"
    assert prepared_request_context.all_runs is True
    assert prepared_request_context.source_uri == "file:///prepared/prepared-run-id.pdf"
    assert captured["retrieval_policy"] is alternate_policy
    assert captured["run_id"] == "prepared-run-id"
    assert captured["all_runs"] is True
    assert captured["source_uri"] == "file:///prepared/prepared-run-id.pdf"


def test_default_entity_type_normalization_policy_matches_power_atlas_defaults() -> None:
    from power_atlas.contracts import (
        POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY,
        get_default_entity_type_normalization_policy,
        normalize_entity_type,
    )

    policy = get_default_entity_type_normalization_policy()

    assert policy is POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY
    assert normalize_entity_type("ORG", policy) == "Organization"
    assert normalize_entity_type("person", policy) == "Person"
    assert normalize_entity_type("", policy) is None


def test_dataset_env_selection_prefers_power_atlas_dataset() -> None:
    from power_atlas.bootstrap import dataset_env_selection

    selection = dataset_env_selection(
        {
            "POWER_ATLAS_DATASET": "demo_dataset_v2",
            "FIXTURE_DATASET": "demo_dataset_v1",
        }
    )

    assert selection == ("demo_dataset_v2", "demo_dataset_v1", "demo_dataset_v2")


def test_dataset_env_selection_uses_fixture_dataset_when_power_atlas_missing() -> None:
    from power_atlas.bootstrap import dataset_env_selection

    selection = dataset_env_selection({"FIXTURE_DATASET": "demo_dataset_v1"})

    assert selection == (None, "demo_dataset_v1", "demo_dataset_v1")


def test_require_openai_api_key_uses_mapping() -> None:
    from power_atlas.bootstrap import has_openai_api_key, require_openai_api_key

    assert has_openai_api_key({"OPENAI_API_KEY": "test-key"}) is True
    assert has_openai_api_key({"OPENAI_API_KEY": ""}) is False

    require_openai_api_key("missing key", environ={"OPENAI_API_KEY": "test-key"})

    try:
        require_openai_api_key("missing key", environ={})
    except ValueError as exc:
        assert str(exc) == "missing key"
    else:
        raise AssertionError("Expected require_openai_api_key to raise for missing key")


def test_temporary_environment_restores_mapping_state() -> None:
    from power_atlas.bootstrap import temporary_environment

    env = {"EXISTING": "before"}

    with temporary_environment({"EXISTING": "after", "NEW_KEY": "value"}, environ=env):
        assert env["EXISTING"] == "after"
        assert env["NEW_KEY"] == "value"

    assert env == {"EXISTING": "before"}


def test_normalize_mention_text() -> None:
    from power_atlas.text_utils import normalize_mention_text

    assert normalize_mention_text("  M\u00fcller\u2013Group  ") == "muller-group"


def test_build_llm_for_settings_uses_model_from_settings() -> None:
    from power_atlas.bootstrap.clients import build_llm_for_settings
    from power_atlas.settings import AppSettings, Neo4jSettings

    settings = AppSettings(
        neo4j=Neo4jSettings(),
        openai_model="gpt-5.4",
        embedder_model="text-embedding-3-small",
        output_dir=Path("artifacts"),
        dataset_name=None,
    )

    with mock.patch("power_atlas.bootstrap.clients.build_openai_llm") as build_openai_llm:
        build_llm_for_settings(settings, reasoning_effort="none")

    build_openai_llm.assert_called_once_with("gpt-5.4", reasoning_effort="none")


def test_create_neo4j_driver_uses_settings_credentials() -> None:
    from power_atlas.bootstrap.clients import create_neo4j_driver
    from power_atlas.settings import AppSettings, Neo4jSettings

    settings = AppSettings(
        neo4j=Neo4jSettings(
            uri="bolt://example.test:7687",
            username="atlas",
            password="secret",
            database="neo4j",
        ),
        openai_model="gpt-5.4",
        embedder_model="text-embedding-3-small",
        output_dir=Path("artifacts"),
        dataset_name=None,
    )

    with mock.patch("power_atlas.bootstrap.clients.neo4j.GraphDatabase.driver") as driver:
        create_neo4j_driver(settings)

    driver.assert_called_once_with(
        "bolt://example.test:7687",
        auth=("atlas", "secret"),
    )


def test_create_neo4j_driver_uses_neo4j_settings_credentials() -> None:
    from power_atlas.bootstrap.clients import create_neo4j_driver
    from power_atlas.settings import Neo4jSettings

    settings = Neo4jSettings(
        uri="bolt://example.settings:7687",
        username="settings-user",
        password="settings-secret",
        database="settings-db",
    )

    with mock.patch("power_atlas.bootstrap.clients.neo4j.GraphDatabase.driver") as driver:
        create_neo4j_driver(settings)

    driver.assert_called_once_with(
        "bolt://example.settings:7687",
        auth=("settings-user", "settings-secret"),
    )


def test_claim_extraction_lexical_config_reads_live_pipeline_contract_snapshot() -> None:
    import power_atlas.contracts.claim_schema as claim_schema_module
    import power_atlas.contracts.pipeline as pipeline_module

    original_state = pipeline_module._get_pipeline_contract_state_for_test()
    try:
        pipeline_module._set_pipeline_contract_state_for_test(
            chunk_embedding_label="DynamicChunk",
            chunk_embedding_property="dynamic_embedding",
        )

        lexical_config = claim_schema_module.claim_extraction_lexical_config(
            pipeline_module.get_pipeline_contract_snapshot()
        )

        assert lexical_config.chunk_node_label == "DynamicChunk"
        assert lexical_config.chunk_embedding_property == "dynamic_embedding"
    finally:
        pipeline_module._set_pipeline_contract_state_for_test(
            config_data=original_state.config_data,
            chunk_embedding_index_name=original_state.snapshot.chunk_embedding_index_name,
            chunk_embedding_label=original_state.snapshot.chunk_embedding_label,
            chunk_embedding_property=original_state.snapshot.chunk_embedding_property,
            chunk_embedding_dimensions=original_state.snapshot.chunk_embedding_dimensions,
            embedder_model_name=original_state.snapshot.embedder_model_name,
            chunk_fallback_stride=original_state.snapshot.chunk_fallback_stride,
        )


def test_claim_extraction_lexical_config_accepts_explicit_pipeline_contract() -> None:
    import power_atlas.contracts.claim_schema as claim_schema_module
    from power_atlas.contracts.pipeline import PipelineContractSnapshot

    lexical_config = claim_schema_module.claim_extraction_lexical_config(
        PipelineContractSnapshot(
            chunk_embedding_index_name="ignored_index",
            chunk_embedding_label="ExplicitChunk",
            chunk_embedding_property="explicit_embedding",
            chunk_embedding_dimensions=1536,
            embedder_model_name="text-embedding-3-small",
            chunk_fallback_stride=1000,
        )
    )

    assert lexical_config.chunk_node_label == "ExplicitChunk"
    assert lexical_config.chunk_embedding_property == "explicit_embedding"


def test_package_contracts_root_does_not_reexport_stateful_pipeline_symbols() -> None:
    import power_atlas.contracts as contracts_module

    disallowed_exports = {
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
        "get_dataset_id",
        "refresh_pipeline_contract",
        "set_dataset_id",
    }

    assert disallowed_exports.isdisjoint(contracts_module.__all__)
    for name in disallowed_exports:
        assert not hasattr(contracts_module, name)


def test_demo_run_demo_module_does_not_reexport_mutable_pipeline_symbols() -> None:
    import demo.run_demo as run_demo_module

    disallowed_exports = {
        "CHUNK_EMBEDDING_DIMENSIONS",
        "CHUNK_EMBEDDING_INDEX_NAME",
        "CHUNK_EMBEDDING_LABEL",
        "CHUNK_EMBEDDING_PROPERTY",
        "CHUNK_FALLBACK_STRIDE",
        "EMBEDDER_MODEL_NAME",
    }

    for name in disallowed_exports:
        assert not hasattr(run_demo_module, name)


def test_build_embedder_for_settings_uses_embedder_model() -> None:
    from power_atlas.bootstrap.clients import build_embedder_for_settings
    from power_atlas.settings import AppSettings, Neo4jSettings

    settings = AppSettings(
        neo4j=Neo4jSettings(),
        openai_model="gpt-5.4",
        embedder_model="text-embedding-3-large",
        output_dir=Path("artifacts"),
        dataset_name=None,
    )

    with mock.patch("power_atlas.bootstrap.clients.OpenAIEmbeddings") as embedder_cls:
        build_embedder_for_settings(settings)

    embedder_cls.assert_called_once_with(model="text-embedding-3-large")


def test_build_llm_uses_explicit_model_name() -> None:
    from power_atlas.bootstrap.clients import build_llm

    with mock.patch("power_atlas.bootstrap.clients.build_openai_llm") as build_openai_llm:
        build_llm("gpt-5.4", reasoning_effort="none")

    build_openai_llm.assert_called_once_with("gpt-5.4", reasoning_effort="none")


def test_build_embedder_uses_explicit_model_name() -> None:
    from power_atlas.bootstrap.clients import build_embedder

    with mock.patch("power_atlas.bootstrap.clients.OpenAIEmbeddings") as embedder_cls:
        build_embedder("text-embedding-3-large")

    embedder_cls.assert_called_once_with(model="text-embedding-3-large")
