from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from power_atlas.context import RequestContext
from power_atlas.contracts import (
    CSV_FIRST_DATA_ROW,
    FIXTURES_DIR,
    ID_PATTERNS,
    DatasetRoot,
    StructuredGraphShapeContract,
    StructuredSchemaContract,
    STRUCTURED_FILE_HEADERS,
    VALUE_TYPES,
    COMMON_PREDICATE_LABELS,
    resolve_dataset_root,
)
from power_atlas.settings import Neo4jSettings
from power_atlas.structured_ingest_entrypoint import (
    neo4j_settings_from_config as _neo4j_settings_from_config,
    run_structured_ingest as _run_structured_ingest,
    run_structured_ingest_request_context as _run_structured_ingest_request_context,
)
from power_atlas.structured_ingest_runner import (
    lint_and_clean_structured_csvs,
    load_csv_rows,
    resolve_structured_dataset as _resolve_structured_dataset,
    run_structured_ingest_runtime as _run_structured_ingest_runtime_impl,
)
from power_atlas.structured_ingest_runtime import run_structured_ingest_live
from power_atlas.structured_ingest_writes import write_structured_ingest_graph


def _run_structured_ingest_impl(
    config: object,
    *,
    run_id: str,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
) -> dict[str, Any]:
    return _run_structured_ingest(
        config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
        runtime_runner=_run_structured_ingest_runtime,
    )


def _run_structured_ingest_runtime(
    *,
    config: object,
    run_id: str,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings,
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
) -> dict[str, Any]:
    return _run_structured_ingest_runtime_impl(
        config=config,
        run_id=run_id,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
        live_runner=run_structured_ingest_live,
        write_graph=write_structured_ingest_graph,
    )


def run_structured_ingest_request_context(
    request_context: RequestContext,
    *,
    fixtures_dir: Path | None = None,
    dataset_id: str | None = None,
    structured_graph_shape: StructuredGraphShapeContract | None = None,
    structured_schema: StructuredSchemaContract | None = None,
) -> dict[str, Any]:
    """Run structured ingest using request-scoped context as the primary input."""
    return _run_structured_ingest_request_context(
        request_context,
        fixtures_dir=fixtures_dir,
        dataset_id=dataset_id,
        structured_graph_shape=structured_graph_shape,
        structured_schema=structured_schema,
        config_runner=_run_structured_ingest_impl,
    )


__all__ = [
    "lint_and_clean_structured_csvs",
    "load_csv_rows",
    "run_structured_ingest_request_context",
]
