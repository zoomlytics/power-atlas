from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"
DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")

# Default values for the chunk embedding index contract.
# These are used as fallbacks if the YAML configuration does not provide them.
_DEFAULT_CHUNK_EMBEDDING_INDEX_NAME = "chain_custody_chunk_embedding_index"
_DEFAULT_CHUNK_EMBEDDING_LABEL = "Chunk"
_DEFAULT_CHUNK_EMBEDDING_PROPERTY = "embedding"
_DEFAULT_CHUNK_EMBEDDING_DIMENSIONS = 1536

# Load the vector index contract from the pipeline config (if available) to avoid
# drifting from the configuration defined under `demo_contract` in
# pdf_simple_kg_pipeline.yaml.
_demo_contract: dict[str, Any] = {}
_pipeline_config_data: dict[str, Any] = {}
if PDF_PIPELINE_CONFIG_PATH.is_file():
    try:
        with PDF_PIPELINE_CONFIG_PATH.open("r", encoding="utf-8") as _cfg_handle:
            _cfg_data = yaml.safe_load(_cfg_handle)
        if not isinstance(_cfg_data, dict):
            warnings.warn(
                f"Falling back to default chunk embedding contract; expected mapping at top-level in "
                f"{PDF_PIPELINE_CONFIG_PATH}, got {type(_cfg_data).__name__}",
                RuntimeWarning,
                stacklevel=2,
            )
            _cfg_data = {}
        _pipeline_config_data = _cfg_data if isinstance(_cfg_data, dict) else {}
        _demo_contract = _cfg_data.get("demo_contract")
        if _demo_contract is None:
            _demo_contract = {}
        else:
            if not isinstance(_demo_contract, dict):
                warnings.warn(
                    f"Falling back to default chunk embedding contract; expected mapping for demo_contract in "
                    f"{PDF_PIPELINE_CONFIG_PATH}, got {type(_demo_contract).__name__}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _demo_contract = {}
    except (OSError, yaml.YAMLError) as exc:
        warnings.warn(
            f"Falling back to default chunk embedding contract; unable to load "
            f"{PDF_PIPELINE_CONFIG_PATH}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        # If the config cannot be read or parsed, fall back to the defaults.
        _demo_contract = {}

# The chunk embedding index contract lives under `demo_contract.chunk_embedding`
# in pdf_simple_kg_pipeline.yaml. Use that if present; otherwise, fall back to
# the hard-coded defaults above.
_chunk_embedding_contract = _demo_contract.get("chunk_embedding")
if _chunk_embedding_contract is None:
    _chunk_embedding_contract = {}
elif not isinstance(_chunk_embedding_contract, dict):
    warnings.warn(
        f"Falling back to default chunk embedding contract; expected mapping for demo_contract.chunk_embedding in "
        f"{PDF_PIPELINE_CONFIG_PATH}, got {type(_chunk_embedding_contract).__name__}",
        RuntimeWarning,
        stacklevel=2,
    )
    _chunk_embedding_contract = {}

CHUNK_EMBEDDING_INDEX_NAME = _chunk_embedding_contract.get(
    "index_name", _DEFAULT_CHUNK_EMBEDDING_INDEX_NAME
)
CHUNK_EMBEDDING_LABEL = _chunk_embedding_contract.get(
    "label", _DEFAULT_CHUNK_EMBEDDING_LABEL
)
CHUNK_EMBEDDING_PROPERTY = _chunk_embedding_contract.get(
    "embedding_property", _DEFAULT_CHUNK_EMBEDDING_PROPERTY
)
CHUNK_EMBEDDING_DIMENSIONS = _chunk_embedding_contract.get(
    "dimensions", _DEFAULT_CHUNK_EMBEDDING_DIMENSIONS
)
_DEFAULT_EMBEDDER_MODEL_NAME = "text-embedding-3-small"
EMBEDDER_MODEL_NAME = _DEFAULT_EMBEDDER_MODEL_NAME
_embedder_config = _pipeline_config_data.get("embedder_config", {})
if isinstance(_embedder_config, dict):
    _embedder_params = _embedder_config.get("params_")
    if isinstance(_embedder_params, dict):
        _embedder_model = _embedder_params.get("model")
        if isinstance(_embedder_model, str):
            EMBEDDER_MODEL_NAME = _embedder_model

_STRUCTURED_FILE_HEADERS: dict[str, list[str]] = {
    "entities.csv": ["entity_id", "name", "entity_type", "aliases", "description", "wikidata_url"],
    "facts.csv": [
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
    ],
    "relationships.csv": [
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
    ],
    "claims.csv": [
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
    ],
}
_ID_PATTERNS = {
    "entity_id": re.compile(r"^Q\d+$"),
    "fact_id": re.compile(r"^F\d+$"),
    "rel_id": re.compile(r"^R\d+$"),
    "claim_id": re.compile(r"^C\d+$"),
    "predicate_pid": re.compile(r"^P\d+$"),
}
_VALUE_TYPES = {"date", "url", "entity", "string", "number", "boolean"}
_CSV_FIRST_DATA_ROW = 2
_COMMON_PREDICATE_LABELS = {
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P39": "position held",
    "P108": "employer",
    "P112": "founded by",
    "P169": "chief executive officer",
    "P463": "member of",
    "P569": "date of birth",
    "P570": "date of death",
    "P571": "inception",
    "P856": "official website",
    "P1830": "owner of",
}


@dataclass(frozen=True)
class DemoConfig:
    dry_run: bool
    output_dir: Path
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    openai_model: str


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _make_run_id(scope: str) -> str:
    return f"{scope}-{_timestamp()}-{uuid4().hex[:8]}"


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_parseable_date(value: str) -> bool:
    if not value:
        return False
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return bool(re.fullmatch(r"\d{4}", value))


def _deduplicate_rows(
    rows: list[tuple[int, dict[str, str]]], headers: list[str]
) -> tuple[list[tuple[int, dict[str, str]]], int]:
    seen: set[tuple[str, ...]] = set()
    deduped_rows: list[tuple[int, dict[str, str]]] = []
    duplicates = 0
    for row in rows:
        _, row_data = row
        row_key = tuple((row_data.get(header) or "").strip() for header in headers)
        if row_key in seen:
            duplicates += 1
            continue
        seen.add(row_key)
        deduped_rows.append(row)
    return deduped_rows, duplicates


def _is_blank_csv_row(row: dict[str | None, str | list[str] | None]) -> bool:
    for value in row.values():
        if isinstance(value, list):
            if any(str(item).strip() for item in value):
                return False
            continue
        if value is not None and str(value).strip():
            return False
    return True


def _lint_and_clean_structured_csvs(run_id: str, output_dir: Path) -> dict[str, Any]:
    structured_dir = FIXTURES_DIR / "structured"
    run_root = output_dir / "runs" / run_id
    clean_dir = run_root / "structured_clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    lint_issues: list[dict[str, Any]] = []
    cleaned_rows: dict[str, list[dict[str, str]]] = {}
    cleaned_row_numbers: dict[str, list[int]] = {}
    file_summaries: dict[str, dict[str, Any]] = {}
    read_error_files: set[str] = set()

    def _add_issue(file_name: str, row_number: int, field: str, code: str, message: str) -> None:
        lint_issues.append(
            {
                "file": file_name,
                "row": row_number,
                "field": field,
                "code": code,
                "message": message,
            }
        )

    for file_name, expected_headers in _STRUCTURED_FILE_HEADERS.items():
        source_path = structured_dir / file_name
        rows: list[tuple[int, dict[str, str]]] = []
        dropped_blank_rows = 0
        try:
            with source_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                actual_headers = reader.fieldnames or []
                if actual_headers != expected_headers:
                    _add_issue(
                        file_name,
                        1,
                        "header",
                        "HEADER_MISMATCH",
                        f"Expected {expected_headers}, got {actual_headers}",
                    )
                raw_rows = list(reader)
                for row_number, raw_row in enumerate(raw_rows, start=2):
                    if _is_blank_csv_row(raw_row):
                        dropped_blank_rows += 1
                        continue
                    # csv.DictReader stores overflow columns under key `None` when a
                    # row has more fields than the header declaration.
                    extra_columns = raw_row.get(None)
                    if extra_columns and any(str(item).strip() for item in extra_columns):
                        _add_issue(
                            file_name,
                            row_number,
                            "header",
                            "EXTRA_COLUMNS",
                            f"Unexpected extra columns detected: {extra_columns}",
                        )
                    # Keep only the expected header columns for downstream lint/dedup/write.
                    rows.append((row_number, {header: raw_row.get(header, "") for header in expected_headers}))
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            _add_issue(
                file_name,
                1,
                "file",
                "READ_ERROR",
                f"Could not read structured CSV file '{file_name}': {exc}",
            )
            read_error_files.add(file_name)
            cleaned_rows[file_name] = []
            cleaned_row_numbers[file_name] = []
            file_summaries[file_name] = {
                "input_rows": 0,
                "dropped_blank_rows": 0,
                "output_rows": 0,
                "deduplicated_rows": 0,
                "source_uri": str(source_path),
            }
            continue

        deduped = rows
        duplicates = 0
        if file_name in {"entities.csv", "facts.csv", "relationships.csv"}:
            deduped, duplicates = _deduplicate_rows(rows, expected_headers)

        for row_number, row in deduped:
            id_field = {
                "entities.csv": "entity_id",
                "facts.csv": "fact_id",
                "relationships.csv": "rel_id",
                "claims.csv": "claim_id",
            }[file_name]
            id_pattern = _ID_PATTERNS[id_field]
            id_value = (row.get(id_field) or "").strip()
            if not id_pattern.fullmatch(id_value):
                _add_issue(file_name, row_number, id_field, "INVALID_ID", f"Invalid {id_field}: {id_value!r}")

            predicate_pid = (row.get("predicate_pid") or "").strip()
            if "predicate_pid" in row and not _ID_PATTERNS["predicate_pid"].fullmatch(predicate_pid):
                _add_issue(file_name, row_number, "predicate_pid", "INVALID_PID", f"Invalid PID: {predicate_pid!r}")
            if predicate_pid in _COMMON_PREDICATE_LABELS:
                expected_label = _COMMON_PREDICATE_LABELS[predicate_pid]
                actual_label = (row.get("predicate_label") or "").strip()
                if actual_label and actual_label != expected_label:
                    _add_issue(
                        file_name,
                        row_number,
                        "predicate_label",
                        "PID_LABEL_MISMATCH",
                        f"Expected label {expected_label!r} for {predicate_pid}, got {actual_label!r}",
                    )

            if "value_type" in row:
                value_type = (row.get("value_type") or "").strip()
                if value_type not in _VALUE_TYPES:
                    _add_issue(
                        file_name,
                        row_number,
                        "value_type",
                        "INVALID_VALUE_TYPE",
                        f"Unsupported value_type {value_type!r}",
                    )
                if value_type == "date" and not _is_parseable_date((row.get("value") or "").strip()):
                    _add_issue(file_name, row_number, "value", "INVALID_DATE_VALUE", "Expected parseable date value")

            retrieved_at = (row.get("retrieved_at") or "").strip()
            if "retrieved_at" in row and not _is_parseable_date(retrieved_at):
                _add_issue(
                    file_name,
                    row_number,
                    "retrieved_at",
                    "INVALID_RETRIEVED_AT",
                    f"Expected parseable date, got {retrieved_at!r}",
                )

            if "subject_id" in row:
                subject_id = (row.get("subject_id") or "").strip()
                if subject_id and not _ID_PATTERNS["entity_id"].fullmatch(subject_id):
                    _add_issue(file_name, row_number, "subject_id", "INVALID_SUBJECT_ID", f"Invalid ID: {subject_id!r}")
            if "object_id" in row:
                object_id = (row.get("object_id") or "").strip()
                if object_id and not _ID_PATTERNS["entity_id"].fullmatch(object_id):
                    _add_issue(file_name, row_number, "object_id", "INVALID_OBJECT_ID", f"Invalid ID: {object_id!r}")
            if file_name == "claims.csv":
                claim_type = (row.get("claim_type") or "").strip()
                if claim_type not in {"fact", "relationship"}:
                    _add_issue(file_name, row_number, "claim_type", "INVALID_CLAIM_TYPE", f"Invalid claim_type {claim_type!r}")
                confidence_text = (row.get("confidence") or "").strip()
                try:
                    confidence = float(confidence_text)
                    if confidence < 0 or confidence > 1:
                        raise ValueError("out_of_range")
                except ValueError:
                    _add_issue(
                        file_name,
                        row_number,
                        "confidence",
                        "INVALID_CONFIDENCE",
                        f"Expected confidence in [0,1], got {confidence_text!r}",
                    )

        cleaned_rows[file_name] = [row for _, row in deduped]
        cleaned_row_numbers[file_name] = [row_number for row_number, _ in deduped]
        file_summaries[file_name] = {
            "input_rows": len(rows),
            "dropped_blank_rows": dropped_blank_rows,
            "output_rows": len(deduped),
            "deduplicated_rows": duplicates,
            "source_uri": str(source_path),
        }

    entity_ids = {
        (row.get("entity_id") or "").strip()
        for row in cleaned_rows.get("entities.csv", [])
        if (row.get("entity_id") or "").strip()
    }
    fact_ids = {
        (row.get("fact_id") or "").strip()
        for row in cleaned_rows.get("facts.csv", [])
        if (row.get("fact_id") or "").strip()
    }
    relationship_ids = {
        (row.get("rel_id") or "").strip()
        for row in cleaned_rows.get("relationships.csv", [])
        if (row.get("rel_id") or "").strip()
    }
    claims_rows = cleaned_rows.get("claims.csv", [])
    claims_row_numbers = cleaned_row_numbers.get("claims.csv", [])
    can_validate_entities = "entities.csv" not in read_error_files
    can_validate_facts = "facts.csv" not in read_error_files
    can_validate_relationships = "relationships.csv" not in read_error_files
    for index, claim in enumerate(claims_rows):
        row_number = claims_row_numbers[index] if index < len(claims_row_numbers) else index + 2
        subject_id = (claim.get("subject_id") or "").strip()
        if can_validate_entities and subject_id and subject_id not in entity_ids:
            _add_issue("claims.csv", row_number, "subject_id", "UNKNOWN_SUBJECT_ID", f"Unknown subject_id {subject_id!r}")
        source_row_id = (claim.get("source_row_id") or "").strip()
        claim_type = (claim.get("claim_type") or "").strip()
        if can_validate_facts and claim_type == "fact" and source_row_id not in fact_ids:
            _add_issue(
                "claims.csv",
                row_number,
                "source_row_id",
                "UNKNOWN_FACT_SOURCE_ROW",
                f"Missing fact_id {source_row_id!r}",
            )
        if can_validate_relationships and claim_type == "relationship" and source_row_id not in relationship_ids:
            _add_issue(
                "claims.csv",
                row_number,
                "source_row_id",
                "UNKNOWN_REL_SOURCE_ROW",
                f"Missing rel_id {source_row_id!r}",
            )

    for file_name, expected_headers in _STRUCTURED_FILE_HEADERS.items():
        output_path = clean_dir / file_name
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=expected_headers)
            writer.writeheader()
            writer.writerows(cleaned_rows[file_name])

    lint_issues = sorted(
        lint_issues,
        key=lambda issue: (issue["file"], issue["row"], issue["field"], issue["code"], issue["message"]),
    )
    lint_report = {
        "run_id": run_id,
        "dataset_id": "chain_of_custody_dataset_v1",
        "method": "structured_pre_ingest_lint_and_dedup",
        "source_uri": str(structured_dir),
        "structured_clean_dir": str(clean_dir),
        "files": file_summaries,
        "issues": lint_issues,
        "summary": {
            "issue_count": len(lint_issues),
            "status": "failed" if lint_issues else "ok",
        },
    }
    lint_report_path = run_root / "lint_report.json"
    lint_report_path.write_text(json.dumps(lint_report, indent=2, sort_keys=True), encoding="utf-8")
    if lint_issues:
        raise ValueError(f"Structured CSV lint failed with {len(lint_issues)} issue(s): {lint_report_path}")
    return {
        "run_id": run_id,
        "structured_clean_dir": str(clean_dir),
        "lint_report_path": str(lint_report_path),
        "lint_summary": lint_report["summary"],
        "files": file_summaries,
    }


def _validate_cypher_identifier(value: str, kind: str) -> None:
    """Allow only Cypher-safe identifiers ([A-Za-z_][A-Za-z0-9_]*) for fallback interpolation."""
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {kind} for Cypher fallback: expected a string, got "
            f"{value!r} (type {type(value).__name__})"
        )
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe {kind} for Cypher fallback: {value!r}")


def _normalize_pipeline_result(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # Fall back to a compact, textual representation for non-JSON-serializable values.
        try:
            summary = repr(value)
        except Exception:
            summary = f"<unrepresentable {type(value).__name__} object>"

        max_len = 200
        if len(summary) > max_len:
            summary = summary[: max_len - 3] + "..."

        return {
            "type": type(value).__name__,
            "summary": summary,
        }


def _run_structured_ingest(config: DemoConfig, run_id: str) -> dict[str, Any]:
    lint_output = _lint_and_clean_structured_csvs(run_id=run_id, output_dir=config.output_dir)
    structured_clean_dir = Path(lint_output["structured_clean_dir"])
    entities_rows = _load_csv_rows(structured_clean_dir / "entities.csv")
    facts_rows = _load_csv_rows(structured_clean_dir / "facts.csv")
    relationship_rows = _load_csv_rows(structured_clean_dir / "relationships.csv")
    claims_rows = _load_csv_rows(structured_clean_dir / "claims.csv")
    source_uri = str(FIXTURES_DIR / "structured")
    dataset_id = "chain_of_custody_dataset_v1"
    ingested_at = datetime.now(UTC).isoformat()

    fact_ids = {row["fact_id"] for row in facts_rows}
    relationship_ids = {row["rel_id"] for row in relationship_rows}
    validation_warnings: list[dict[str, Any]] = []
    for row_index, claim in enumerate(claims_rows, start=_CSV_FIRST_DATA_ROW):
        claim_type = (claim.get("claim_type") or "").strip()
        source_row_id = (claim.get("source_row_id") or "").strip()
        if claim_type == "fact" and source_row_id not in fact_ids:
            validation_warnings.append(
                {
                    "file": "claims.csv",
                    "row": row_index,
                    "claim_id": claim.get("claim_id"),
                    "code": "BROKEN_FACT_SOURCE_ROW",
                    "message": f"Fact with fact_id not found for source_row_id {source_row_id!r}",
                }
            )
        if claim_type == "relationship" and source_row_id not in relationship_ids:
            validation_warnings.append(
                {
                    "file": "claims.csv",
                    "row": row_index,
                    "claim_id": claim.get("claim_id"),
                    "code": "BROKEN_REL_SOURCE_ROW",
                    "message": f"Relationship with rel_id not found for source_row_id {source_row_id!r}",
                }
            )

    run_root = config.output_dir / "runs" / run_id
    structured_ingest_dir = run_root / "structured_ingest"
    structured_ingest_dir.mkdir(parents=True, exist_ok=True)
    validation_warnings_path = structured_ingest_dir / "validation_warnings.json"
    validation_warnings_path.write_text(json.dumps(validation_warnings, indent=2), encoding="utf-8")
    ingest_summary = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "source_uri": source_uri,
        "ingested_at": ingested_at,
        "counts": {
            "entities": len(entities_rows),
            "facts": len(facts_rows),
            "relationships": len(relationship_rows),
            "claims": len(claims_rows),
        },
        "warning_count": len(validation_warnings),
        "validation_warnings_path": str(validation_warnings_path),
        "structured_clean_dir": str(structured_clean_dir),
    }
    ingest_summary_path = structured_ingest_dir / "ingest_summary.json"
    ingest_summary_path.write_text(json.dumps(ingest_summary, indent=2), encoding="utf-8")

    if config.dry_run:
        return {
            "status": "dry_run",
            "claims": ingest_summary["counts"]["claims"],
            "entities": ingest_summary["counts"]["entities"],
            "relationships": ingest_summary["counts"]["relationships"],
            "facts": ingest_summary["counts"]["facts"],
            "structured_clean_dir": lint_output["structured_clean_dir"],
            "lint_report_path": lint_output["lint_report_path"],
            "lint_summary": lint_output["lint_summary"],
            "structured_ingest_dir": str(structured_ingest_dir),
            "ingest_summary_path": str(ingest_summary_path),
            "validation_warnings_path": str(validation_warnings_path),
            "validation_warning_count": len(validation_warnings),
        }
    import neo4j

    driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
    with driver:
        with driver.session(database=config.neo4j_database) as session:
            session.run(
                """
                MERGE (dataset:Source {source_key: $source_uri, run_id: $run_id})
                SET dataset.source_type = 'dataset',
                    dataset.dataset_id = $dataset_id,
                    dataset.retrieved_at = $ingested_at,
                    dataset.source_uri = $source_uri
                """,
                source_uri=source_uri,
                run_id=run_id,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (entity:CanonicalEntity {entity_id: trim(row.entity_id), run_id: $run_id})
                SET entity.name = row.name,
                    entity.entity_type = row.entity_type,
                    entity.aliases = row.aliases,
                    entity.description = row.description,
                    entity.wikidata_url = row.wikidata_url,
                    entity.source_uri = $source_uri,
                    entity.dataset_id = $dataset_id,
                    entity.retrieved_at = $ingested_at
                WITH entity
                MATCH (dataset:Source {source_key: $source_uri, run_id: $run_id})
                MERGE (entity)-[asserted_in:ASSERTED_IN]->(dataset)
                SET asserted_in.run_id = $run_id,
                    asserted_in.source_uri = $source_uri,
                    asserted_in.retrieved_at = $ingested_at
                """,
                rows=entities_rows,
                run_id=run_id,
                source_uri=source_uri,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (fact:Fact {fact_id: trim(row.fact_id), run_id: $run_id})
                SET fact.subject_id = trim(row.subject_id),
                    fact.subject_label = row.subject_label,
                    fact.predicate_pid = row.predicate_pid,
                    fact.predicate_label = row.predicate_label,
                    fact.value = row.value,
                    fact.value_type = row.value_type,
                    fact.source = row.source,
                    fact.source_url = row.source_url,
                    fact.retrieved_at = row.retrieved_at,
                    fact.source_uri = $source_uri,
                    fact.dataset_id = $dataset_id
                MERGE (subject:CanonicalEntity {entity_id: trim(row.subject_id), run_id: $run_id})
                ON CREATE SET subject.name = row.subject_label,
                              subject.source_uri = $source_uri,
                              subject.dataset_id = $dataset_id,
                              subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                MERGE (fact)-[about:ABOUT]->(subject)
                SET about.run_id = $run_id,
                    about.source_uri = $source_uri,
                    about.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                WITH fact, row
                MATCH (dataset:Source {source_key: $source_uri, run_id: $run_id})
                MERGE (fact)-[asserted_in:ASSERTED_IN]->(dataset)
                SET asserted_in.run_id = $run_id,
                    asserted_in.source_uri = $source_uri,
                    asserted_in.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                FOREACH (_ IN CASE WHEN coalesce(row.source_url, '') = '' THEN [] ELSE [1] END |
                    MERGE (source:Source {source_key: row.source_url, run_id: $run_id})
                    SET source.source_type = 'row_source',
                        source.source = row.source,
                        source.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                        source.source_uri = $source_uri
                    MERGE (fact)-[cited_from:CITED_FROM]->(source)
                    SET cited_from.run_id = $run_id,
                        cited_from.source_uri = $source_uri,
                        cited_from.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                )
                """,
                rows=facts_rows,
                run_id=run_id,
                source_uri=source_uri,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (relationship:Relationship {rel_id: trim(row.rel_id), run_id: $run_id})
                SET relationship.subject_id = trim(row.subject_id),
                    relationship.subject_label = row.subject_label,
                    relationship.predicate_pid = row.predicate_pid,
                    relationship.predicate_label = row.predicate_label,
                    relationship.object_id = trim(row.object_id),
                    relationship.object_label = row.object_label,
                    relationship.object_entity_type = row.object_entity_type,
                    relationship.source = row.source,
                    relationship.source_url = row.source_url,
                    relationship.retrieved_at = row.retrieved_at,
                    relationship.source_uri = $source_uri,
                    relationship.dataset_id = $dataset_id
                MERGE (subject:CanonicalEntity {entity_id: trim(row.subject_id), run_id: $run_id})
                ON CREATE SET subject.name = row.subject_label,
                              subject.source_uri = $source_uri,
                              subject.dataset_id = $dataset_id,
                              subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                MERGE (object:CanonicalEntity {entity_id: trim(row.object_id), run_id: $run_id})
                ON CREATE SET object.name = row.object_label,
                              object.entity_type = row.object_entity_type,
                              object.source_uri = $source_uri,
                              object.dataset_id = $dataset_id,
                              object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                MERGE (relationship)-[has_subject:SUBJECT]->(subject)
                SET has_subject.run_id = $run_id,
                    has_subject.source_uri = $source_uri,
                    has_subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                MERGE (relationship)-[has_object:OBJECT]->(object)
                SET has_object.run_id = $run_id,
                    has_object.source_uri = $source_uri,
                    has_object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                WITH relationship, row
                MATCH (dataset:Source {source_key: $source_uri, run_id: $run_id})
                MERGE (relationship)-[asserted_in:ASSERTED_IN]->(dataset)
                SET asserted_in.run_id = $run_id,
                    asserted_in.source_uri = $source_uri,
                    asserted_in.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                FOREACH (_ IN CASE WHEN coalesce(row.source_url, '') = '' THEN [] ELSE [1] END |
                    MERGE (source:Source {source_key: row.source_url, run_id: $run_id})
                    SET source.source_type = 'row_source',
                        source.source = row.source,
                        source.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                        source.source_uri = $source_uri
                    MERGE (relationship)-[cited_from:CITED_FROM]->(source)
                    SET cited_from.run_id = $run_id,
                        cited_from.source_uri = $source_uri,
                        cited_from.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                )
                """,
                rows=relationship_rows,
                run_id=run_id,
                source_uri=source_uri,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (claim:Claim {claim_id: trim(row.claim_id), run_id: $run_id})
                SET claim.claim_type = trim(row.claim_type),
                    claim.subject_id = trim(row.subject_id),
                    claim.subject_label = row.subject_label,
                    claim.predicate_pid = row.predicate_pid,
                    claim.predicate_label = row.predicate_label,
                    claim.object_id = trim(row.object_id),
                    claim.object_label = row.object_label,
                    claim.value = row.value,
                    claim.value_type = row.value_type,
                    claim.claim_text = row.claim_text,
                    claim.confidence = CASE
                        WHEN coalesce(row.confidence, '') =~ '^[+-]?(\\d+\\.?\\d*|\\.\\d+)$' THEN toFloat(row.confidence)
                        ELSE NULL
                    END,
                    claim.source = row.source,
                    claim.source_url = row.source_url,
                    claim.retrieved_at = row.retrieved_at,
                    claim.source_row_id = trim(row.source_row_id),
                    claim.source_uri = $source_uri,
                    claim.dataset_id = $dataset_id
                MERGE (subject:CanonicalEntity {entity_id: trim(row.subject_id), run_id: $run_id})
                ON CREATE SET subject.name = row.subject_label,
                              subject.source_uri = $source_uri,
                              subject.dataset_id = $dataset_id,
                              subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                MERGE (claim)-[about:ABOUT]->(subject)
                SET about.run_id = $run_id,
                    about.source_uri = $source_uri,
                    about.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                FOREACH (_ IN CASE WHEN trim(coalesce(row.object_id, '')) = '' THEN [] ELSE [1] END |
                    MERGE (object:CanonicalEntity {entity_id: trim(row.object_id), run_id: $run_id})
                    ON CREATE SET object.name = row.object_label,
                                  object.source_uri = $source_uri,
                                  object.dataset_id = $dataset_id,
                                  object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                    MERGE (claim)-[targets:TARGETS]->(object)
                    SET targets.run_id = $run_id,
                        targets.source_uri = $source_uri,
                        targets.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                )
                WITH claim, row
                MATCH (dataset:Source {source_key: $source_uri, run_id: $run_id})
                MERGE (claim)-[asserted_in:ASSERTED_IN]->(dataset)
                SET asserted_in.run_id = $run_id,
                    asserted_in.source_uri = $source_uri,
                    asserted_in.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                OPTIONAL MATCH (fact:Fact {fact_id: trim(row.source_row_id), run_id: $run_id})
                OPTIONAL MATCH (relationship:Relationship {rel_id: trim(row.source_row_id), run_id: $run_id})
                FOREACH (_ IN CASE WHEN trim(row.claim_type) = 'fact' AND fact IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (claim)-[supported_by:SUPPORTED_BY]->(fact)
                    SET supported_by.run_id = $run_id,
                        supported_by.source_uri = $source_uri,
                        supported_by.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                        supported_by.source_row_id = trim(row.source_row_id)
                )
                FOREACH (_ IN CASE WHEN trim(row.claim_type) = 'relationship' AND relationship IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (claim)-[supported_by:SUPPORTED_BY]->(relationship)
                    SET supported_by.run_id = $run_id,
                        supported_by.source_uri = $source_uri,
                        supported_by.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                        supported_by.source_row_id = trim(row.source_row_id)
                )
                FOREACH (_ IN CASE WHEN coalesce(row.source_url, '') = '' THEN [] ELSE [1] END |
                    MERGE (source:Source {source_key: row.source_url, run_id: $run_id})
                    SET source.source_type = 'row_source',
                        source.source = row.source,
                        source.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                        source.source_uri = $source_uri
                    MERGE (claim)-[cited_from:CITED_FROM]->(source)
                    SET cited_from.run_id = $run_id,
                        cited_from.source_uri = $source_uri,
                        cited_from.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
                )
                """,
                rows=claims_rows,
                run_id=run_id,
                source_uri=source_uri,
                dataset_id=dataset_id,
                ingested_at=ingested_at,
            ).consume()

    return {
        "status": "live",
        "claims": ingest_summary["counts"]["claims"],
        "entities": ingest_summary["counts"]["entities"],
        "relationships": ingest_summary["counts"]["relationships"],
        "facts": ingest_summary["counts"]["facts"],
        "structured_clean_dir": lint_output["structured_clean_dir"],
        "lint_report_path": lint_output["lint_report_path"],
        "lint_summary": lint_output["lint_summary"],
        "structured_ingest_dir": str(structured_ingest_dir),
        "ingest_summary_path": str(ingest_summary_path),
        "validation_warnings_path": str(validation_warnings_path),
        "validation_warning_count": len(validation_warnings),
        "provenance": {
            "run_id": run_id,
            "source_uri": source_uri,
            "dataset_id": dataset_id,
            "retrieved_at": ingested_at,
        },
    }


def _run_pdf_ingest(config: DemoConfig, run_id: str | None = None) -> dict[str, Any]:
    pdf_path = FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"Required PDF fixture not found: {pdf_path}")
    pdf_source_uri = str(pdf_path)
    stage_run_id = run_id or _make_run_id("unstructured_ingest")
    run_root = config.output_dir / "runs" / stage_run_id
    pdf_ingest_dir = run_root / "pdf_ingest"
    pdf_ingest_dir.mkdir(parents=True, exist_ok=True)
    ingest_summary_path = pdf_ingest_dir / "ingest_summary.json"
    pdf_fingerprint_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    summary_counts = {"documents": 0, "pages": 0, "chunks": 0}
    extraction_warnings: list[Any] = []

    if config.dry_run:
        ingest_summary = {
            "run_id": stage_run_id,
            "source_uri": pdf_source_uri,
            "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
            "counts": summary_counts,
            "embedding_model": EMBEDDER_MODEL_NAME,
            "embedding_dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            "vector_index": {
                "index_name": CHUNK_EMBEDDING_INDEX_NAME,
                "label": CHUNK_EMBEDDING_LABEL,
                "embedding_property": CHUNK_EMBEDDING_PROPERTY,
                "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            },
            "warnings": extraction_warnings,
            "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        }
        ingest_summary_path.write_text(json.dumps(ingest_summary, indent=2), encoding="utf-8")
        return {
            "status": "dry_run",
            "documents": [pdf_source_uri],
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + FixedSizeSplitter",
            "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
            "vector_index": {
                "index_name": CHUNK_EMBEDDING_INDEX_NAME,
                "label": CHUNK_EMBEDDING_LABEL,
                "embedding_property": CHUNK_EMBEDDING_PROPERTY,
                "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            },
            "pdf_ingest_dir": str(pdf_ingest_dir),
            "ingest_summary_path": str(ingest_summary_path),
            "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
            "counts": summary_counts,
            "embedding_model": EMBEDDER_MODEL_NAME,
            "extraction_warnings": extraction_warnings,
        }

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY when using --live ingest-pdf")

    import neo4j
    from neo4j_graphrag.experimental.pipeline.config.runner import PipelineRunner
    from neo4j_graphrag.indexes import create_vector_index

    env_updates = {
        "NEO4J_URI": config.neo4j_uri,
        "NEO4J_USERNAME": config.neo4j_username,
        "NEO4J_PASSWORD": config.neo4j_password,
        "NEO4J_DATABASE": config.neo4j_database,
        "OPENAI_MODEL": config.openai_model,
    }
    previous_env = {key: (key in os.environ, os.environ.get(key)) for key in env_updates}
    os.environ.update(env_updates)

    index_creation_strategy = "neo4j_graphrag.indexes.create_vector_index"
    index_fallback_reason: str | None = None
    pipeline_result: object | None = None
    try:
        driver = neo4j.GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver:
            try:
                create_vector_index(
                    driver,
                    CHUNK_EMBEDDING_INDEX_NAME,
                    label=CHUNK_EMBEDDING_LABEL,
                    embedding_property=CHUNK_EMBEDDING_PROPERTY,
                    dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                    similarity_fn="cosine",
                    database_=config.neo4j_database,
                )
            except Exception as exc:
                index_creation_strategy = "cypher_fallback"
                exc_message = str(exc).splitlines()[0].strip()
                index_fallback_reason = (
                    f"{type(exc).__name__}: {exc_message}" if exc_message else type(exc).__name__
                )
                _validate_cypher_identifier(CHUNK_EMBEDDING_INDEX_NAME, "index name")
                _validate_cypher_identifier(CHUNK_EMBEDDING_LABEL, "label")
                _validate_cypher_identifier(CHUNK_EMBEDDING_PROPERTY, "property")
                with driver.session(database=config.neo4j_database) as session:
                    session.run(
                        f"""
                        CREATE VECTOR INDEX `{CHUNK_EMBEDDING_INDEX_NAME}` IF NOT EXISTS
                        FOR (n:{CHUNK_EMBEDDING_LABEL}) ON (n.{CHUNK_EMBEDDING_PROPERTY})
                        OPTIONS {{indexConfig: {{
                            `vector.dimensions`: $dimensions,
                            `vector.similarity_function`: 'cosine'
                        }}}}
                        """,
                        dimensions=CHUNK_EMBEDDING_DIMENSIONS,
                    ).consume()

            pipeline = PipelineRunner.from_config_file(PDF_PIPELINE_CONFIG_PATH)
            pipeline_result = asyncio.run(
                pipeline.run(
                    {
                        "file_path": pdf_source_uri,
                    }
                )
            )
            if isinstance(pipeline_result, dict):
                for warnings_key in ("warnings", "extraction_warnings"):
                    maybe_warnings = pipeline_result.get(warnings_key)
                    if isinstance(maybe_warnings, list):
                        extraction_warnings = maybe_warnings
                        break

            with driver.session(database=config.neo4j_database) as session:
                # Vendor versions can emit Chunk ordering/embedding fields as
                # index/chunk_index and embedding/embedding_vector/vector/embeddings.
                # Normalize them into the demo retrieval contract:
                # Chunk.chunk_order + Chunk.embedding on every ingested Chunk.
                session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND (d.run_id IS NULL OR d.run_id = $run_id)
                    SET d.run_id = coalesce(d.run_id, $run_id),
                        d.source_uri = coalesce(d.source_uri, $source_uri)
                    WITH d
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id IS NULL OR c.run_id = $run_id
                    WITH d, c,
                         toInteger(coalesce(c.chunk_order, c.index, c.chunk_index)) AS normalized_chunk_order
                    SET c.run_id = coalesce(c.run_id, $run_id),
                        c.source_uri = coalesce(c.source_uri, d.source_uri, $source_uri),
                        c.chunk_order = normalized_chunk_order,
                        c.chunk_id = coalesce(
                            c.chunk_id,
                            c.uid,
                            d.source_uri + ':' + toString(normalized_chunk_order)
                        ),
                        c.page_number = coalesce(c.page_number, c.page),
                        c.embedding = coalesce(c.embedding, c.embedding_vector, c.vector, c.embeddings)
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).consume()
                run_counts = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                    RETURN count(DISTINCT d) AS document_count, count(c) AS chunk_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single() or {}
                document_count = int(run_counts.get("document_count") or 0)
                chunk_count = int(run_counts.get("chunk_count") or 0)
                if document_count == 0 or chunk_count == 0:
                    raise ValueError(
                        "Ingest contract violation: expected at least one Document and Chunk for this run"
                    )
                page_count_result = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                    WITH coalesce(c.page_number, c.page) AS page_val
                    WHERE page_val IS NOT NULL
                    RETURN count(DISTINCT page_val) AS page_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single() or {}
                page_count = int(page_count_result.get("page_count") or 0)
                summary_counts = {
                    "documents": document_count,
                    "pages": page_count,
                    "chunks": chunk_count,
                }
                missing_chunk_order_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.chunk_order IS NULL
                    RETURN count(c) AS missing_chunk_order_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single()["missing_chunk_order_count"]
                if missing_chunk_order_count:
                    raise ValueError(
                        "Chunk ordering contract violation: expected stable chunk index on all ingested chunks"
                    )
                missing_embedding_count = session.run(
                    """
                    MATCH (d:Document)
                    WHERE (d.path = $source_uri OR d.source_uri = $source_uri)
                      AND d.run_id = $run_id
                    MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
                    WHERE c.run_id = $run_id
                      AND c.embedding IS NULL
                    RETURN count(c) AS missing_embedding_count
                    """,
                    run_id=stage_run_id,
                    source_uri=pdf_source_uri,
                ).single()["missing_embedding_count"]
                if missing_embedding_count:
                    raise ValueError(
                        "Chunk embedding contract violation: expected :Chunk.embedding for all ingested chunks"
                    )
    finally:
        for key, (had_key, previous_value) in previous_env.items():
            if not had_key:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value

    ingest_summary = {
        "run_id": stage_run_id,
        "source_uri": pdf_source_uri,
        "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
        "counts": summary_counts,
        "embedding_model": EMBEDDER_MODEL_NAME,
        "embedding_dimensions": CHUNK_EMBEDDING_DIMENSIONS,
        "vector_index": {
            "index_name": CHUNK_EMBEDDING_INDEX_NAME,
            "label": CHUNK_EMBEDDING_LABEL,
            "embedding_property": CHUNK_EMBEDDING_PROPERTY,
            "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            "creation_strategy": index_creation_strategy,
        },
        "warnings": extraction_warnings,
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
    }
    ingest_summary_path.write_text(json.dumps(ingest_summary, indent=2), encoding="utf-8")

    return {
        "status": "live",
        "documents": [pdf_source_uri],
        "pipeline_config": str(PDF_PIPELINE_CONFIG_PATH),
        "vector_index": {
            "index_name": CHUNK_EMBEDDING_INDEX_NAME,
            "label": CHUNK_EMBEDDING_LABEL,
            "embedding_property": CHUNK_EMBEDDING_PROPERTY,
            "dimensions": CHUNK_EMBEDDING_DIMENSIONS,
            "creation_strategy": index_creation_strategy,
        },
        "pipeline_result": _normalize_pipeline_result(pipeline_result),
        "provenance": {
            "run_id": stage_run_id,
            "source_uri": pdf_source_uri,
            "chunk_order_property": "chunk_order",
            "chunk_id_property": "chunk_id",
            "page_property": "page_number",
        },
        "pdf_ingest_dir": str(pdf_ingest_dir),
        "ingest_summary_path": str(ingest_summary_path),
        "pdf_fingerprint_sha256": pdf_fingerprint_sha256,
        "counts": summary_counts,
        "embedding_model": EMBEDDER_MODEL_NAME,
        "extraction_warnings": extraction_warnings,
        **({"vector_index_fallback_reason": index_fallback_reason} if index_fallback_reason else {}),
    }


def _run_claim_and_mention_extraction(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "claim_extraction": "planned",
            "mention_resolution": "deterministic by canonical entity_id",
        }
    return {
        "status": "configured",
        "claim_extraction": "LLMEntityRelationExtractor",
        "mention_resolution": "SinglePropertyExactMatchResolver",
    }


def _run_retrieval_and_qa(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
        }
    return {
        "status": "configured",
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
    }


def run_demo(config: DemoConfig) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    structured_run_id = _make_run_id("structured_ingest")
    unstructured_run_id = _make_run_id("unstructured_ingest")
    resolution_run_id = _make_run_id("resolution")

    manifest = {
        "run_id": _make_run_id("chain_of_custody_batch"),
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "sequential_independent_runs",
            "structured_ingest_run_id": structured_run_id,
            "unstructured_ingest_run_id": unstructured_run_id,
            "resolution_run_id": resolution_run_id,
        },
        "config": {
            "dry_run": config.dry_run,
            "neo4j_database": config.neo4j_database,
            "openai_model": config.openai_model,
        },
        "stages": {
            "structured_ingest": {
                **_run_structured_ingest(config, structured_run_id),
                "run_id": structured_run_id,
            },
            "pdf_ingest": {
                **_run_pdf_ingest(config, unstructured_run_id),
                "run_id": unstructured_run_id,
            },
            "claim_and_mention_extraction": {
                **_run_claim_and_mention_extraction(config),
                "run_id": resolution_run_id,
            },
            "retrieval_and_qa": {
                **_run_retrieval_and_qa(config),
                "run_id": resolution_run_id,
            },
        },
    }

    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def run_independent_demo(config: DemoConfig, command: str) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stage_runners: dict[str, tuple[str, str, Callable[[DemoConfig, str], dict[str, Any]]]] = {
        "ingest-structured": (
            "structured_ingest",
            "structured_ingest_run_id",
            lambda cfg, stage_run_id: _run_structured_ingest(cfg, stage_run_id),
        ),
        "ingest-pdf": ("pdf_ingest", "unstructured_ingest_run_id", _run_pdf_ingest),
    }
    if command not in stage_runners:
        raise ValueError(f"Unsupported independent command: {command}")
    stage_name, run_scope_key, stage_runner = stage_runners[command]
    run_scope = run_scope_key.removesuffix("_run_id")
    stage_run_id = _make_run_id(run_scope)
    stage_output = stage_runner(config, stage_run_id)
    manifest = {
        "run_id": stage_run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "run_scopes": {
            "batch_mode": "single_independent_run",
            run_scope_key: stage_run_id,
        },
        "config": {
            "dry_run": config.dry_run,
            "neo4j_database": config.neo4j_database,
            "openai_model": config.openai_model,
        },
        "stages": {
            stage_name: {
                **stage_output,
                "run_id": stage_run_id,
            }
        },
    }
    manifest_path = config.output_dir / f"{stage_name}_{stage_run_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Run without live Neo4j/OpenAI calls",
    )
    mode_group.add_argument(
        "--live",
        action="store_false",
        dest="dry_run",
        help="Enable live Neo4j/OpenAI calls",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "CHANGE_ME_BEFORE_USE"))
    parser.add_argument("--neo4j-database", default=DEFAULT_DB)
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    common_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    _add_common_args(common_parser)
    parser = argparse.ArgumentParser(
        description="Chain of Custody demo orchestrator",
        parents=[common_parser],
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for command in (
        "lint-structured",
        "ingest-structured",
        "ingest-pdf",
        "extract-claims",
        "resolve-entities",
        "ask",
        "reset",
        "ingest",
    ):
        subparsers.add_parser(command, parents=[common_parser], allow_abbrev=False)
        if command == "ask":
            subparsers.choices[command].add_argument("--question", default=None)
    parser.set_defaults(command="ingest")

    # Enforce mutual exclusivity of --dry-run/--live while ignoring cases where
    # those strings are used as *values* to other options that take an argument.
    options_with_values = {
        "--output-dir",
        "--neo4j-uri",
        "--neo4j-username",
        "--neo4j-password",
        "--neo4j-database",
        "--openai-model",
        "--question",
    }
    saw_dry_run_flag = False
    saw_live_flag = False
    i = 0
    while i < len(raw_argv):
        token = raw_argv[i]
        if token in options_with_values:
            # Skip the value associated with this option, even if it looks like a flag.
            i += 2
            continue
        if token == "--dry-run":
            saw_dry_run_flag = True
        elif token == "--live":
            saw_live_flag = True
        i += 1

    if saw_dry_run_flag and saw_live_flag:
        parser.error("argument --dry-run: not allowed with argument --live")
    return parser.parse_args(raw_argv)


def main() -> None:
    args = parse_args()
    if args.command == "lint-structured":
        config = DemoConfig(
            dry_run=True,
            output_dir=args.output_dir,
            neo4j_uri=args.neo4j_uri,
            neo4j_username=args.neo4j_username,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.neo4j_database,
            openai_model=args.openai_model,
        )
        run_id = _make_run_id("structured_lint")
        lint_result = _lint_and_clean_structured_csvs(run_id=run_id, output_dir=config.output_dir)
        print(f"Structured lint report written to: {lint_result['lint_report_path']}")
        return
    if args.command in {"ingest", "ingest-structured", "ingest-pdf"}:
        if not args.dry_run and args.neo4j_password in ("", "CHANGE_ME_BEFORE_USE"):
            raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password when using --live")
        config = DemoConfig(
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            neo4j_uri=args.neo4j_uri,
            neo4j_username=args.neo4j_username,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.neo4j_database,
            openai_model=args.openai_model,
        )
        if args.command == "ingest":
            manifest_path = run_demo(config)
            print(f"Demo manifest written to: {manifest_path}")
        elif args.command in {"ingest-structured", "ingest-pdf"}:
            manifest_path = run_independent_demo(config, args.command)
            print(f"Independent run manifest written to: {manifest_path}")
        return
    if args.command == "reset":
        print("Stub: use demo/chain_of_custody/reset_demo_db.py --confirm to reset demo data.")
        return
    if args.command == "ask":
        question = args.question or "<question>"
        print(f"Stub: '{args.command}' planned for question: {question}")
        return
    print(f"Stub: '{args.command}' command scaffold is ready.")


if __name__ == "__main__":
    main()
