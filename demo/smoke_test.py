from __future__ import annotations

import argparse
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path

from power_atlas.bootstrap import build_runtime_config, build_settings
from power_atlas.contracts.runtime import Config
from run_demo import run_demo, run_independent_demo

# Valid evidence levels per citation contract (#159).
_VALID_EVIDENCE_LEVELS = frozenset({"full", "degraded", "no_answer"})

# Required citation fields per citation contract (#159).
# page, start_char, and end_char are intentionally absent: they are optional.
_REQUIRED_CITATION_FIELDS = frozenset({"chunk_id", "run_id", "source_uri", "chunk_index"})

# Core fields required in every manifest (batch and independent stage).
_REQUIRED_CORE_MANIFEST_FIELDS = frozenset(
    {"run_id", "created_at", "started_at", "run_scopes", "config", "stages"}
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run demo smoke test")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional manifest output directory; defaults to an isolated temporary directory.",
    )
    return parser.parse_args()


def _validate_core_manifest_fields(manifest: dict, manifest_path: Path) -> None:
    """Assert that the core fields required by every manifest are present."""
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


def _validate_citation_token(token: str) -> dict:
    """Parse and validate a citation token string.  Returns parsed key-value pairs.

    chunk_id, run_id, source_uri, and chunk_index are required.
    page, start_char, and end_char are optional per citation contract (#159);
    when present they must be non-negative integers with end_char >= start_char.
    """
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
    try:
        ci_int = int(raw_ci)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise SystemExit(f"Citation field 'chunk_index' must be an integer (got {raw_ci!r})")
    if ci_int < 0:
        raise SystemExit(f"Citation field 'chunk_index' must be >= 0 (got {ci_int})")
    # Validate optional numeric fields only when present and non-empty.
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
                raise SystemExit(
                    f"Citation field {key!r} must be >= 0 (got {int_value})"
                )
    start_raw = parsed.get("start_char")
    end_raw = parsed.get("end_char")
    if start_raw is not None and start_raw != "" and end_raw is not None and end_raw != "":
        if int(end_raw) < int(start_raw):
            raise SystemExit(
                f"Citation field 'end_char' must be >= 'start_char' "
                f"(got start_char={start_raw}, end_char={end_raw})"
            )
    return parsed


def _validate_independent_manifest(
    manifest_path: Path, expected_stage: str, expected_run_scope_key: str
) -> None:
    """Validate an independent stage run manifest.

    Confirms:
    - Core manifest fields are present.
    - batch_mode is 'single_independent_run'.
    - The expected run scope key is present and consistent with the stage's run_id.
    - The expected stage is present in the manifest.
    - The stage's run_id matches the run scope key.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_core_manifest_fields(manifest, manifest_path)
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


def _validate_batch_manifest(manifest_path: Path) -> None:
    """Validate a batch orchestrated manifest.

    Confirms:
    - Core manifest fields are present.
    - batch_mode is 'sequential_independent_runs'.
    - Structured and unstructured run_ids are distinct (independent run boundaries).
    - Required stages are present.
    - Citation token and citation example are well-formed per citation contract (#159).
    - qa_signals are present and valid.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_core_manifest_fields(manifest, manifest_path)
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
    _validate_citation_token(token)
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


def _build_config(output_dir: Path) -> Config:
    settings = build_settings()
    return build_runtime_config(settings, dry_run=True, output_dir=output_dir)


def _run_structured_scenario(output_dir: Path) -> Path:
    """Run and validate the structured-only independent path.

    Runs 'ingest-structured' in dry-run mode and validates the resulting
    stage-scoped manifest at runs/<run_id>/structured_ingest/manifest.json.
    """
    config = _build_config(output_dir)
    manifest_path = run_independent_demo(config, "ingest-structured")
    _validate_independent_manifest(
        manifest_path,
        expected_stage="structured_ingest",
        expected_run_scope_key="structured_ingest_run_id",
    )
    return manifest_path


def _run_unstructured_scenario(output_dir: Path) -> Path:
    """Run and validate the unstructured-only independent path.

    Runs 'ingest-pdf' in dry-run mode and validates the resulting
    stage-scoped manifest at runs/<run_id>/pdf_ingest/manifest.json.
    """
    config = _build_config(output_dir)
    manifest_path = run_independent_demo(config, "ingest-pdf")
    _validate_independent_manifest(
        manifest_path,
        expected_stage="pdf_ingest",
        expected_run_scope_key="unstructured_ingest_run_id",
    )
    return manifest_path


def _run_batch_scenario(output_dir: Path) -> Path:
    """Run and validate the orchestrated batch path (sequential independent runs).

    Runs the full demo orchestration in dry-run mode and validates:
    - All required stages are present.
    - Structured and unstructured run_ids are distinct (no implicit coupling).
    - Citation tokens are well-formed per citation contract (#159).
    - QA signals are present and valid.
    """
    config = _build_config(output_dir)
    manifest_path = run_demo(config)
    _validate_batch_manifest(manifest_path)
    return manifest_path


# Backward-compatible aliases for scripts and tests that call these directly.
def _run_and_validate(output_dir: Path) -> Path:
    return _run_batch_scenario(output_dir)


_validate_manifest = _validate_batch_manifest


def main() -> None:
    args = _parse_args()
    with ExitStack() as stack:
        output_dir = args.output_dir or Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="smoke_"))
        )
        structured_path = _run_structured_scenario(output_dir)
        print(f"[PASS] structured-only: {structured_path}")
        unstructured_path = _run_unstructured_scenario(output_dir)
        print(f"[PASS] unstructured-only: {unstructured_path}")
        batch_path = _run_batch_scenario(output_dir)
        print(f"[PASS] batch: {batch_path}")
        print("Smoke test passed.")


if __name__ == "__main__":
    main()
