from __future__ import annotations

import importlib
from pathlib import Path
from unittest import mock

import pytest


def test_package_modules_import() -> None:
    package = importlib.import_module("power_atlas")
    context_module = importlib.import_module("power_atlas.context")
    contracts_module = importlib.import_module("power_atlas.contracts")
    pipeline_module = importlib.import_module("power_atlas.contracts.pipeline")
    settings_module = importlib.import_module("power_atlas.settings")
    bootstrap_module = importlib.import_module("power_atlas.bootstrap")
    llm_utils_module = importlib.import_module("power_atlas.llm_utils")
    text_utils_module = importlib.import_module("power_atlas.text_utils")

    assert package.ALIGNMENT_VERSION is contracts_module.ALIGNMENT_VERSION
    assert package.AmbiguousDatasetError is contracts_module.AmbiguousDatasetError
    assert package.ARTIFACTS_DIR == contracts_module.ARTIFACTS_DIR
    assert package.build_batch_manifest is contracts_module.build_batch_manifest
    assert package.build_stage_manifest is contracts_module.build_stage_manifest
    assert package.claim_extraction_lexical_config is contracts_module.claim_extraction_lexical_config
    assert package.claim_extraction_schema is contracts_module.claim_extraction_schema
    assert package.EarlyReturnRule is contracts_module.EarlyReturnRule
    assert package.EARLY_RETURN_PRECEDENCE is contracts_module.EARLY_RETURN_PRECEDENCE
    assert package.EARLY_RETURN_RULE_BY_NAME is contracts_module.EARLY_RETURN_RULE_BY_NAME
    assert package.CONFIG_DIR == contracts_module.CONFIG_DIR
    assert package.PROMPT_IDS is contracts_module.PROMPT_IDS
    assert package.POWER_ATLAS_RAG_TEMPLATE is contracts_module.POWER_ATLAS_RAG_TEMPLATE
    assert package.Config is contracts_module.Config
    assert package.COMMON_PREDICATE_LABELS is contracts_module.COMMON_PREDICATE_LABELS
    assert package.CSV_FIRST_DATA_ROW is contracts_module.CSV_FIRST_DATA_ROW
    assert package.DATASETS_CONTAINER_DIR == contracts_module.DATASETS_CONTAINER_DIR
    assert package.DatasetRoot is contracts_module.DatasetRoot
    assert package.FieldSurfacePolicy is contracts_module.FieldSurfacePolicy
    assert package.FIXTURES_DIR == contracts_module.FIXTURES_DIR
    assert package.ID_PATTERNS is contracts_module.ID_PATTERNS
    assert package.AppContext is context_module.AppContext
    assert package.PDF_PIPELINE_CONFIG_PATH == contracts_module.PDF_PIPELINE_CONFIG_PATH
    assert package.RETRIEVAL_METADATA_SURFACE_POLICY is contracts_module.RETRIEVAL_METADATA_SURFACE_POLICY
    assert package.RequestContext is context_module.RequestContext
    assert package.RetrievalMetadataSurface is contracts_module.RetrievalMetadataSurface
    assert package.STRUCTURED_FILE_HEADERS is contracts_module.STRUCTURED_FILE_HEADERS
    assert package.VALUE_TYPES is contracts_module.VALUE_TYPES
    assert package.list_available_datasets is contracts_module.list_available_datasets
    assert package.make_run_id is contracts_module.make_run_id
    assert package.resolve_dataset_root is contracts_module.resolve_dataset_root
    assert package.resolve_early_return_rule is contracts_module.resolve_early_return_rule
    assert package.resolution_layer_schema is contracts_module.resolution_layer_schema
    assert package.timestamp is contracts_module.timestamp
    assert package.write_manifest is contracts_module.write_manifest
    assert package.write_manifest_md is contracts_module.write_manifest_md
    assert package.AppSettings is settings_module.AppSettings
    assert package.build_settings is bootstrap_module.build_settings
    assert package.build_app_context is bootstrap_module.build_app_context
    assert package.build_request_context is bootstrap_module.build_request_context
    assert package.build_openai_llm is llm_utils_module.build_openai_llm
    assert package.normalize_mention_text is text_utils_module.normalize_mention_text
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
    assert request_context.app is app.app_context
    assert request_context.settings is app.settings
    assert request_context.command == "ask"
    assert request_context.run_id == "run-123"
    assert request_context.source_uri == "file:///example/doc.pdf"
    assert request_context.config.question == "Who acquired Xapo?"
    assert request_context.config.resolution_mode == "hybrid"
    assert request_context.config.dataset_name == "demo_dataset_v1"


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


def test_create_neo4j_driver_accepts_legacy_config_shape() -> None:
    from power_atlas.bootstrap.clients import create_neo4j_driver
    from power_atlas.contracts.runtime import Config

    config = Config(
        dry_run=False,
        output_dir=Path("artifacts"),
        neo4j_uri="bolt://legacy.test:7687",
        neo4j_username="legacy-user",
        neo4j_password="legacy-secret",
        neo4j_database="legacy-db",
        openai_model="gpt-5.4",
    )

    with mock.patch("power_atlas.bootstrap.clients.neo4j.GraphDatabase.driver") as driver:
        create_neo4j_driver(config)

    driver.assert_called_once_with(
        "bolt://legacy.test:7687",
        auth=("legacy-user", "legacy-secret"),
    )


def test_demo_runtime_contract_shim_matches_package_exports() -> None:
    import demo.contracts.runtime as demo_runtime
    import power_atlas.contracts as contracts_module

    assert demo_runtime.Config is contracts_module.Config
    assert demo_runtime.make_run_id is contracts_module.make_run_id
    assert demo_runtime.timestamp is contracts_module.timestamp


def test_demo_structured_contract_shim_matches_package_exports() -> None:
    import demo.contracts.structured as demo_structured
    import power_atlas.contracts as contracts_module

    assert demo_structured.COMMON_PREDICATE_LABELS is contracts_module.COMMON_PREDICATE_LABELS
    assert demo_structured.CSV_FIRST_DATA_ROW is contracts_module.CSV_FIRST_DATA_ROW
    assert demo_structured.ID_PATTERNS is contracts_module.ID_PATTERNS
    assert demo_structured.STRUCTURED_FILE_HEADERS is contracts_module.STRUCTURED_FILE_HEADERS
    assert demo_structured.VALUE_TYPES is contracts_module.VALUE_TYPES


def test_demo_paths_contract_shim_matches_package_exports() -> None:
    import demo.contracts.paths as demo_paths
    import power_atlas.contracts as contracts_module

    assert demo_paths.AmbiguousDatasetError is contracts_module.AmbiguousDatasetError
    assert demo_paths.ARTIFACTS_DIR == contracts_module.ARTIFACTS_DIR
    assert demo_paths.CONFIG_DIR == contracts_module.CONFIG_DIR
    assert demo_paths.DATASETS_CONTAINER_DIR == contracts_module.DATASETS_CONTAINER_DIR
    assert demo_paths.DatasetRoot is contracts_module.DatasetRoot
    assert demo_paths.FIXTURES_DIR == contracts_module.FIXTURES_DIR
    assert demo_paths.PDF_PIPELINE_CONFIG_PATH == contracts_module.PDF_PIPELINE_CONFIG_PATH
    assert demo_paths.list_available_datasets is contracts_module.list_available_datasets
    assert demo_paths.resolve_dataset_root is contracts_module.resolve_dataset_root


def test_demo_manifest_contract_shim_matches_package_exports() -> None:
    import demo.contracts.manifest as demo_manifest
    import power_atlas.contracts as contracts_module

    assert demo_manifest.build_batch_manifest is contracts_module.build_batch_manifest
    assert demo_manifest.build_stage_manifest is contracts_module.build_stage_manifest
    assert demo_manifest.write_manifest is contracts_module.write_manifest
    assert demo_manifest.write_manifest_md is contracts_module.write_manifest_md


def test_demo_claim_schema_contract_shim_matches_package_exports() -> None:
    import demo.contracts.claim_schema as demo_claim_schema
    import power_atlas.contracts as contracts_module

    assert demo_claim_schema.claim_extraction_lexical_config is contracts_module.claim_extraction_lexical_config
    assert demo_claim_schema.claim_extraction_schema is contracts_module.claim_extraction_schema
    assert demo_claim_schema.resolution_layer_schema is contracts_module.resolution_layer_schema


def test_claim_extraction_lexical_config_reads_live_pipeline_contract_snapshot() -> None:
    import power_atlas.contracts.claim_schema as claim_schema_module
    import power_atlas.contracts.pipeline as pipeline_module

    original_state = pipeline_module._get_pipeline_contract_state_for_test()
    try:
        pipeline_module._set_pipeline_contract_state_for_test(
            chunk_embedding_label="DynamicChunk",
            chunk_embedding_property="dynamic_embedding",
        )

        lexical_config = claim_schema_module.claim_extraction_lexical_config()

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


def test_demo_pipeline_contract_shim_is_package_module() -> None:
    import demo.contracts.pipeline as demo_pipeline
    import power_atlas.contracts.pipeline as package_pipeline

    assert demo_pipeline is package_pipeline


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


def test_demo_contracts_root_does_not_reexport_mutable_pipeline_symbols() -> None:
    import demo.contracts as demo_contracts

    disallowed_exports = {
        "CHUNK_EMBEDDING_DIMENSIONS",
        "CHUNK_EMBEDDING_INDEX_NAME",
        "CHUNK_EMBEDDING_LABEL",
        "CHUNK_EMBEDDING_PROPERTY",
        "CHUNK_FALLBACK_STRIDE",
        "DATASET_ID",
        "EMBEDDER_MODEL_NAME",
        "get_dataset_id",
        "PIPELINE_CONFIG_DATA",
        "set_dataset_id",
    }

    assert disallowed_exports.isdisjoint(demo_contracts.__all__)
    for name in disallowed_exports:
        assert not hasattr(demo_contracts, name)


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
