"""Declarative retrieval metadata surface-ownership contract map.

This module is the single canonical in-code reference for surface ownership and
mirroring rules for retrieval/citation metadata fields surfaced by
``run_retrieval_and_qa()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

__all__ = [
    "FieldSurfacePolicy",
    "RetrievalMetadataSurface",
    "RETRIEVAL_METADATA_SURFACE_POLICY",
]

RetrievalMetadataSurface = Literal[
    "top_level",
    "citation_quality",
    "telemetry",
    "debug_view",
    "warnings",
]


@dataclass(frozen=True)
class FieldSurfacePolicy:
    canonical_surface: RetrievalMetadataSurface
    mirrored_in: tuple[RetrievalMetadataSurface, ...] = ()
    forbidden_in: tuple[RetrievalMetadataSurface, ...] = ()
    propagates_to: tuple[RetrievalMetadataSurface, ...] = ()
    field_name_by_surface: Mapping[RetrievalMetadataSurface, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "field_name_by_surface",
            MappingProxyType(dict(self.field_name_by_surface)),
        )


RETRIEVAL_METADATA_SURFACE_POLICY: Mapping[str, FieldSurfacePolicy] = MappingProxyType({
    "all_answers_cited": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("citation_quality", "debug_view"),
        field_name_by_surface=MappingProxyType({
            "citation_quality": "all_cited",
            "debug_view": "all_cited",
        }),
        notes=(
            "Top-level key is 'all_answers_cited'; the same value appears as 'all_cited' "
            "inside citation_quality and debug_view (§2.9 Inspection-only) — see "
            "field_name_by_surface for the per-surface name mapping. "
            "The bare name 'all_cited' must NOT be a direct top-level key."
        ),
    ),
    "raw_answer_all_cited": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("citation_quality", "debug_view"),
        notes="Same name at top-level, inside citation_quality, and in debug_view (§2.9 Mirrored).",
    ),
    "citation_repair_attempted": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric (§2.6 rule 2 "
            "does not apply). Forbidden in citation_quality. Same name at both top-level "
            "and debug_view (§2.9 Mirrored)."
        ),
    ),
    "citation_repair_applied": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric. Forbidden in "
            "citation_quality. Same name at both top-level and debug_view (§2.9 Mirrored)."
        ),
    ),
    "citation_fallback_applied": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric. Forbidden in "
            "citation_quality. Same name at both top-level and debug_view (§2.9 Mirrored)."
        ),
    ),
    "malformed_diagnostics_count": FieldSurfacePolicy(
        canonical_surface="telemetry",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality", "warnings"),
        notes=(
            "Machine-readable counter for alerting pipelines; not a human-facing "
            "warning (§2.6 rule 3, §2.7, §3.10). Must NOT add string entries to the "
            "warnings list or appear inside citation_quality. Exposed via the telemetry "
            "top-level integer field; mirrored in debug_view under the same name (§2.9 Mirrored)."
        ),
    ),
    "evidence_level": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        notes=(
            "Citation-quality flag; not a warning string (§2.6 rule 2, §2.8). Must NOT "
            "be a direct top-level key. Access via citation_quality['evidence_level'] for "
            "production logic, or debug_view['evidence_level'] for inspection (§2.9 Inspection-only)."
        ),
    ),
    "warning_count": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        notes=(
            "Citation-quality metric; not a warning string (§2.6 rule 2). Must NOT be a "
            "direct top-level key. Access via citation_quality['warning_count'] for "
            "production logic, or debug_view['warning_count'] for inspection (§2.9 Inspection-only)."
        ),
    ),
    "citation_warnings": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        propagates_to=("warnings",),
        notes=(
            "Citation-quality warning strings (§2.6 rule 1): every entry in "
            "citation_quality['citation_warnings'] is also propagated to the top-level "
            "warnings list (superset invariant §3.7) — see propagates_to. "
            "debug_view['citation_warnings'] mirrors the citation_quality list exactly. "
            "The top-level warnings list is the superset and may contain additional "
            "non-citation warnings. The key 'citation_warnings' must NOT appear as a "
            "direct top-level key (§2.9 Inspection-only)."
        ),
    ),
})