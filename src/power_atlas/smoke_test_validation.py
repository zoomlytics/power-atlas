from __future__ import annotations

import json
from pathlib import Path


_VALID_EVIDENCE_LEVELS = frozenset({"full", "degraded", "no_answer"})
_REQUIRED_CITATION_FIELDS = frozenset({"chunk_id", "run_id", "source_uri", "chunk_index"})
_REQUIRED_CORE_MANIFEST_FIELDS = frozenset(
    {"run_id", "created_at", "started_at", "run_scopes", "config", "stages"}
)


def validate_core_manifest_fields(manifest: dict, manifest_path: Path) -> None:
    missing = _REQUIRED_CORE_MANIFEST_FIELDS.difference(manifest)
    if missing:
        raise SystemExit(
            f"Missing required manifest fields in {manifest_path}: {sorted(missing)}"
        )
    cfg = manifest.get("config", {})
    for cfg_field in ("dry_run", "neo4j_database", "openai_model"):
        if cfg_field not in cfg:
            raise SystemExit(
                f"Missing config field {cfg_field!r} in manifest: {manifest_path}"
            )


def validate_citation_token(token: str) -> dict[str, str]:
    if not isinstance(token, str) or not token.startswith("[CITATION|") or not token.endswith("]"):
        raise SystemExit(
            "Citation token must be a string starting with '[CITATION|' and ending with ']' "
            f"(got {token!r})"
        )
    body = token[len("[CITATION|") : -1]
    parts = body.split("|")
    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise SystemExit(f"Malformed citation segment (expected key=value): {part!r}")
        key, value = part.split("=", 1)
        if not key:
            raise SystemExit("Citation segment key must be non-empty")
        parsed[key] = value
    missing_keys = _REQUIRED_CITATION_FIELDS.difference(parsed)
    if missing_keys:
        raise SystemExit(f"Missing required citation fields in token: {sorted(missing_keys)}")
    for key in _REQUIRED_CITATION_FIELDS:
        if not parsed.get(key):
            raise SystemExit(f"Required citation field {key!r} must be non-empty")
    raw_ci = parsed.get("chunk_index")
    if raw_ci is None:
        raise SystemExit("Required citation field 'chunk_index' must be non-empty")
    try:
        ci_int = int(raw_ci)
    except (TypeError, ValueError):
        raise SystemExit(f"Citation field 'chunk_index' must be an integer (got {raw_ci!r})")
    if ci_int < 0:
        raise SystemExit(f"Citation field 'chunk_index' must be >= 0 (got {ci_int})")
    for key in ("page", "start_char", "end_char"):
        raw_value = parsed.get(key)
        if raw_value is not None and raw_value != "":
            try:
                int_value = int(raw_value)
            except (TypeError, ValueError):
                raise SystemExit(
                    f"Citation field {key!r} must be an integer when present "
                    f"(got {raw_value!r})"
                )
            if int_value < 0:
                raise SystemExit(f"Citation field {key!r} must be >= 0 (got {int_value})")
    start_raw = parsed.get("start_char")
    end_raw = parsed.get("end_char")
    if start_raw is not None and start_raw != "" and end_raw is not None and end_raw != "":
        if int(end_raw) < int(start_raw):
            raise SystemExit(
                f"Citation field 'end_char' must be >= 'start_char' "
                f"(got start_char={start_raw}, end_char={end_raw})"
            )
    return parsed


def validate_independent_manifest(
    manifest_path: Path, expected_stage: str, expected_run_scope_key: str
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_core_manifest_fields(manifest, manifest_path)
    run_scopes = manifest.get("run_scopes", {})
    if run_scopes.get("batch_mode") != "single_independent_run":
        raise SystemExit(
            f"Independent stage manifest must have batch_mode='single_independent_run' "
            f"(got {run_scopes.get('batch_mode')!r}) in {manifest_path}"
        )
    if expected_run_scope_key not in run_scopes:
        raise SystemExit(
            f"Independent manifest missing expected run scope key "
            f"{expected_run_scope_key!r}: {manifest_path}"
        )
    stage_run_id = run_scopes[expected_run_scope_key]
    if manifest["run_id"] != stage_run_id:
        raise SystemExit(
            f"Manifest run_id mismatch: run_id={manifest['run_id']!r} but "
            f"{expected_run_scope_key}={stage_run_id!r} in {manifest_path}"
        )
    stages = manifest.get("stages", {})
    if expected_stage not in stages:
        raise SystemExit(
            f"Expected stage {expected_stage!r} not found in independent manifest "
            f"(found: {sorted(stages.keys())}) in {manifest_path}"
        )
    stage_output = stages[expected_stage]
    if stage_output.get("run_id") != stage_run_id:
        raise SystemExit(
            f"Stage {expected_stage!r} run_id={stage_output.get('run_id')!r} does not match "
            f"{expected_run_scope_key}={stage_run_id!r} in {manifest_path}"
        )


def validate_batch_manifest(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_core_manifest_fields(manifest, manifest_path)
    run_scopes = manifest.get("run_scopes", {})
    if run_scopes.get("batch_mode") != "sequential_independent_runs":
        raise SystemExit(
            f"Batch manifest must have batch_mode='sequential_independent_runs' "
            f"(got {run_scopes.get('batch_mode')!r})"
        )
    structured_run_id = run_scopes.get("structured_ingest_run_id")
    unstructured_run_id = run_scopes.get("unstructured_ingest_run_id")
    if not structured_run_id:
        raise SystemExit(
            f"Batch manifest missing structured_ingest_run_id in run_scopes: {manifest_path}"
        )
    if not unstructured_run_id:
        raise SystemExit(
            f"Batch manifest missing unstructured_ingest_run_id in run_scopes: {manifest_path}"
        )
    if structured_run_id == unstructured_run_id:
        raise SystemExit(
            f"Batch manifest must have distinct structured_ingest_run_id and "
            f"unstructured_ingest_run_id (both are {structured_run_id!r}): {manifest_path}"
        )
    required_stages = {
        "structured_ingest",
        "pdf_ingest",
        "claim_and_mention_extraction",
        "retrieval_and_qa",
    }
    missing = required_stages.difference(manifest.get("stages", {}))
    if missing:
        raise SystemExit(f"Missing stages in batch manifest: {sorted(missing)}")
    retrieval_stage = manifest["stages"]["retrieval_and_qa"]
    token = retrieval_stage.get("citation_token_example")
    if not isinstance(token, str):
        raise SystemExit("Missing citation_token_example in retrieval_and_qa stage")
    validate_citation_token(token)
    citation_example = retrieval_stage.get("citation_example")
    if not isinstance(citation_example, dict):
        raise SystemExit("Missing citation_example in retrieval_and_qa stage")
    missing_example = sorted(_REQUIRED_CITATION_FIELDS.difference(citation_example))
    if missing_example:
        raise SystemExit(
            f"citation_example missing required citation fields: {missing_example}"
        )
    citation_quality = retrieval_stage.get("citation_quality")
    if not isinstance(citation_quality, dict):
        raise SystemExit("Missing citation_quality in retrieval_and_qa stage")
    required_cq_keys = {"all_cited", "evidence_level", "warning_count", "citation_warnings"}
    missing_cq_keys = required_cq_keys.difference(citation_quality)
    if missing_cq_keys:
        raise SystemExit(f"citation_quality missing required keys: {sorted(missing_cq_keys)}")
    if citation_quality.get("evidence_level") not in _VALID_EVIDENCE_LEVELS:
        raise SystemExit(
            f"citation_quality.evidence_level must be one of {sorted(_VALID_EVIDENCE_LEVELS)} "
            f"(got {citation_quality.get('evidence_level')!r})"
        )
    qa_signals = manifest.get("qa_signals")
    if not isinstance(qa_signals, dict):
        raise SystemExit("Missing qa_signals in batch manifest")
    required_qa_signal_keys = {"all_answers_cited", "evidence_level", "warning_count", "warnings"}
    missing_qa_signal_keys = required_qa_signal_keys.difference(qa_signals)
    if missing_qa_signal_keys:
        raise SystemExit(f"qa_signals missing required keys: {sorted(missing_qa_signal_keys)}")
    if qa_signals.get("evidence_level") not in _VALID_EVIDENCE_LEVELS:
        raise SystemExit(
            f"qa_signals.evidence_level must be one of {sorted(_VALID_EVIDENCE_LEVELS)} "
            f"(got {qa_signals.get('evidence_level')!r})"
        )


__all__ = [
    "validate_batch_manifest",
    "validate_citation_token",
    "validate_core_manifest_fields",
    "validate_independent_manifest",
]