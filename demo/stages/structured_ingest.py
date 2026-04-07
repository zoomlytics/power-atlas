from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demo.contracts import (
    CSV_FIRST_DATA_ROW,
    DATASET_ID,
    FIXTURES_DIR,
    ID_PATTERNS,
    STRUCTURED_FILE_HEADERS,
    VALUE_TYPES,
)
from demo.contracts.structured import COMMON_PREDICATE_LABELS


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


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


def _deduplicate_rows(rows: list[tuple[int, dict[str, str]]], headers: list[str]) -> tuple[list[tuple[int, dict[str, str]]], int]:
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


def lint_and_clean_structured_csvs(run_id: str, output_dir: Path, fixtures_dir: Path | None = None) -> dict[str, Any]:
    structured_dir = (fixtures_dir or FIXTURES_DIR) / "structured"
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

    for file_name, expected_headers in STRUCTURED_FILE_HEADERS.items():
        source_path = structured_dir / file_name
        rows: list[tuple[int, dict[str, str]]] = []
        dropped_blank_rows = 0
        try:
            with source_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                actual_headers = reader.fieldnames or []
                if actual_headers != expected_headers:
                    _add_issue(file_name, 1, "header", "HEADER_MISMATCH", f"Expected {expected_headers}, got {actual_headers}")
                raw_rows = list(reader)
                for row_number, raw_row in enumerate(raw_rows, start=2):
                    if _is_blank_csv_row(raw_row):
                        dropped_blank_rows += 1
                        continue
                    extra_columns = raw_row.get(None)
                    if extra_columns and any(str(item).strip() for item in extra_columns):
                        _add_issue(
                            file_name,
                            row_number,
                            "header",
                            "EXTRA_COLUMNS",
                            f"Unexpected extra columns detected: {extra_columns}",
                        )
                    rows.append((row_number, {header: (raw_row.get(header) or "") for header in expected_headers}))
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
            id_pattern = ID_PATTERNS[id_field]
            id_value = (row.get(id_field) or "").strip()
            if not id_pattern.fullmatch(id_value):
                _add_issue(file_name, row_number, id_field, "INVALID_ID", f"Invalid {id_field}: {id_value!r}")

            predicate_pid = (row.get("predicate_pid") or "").strip()
            if "predicate_pid" in row and not ID_PATTERNS["predicate_pid"].fullmatch(predicate_pid):
                _add_issue(file_name, row_number, "predicate_pid", "INVALID_PID", f"Invalid PID: {predicate_pid!r}")
            if predicate_pid in COMMON_PREDICATE_LABELS:
                expected_label = COMMON_PREDICATE_LABELS[predicate_pid]
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
                if value_type not in VALUE_TYPES:
                    _add_issue(file_name, row_number, "value_type", "INVALID_VALUE_TYPE", f"Unsupported value_type {value_type!r}")
                if value_type == "date" and not _is_parseable_date((row.get("value") or "").strip()):
                    _add_issue(file_name, row_number, "value", "INVALID_DATE_VALUE", "Expected parseable date value")

            retrieved_at = (row.get("retrieved_at") or "").strip()
            if "retrieved_at" in row and not _is_parseable_date(retrieved_at):
                _add_issue(file_name, row_number, "retrieved_at", "INVALID_RETRIEVED_AT", f"Expected parseable date, got {retrieved_at!r}")

            if "subject_id" in row:
                subject_id = (row.get("subject_id") or "").strip()
                if subject_id and not ID_PATTERNS["entity_id"].fullmatch(subject_id):
                    _add_issue(file_name, row_number, "subject_id", "INVALID_SUBJECT_ID", f"Invalid ID: {subject_id!r}")
            if "object_id" in row:
                object_id = (row.get("object_id") or "").strip()
                if object_id and not ID_PATTERNS["entity_id"].fullmatch(object_id):
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

    entity_ids = {(row.get("entity_id") or "").strip() for row in cleaned_rows.get("entities.csv", []) if (row.get("entity_id") or "").strip()}
    fact_ids = {(row.get("fact_id") or "").strip() for row in cleaned_rows.get("facts.csv", []) if (row.get("fact_id") or "").strip()}
    relationship_ids = {(row.get("rel_id") or "").strip() for row in cleaned_rows.get("relationships.csv", []) if (row.get("rel_id") or "").strip()}
    claims_rows = cleaned_rows.get("claims.csv", [])
    claims_row_numbers = cleaned_row_numbers.get("claims.csv", [])
    can_validate_entities = "entities.csv" not in read_error_files
    can_validate_facts = "facts.csv" not in read_error_files
    can_validate_relationships = "relationships.csv" not in read_error_files
    for index, claim in enumerate(claims_rows):
        row_number = claims_row_numbers[index] if index < len(claims_row_numbers) else index + CSV_FIRST_DATA_ROW
        subject_id = (claim.get("subject_id") or "").strip()
        if can_validate_entities and subject_id and subject_id not in entity_ids:
            _add_issue("claims.csv", row_number, "subject_id", "UNKNOWN_SUBJECT_ID", f"Unknown subject_id {subject_id!r}")
        source_row_id = (claim.get("source_row_id") or "").strip()
        claim_type = (claim.get("claim_type") or "").strip()
        if can_validate_facts and claim_type == "fact" and source_row_id not in fact_ids:
            _add_issue("claims.csv", row_number, "source_row_id", "UNKNOWN_FACT_SOURCE_ROW", f"Missing fact_id {source_row_id!r}")
        if can_validate_relationships and claim_type == "relationship" and source_row_id not in relationship_ids:
            _add_issue(
                "claims.csv",
                row_number,
                "source_row_id",
                "UNKNOWN_REL_SOURCE_ROW",
                f"Missing rel_id {source_row_id!r}",
            )

    for file_name, expected_headers in STRUCTURED_FILE_HEADERS.items():
        output_path = clean_dir / file_name
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=expected_headers)
            writer.writeheader()
            writer.writerows(cleaned_rows.get(file_name, []))

    lint_issues = sorted(
        lint_issues,
        key=lambda issue: (issue["file"], issue["row"], issue["field"], issue["code"], issue["message"]),
    )
    lint_report = {
        "run_id": run_id,
        "dataset_id": DATASET_ID,
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


def run_structured_ingest(config: Any, run_id: str, *, fixtures_dir: Path | None = None, dataset_id: str | None = None) -> dict[str, Any]:
    lint_output = lint_and_clean_structured_csvs(run_id=run_id, output_dir=config.output_dir, fixtures_dir=fixtures_dir)
    structured_clean_dir = Path(lint_output["structured_clean_dir"])
    entities_rows = load_csv_rows(structured_clean_dir / "entities.csv")
    facts_rows = load_csv_rows(structured_clean_dir / "facts.csv")
    relationship_rows = load_csv_rows(structured_clean_dir / "relationships.csv")
    claims_rows = load_csv_rows(structured_clean_dir / "claims.csv")
    effective_fixtures_dir = fixtures_dir or FIXTURES_DIR
    source_uri = str(effective_fixtures_dir / "structured")
    effective_dataset_id = dataset_id if isinstance(dataset_id, str) and dataset_id else DATASET_ID
    ingested_at = _timestamp()

    # Detailed validation of claim source_row_id values is performed during linting
    # by lint_and_clean_structured_csvs(), which raises on any issues. At this stage
    # we only emit a (typically empty) warnings file to preserve the interface for
    # downstream tooling.
    validation_warnings: list[dict[str, Any]] = []

    run_root = config.output_dir / "runs" / run_id
    structured_ingest_dir = run_root / "structured_ingest"
    structured_ingest_dir.mkdir(parents=True, exist_ok=True)
    validation_warnings_path = structured_ingest_dir / "validation_warnings.json"
    validation_warnings_path.write_text(json.dumps(validation_warnings, indent=2), encoding="utf-8")
    ingest_summary = {
        "run_id": run_id,
        "dataset_id": effective_dataset_id,
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
                dataset_id=effective_dataset_id,
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
                dataset_id=effective_dataset_id,
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
                dataset_id=effective_dataset_id,
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
                dataset_id=effective_dataset_id,
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
                WITH claim, row
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
                dataset_id=effective_dataset_id,
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
            "dataset_id": effective_dataset_id,
            "retrieved_at": ingested_at,
        },
    }


__all__ = ["lint_and_clean_structured_csvs", "load_csv_rows", "run_structured_ingest"]
