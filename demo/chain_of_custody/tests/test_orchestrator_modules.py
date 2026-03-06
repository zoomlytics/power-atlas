from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from demo.chain_of_custody.contracts.manifest import build_batch_manifest, build_stage_manifest
from demo.chain_of_custody.contracts.pipeline import (
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
)
from demo.chain_of_custody.contracts.prompts import PROMPT_IDS
from demo.chain_of_custody.contracts.runtime import DemoConfig, make_run_id
from demo.chain_of_custody.contracts.structured import STRUCTURED_FILE_HEADERS
from demo.chain_of_custody.stages import lint_and_clean_structured_csvs, run_pdf_ingest


def _dry_run_config(tmp_path: Path) -> DemoConfig:
    return DemoConfig(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


def test_make_run_id_uses_scope_prefix():
    run_id = make_run_id("example")
    assert run_id.startswith("example-")


def test_batch_manifest_includes_stage_runs(tmp_path: Path):
    manifest = build_batch_manifest(
        config=_dry_run_config(tmp_path),
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        resolution_run_id="resolution-3",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage={"status": "dry_run"},
    )
    assert manifest["stages"]["structured_ingest"]["run_id"] == "structured-1"
    assert manifest["stages"]["pdf_ingest"]["run_id"] == "unstructured-2"
    assert manifest["stages"]["claim_and_mention_extraction"]["run_id"] == "unstructured-2"
    assert manifest["stages"]["retrieval_and_qa"]["run_id"] == "resolution-3"


def test_stage_manifest_carries_config(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    manifest = build_stage_manifest(
        config=config,
        stage_name="pdf_ingest",
        stage_run_id="stage-123",
        run_scope_key="unstructured_ingest_run_id",
        stage_output={"status": "dry_run"},
    )
    assert manifest["run_scopes"]["unstructured_ingest_run_id"] == "stage-123"
    assert manifest["config"]["dry_run"] is True


def test_structured_lint_writes_clean_files(tmp_path: Path):
    result = lint_and_clean_structured_csvs(run_id="test-run", output_dir=tmp_path)
    clean_dir = Path(result["structured_clean_dir"])
    assert clean_dir.exists()
    assert Path(result["lint_report_path"]).exists()
    assert result["lint_summary"]["status"] == "ok"


def _write_structured_csv(structured_dir: Path, name: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    structured_dir.mkdir(parents=True, exist_ok=True)
    with (structured_dir / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_structured_lint_reports_and_raises_on_invalid_data(tmp_path: Path):
    fixtures_dir = tmp_path / "fixtures"
    structured_dir = fixtures_dir / "structured"

    _write_structured_csv(
        structured_dir,
        "entities.csv",
        headers=STRUCTURED_FILE_HEADERS["entities.csv"] + ["extra"],
        rows=[
            {
                "entity_id": "Q1",
                "name": "Example Entity",
                "entity_type": "person",
                "aliases": "",
                "description": "",
                "wikidata_url": "https://example.invalid/entity/Q1",
                "extra": "ignored",
            }
        ],
    )
    _write_structured_csv(
        structured_dir,
        "facts.csv",
        headers=STRUCTURED_FILE_HEADERS["facts.csv"],
        rows=[
            {
                "fact_id": "F1",
                "subject_id": "Q1",
                "subject_label": "Example Entity",
                "predicate_pid": "P22",
                "predicate_label": "father",
                "value": "Someone",
                "value_type": "string",
                "source": "example",
                "source_url": "https://example.invalid/f1",
                "retrieved_at": "2020-01-01",
            }
        ],
    )
    _write_structured_csv(
        structured_dir,
        "relationships.csv",
        headers=STRUCTURED_FILE_HEADERS["relationships.csv"],
        rows=[],
    )
    _write_structured_csv(
        structured_dir,
        "claims.csv",
        headers=STRUCTURED_FILE_HEADERS["claims.csv"],
        rows=[
            {
                "claim_id": "C1",
                "claim_type": "fact",
                "subject_id": "Q2",
                "subject_label": "Unknown Subject",
                "predicate_pid": "P22",
                "predicate_label": "father",
                "object_id": "",
                "object_label": "",
                "value": "Someone",
                "value_type": "string",
                "claim_text": "Claim text",
                "confidence": "0.5",
                "source": "example",
                "source_url": "https://example.invalid/c1",
                "retrieved_at": "2020-01-01",
                "source_row_id": "F999",
            }
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        lint_and_clean_structured_csvs(run_id="bad-run", output_dir=tmp_path, fixtures_dir=fixtures_dir)

    lint_report_path = tmp_path / "runs" / "bad-run" / "lint_report.json"
    assert lint_report_path.exists()
    report = json.loads(lint_report_path.read_text())
    assert report["summary"]["status"] == "failed"
    assert report["summary"]["issue_count"] == len(report["issues"]) == 3
    assert [issue["code"] for issue in report["issues"]] == [
        "UNKNOWN_FACT_SOURCE_ROW",
        "UNKNOWN_SUBJECT_ID",
        "HEADER_MISMATCH",
    ]
    assert str(lint_report_path) in str(excinfo.value)


def test_pdf_ingest_dry_run_uses_contract(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    summary = run_pdf_ingest(config, run_id="test-unstructured")
    assert summary["vector_index"]["index_name"] == CHUNK_EMBEDDING_INDEX_NAME
    assert summary["vector_index"]["label"] == CHUNK_EMBEDDING_LABEL
    assert summary["vector_index"]["embedding_property"] == CHUNK_EMBEDDING_PROPERTY
    assert summary["vector_index"]["dimensions"] == CHUNK_EMBEDDING_DIMENSIONS
    assert Path(summary["ingest_summary_path"]).exists()


def test_claim_extraction_dry_run_uses_prompt_registry(tmp_path: Path):
    pytest.importorskip("neo4j_graphrag")
    from demo.chain_of_custody.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert summary["prompt_version"] == PROMPT_IDS["claim_extraction"]
    assert summary["status"] == "dry_run"


def test_claim_extraction_dry_run_includes_count_fields(tmp_path: Path):
    pytest.importorskip("neo4j_graphrag")
    from demo.chain_of_custody.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert "chunks_processed" in summary
    assert "extracted_claim_count" in summary
    assert "entity_mention_count" in summary
    assert summary["chunks_processed"] == 0
    assert summary["extracted_claim_count"] == 0
    assert summary["entity_mention_count"] == 0


def test_retrieval_and_qa_dry_run_includes_metadata_fields(tmp_path: Path):
    from demo.chain_of_custody.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-1", source_uri=None, top_k=5)
    assert result["run_id"] == "qa-run-1"
    assert result["top_k"] == 5
    assert "retriever_index_name" in result
    assert result["qa_model"] == "test-model"
    assert result["qa_prompt_version"] == PROMPT_IDS["qa"]
    assert "all_answers_cited" in result
    assert isinstance(result["all_answers_cited"], bool)
    assert "citation_object_example" in result
    assert "citation_example" in result
    required_keys = {"chunk_id", "run_id", "source_uri", "chunk_index", "page", "start_char", "end_char"}
    assert required_keys.issubset(result["citation_object_example"].keys())


def test_retrieval_and_qa_run_id_appears_in_batch_manifest(tmp_path: Path):
    from demo.chain_of_custody.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    retrieval_stage = run_retrieval_and_qa(config, run_id="resolution-3", source_uri=None)
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        resolution_run_id="resolution-3",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )
    qa_stage = manifest["stages"]["retrieval_and_qa"]
    assert qa_stage["run_id"] == "resolution-3"
    assert qa_stage["qa_prompt_version"] == PROMPT_IDS["qa"]
    assert "citation_object_example" in qa_stage
