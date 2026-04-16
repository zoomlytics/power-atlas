from __future__ import annotations

import importlib
from pathlib import Path
from unittest import mock


def test_package_modules_import() -> None:
    package = importlib.import_module("power_atlas")
    contracts_module = importlib.import_module("power_atlas.contracts")
    settings_module = importlib.import_module("power_atlas.settings")
    bootstrap_module = importlib.import_module("power_atlas.bootstrap")
    llm_utils_module = importlib.import_module("power_atlas.llm_utils")
    text_utils_module = importlib.import_module("power_atlas.text_utils")

    assert package.ALIGNMENT_VERSION is contracts_module.ALIGNMENT_VERSION
    assert package.AmbiguousDatasetError is contracts_module.AmbiguousDatasetError
    assert package.ARTIFACTS_DIR == contracts_module.ARTIFACTS_DIR
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
    assert package.PDF_PIPELINE_CONFIG_PATH == contracts_module.PDF_PIPELINE_CONFIG_PATH
    assert package.RETRIEVAL_METADATA_SURFACE_POLICY is contracts_module.RETRIEVAL_METADATA_SURFACE_POLICY
    assert package.RetrievalMetadataSurface is contracts_module.RetrievalMetadataSurface
    assert package.STRUCTURED_FILE_HEADERS is contracts_module.STRUCTURED_FILE_HEADERS
    assert package.VALUE_TYPES is contracts_module.VALUE_TYPES
    assert package.list_available_datasets is contracts_module.list_available_datasets
    assert package.make_run_id is contracts_module.make_run_id
    assert package.resolve_dataset_root is contracts_module.resolve_dataset_root
    assert package.resolve_early_return_rule is contracts_module.resolve_early_return_rule
    assert package.timestamp is contracts_module.timestamp
    assert package.AppSettings is settings_module.AppSettings
    assert package.build_settings is bootstrap_module.build_settings
    assert package.build_openai_llm is llm_utils_module.build_openai_llm
    assert package.normalize_mention_text is text_utils_module.normalize_mention_text


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
