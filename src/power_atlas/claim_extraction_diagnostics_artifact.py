from __future__ import annotations

import json
from dataclasses import dataclass

from power_atlas.backend_run_catalog import (
    extract_run_stage_prefix,
    resolve_backend_current_run_catalog,
    resolve_run_root,
    resolve_runs_root,
)
from power_atlas.contracts import RepoPaths
from power_atlas.settings import AppSettings


@dataclass(frozen=True, slots=True)
class ClaimExtractionDiagnosticsParticipationSummary:
    total_edges: int
    edges_by_role: dict[str, int]
    total_claims: int
    claims_with_zero_edges: int
    claim_coverage_pct: float | None


@dataclass(frozen=True, slots=True)
class ClaimExtractionDiagnosticsMatchSummary:
    total_edges_with_match_method: int
    edges_by_match_method: dict[str, int]


@dataclass(frozen=True, slots=True)
class ClaimExtractionDiagnosticsArtifactResult:
    status: str
    detail: str
    run_id: str
    generated_at: str | None
    source_uri: str | None
    artifact_path: str
    participation_summary: ClaimExtractionDiagnosticsParticipationSummary | None = None
    match_summary: ClaimExtractionDiagnosticsMatchSummary | None = None
    warnings: list[str] | None = None


@dataclass(frozen=True, slots=True)
class CurrentClaimExtractionDiagnosticsArtifactResult(
    ClaimExtractionDiagnosticsArtifactResult
):
    inferred_dataset_id: str | None = None


def _require_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} must be an object")
    return value


def _require_int(value: object, *, context: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} must be an integer")
    return value


def _optional_float(value: object, *, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} must be a number or null")


def _optional_str(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} must be a string or null")


def _string_int_map(value: object, *, context: str) -> dict[str, int]:
    payload = _require_dict(value, context=context)
    result: dict[str, int] = {}
    for key, item in payload.items():
        if not isinstance(key, str):
            raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} keys must be strings")
        result[key] = _require_int(item, context=f"{context}[{key!r}]")
    return result


def _string_list(value: object, *, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Claim extraction diagnostics artifact is invalid: {context} must be a list of strings")
    return list(value)


def resolve_claim_extraction_diagnostics_artifact(
    settings: AppSettings,
    run_id: str,
) -> ClaimExtractionDiagnosticsArtifactResult:
    output_dir = settings.output_dir.resolve()
    runs_root = resolve_runs_root(output_dir)
    run_root = resolve_run_root(output_dir, run_id)
    if not run_root.is_dir():
        raise FileNotFoundError(f"Run {run_id!r} was not found under {runs_root}.")

    artifact_path = (
        run_root
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json"
    )
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"Claim extraction diagnostics artifact for run {run_id!r} was not found under {run_root}."
        )

    try:
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Claim extraction diagnostics artifact for run {run_id!r} could not be read: {exc}"
        ) from exc

    artifact = _require_dict(artifact_data, context="root")
    participation_summary_data = artifact.get("participation_summary")
    match_summary_data = artifact.get("match_summary")

    participation_summary = None
    if participation_summary_data is not None:
        participation_payload = _require_dict(
            participation_summary_data,
            context="participation_summary",
        )
        participation_summary = ClaimExtractionDiagnosticsParticipationSummary(
            total_edges=_require_int(
                participation_payload.get("total_edges"),
                context="participation_summary.total_edges",
            ),
            edges_by_role=_string_int_map(
                participation_payload.get("edges_by_role"),
                context="participation_summary.edges_by_role",
            ),
            total_claims=_require_int(
                participation_payload.get("total_claims"),
                context="participation_summary.total_claims",
            ),
            claims_with_zero_edges=_require_int(
                participation_payload.get("claims_with_zero_edges"),
                context="participation_summary.claims_with_zero_edges",
            ),
            claim_coverage_pct=_optional_float(
                participation_payload.get("claim_coverage_pct"),
                context="participation_summary.claim_coverage_pct",
            ),
        )

    match_summary = None
    if match_summary_data is not None:
        match_payload = _require_dict(match_summary_data, context="match_summary")
        match_summary = ClaimExtractionDiagnosticsMatchSummary(
            total_edges_with_match_method=_require_int(
                match_payload.get("total_edges_with_match_method"),
                context="match_summary.total_edges_with_match_method",
            ),
            edges_by_match_method=_string_int_map(
                match_payload.get("edges_by_match_method"),
                context="match_summary.edges_by_match_method",
            ),
        )

    return ClaimExtractionDiagnosticsArtifactResult(
        status=str(artifact.get("status") or "unknown"),
        detail="Claim extraction diagnostics artifact retrieved successfully",
        run_id=run_id,
        generated_at=_optional_str(artifact.get("generated_at"), context="generated_at"),
        source_uri=_optional_str(artifact.get("source_uri"), context="source_uri"),
        artifact_path=str(artifact_path),
        participation_summary=participation_summary,
        match_summary=match_summary,
        warnings=_string_list(artifact.get("warnings", []), context="warnings"),
    )


def resolve_current_claim_extraction_diagnostics_artifact(
    settings: AppSettings,
    stage_prefix: str,
    *,
    dataset_id: str | None = None,
    repo_paths: RepoPaths | None = None,
) -> CurrentClaimExtractionDiagnosticsArtifactResult:
    run_catalog = resolve_backend_current_run_catalog(
        settings,
        dataset_id=dataset_id,
        repo_paths=repo_paths,
    )
    matching_run = next(
        (run for run in run_catalog.runs if extract_run_stage_prefix(run.run_id) == stage_prefix),
        None,
    )
    if matching_run is None:
        raise FileNotFoundError(
            "Current claim extraction diagnostics artifact for stage_prefix "
            f"{stage_prefix!r} was not found under {run_catalog.runs_root}."
        )

    result = resolve_claim_extraction_diagnostics_artifact(settings, matching_run.run_id)
    return CurrentClaimExtractionDiagnosticsArtifactResult(
        status=result.status,
        detail=result.detail,
        run_id=result.run_id,
        generated_at=result.generated_at,
        source_uri=result.source_uri,
        artifact_path=result.artifact_path,
        participation_summary=result.participation_summary,
        match_summary=result.match_summary,
        warnings=result.warnings,
        inferred_dataset_id=run_catalog.inferred_dataset_id,
    )


__all__ = [
    "ClaimExtractionDiagnosticsArtifactResult",
    "ClaimExtractionDiagnosticsMatchSummary",
    "ClaimExtractionDiagnosticsParticipationSummary",
    "CurrentClaimExtractionDiagnosticsArtifactResult",
    "resolve_current_claim_extraction_diagnostics_artifact",
    "resolve_claim_extraction_diagnostics_artifact",
]