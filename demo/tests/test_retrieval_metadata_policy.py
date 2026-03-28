"""Structural tests for the declarative retrieval metadata surface-ownership policy.

These tests validate the shape and internal consistency of
:data:`~demo.contracts.retrieval_metadata_policy.RETRIEVAL_METADATA_SURFACE_POLICY`
without re-running the runtime contract assertions that already live in
:mod:`demo.tests.test_retrieval_result_contract`.

The goals here are:

1. Guarantee the policy map covers the required set of settled fields
   (acceptance criterion: "Policy covers all established metadata surfaces and
   at least the main ambiguous fields").
2. Confirm every :class:`~demo.contracts.retrieval_metadata_policy.FieldSurfacePolicy`
   entry uses valid surface identifiers.
3. Confirm no field lists its canonical surface as a forbidden surface (structural
   contradiction).
4. Confirm the known ambiguous fields (§2.6) are correctly classified.
5. Confirm the module is importable and exports the documented public names via
   the public ``demo.contracts`` package surface (not just the submodule).
"""

from __future__ import annotations

import pytest

from demo.contracts.retrieval_metadata_policy import (
    FieldSurfacePolicy,
    RETRIEVAL_METADATA_SURFACE_POLICY,
)

# ---------------------------------------------------------------------------
# Constants: expected fields and valid surfaces
# ---------------------------------------------------------------------------

#: Every settled field that must appear in the policy map.
#: Covers the main ambiguous fields called out in the issue scope and the
#: full §2.9 debug_view field classification table.
_REQUIRED_POLICY_FIELDS = frozenset({
    "all_answers_cited",
    "raw_answer_all_cited",
    "citation_repair_attempted",
    "citation_repair_applied",
    "citation_fallback_applied",
    "malformed_diagnostics_count",
    "evidence_level",
    "warning_count",
    "citation_warnings",
})

#: The set of surface identifiers that are permitted in a FieldSurfacePolicy.
_VALID_SURFACES = frozenset({
    "top_level",
    "citation_quality",
    "telemetry",
    "debug_view",
    "warnings",
})


# ---------------------------------------------------------------------------
# Coverage tests
# ---------------------------------------------------------------------------


class TestPolicyMapCoverage:
    """The policy map must cover the full set of required settled fields."""

    def test_all_required_fields_present(self) -> None:
        """Every required settled field must appear as a key in the policy map."""
        missing = _REQUIRED_POLICY_FIELDS - frozenset(RETRIEVAL_METADATA_SURFACE_POLICY)
        assert not missing, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY is missing entries for the following "
            f"settled fields: {sorted(missing)!r}. "
            f"Each settled field must have an explicit FieldSurfacePolicy entry."
        )

    def test_no_unexpected_extra_fields(self) -> None:
        """Every key in the policy map must be a known settled field.

        This is a forward-compatibility guard: contributors adding new fields to
        the policy map must also update _REQUIRED_POLICY_FIELDS so that the
        coverage is always explicit.
        """
        extra = frozenset(RETRIEVAL_METADATA_SURFACE_POLICY) - _REQUIRED_POLICY_FIELDS
        assert not extra, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY contains entries for unknown fields: "
            f"{sorted(extra)!r}. "
            f"If these fields are newly settled, add them to _REQUIRED_POLICY_FIELDS "
            f"in this test module."
        )

    def test_all_values_are_field_surface_policy_instances(self) -> None:
        """Every value in the policy map must be a FieldSurfacePolicy instance."""
        for field_name, policy in RETRIEVAL_METADATA_SURFACE_POLICY.items():
            assert isinstance(policy, FieldSurfacePolicy), (
                f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}] is not a "
                f"FieldSurfacePolicy instance (got {type(policy).__name__!r})."
            )


# ---------------------------------------------------------------------------
# Surface validity tests
# ---------------------------------------------------------------------------


class TestPolicyMapSurfaceValidity:
    """Every surface referenced in a policy entry must be a valid identifier."""

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_canonical_surface_is_valid(self, field_name: str) -> None:
        """canonical_surface must be a recognised RetrievalMetadataSurface literal."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        assert policy.canonical_surface in _VALID_SURFACES, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].canonical_surface "
            f"is {policy.canonical_surface!r}, which is not a valid surface. "
            f"Valid surfaces: {sorted(_VALID_SURFACES)!r}."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_mirrored_in_surfaces_are_valid(self, field_name: str) -> None:
        """Every surface in mirrored_in must be a recognised RetrievalMetadataSurface."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        invalid = frozenset(policy.mirrored_in) - _VALID_SURFACES
        assert not invalid, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].mirrored_in contains "
            f"invalid surface(s): {sorted(invalid)!r}. "
            f"Valid surfaces: {sorted(_VALID_SURFACES)!r}."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_forbidden_in_surfaces_are_valid(self, field_name: str) -> None:
        """Every surface in forbidden_in must be a recognised RetrievalMetadataSurface."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        invalid = frozenset(policy.forbidden_in) - _VALID_SURFACES
        assert not invalid, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].forbidden_in contains "
            f"invalid surface(s): {sorted(invalid)!r}. "
            f"Valid surfaces: {sorted(_VALID_SURFACES)!r}."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_field_name_by_surface_keys_are_valid(self, field_name: str) -> None:
        """Every key in field_name_by_surface must be a recognised RetrievalMetadataSurface."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        invalid = frozenset(policy.field_name_by_surface) - _VALID_SURFACES
        assert not invalid, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].field_name_by_surface "
            f"contains invalid surface key(s): {sorted(invalid)!r}. "
            f"Valid surfaces: {sorted(_VALID_SURFACES)!r}."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_field_name_by_surface_values_are_non_empty_strings(self, field_name: str) -> None:
        """Every value in field_name_by_surface must be a non-empty string."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        for surface, alias in policy.field_name_by_surface.items():
            assert isinstance(alias, str) and alias, (
                f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].field_name_by_surface"
                f"[{surface!r}] must be a non-empty string; got {alias!r}."
            )


# ---------------------------------------------------------------------------
# Internal consistency tests
# ---------------------------------------------------------------------------


class TestPolicyMapInternalConsistency:
    """Policy entries must not contain structural contradictions."""

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_canonical_surface_not_in_forbidden_in(self, field_name: str) -> None:
        """A field's canonical_surface must not also appear in its forbidden_in tuple.

        Listing the canonical surface as forbidden is a structural contradiction:
        the field must both be and not be on that surface at the same time.
        """
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        assert policy.canonical_surface not in policy.forbidden_in, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}] lists "
            f"{policy.canonical_surface!r} as both canonical_surface and in "
            f"forbidden_in — this is a structural contradiction."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_canonical_surface_not_in_mirrored_in(self, field_name: str) -> None:
        """A field's canonical_surface must not also appear in its mirrored_in tuple.

        The canonical surface is the primary home; mirrored_in lists *additional*
        surfaces.  Listing the canonical surface in both is redundant and
        potentially confusing.
        """
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        assert policy.canonical_surface not in policy.mirrored_in, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}] lists "
            f"{policy.canonical_surface!r} as both canonical_surface and in "
            f"mirrored_in — canonical_surface must not be duplicated in mirrored_in."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_no_overlap_between_mirrored_in_and_forbidden_in(self, field_name: str) -> None:
        """A surface must not appear in both mirrored_in and forbidden_in simultaneously."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        overlap = frozenset(policy.mirrored_in) & frozenset(policy.forbidden_in)
        assert not overlap, (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}] lists "
            f"{sorted(overlap)!r} in both mirrored_in and forbidden_in — "
            f"a surface cannot simultaneously be a mirror and forbidden."
        )


# ---------------------------------------------------------------------------
# Specific field classification tests (§2.6 and §2.9 rules)
# ---------------------------------------------------------------------------


class TestKnownFieldClassifications:
    """Named fields must carry the ownership and mirroring rules from §2.6 and §2.9."""

    def test_all_answers_cited_canonical_surface_is_top_level(self) -> None:
        """all_answers_cited must have top_level as its canonical surface."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        assert policy.canonical_surface == "top_level", (
            f"'all_answers_cited' canonical_surface must be 'top_level' (§2.9); "
            f"got {policy.canonical_surface!r}."
        )

    def test_all_answers_cited_is_mirrored_in_debug_view(self) -> None:
        """all_answers_cited must be mirrored in debug_view (as 'all_cited', §2.9)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        assert "debug_view" in policy.mirrored_in, (
            f"'all_answers_cited' must be mirrored in 'debug_view' (§2.9); "
            f"got mirrored_in={policy.mirrored_in!r}."
        )

    def test_all_answers_cited_alias_in_debug_view_is_all_cited(self) -> None:
        """all_answers_cited must encode 'all_cited' as its name in debug_view (§2.9 naming alias)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        assert policy.field_name_by_surface.get("debug_view") == "all_cited", (
            f"'all_answers_cited' must map 'debug_view' -> 'all_cited' in "
            f"field_name_by_surface (§2.9 naming alias); "
            f"got field_name_by_surface={policy.field_name_by_surface!r}."
        )

    def test_all_answers_cited_alias_in_citation_quality_is_all_cited(self) -> None:
        """all_answers_cited must encode 'all_cited' as its name in citation_quality (§2.9)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        assert policy.field_name_by_surface.get("citation_quality") == "all_cited", (
            f"'all_answers_cited' must map 'citation_quality' -> 'all_cited' in "
            f"field_name_by_surface (§2.9 naming alias); "
            f"got field_name_by_surface={policy.field_name_by_surface!r}."
        )

    def test_evidence_level_canonical_surface_is_citation_quality(self) -> None:
        """evidence_level must have citation_quality as its canonical surface (§2.6 rule 2)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["evidence_level"]
        assert policy.canonical_surface == "citation_quality", (
            f"'evidence_level' canonical_surface must be 'citation_quality' (§2.6 rule 2); "
            f"got {policy.canonical_surface!r}."
        )

    def test_evidence_level_forbidden_at_top_level(self) -> None:
        """evidence_level must be forbidden at the top level (§2.6 rule 2, §2.9)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["evidence_level"]
        assert "top_level" in policy.forbidden_in, (
            f"'evidence_level' must be forbidden at 'top_level' (§2.6 rule 2); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_warning_count_canonical_surface_is_citation_quality(self) -> None:
        """warning_count must have citation_quality as its canonical surface (§2.6 rule 2)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["warning_count"]
        assert policy.canonical_surface == "citation_quality", (
            f"'warning_count' canonical_surface must be 'citation_quality' (§2.6 rule 2); "
            f"got {policy.canonical_surface!r}."
        )

    def test_warning_count_forbidden_at_top_level(self) -> None:
        """warning_count must be forbidden at the top level (§2.6 rule 2, §2.9)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["warning_count"]
        assert "top_level" in policy.forbidden_in, (
            f"'warning_count' must be forbidden at 'top_level' (§2.6 rule 2); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_citation_warnings_canonical_surface_is_citation_quality(self) -> None:
        """citation_warnings must have citation_quality as its canonical surface (§2.6 rule 1)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_warnings"]
        assert policy.canonical_surface == "citation_quality", (
            f"'citation_warnings' canonical_surface must be 'citation_quality' (§2.6 rule 1); "
            f"got {policy.canonical_surface!r}."
        )

    def test_citation_warnings_forbidden_at_top_level(self) -> None:
        """citation_warnings must be forbidden as a direct top-level key (§2.9 Inspection-only).

        The top-level ``warnings`` list is a *superset* of
        ``citation_quality["citation_warnings"]`` — it may contain additional
        non-citation warnings (§3.7).  Because the relationship is superset
        (not identical-value mirror), ``"warnings"`` is not listed in
        ``mirrored_in``.  The structural enforcement for this field is that the
        bare key ``"citation_warnings"`` must not appear as a direct top-level
        key (§2.9 Inspection-only).
        """
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_warnings"]
        assert "top_level" in policy.forbidden_in, (
            f"'citation_warnings' must be forbidden at 'top_level' (§2.9 Inspection-only); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_malformed_diagnostics_count_canonical_surface_is_telemetry(self) -> None:
        """malformed_diagnostics_count must have telemetry as its canonical surface (§2.6 rule 3)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["malformed_diagnostics_count"]
        assert policy.canonical_surface == "telemetry", (
            f"'malformed_diagnostics_count' canonical_surface must be 'telemetry' "
            f"(§2.6 rule 3); got {policy.canonical_surface!r}."
        )

    def test_malformed_diagnostics_count_forbidden_in_citation_quality(self) -> None:
        """malformed_diagnostics_count must be forbidden inside citation_quality (§2.6 rule 3, §3.10)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["malformed_diagnostics_count"]
        assert "citation_quality" in policy.forbidden_in, (
            f"'malformed_diagnostics_count' must be forbidden in 'citation_quality' "
            f"(§2.6 rule 3, §3.10); got forbidden_in={policy.forbidden_in!r}."
        )

    def test_malformed_diagnostics_count_forbidden_in_warnings(self) -> None:
        """malformed_diagnostics_count must be forbidden in warnings (§3.10 — not a human-facing string)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["malformed_diagnostics_count"]
        assert "warnings" in policy.forbidden_in, (
            f"'malformed_diagnostics_count' must be forbidden in 'warnings' "
            f"(§3.10 — telemetry counter must not add string entries to warnings); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_citation_repair_attempted_canonical_surface_is_top_level(self) -> None:
        """citation_repair_attempted must have top_level as its canonical surface."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_attempted"]
        assert policy.canonical_surface == "top_level", (
            f"'citation_repair_attempted' canonical_surface must be 'top_level'; "
            f"got {policy.canonical_surface!r}."
        )

    def test_citation_repair_attempted_mirrored_in_debug_view(self) -> None:
        """citation_repair_attempted must be mirrored in debug_view (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_attempted"]
        assert "debug_view" in policy.mirrored_in, (
            f"'citation_repair_attempted' must be mirrored in 'debug_view' (§2.9); "
            f"got mirrored_in={policy.mirrored_in!r}."
        )

    def test_citation_repair_attempted_forbidden_in_citation_quality(self) -> None:
        """citation_repair_attempted must be forbidden in citation_quality (not a citation-quality metric)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_attempted"]
        assert "citation_quality" in policy.forbidden_in, (
            f"'citation_repair_attempted' must be forbidden in 'citation_quality' "
            f"(it is a postprocessing control field, not a citation-quality metric); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_citation_repair_applied_canonical_surface_is_top_level(self) -> None:
        """citation_repair_applied must have top_level as its canonical surface (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_applied"]
        assert policy.canonical_surface == "top_level", (
            f"'citation_repair_applied' canonical_surface must be 'top_level' (§2.9 Mirrored); "
            f"got {policy.canonical_surface!r}."
        )

    def test_citation_repair_applied_mirrored_in_debug_view(self) -> None:
        """citation_repair_applied must be mirrored in debug_view (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_applied"]
        assert "debug_view" in policy.mirrored_in, (
            f"'citation_repair_applied' must be mirrored in 'debug_view' (§2.9 Mirrored); "
            f"got mirrored_in={policy.mirrored_in!r}."
        )

    def test_citation_repair_applied_forbidden_in_citation_quality(self) -> None:
        """citation_repair_applied must be forbidden in citation_quality (not a citation-quality metric)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_repair_applied"]
        assert "citation_quality" in policy.forbidden_in, (
            f"'citation_repair_applied' must be forbidden in 'citation_quality' "
            f"(postprocessing control field, not a citation-quality metric); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_citation_fallback_applied_canonical_surface_is_top_level(self) -> None:
        """citation_fallback_applied must have top_level as its canonical surface (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_fallback_applied"]
        assert policy.canonical_surface == "top_level", (
            f"'citation_fallback_applied' canonical_surface must be 'top_level' (§2.9 Mirrored); "
            f"got {policy.canonical_surface!r}."
        )

    def test_citation_fallback_applied_mirrored_in_debug_view(self) -> None:
        """citation_fallback_applied must be mirrored in debug_view (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_fallback_applied"]
        assert "debug_view" in policy.mirrored_in, (
            f"'citation_fallback_applied' must be mirrored in 'debug_view' (§2.9 Mirrored); "
            f"got mirrored_in={policy.mirrored_in!r}."
        )

    def test_citation_fallback_applied_forbidden_in_citation_quality(self) -> None:
        """citation_fallback_applied must be forbidden in citation_quality (not a citation-quality metric)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["citation_fallback_applied"]
        assert "citation_quality" in policy.forbidden_in, (
            f"'citation_fallback_applied' must be forbidden in 'citation_quality' "
            f"(postprocessing control field, not a citation-quality metric); "
            f"got forbidden_in={policy.forbidden_in!r}."
        )

    def test_raw_answer_all_cited_canonical_surface_is_top_level(self) -> None:
        """raw_answer_all_cited must have top_level as its canonical surface (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["raw_answer_all_cited"]
        assert policy.canonical_surface == "top_level", (
            f"'raw_answer_all_cited' canonical_surface must be 'top_level' (§2.9 Mirrored); "
            f"got {policy.canonical_surface!r}."
        )

    def test_raw_answer_all_cited_mirrored_in_debug_view(self) -> None:
        """raw_answer_all_cited must be mirrored in debug_view (§2.9 Mirrored)."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["raw_answer_all_cited"]
        assert "debug_view" in policy.mirrored_in, (
            f"'raw_answer_all_cited' must be mirrored in 'debug_view' (§2.9 Mirrored); "
            f"got mirrored_in={policy.mirrored_in!r}."
        )

    def test_all_debug_view_mirrored_fields_listed(self) -> None:
        """All §2.9 Mirrored fields must declare debug_view in their mirrored_in tuple.

        The §2.9 classification table lists the following as "Mirrored" (same name
        at top-level and in debug_view): raw_answer_all_cited, citation_repair_attempted,
        citation_repair_applied, citation_fallback_applied, malformed_diagnostics_count.
        """
        mirrored_fields = {
            "raw_answer_all_cited",
            "citation_repair_attempted",
            "citation_repair_applied",
            "citation_fallback_applied",
            "malformed_diagnostics_count",
        }
        for field_name in mirrored_fields:
            policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
            assert "debug_view" in policy.mirrored_in, (
                f"§2.9 Mirrored field {field_name!r} must declare 'debug_view' in "
                f"mirrored_in; got mirrored_in={policy.mirrored_in!r}."
            )

    def test_all_debug_view_inspection_only_fields_listed(self) -> None:
        """All §2.9 Inspection-only fields must declare debug_view in their mirrored_in tuple.

        The §2.9 classification table lists the following as "Inspection-only"
        (exist only inside debug_view or citation_quality, not as direct top-level keys):
        all_cited (→ all_answers_cited), evidence_level, warning_count, citation_warnings.
        """
        inspection_only_fields = {
            "all_answers_cited",
            "evidence_level",
            "warning_count",
            "citation_warnings",
        }
        for field_name in inspection_only_fields:
            policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
            assert "debug_view" in policy.mirrored_in, (
                f"§2.9 Inspection-only field {field_name!r} must declare 'debug_view' in "
                f"mirrored_in; got mirrored_in={policy.mirrored_in!r}."
            )


# ---------------------------------------------------------------------------
# Package public-surface import test
# ---------------------------------------------------------------------------


class TestPackagePublicExports:
    """Verify the three policy names are importable from the public ``demo.contracts`` surface.

    Importing from ``demo.contracts`` rather than the submodule catches any drift
    in ``demo/contracts/__init__.py`` — if a name is removed from the package
    ``__all__`` or the re-export import is deleted, this test will fail before
    callers encounter a runtime ``ImportError``.
    """

    def test_field_surface_policy_importable_from_package(self) -> None:
        """``FieldSurfacePolicy`` must be importable from ``demo.contracts``."""
        from demo.contracts import FieldSurfacePolicy as _FieldSurfacePolicy  # noqa: PLC0415

        assert _FieldSurfacePolicy is not None

    def test_retrieval_metadata_surface_importable_from_package(self) -> None:
        """``RetrievalMetadataSurface`` must be importable from ``demo.contracts``."""
        from demo.contracts import RetrievalMetadataSurface as _Surface  # noqa: PLC0415

        assert _Surface is not None

    def test_retrieval_metadata_surface_policy_importable_from_package(self) -> None:
        """``RETRIEVAL_METADATA_SURFACE_POLICY`` must be importable from ``demo.contracts``."""
        from demo.contracts import RETRIEVAL_METADATA_SURFACE_POLICY as _POLICY  # noqa: PLC0415

        assert _POLICY is not None

    def test_all_three_names_in_package_all(self) -> None:
        """All three public names must appear in ``demo.contracts.__all__``."""
        import demo.contracts as _contracts  # noqa: PLC0415

        expected = {"FieldSurfacePolicy", "RetrievalMetadataSurface", "RETRIEVAL_METADATA_SURFACE_POLICY"}
        missing = expected - set(_contracts.__all__)
        assert not missing, (
            f"The following names are missing from demo.contracts.__all__: {sorted(missing)!r}. "
            f"Add them so callers using 'from demo.contracts import *' receive them."
        )

    def test_package_exports_are_same_objects_as_submodule(self) -> None:
        """Names re-exported from ``demo.contracts`` must be the same objects as from the submodule."""
        import demo.contracts as _contracts  # noqa: PLC0415
        from demo.contracts.retrieval_metadata_policy import (  # noqa: PLC0415
            FieldSurfacePolicy as _SubFieldSurfacePolicy,
            RetrievalMetadataSurface as _SubSurface,
            RETRIEVAL_METADATA_SURFACE_POLICY as _SubPolicy,
        )

        assert _contracts.FieldSurfacePolicy is _SubFieldSurfacePolicy, (
            "demo.contracts.FieldSurfacePolicy must be the same object as "
            "demo.contracts.retrieval_metadata_policy.FieldSurfacePolicy"
        )
        assert _contracts.RetrievalMetadataSurface is _SubSurface, (
            "demo.contracts.RetrievalMetadataSurface must be the same object as "
            "demo.contracts.retrieval_metadata_policy.RetrievalMetadataSurface"
        )
        assert _contracts.RETRIEVAL_METADATA_SURFACE_POLICY is _SubPolicy, (
            "demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY must be the same object as "
            "demo.contracts.retrieval_metadata_policy.RETRIEVAL_METADATA_SURFACE_POLICY"
        )


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------


class TestImmutability:
    """Policy map and field-name alias mapping must be immutable at runtime.

    ``FieldSurfacePolicy`` is a frozen dataclass, so attributes cannot be
    reassigned.  The ``field_name_by_surface`` attribute and the module-level
    ``RETRIEVAL_METADATA_SURFACE_POLICY`` are additionally stored as
    :class:`~types.MappingProxyType` instances, which raise :exc:`TypeError`
    on any mutation attempt (``__setitem__``, ``__delitem__``, etc.).
    """

    def test_policy_map_is_mapping_proxy(self) -> None:
        """RETRIEVAL_METADATA_SURFACE_POLICY must be a MappingProxyType."""
        from types import MappingProxyType  # noqa: PLC0415

        assert isinstance(RETRIEVAL_METADATA_SURFACE_POLICY, MappingProxyType), (
            "RETRIEVAL_METADATA_SURFACE_POLICY must be a MappingProxyType so callers "
            f"cannot mutate the canonical policy map; got {type(RETRIEVAL_METADATA_SURFACE_POLICY).__name__!r}."
        )

    def test_policy_map_rejects_new_entry(self) -> None:
        """Attempting to add a new key to RETRIEVAL_METADATA_SURFACE_POLICY must raise TypeError."""
        with pytest.raises(TypeError):
            RETRIEVAL_METADATA_SURFACE_POLICY["__test_mutation__"] = None  # type: ignore[index]

    def test_policy_map_rejects_delete_entry(self) -> None:
        """Attempting to delete a key from RETRIEVAL_METADATA_SURFACE_POLICY must raise TypeError."""
        existing_key = next(iter(RETRIEVAL_METADATA_SURFACE_POLICY))
        with pytest.raises(TypeError):
            del RETRIEVAL_METADATA_SURFACE_POLICY[existing_key]  # type: ignore[attr-defined]

    def test_field_name_by_surface_is_mapping_proxy(self) -> None:
        """field_name_by_surface on all_answers_cited must be a MappingProxyType."""
        from types import MappingProxyType  # noqa: PLC0415

        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        assert isinstance(policy.field_name_by_surface, MappingProxyType), (
            "'all_answers_cited'.field_name_by_surface must be a MappingProxyType so it "
            "cannot be mutated at runtime; got "
            f"{type(policy.field_name_by_surface).__name__!r}."
        )

    def test_field_name_by_surface_rejects_mutation(self) -> None:
        """Attempting to add an entry to field_name_by_surface must raise TypeError."""
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["all_answers_cited"]
        with pytest.raises(TypeError):
            policy.field_name_by_surface["top_level"] = "__test__"  # type: ignore[index]

    def test_default_field_name_by_surface_is_mapping_proxy(self) -> None:
        """Fields with no name aliases must use an empty MappingProxyType as default."""
        from types import MappingProxyType  # noqa: PLC0415

        # raw_answer_all_cited has no aliases; its field_name_by_surface should
        # be an empty MappingProxyType, not a plain dict.
        policy = RETRIEVAL_METADATA_SURFACE_POLICY["raw_answer_all_cited"]
        assert isinstance(policy.field_name_by_surface, MappingProxyType), (
            "'raw_answer_all_cited'.field_name_by_surface (no-alias field) must be a "
            f"MappingProxyType; got {type(policy.field_name_by_surface).__name__!r}."
        )
        assert len(policy.field_name_by_surface) == 0, (
            "'raw_answer_all_cited'.field_name_by_surface must be empty (no aliases); "
            f"got {dict(policy.field_name_by_surface)!r}."
        )

    @pytest.mark.parametrize("field_name", sorted(RETRIEVAL_METADATA_SURFACE_POLICY))
    def test_every_field_name_by_surface_is_mapping_proxy(self, field_name: str) -> None:
        """field_name_by_surface must be a MappingProxyType for every policy entry.

        ``FieldSurfacePolicy.__post_init__`` coerces any input to a
        ``MappingProxyType``, so this test catches any regression where a plain
        ``dict`` is stored instead (e.g. if the coercion is accidentally removed).
        """
        from types import MappingProxyType  # noqa: PLC0415

        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        assert isinstance(policy.field_name_by_surface, MappingProxyType), (
            f"RETRIEVAL_METADATA_SURFACE_POLICY[{field_name!r}].field_name_by_surface "
            f"must be a MappingProxyType (coerced by __post_init__); got "
            f"{type(policy.field_name_by_surface).__name__!r}."
        )

