"""Drift checks for the §2.10 metadata relationship taxonomy representative examples.

These tests keep the structured examples from the §2.10 taxonomy table in
``docs/architecture/retrieval-citation-result-contract-v0.1.md`` aligned with
the actual ``RETRIEVAL_METADATA_SURFACE_POLICY`` declarations.  They guard against
silent drift when a field's canonical surface, mirroring relationship, alias name,
propagation target, or forbidden surface changes without the documentation table
being updated to match.

Design principles
-----------------
- No brittle full-document parsing.  The expected values are encoded in a small
  structured fixture (``_TAXONOMY_EXAMPLE_CLAIMS``) that mirrors the §2.10 prose
  table; it is the only thing that needs updating when the table changes.
- Each test class verifies one category of relationship claim (canonical surface,
  exact mirror, alias mirror, propagation, forbidden) and is parametrised over the
  six representative fields so failures clearly identify which documented example
  drifted from the current policy.
- This file complements ``test_retrieval_metadata_policy.py`` (structural and
  coverage tests) and ``test_retrieval_metadata_projection_parity.py`` (runtime
  tests); it does not duplicate their assertions.

The six representative fields covered here are those listed in the §2.10 table:

- ``all_answers_cited``
- ``raw_answer_all_cited``
- ``citation_warnings``
- ``warning_count``
- ``malformed_diagnostics_count``
- ``evidence_level``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import pytest

from demo.contracts.retrieval_metadata_policy import (
    RETRIEVAL_METADATA_SURFACE_POLICY,
    RetrievalMetadataSurface,
)

# ---------------------------------------------------------------------------
# Structured fixture: machine-readable encoding of the §2.10 taxonomy table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TaxonomyClaim:
    """Machine-readable encoding of one row in the §2.10 taxonomy examples table.

    Attributes
    ----------
    canonical_surface:
        The documented canonical surface for the field.
    exact_mirror_surfaces:
        Surfaces documented as *exact mirrors* (same key name, identical value).
        No ``field_name_by_surface`` entry is expected for these surfaces.
    alias_mirror_surfaces:
        Surfaces documented as *alias mirrors* (different key name, identical value).
        Maps the surface identifier to the expected alias key name.
    propagation_targets:
        Surfaces documented as *propagation / superset* targets.
    forbidden_surfaces:
        Surfaces documented as *forbidden placements*.
    """

    canonical_surface: RetrievalMetadataSurface
    exact_mirror_surfaces: tuple[RetrievalMetadataSurface, ...] = ()
    alias_mirror_surfaces: Mapping[RetrievalMetadataSurface, str] = field(
        default_factory=dict
    )
    propagation_targets: tuple[RetrievalMetadataSurface, ...] = ()
    forbidden_surfaces: tuple[RetrievalMetadataSurface, ...] = ()

    def __post_init__(self) -> None:
        # Wrap the mutable dict in an immutable proxy so that frozen=True is
        # meaningful end-to-end: the attribute itself cannot be rebound *and*
        # the mapping contents cannot be mutated across tests.
        object.__setattr__(
            self,
            "alias_mirror_surfaces",
            MappingProxyType(dict(self.alias_mirror_surfaces)),
        )


#: Structured encoding of the §2.10 representative field examples table.
#:
#: Each entry must exactly reflect the corresponding table row in §2.10 of
#: ``docs/architecture/retrieval-citation-result-contract-v0.1.md``.
#: When the prose table is updated, update this fixture to match — a test
#: failure here means either the policy or the docs table has drifted.
#:
#: Table row format (from §2.10):
#: | Field | Canonical surface | Relationship | Notes |
_TAXONOMY_EXAMPLE_CLAIMS: dict[str, _TaxonomyClaim] = {
    # | `all_answers_cited` | `top_level` | **Alias mirror** → `citation_quality`
    # (as `all_cited`), `debug_view` (as `all_cited`) |
    "all_answers_cited": _TaxonomyClaim(
        canonical_surface="top_level",
        alias_mirror_surfaces={
            "citation_quality": "all_cited",
            "debug_view": "all_cited",
        },
    ),
    # | `raw_answer_all_cited` | `top_level` | **Exact mirror** → `citation_quality`,
    # `debug_view` |
    "raw_answer_all_cited": _TaxonomyClaim(
        canonical_surface="top_level",
        exact_mirror_surfaces=("citation_quality", "debug_view"),
    ),
    # | `citation_warnings` | `citation_quality` | **Propagation** → `warnings`
    # (superset); **exact mirror** → `debug_view`; **forbidden** at `top_level` |
    "citation_warnings": _TaxonomyClaim(
        canonical_surface="citation_quality",
        exact_mirror_surfaces=("debug_view",),
        propagation_targets=("warnings",),
        forbidden_surfaces=("top_level",),
    ),
    # | `warning_count` | `citation_quality` | **Exact mirror** → `debug_view`;
    # **forbidden** at `top_level` |
    "warning_count": _TaxonomyClaim(
        canonical_surface="citation_quality",
        exact_mirror_surfaces=("debug_view",),
        forbidden_surfaces=("top_level",),
    ),
    # | `malformed_diagnostics_count` | `telemetry` | **Exact mirror** → `debug_view`;
    # **forbidden** in `citation_quality` and `warnings` |
    "malformed_diagnostics_count": _TaxonomyClaim(
        canonical_surface="telemetry",
        exact_mirror_surfaces=("debug_view",),
        forbidden_surfaces=("citation_quality", "warnings"),
    ),
    # | `evidence_level` | `citation_quality` | **Exact mirror** → `debug_view`;
    # **forbidden** at `top_level` |
    "evidence_level": _TaxonomyClaim(
        canonical_surface="citation_quality",
        exact_mirror_surfaces=("debug_view",),
        forbidden_surfaces=("top_level",),
    ),
}

#: Sorted list of field names for use as pytest parametrize IDs.
_TAXONOMY_FIELDS = sorted(_TAXONOMY_EXAMPLE_CLAIMS)


# ---------------------------------------------------------------------------
# Guard: every taxonomy example field must exist in the policy map
# ---------------------------------------------------------------------------


class TestTaxonomyExampleFieldsExistInPolicy:
    """Every field referenced in the §2.10 taxonomy examples must exist in the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_taxonomy_example_field_exists_in_policy(self, field_name: str) -> None:
        """A field documented in the §2.10 table must have a policy entry.

        If this test fails it means the field was removed from
        ``RETRIEVAL_METADATA_SURFACE_POLICY`` without updating the taxonomy table,
        or the field was renamed in the policy.
        """
        assert field_name in RETRIEVAL_METADATA_SURFACE_POLICY, (
            f"Taxonomy example drift: §2.10 documents {field_name!r} but it has no "
            f"entry in RETRIEVAL_METADATA_SURFACE_POLICY. "
            f"Either add a policy entry or remove the field from the §2.10 table."
        )


# ---------------------------------------------------------------------------
# Canonical surface drift checks
# ---------------------------------------------------------------------------


class TestTaxonomyExampleCanonicalSurface:
    """Canonical surface claims in the §2.10 table must match the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_canonical_surface_matches_claim(self, field_name: str) -> None:
        """The canonical_surface in the policy must match the §2.10 taxonomy claim."""
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        assert policy.canonical_surface == claim.canonical_surface, (
            f"Taxonomy example drift for {field_name!r}: "
            f"§2.10 documents canonical_surface={claim.canonical_surface!r} but "
            f"RETRIEVAL_METADATA_SURFACE_POLICY has {policy.canonical_surface!r}. "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )


# ---------------------------------------------------------------------------
# Exact mirror drift checks
# ---------------------------------------------------------------------------


class TestTaxonomyExampleExactMirrors:
    """Exact-mirror claims in the §2.10 table must match the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_mirrored_in_matches_documented_mirrors(self, field_name: str) -> None:
        """policy.mirrored_in must equal the union of exact-mirror and alias-mirror surfaces.

        Checks both directions:
        - Every surface documented as a mirror (exact or alias) must appear in
          ``mirrored_in``.
        - No surface may appear in ``mirrored_in`` that is not documented as either
          an exact mirror or an alias mirror in §2.10.

        If either direction fails, the §2.10 taxonomy table and the policy have
        drifted; one of them must be updated.
        """
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        documented_mirrors = set(claim.exact_mirror_surfaces) | set(claim.alias_mirror_surfaces)
        actual_mirrors = set(policy.mirrored_in)

        undocumented = actual_mirrors - documented_mirrors
        assert not undocumented, (
            f"Taxonomy example drift for {field_name!r}: "
            f"policy.mirrored_in contains surface(s) {sorted(undocumented)!r} "
            f"that are not documented as mirrors in §2.10 "
            f"(documented_mirrors={sorted(documented_mirrors)!r}, "
            f"policy_mirrored_in={sorted(actual_mirrors)!r}). "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

        missing = documented_mirrors - actual_mirrors
        assert not missing, (
            f"Taxonomy example drift for {field_name!r}: "
            f"§2.10 documents surface(s) {sorted(missing)!r} as mirrors but they "
            f"are not listed in policy.mirrored_in={sorted(actual_mirrors)!r}. "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_exact_mirror_surfaces_have_no_alias_entry(self, field_name: str) -> None:
        """An exact mirror uses the same key name, so no alias entry should exist.

        If ``field_name_by_surface`` has an entry for a surface that the docs
        document as an *exact* mirror, the relationship has changed to an alias
        mirror and the §2.10 taxonomy table must be updated to reflect that.
        """
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        for surface in claim.exact_mirror_surfaces:
            assert surface not in policy.field_name_by_surface, (
                f"Taxonomy example drift for {field_name!r}: "
                f"§2.10 documents {surface!r} as an *exact* mirror (same key name) "
                f"but field_name_by_surface contains an alias for it: "
                f"{policy.field_name_by_surface.get(surface)!r}. "
                f"If the key name changed, update the §2.10 taxonomy table to "
                f"'alias mirror' and add the alias key to the fixture."
            )


# ---------------------------------------------------------------------------
# Alias mirror drift checks
# ---------------------------------------------------------------------------


class TestTaxonomyExampleAliasMirrors:
    """Alias-mirror claims in the §2.10 table must match the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_field_name_by_surface_matches_documented_aliases(self, field_name: str) -> None:
        """policy.field_name_by_surface must equal the set of documented alias mirrors.

        Checks both directions:
        - Every surface documented as an alias mirror must have a corresponding
          entry in ``field_name_by_surface``.
        - No entry may exist in ``field_name_by_surface`` that is not documented
          as an alias mirror in §2.10.

        Also verifies that every alias mirror surface appears in ``mirrored_in``
        and that the documented alias key name matches the policy.
        """
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        documented_alias_surfaces = set(claim.alias_mirror_surfaces)
        actual_alias_surfaces = set(policy.field_name_by_surface)

        undocumented = actual_alias_surfaces - documented_alias_surfaces
        assert not undocumented, (
            f"Taxonomy example drift for {field_name!r}: "
            f"policy.field_name_by_surface contains alias entries for surface(s) "
            f"{sorted(undocumented)!r} that are not documented as alias mirrors in §2.10 "
            f"(documented_alias_mirrors={sorted(documented_alias_surfaces)!r}, "
            f"policy_field_name_by_surface keys={sorted(actual_alias_surfaces)!r}). "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

        missing = documented_alias_surfaces - actual_alias_surfaces
        assert not missing, (
            f"Taxonomy example drift for {field_name!r}: "
            f"§2.10 documents surface(s) {sorted(missing)!r} as alias mirrors but "
            f"field_name_by_surface has no entry for them "
            f"(policy_field_name_by_surface keys={sorted(actual_alias_surfaces)!r}). "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

        # Verify each documented alias surface is in mirrored_in and the alias name matches.
        for surface, expected_alias in claim.alias_mirror_surfaces.items():
            assert surface in policy.mirrored_in, (
                f"Taxonomy example drift for {field_name!r}: "
                f"§2.10 documents {surface!r} as an alias mirror but it is not "
                f"listed in mirrored_in={policy.mirrored_in!r}. "
                f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
            )
            actual_alias = policy.field_name_by_surface.get(surface)
            assert actual_alias == expected_alias, (
                f"Taxonomy example drift for {field_name!r}: "
                f"§2.10 documents the alias name on {surface!r} as {expected_alias!r} "
                f"but field_name_by_surface[{surface!r}]={actual_alias!r}. "
                f"Update the §2.10 taxonomy table note or the policy alias to restore "
                f"alignment."
            )


# ---------------------------------------------------------------------------
# Propagation drift checks
# ---------------------------------------------------------------------------


class TestTaxonomyExamplePropagationTargets:
    """Propagation / superset claims in the §2.10 table must match the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_propagation_targets_match(self, field_name: str) -> None:
        """policy.propagates_to must equal the set of documented propagation targets.

        Checks both directions:
        - Every surface documented as a propagation target must appear in
          ``propagates_to``.
        - No surface may appear in ``propagates_to`` that is not documented as
          a propagation target in §2.10.

        A propagation relationship means the canonical surface is a subset and
        every element from it must also appear on the target (superset) surface.
        This is distinct from a mirror (which carries the identical value).
        """
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        expected_targets = set(claim.propagation_targets)
        actual_targets = set(policy.propagates_to)

        undocumented = actual_targets - expected_targets
        assert not undocumented, (
            f"Taxonomy example drift for {field_name!r}: "
            f"policy.propagates_to contains surface(s) {sorted(undocumented)!r} "
            f"that are not documented as propagation targets in §2.10 "
            f"(documented_propagation_targets={sorted(expected_targets)!r}, "
            f"policy_propagates_to={sorted(actual_targets)!r}). "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

        missing = expected_targets - actual_targets
        assert not missing, (
            f"Taxonomy example drift for {field_name!r}: "
            f"§2.10 documents propagation targets {sorted(missing)!r} but they "
            f"are not listed in policy.propagates_to={sorted(actual_targets)!r}. "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )


# ---------------------------------------------------------------------------
# Forbidden placement drift checks
# ---------------------------------------------------------------------------


class TestTaxonomyExampleForbiddenSurfaces:
    """Forbidden-placement claims in the §2.10 table must match the policy."""

    @pytest.mark.parametrize("field_name", _TAXONOMY_FIELDS)
    def test_forbidden_surfaces_match(self, field_name: str) -> None:
        """policy.forbidden_in must equal the set of documented forbidden surfaces.

        Checks both directions:
        - Every surface documented as forbidden must appear in ``forbidden_in``.
        - No surface may appear in ``forbidden_in`` that is not documented as
          forbidden in §2.10.

        A forbidden placement means the field must never appear on that surface.
        If a field is no longer forbidden on a surface that the §2.10 table
        documents as forbidden, or if a new forbidden surface is added to the
        policy, the relationship has changed and both the policy and the docs
        table must be updated deliberately.
        """
        claim = _TAXONOMY_EXAMPLE_CLAIMS[field_name]
        policy = RETRIEVAL_METADATA_SURFACE_POLICY[field_name]
        doc_forbidden = set(claim.forbidden_surfaces)
        policy_forbidden = set(policy.forbidden_in)

        undocumented_policy_surfaces = policy_forbidden - doc_forbidden
        assert not undocumented_policy_surfaces, (
            f"Taxonomy example drift for {field_name!r}: "
            f"policy.forbidden_in contains surface(s) {sorted(undocumented_policy_surfaces)!r} "
            f"that are not documented as forbidden in §2.10 "
            f"(documented_forbidden={sorted(doc_forbidden)!r}, "
            f"policy_forbidden_in={sorted(policy_forbidden)!r}). "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )

        undocumented_in_policy = doc_forbidden - policy_forbidden
        assert not undocumented_in_policy, (
            f"Taxonomy example drift for {field_name!r}: "
            f"§2.10 documents surface(s) {sorted(undocumented_in_policy)!r} as forbidden "
            f"but they are not listed in forbidden_in={sorted(policy_forbidden)!r}. "
            f"Update the §2.10 taxonomy table or the policy entry to restore alignment."
        )
