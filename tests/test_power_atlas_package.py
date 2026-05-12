from __future__ import annotations

import importlib
from pathlib import Path
from unittest import mock

import pytest


def test_package_modules_import() -> None:
    package = importlib.import_module("power_atlas")
    api_module = importlib.import_module("power_atlas.api")
    context_module = importlib.import_module("power_atlas.context")
    contracts_module = importlib.import_module("power_atlas.contracts")
    pipeline_module = importlib.import_module("power_atlas.contracts.pipeline")
    orchestration_module = importlib.import_module("power_atlas.orchestration")
    settings_module = importlib.import_module("power_atlas.settings")
    bootstrap_module = importlib.import_module("power_atlas.bootstrap")
    claim_extraction_entrypoint_module = importlib.import_module(
        "power_atlas.claim_extraction_entrypoint"
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
    assert package.EntityTypeNormalizationPolicy is contracts_module.EntityTypeNormalizationPolicy
    assert package.CONFIG_DIR == contracts_module.CONFIG_DIR
    assert package.PROMPT_IDS is contracts_module.PROMPT_IDS
    assert package.POWER_ATLAS_RAG_TEMPLATE is contracts_module.POWER_ATLAS_RAG_TEMPLATE
    assert package.POWER_ATLAS_RETRIEVAL_ONTOLOGY is contracts_module.POWER_ATLAS_RETRIEVAL_ONTOLOGY
    assert package.POWER_ATLAS_RETRIEVAL_POLICY is contracts_module.POWER_ATLAS_RETRIEVAL_POLICY
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
    assert package.POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY is contracts_module.POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY
    assert package.RETRIEVAL_METADATA_SURFACE_POLICY is contracts_module.RETRIEVAL_METADATA_SURFACE_POLICY
    assert package.RequestContext is context_module.RequestContext
    assert package.RetrievalMetadataSurface is contracts_module.RetrievalMetadataSurface
    assert package.RetrievalOntology is contracts_module.RetrievalOntology
    assert package.RetrievalPolicy is contracts_module.RetrievalPolicy
    assert package.STRUCTURED_FILE_HEADERS is contracts_module.STRUCTURED_FILE_HEADERS
    assert package.VALUE_TYPES is contracts_module.VALUE_TYPES
    assert package.list_available_datasets is contracts_module.list_available_datasets
    assert package.make_run_id is contracts_module.make_run_id
    assert package.resolve_dataset_root is contracts_module.resolve_dataset_root
    assert package.resolve_early_return_rule is contracts_module.resolve_early_return_rule
    assert package.get_default_retrieval_policy is contracts_module.get_default_retrieval_policy
    assert package.get_default_claim_extraction_policy is contracts_module.get_default_claim_extraction_policy
    assert package.get_default_entity_type_normalization_policy is contracts_module.get_default_entity_type_normalization_policy
    assert package.build_entity_type_cypher_case is contracts_module.build_entity_type_cypher_case
    assert package.normalize_entity_type is contracts_module.normalize_entity_type
    assert package.resolution_layer_schema is contracts_module.resolution_layer_schema
    assert package.timestamp is contracts_module.timestamp
    assert package.write_manifest is contracts_module.write_manifest
    assert package.write_manifest_md is contracts_module.write_manifest_md
    assert package.AppSettings is settings_module.AppSettings
    assert package.build_settings is bootstrap_module.build_settings
    assert package.build_app_context is bootstrap_module.build_app_context
    assert package.build_request_context is bootstrap_module.build_request_context
    assert package.build_default_app_policies is context_module.build_default_app_policies
    assert package.build_openai_llm is llm_utils_module.build_openai_llm
    assert package.normalize_mention_text is text_utils_module.normalize_mention_text
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
    assert api_module.BackendAppOptions.__name__ == "BackendAppOptions"
    assert api_module.BackendRuntime.__name__ == "BackendRuntime"
    assert api_module.RunScopedGraphCountsRequestBody.__name__ == "RunScopedGraphCountsRequestBody"
    assert api_module.RunScopedGraphCountsResponse.__name__ == "RunScopedGraphCountsResponse"
    assert callable(api_module.build_backend_runtime)
    assert callable(api_module.build_backend_router)
    assert callable(api_module.create_backend_app)
    assert callable(api_module.get_backend_runtime)
    assert api_module.backend_router is not None
    assert callable(claim_extraction_entrypoint_module.resolve_claim_extraction_policy)
    assert callable(claim_extraction_entrypoint_module.resolve_pipeline_contract)
    assert callable(claim_extraction_entrypoint_module.neo4j_settings_from_config)
    assert callable(claim_extraction_entrypoint_module.openai_model_from_config)
    assert callable(claim_extraction_entrypoint_module.run_claim_extraction)
    assert callable(claim_extraction_entrypoint_module.run_claim_extraction_request_context)
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
    )


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
    )


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
