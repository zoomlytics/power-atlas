"""Tests for demo/contracts/manifest.py: write_manifest, write_manifest_md,
_manifest_md_summary, and build_*_manifest helpers."""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from demo.contracts.manifest import (
    _manifest_md_summary,
    build_batch_manifest,
    build_stage_manifest,
    write_manifest,
    write_manifest_md,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs):
    defaults = {"dry_run": True, "neo4j_database": "neo4j", "openai_model": "gpt-4o-mini"}
    defaults.update(kwargs)
    cfg = types.SimpleNamespace(**defaults)
    return cfg


def _minimal_manifest() -> dict:
    return {
        "run_id": "batch-20260309T000000Z-abcd1234",
        "created_at": "2026-03-09T00:00:00+00:00",
        "started_at": "2026-03-09T00:00:00+00:00",
        "finished_at": "2026-03-09T00:01:00+00:00",
        "run_scopes": {
            "batch_mode": "sequential_independent_runs",
            "structured_ingest_run_id": "structured_ingest-abc",
            "unstructured_ingest_run_id": "unstructured_ingest-abc",
            "resolution_run_id": "resolution-abc",
        },
        "config": {"dry_run": True, "neo4j_database": "neo4j", "openai_model": "gpt-4o-mini"},
        "qa_signals": {"all_answers_cited": False, "evidence_level": "no_answer", "warning_count": 0, "warnings": []},
        "stages": {
            "structured_ingest": {"run_id": "structured_ingest-abc", "status": "dry_run", "claims": 5},
            "pdf_ingest": {"run_id": "unstructured_ingest-abc", "counts": {"documents": 1, "chunks": 10}},
        },
    }


# ---------------------------------------------------------------------------
# write_manifest – atomic write and content correctness
# ---------------------------------------------------------------------------

def test_write_manifest_creates_file_with_valid_json(tmp_path):
    manifest = {"run_id": "test-run", "config": {"dry_run": True}}
    out = tmp_path / "manifest.json"
    result = write_manifest(out, manifest)
    assert result == out
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == manifest


def test_write_manifest_creates_parent_dirs(tmp_path):
    manifest = {"run_id": "test-run"}
    nested = tmp_path / "a" / "b" / "c" / "manifest.json"
    write_manifest(nested, manifest)
    assert nested.exists()
    assert json.loads(nested.read_text(encoding="utf-8")) == manifest


def test_write_manifest_overwrites_existing_file(tmp_path):
    out = tmp_path / "manifest.json"
    out.write_text('{"old": true}', encoding="utf-8")
    new_manifest = {"run_id": "new-run"}
    write_manifest(out, new_manifest)
    assert json.loads(out.read_text(encoding="utf-8")) == new_manifest


def test_write_manifest_is_atomic_no_partial_file_on_error(tmp_path, monkeypatch):
    """If writing the temp file fails, the target path must remain untouched."""
    original_content = '{"original": true}'
    out = tmp_path / "manifest.json"
    out.write_text(original_content, encoding="utf-8")

    def _fail_write(*_args, **_kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(Path, "write_text", _fail_write)
    with pytest.raises(OSError, match="simulated write failure"):
        write_manifest(out, {"new": "data"})

    # Original file must be intact
    assert out.read_text(encoding="utf-8") == original_content
    # No temp files left behind
    tmps = list(tmp_path.glob("*.tmp"))
    assert tmps == []


def test_write_manifest_leaves_no_temp_files_on_success(tmp_path):
    write_manifest(tmp_path / "manifest.json", {"x": 1})
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# write_manifest_md – companion Markdown file
# ---------------------------------------------------------------------------

def test_write_manifest_md_creates_md_file(tmp_path):
    manifest = _minimal_manifest()
    json_path = tmp_path / "manifest.json"
    md_path = write_manifest_md(json_path, manifest)
    assert md_path == json_path.with_suffix(".md")
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "# Run Manifest Summary" in text


def test_write_manifest_md_creates_parent_dirs(tmp_path):
    manifest = {"run_id": "test-run"}
    json_path = tmp_path / "sub" / "dir" / "manifest.json"
    md_path = write_manifest_md(json_path, manifest)
    assert md_path.exists()


def test_write_manifest_md_leaves_no_temp_files_on_success(tmp_path):
    manifest = {"run_id": "test-run"}
    write_manifest_md(tmp_path / "manifest.json", manifest)
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_manifest_md_is_atomic_no_partial_file_on_error(tmp_path, monkeypatch):
    """If writing the temp file fails, the md path must not exist (was not there before)."""
    real_write_text = Path.write_text

    def _selective_fail(self, *args, **kwargs):
        if str(self).endswith(".tmp"):
            raise OSError("simulated write failure")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _selective_fail)
    md_path = tmp_path / "manifest.md"
    assert not md_path.exists()
    with pytest.raises(OSError, match="simulated write failure"):
        write_manifest_md(tmp_path / "manifest.json", {"x": 1})
    assert not md_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# _manifest_md_summary – content validation
# ---------------------------------------------------------------------------

def test_manifest_md_summary_includes_run_id():
    manifest = {"run_id": "my-run-abc"}
    text = _manifest_md_summary(manifest)
    assert "`my-run-abc`" in text


def test_manifest_md_summary_includes_started_and_finished_at():
    manifest = {
        "run_id": "run-1",
        "started_at": "2026-03-09T00:00:00+00:00",
        "finished_at": "2026-03-09T00:05:00+00:00",
    }
    text = _manifest_md_summary(manifest)
    assert "2026-03-09T00:00:00+00:00" in text
    assert "2026-03-09T00:05:00+00:00" in text


def test_manifest_md_summary_omits_finished_at_when_absent():
    manifest = {"run_id": "run-1", "started_at": "2026-03-09T00:00:00+00:00"}
    text = _manifest_md_summary(manifest)
    assert "Finished" not in text


def test_manifest_md_summary_includes_config_section():
    manifest = {
        "run_id": "run-1",
        "config": {"dry_run": False, "neo4j_database": "testdb", "openai_model": "gpt-4o"},
    }
    text = _manifest_md_summary(manifest)
    assert "## Configuration" in text
    assert "live" in text
    assert "testdb" in text
    assert "gpt-4o" in text


def test_manifest_md_summary_shows_dry_run_mode():
    manifest = {"run_id": "run-1", "config": {"dry_run": True}}
    text = _manifest_md_summary(manifest)
    assert "dry-run" in text


def test_manifest_md_summary_includes_run_scopes():
    manifest = {
        "run_id": "run-1",
        "run_scopes": {
            "batch_mode": "sequential_independent_runs",
            "structured_ingest_run_id": "s-id",
        },
    }
    text = _manifest_md_summary(manifest)
    assert "## Run Scopes" in text
    assert "sequential_independent_runs" in text
    assert "s-id" in text


def test_manifest_md_summary_includes_stage_counts_dict():
    manifest = {
        "run_id": "run-1",
        "stages": {
            "pdf_ingest": {"run_id": "u-id", "counts": {"documents": 2, "chunks": 20}},
        },
    }
    text = _manifest_md_summary(manifest)
    assert "pdf_ingest" in text
    assert "documents=2" in text
    assert "chunks=20" in text


def test_manifest_md_summary_includes_stage_counts_top_level():
    manifest = {
        "run_id": "run-1",
        "stages": {
            "structured_ingest": {"run_id": "s-id", "claims": 7, "entities": 3},
        },
    }
    text = _manifest_md_summary(manifest)
    assert "structured_ingest" in text
    assert "claims" in text
    assert "7" in text


def test_manifest_md_summary_includes_qa_signals():
    manifest = {
        "run_id": "run-1",
        "qa_signals": {
            "all_answers_cited": True,
            "evidence_level": "full",
            "warning_count": 0,
        },
    }
    text = _manifest_md_summary(manifest)
    assert "## QA Signals" in text
    assert "full" in text
    assert "True" in text


def test_manifest_md_summary_minimal_manifest():
    """Smoke test: does not raise on a bare manifest with only run_id."""
    text = _manifest_md_summary({"run_id": "x"})
    assert "x" in text
    assert isinstance(text, str)


# ---------------------------------------------------------------------------
# build_batch_manifest – started_at / finished_at fields
# ---------------------------------------------------------------------------

def test_build_batch_manifest_includes_timing_fields():
    config = _make_config()
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s-id",
        unstructured_run_id="u-id",
        resolution_run_id="r-id",
        structured_stage={},
        pdf_stage={},
        claim_stage={},
        retrieval_stage={},
        started_at="2026-03-09T00:00:00+00:00",
        finished_at="2026-03-09T00:10:00+00:00",
    )
    assert manifest["started_at"] == "2026-03-09T00:00:00+00:00"
    assert manifest["finished_at"] == "2026-03-09T00:10:00+00:00"


def test_build_batch_manifest_omits_finished_at_when_not_provided():
    config = _make_config()
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s-id",
        unstructured_run_id="u-id",
        resolution_run_id="r-id",
        structured_stage={},
        pdf_stage={},
        claim_stage={},
        retrieval_stage={},
    )
    assert "finished_at" not in manifest


def test_build_batch_manifest_started_at_defaults_to_created_at_when_not_provided():
    config = _make_config()
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s-id",
        unstructured_run_id="u-id",
        resolution_run_id="r-id",
        structured_stage={},
        pdf_stage={},
        claim_stage={},
        retrieval_stage={},
    )
    assert "started_at" in manifest
    assert manifest["started_at"] == manifest["created_at"]


# ---------------------------------------------------------------------------
# build_stage_manifest – started_at / finished_at fields
# ---------------------------------------------------------------------------

def test_build_stage_manifest_includes_timing_fields():
    config = _make_config()
    manifest = build_stage_manifest(
        config=config,
        stage_name="pdf_ingest",
        stage_run_id="u-id",
        run_scope_key="unstructured_ingest_run_id",
        stage_output={"status": "dry_run"},
        started_at="2026-03-09T00:00:00+00:00",
        finished_at="2026-03-09T00:02:00+00:00",
    )
    assert manifest["started_at"] == "2026-03-09T00:00:00+00:00"
    assert manifest["finished_at"] == "2026-03-09T00:02:00+00:00"


def test_build_stage_manifest_omits_finished_at_when_not_provided():
    config = _make_config()
    manifest = build_stage_manifest(
        config=config,
        stage_name="pdf_ingest",
        stage_run_id="u-id",
        run_scope_key="unstructured_ingest_run_id",
        stage_output={"status": "dry_run"},
    )
    assert "finished_at" not in manifest


def test_build_stage_manifest_core_fields_present():
    config = _make_config()
    manifest = build_stage_manifest(
        config=config,
        stage_name="structured_ingest",
        stage_run_id="s-id",
        run_scope_key="structured_ingest_run_id",
        stage_output={"claims": 10, "status": "dry_run"},
    )
    assert manifest["run_id"] == "s-id"
    assert "created_at" in manifest
    assert "started_at" in manifest
    assert manifest["run_scopes"]["batch_mode"] == "single_independent_run"
    assert manifest["run_scopes"]["structured_ingest_run_id"] == "s-id"
    assert manifest["stages"]["structured_ingest"]["claims"] == 10
    assert manifest["config"]["dry_run"] is True
