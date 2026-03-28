"""Declarative retrieval metadata surface-ownership contract map.

This module is the single canonical in-code reference for surface ownership and
mirroring rules for retrieval/citation metadata fields surfaced by
``run_retrieval_and_qa()``.

The governing policy was previously distributed across prose documentation
(``docs/architecture/retrieval-citation-result-contract-v0.1.md``), key constants
in the test files, and individual contract tests.  This module centralises the
already-settled rules in one compact, reviewable data structure so that contributors
can find the intended surface ownership for each field at a glance.

For the full decision-rule narrative and rationale, see §2.6 and §2.9 of the
canonical contract document.  This module is the machine-readable complement to
that prose — not a replacement for it.

Surfaces
--------
Each field belongs to one of five metadata surfaces:

- **top_level** — Direct keys in the ``run_retrieval_and_qa()`` result dict.
  The primary public-facing surface for ordinary application logic.
- **citation_quality** — Nested ``citation_quality`` bundle.  Citation-specific
  flags, metrics, and warning strings.
- **telemetry** — Machine-readable counter fields (e.g. ``malformed_diagnostics_count``).
  For monitoring and alerting pipelines; not human-facing warnings.
- **debug_view** — Supported inspection-oriented surface; consolidates postprocessing
  state for diagnostics, tooling, and evaluation.  Always present in all result shapes;
  carries zero/default values on early-return paths (dry_run, retrieval_skipped).
- **warnings** — Top-level ``warnings`` list.  Superset of
  ``citation_quality["citation_warnings"]``; every actionable human-readable string
  a caller may want to display.

Early-return paths
------------------
All fields covered by this policy are present in **all result shapes** — including
the ``status="dry_run"`` and ``retrieval_skipped=True`` early-return paths.  On
those paths the keys exist but carry zero or default values (``False``, ``0``,
empty list, ``"no_answer"``).  This is documented in §2.9 of the contract document.

Policy map
----------
:data:`RETRIEVAL_METADATA_SURFACE_POLICY` is a ``dict`` keyed by the canonical
field name (as it appears on the canonical owning surface) mapping to a
:class:`FieldSurfacePolicy` instance that records:

- The canonical owning surface.
- Any surfaces that mirror the same value (for convenience — no additional hidden
  state is introduced by mirroring).
- Any surfaces where the field is explicitly forbidden (recorded for the ambiguous
  placement cases discussed in §2.6 and §2.9).
- Optional notes for naming distinctions or multi-surface subtleties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "FieldSurfacePolicy",
    "RetrievalMetadataSurface",
    "RETRIEVAL_METADATA_SURFACE_POLICY",
]

# ---------------------------------------------------------------------------
# Surface identifier type
# ---------------------------------------------------------------------------

#: The five metadata surfaces defined in §2.6 of the contract document.
#:
#: - ``"top_level"``       — Direct keys in the ``run_retrieval_and_qa()`` result dict.
#: - ``"citation_quality"``— Nested ``citation_quality`` bundle (flags, metrics, warnings).
#: - ``"telemetry"``       — Machine-readable integer counters for alerting pipelines.
#: - ``"debug_view"``      — Supported inspection surface; mirrors top-level and
#:                           ``citation_quality`` fields for consolidated diagnostics.
#: - ``"warnings"``        — Top-level ``warnings`` list; superset of
#:                           ``citation_quality["citation_warnings"]``.
RetrievalMetadataSurface = Literal[
    "top_level",
    "citation_quality",
    "telemetry",
    "debug_view",
    "warnings",
]

# ---------------------------------------------------------------------------
# Policy entry dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSurfacePolicy:
    """Surface-ownership and mirroring policy for a single retrieval metadata field.

    Attributes
    ----------
    canonical_surface:
        The primary surface where this field should be read for production
        application logic.  Exactly one surface is canonical per field.
    mirrored_in:
        Additional surfaces where the same value is also present for convenience.
        Mirroring carries no additional hidden state — the value is always
        identical to the value on ``canonical_surface``.
    forbidden_in:
        Surfaces where this field must **not** appear.  Recorded for the
        ambiguous-placement cases discussed in §2.6 and §2.9 so that contributors
        do not accidentally place the field on the wrong surface.
    notes:
        Human-readable annotation for naming distinctions, multi-surface
        subtleties, or references to contract document sections.
        Empty string when there is nothing additional to note.
    """

    canonical_surface: RetrievalMetadataSurface
    mirrored_in: tuple[RetrievalMetadataSurface, ...] = ()
    forbidden_in: tuple[RetrievalMetadataSurface, ...] = ()
    notes: str = ""


# ---------------------------------------------------------------------------
# Declarative policy map
# ---------------------------------------------------------------------------

#: Canonical surface-ownership and mirroring policy for settled retrieval/citation
#: metadata fields.
#:
#: Keys are the canonical field names as they appear on the owning surface.
#: Values are :class:`FieldSurfacePolicy` instances encoding the ownership,
#: mirroring, and forbidden-surface rules.
#:
#: This map is the single in-code reference for field placement decisions.
#: For decision-rule narrative and rationale, see §2.6 and §2.9 of
#: ``docs/architecture/retrieval-citation-result-contract-v0.1.md``.
RETRIEVAL_METADATA_SURFACE_POLICY: dict[str, FieldSurfacePolicy] = {
    # ------------------------------------------------------------------
    # all_answers_cited / all_cited — fully-cited flag for the delivered answer
    #
    # §2.9 classification: Inspection-only (debug_view["all_cited"]).
    # The top-level public alias is "all_answers_cited"; the name inside
    # citation_quality and debug_view is "all_cited".  The bare name "all_cited"
    # must NOT appear as a direct top-level key (§2.9).
    # ------------------------------------------------------------------
    "all_answers_cited": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("citation_quality", "debug_view"),
        forbidden_in=(),
        notes=(
            "Top-level key is 'all_answers_cited'; the same value appears as 'all_cited' "
            "inside citation_quality and debug_view (§2.9 Inspection-only).  "
            "The bare name 'all_cited' must NOT be a direct top-level key."
        ),
    ),
    # ------------------------------------------------------------------
    # raw_answer_all_cited — fully-cited flag for the raw (pre-repair) answer
    #
    # §2.9 classification: Mirrored (same name at top-level and debug_view).
    # Also included in the citation_quality bundle for completeness.
    # ------------------------------------------------------------------
    "raw_answer_all_cited": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("citation_quality", "debug_view"),
        forbidden_in=(),
        notes="Same name at top-level, inside citation_quality, and in debug_view (§2.9 Mirrored).",
    ),
    # ------------------------------------------------------------------
    # citation_repair_attempted — whether citation repair was attempted
    #
    # §2.9 classification: Mirrored (same name at top-level and debug_view).
    # This is a postprocessing control field, not a citation-quality metric,
    # so it does not belong in citation_quality.
    # ------------------------------------------------------------------
    "citation_repair_attempted": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric (§2.6 rule 2 "
            "does not apply).  Forbidden in citation_quality.  "
            "Same name at both top-level and debug_view (§2.9 Mirrored)."
        ),
    ),
    # ------------------------------------------------------------------
    # citation_repair_applied — whether repair changed the answer text
    #
    # §2.9 classification: Mirrored (same name at top-level and debug_view).
    # ------------------------------------------------------------------
    "citation_repair_applied": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric.  "
            "Forbidden in citation_quality.  "
            "Same name at both top-level and debug_view (§2.9 Mirrored)."
        ),
    ),
    # ------------------------------------------------------------------
    # citation_fallback_applied — whether the fallback display answer was used
    #
    # §2.9 classification: Mirrored (same name at top-level and debug_view).
    # ------------------------------------------------------------------
    "citation_fallback_applied": FieldSurfacePolicy(
        canonical_surface="top_level",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality",),
        notes=(
            "Postprocessing control field; not a citation-quality metric.  "
            "Forbidden in citation_quality.  "
            "Same name at both top-level and debug_view (§2.9 Mirrored)."
        ),
    ),
    # ------------------------------------------------------------------
    # malformed_diagnostics_count — telemetry counter for structurally malformed
    # retrieval_path_diagnostics payloads (§2.7)
    #
    # §2.9 classification: Mirrored (same name at top-level and debug_view).
    # Canonical surface is "telemetry" (a dedicated top-level integer field for
    # alerting pipelines — not a human-facing warning).
    # Must NOT add string entries to warnings or appear inside citation_quality.
    # ------------------------------------------------------------------
    "malformed_diagnostics_count": FieldSurfacePolicy(
        canonical_surface="telemetry",
        mirrored_in=("debug_view",),
        forbidden_in=("citation_quality", "warnings"),
        notes=(
            "Machine-readable counter for alerting pipelines; not a human-facing "
            "warning (§2.6 rule 3, §2.7, §3.10).  "
            "Must NOT add string entries to the warnings list or appear inside "
            "citation_quality.  "
            "Also appears at top-level as an integer field; mirrored in debug_view "
            "under the same name (§2.9 Mirrored)."
        ),
    ),
    # ------------------------------------------------------------------
    # evidence_level — citation quality level for the delivered answer (§2.8)
    #
    # §2.9 classification: Inspection-only (debug_view["evidence_level"]).
    # Citation-quality metric; not a warning string (§2.6 rule 2).
    # Must NOT be a direct top-level key; access via citation_quality for
    # production logic.
    # ------------------------------------------------------------------
    "evidence_level": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        notes=(
            "Citation-quality flag; not a warning string (§2.6 rule 2, §2.8).  "
            "Must NOT be a direct top-level key.  "
            "Access via citation_quality['evidence_level'] for production logic, "
            "or debug_view['evidence_level'] for inspection (§2.9 Inspection-only)."
        ),
    ),
    # ------------------------------------------------------------------
    # warning_count — count of citation-quality warnings
    #
    # §2.9 classification: Inspection-only (debug_view["warning_count"]).
    # Citation-quality metric; must not be a direct top-level key (§2.6 rule 2).
    # ------------------------------------------------------------------
    "warning_count": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        notes=(
            "Citation-quality metric; not a warning string (§2.6 rule 2).  "
            "Must NOT be a direct top-level key.  "
            "Access via citation_quality['warning_count'] for production logic, "
            "or debug_view['warning_count'] for inspection (§2.9 Inspection-only)."
        ),
    ),
    # ------------------------------------------------------------------
    # citation_warnings — list of citation-quality warning strings
    #
    # §2.9 classification: Inspection-only (debug_view["citation_warnings"]).
    # §2.6 rule 1: every entry in citation_quality["citation_warnings"] is also
    # propagated to the top-level warnings list (superset invariant §3.7).
    # debug_view["citation_warnings"] mirrors the citation_quality list.
    # The top-level warnings list may additionally contain non-citation warnings.
    # "citation_warnings" as a key must NOT appear as a direct top-level key.
    # ------------------------------------------------------------------
    "citation_warnings": FieldSurfacePolicy(
        canonical_surface="citation_quality",
        mirrored_in=("debug_view",),
        forbidden_in=("top_level",),
        notes=(
            "Citation-quality warning strings (§2.6 rule 1): every entry in "
            "citation_quality['citation_warnings'] is also propagated to the "
            "top-level warnings list (superset invariant §3.7).  "
            "debug_view['citation_warnings'] mirrors the citation_quality list.  "
            "The top-level warnings list is the superset and may contain additional "
            "non-citation warnings.  "
            "The key 'citation_warnings' must NOT appear as a direct top-level key "
            "(§2.9 Inspection-only)."
        ),
    ),
}
