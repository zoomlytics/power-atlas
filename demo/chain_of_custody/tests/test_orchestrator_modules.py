from __future__ import annotations

from pathlib import Path

from demo.chain_of_custody.contracts import (
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
    DemoConfig,
    make_run_id,
    PROMPT_IDS,
)
from demo.chain_of_custody.contracts.manifest import build_batch_manifest, build_stage_manifest
from demo.chain_of_custody.stages import (
    lint_and_clean_structured_csvs,
    run_claim_and_mention_extraction,
    run_pdf_ingest,
)


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


def test_pdf_ingest_dry_run_uses_contract(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    summary = run_pdf_ingest(config, run_id="test-unstructured")
    assert summary["vector_index"]["index_name"] == CHUNK_EMBEDDING_INDEX_NAME
    assert summary["vector_index"]["label"] == CHUNK_EMBEDDING_LABEL
    assert summary["vector_index"]["embedding_property"] == CHUNK_EMBEDDING_PROPERTY
    assert summary["vector_index"]["dimensions"] == CHUNK_EMBEDDING_DIMENSIONS
    assert Path(summary["ingest_summary_path"]).exists()


def test_claim_extraction_dry_run_uses_prompt_registry(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert summary["prompt_version"] == PROMPT_IDS["claim_extraction"]
    assert summary["status"] == "dry_run"
