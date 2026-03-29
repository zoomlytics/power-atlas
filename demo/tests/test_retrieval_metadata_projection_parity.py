"""Policy-vs-runtime projection parity tests for retrieval metadata surfaces.

This suite is the single explicit parity layer whose purpose is:

    Verify that the runtime result shape produced by ``run_retrieval_and_qa()``
    correctly projects every policy-covered field onto the canonical, mirrored,
    and forbidden surfaces declared by
    :data:`~demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY`.

It closes the remaining drift gap left after the field-level contract tests and
exact-key-set checks: those tests verify representative cases or individual
invariants; this suite drives *all* assertions directly from the policy, so any
future change to the policy or the runtime projection is immediately flagged.

Structure
---------
``TestPolicyVsRuntimeProjectionParity``
    Generic parametric tests driven by :data:`RETRIEVAL_METADATA_SURFACE_POLICY`.
    Parametrized over every policy field **and** all three result shapes
    (``live``, ``dry_run``, ``retrieval_skipped``).

    The five contract aspects checked for each (field, shape) combination:

    1. **Canonical presence** — the field key is present on its canonical surface.
    2. **Mirror presence** — the field key (possibly aliased) is present on every
       declared mirror surface.
    3. **Mirror value equality** — the value on each mirror surface equals the
       value on the canonical surface.
    4. **Forbidden absence** — the field key is absent from every declared
       forbidden surface.
    5. **Alias correctness** — when ``field_name_by_surface`` declares a different
       name for a surface, that alias is used (not the canonical key name).

``TestPolicyVsRuntimeProjectionParityAliasHandling``
    Named explicit tests for the ``all_answers_cited`` / ``all_cited`` alias case,
    which is the most important naming distinction in the policy (§2.9).  These
    tests make the alias contract visible and readable at a glance without relying
    on the generic parametric machinery.

``TestPolicyVsRuntimeProjectionParityEarlyReturnDefaults``
    Named explicit tests that confirm policy-covered fields on early-return paths
    (``dry_run``, ``retrieval_skipped``) still obey the declared projection rules
    even when carrying all-zero/default values.

Why this suite complements the existing tests
---------------------------------------------
:class:`~demo.tests.test_retrieval_result_contract.TestMetadataTaxonomyBoundaries`
and
:class:`~demo.tests.test_retrieval_result_contract.TestProjectionPolicySurfaceOwnership`
use representative, rule-based, or per-scenario assertions.  This suite uses the
policy as its only source of truth: every parametrized check is automatically
extended when a new field is added to
:data:`~demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY`, with no manual test
update required.

Notes on the ``warnings`` surface
----------------------------------
:data:`~demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY` lists ``"warnings"`` as
a ``forbidden_in`` surface for ``malformed_diagnostics_count``.  The ``warnings``
surface is a top-level ``list[str]`` (not a dict), so key-based presence checks
cannot be applied directly.  The generic forbidden-surface tests therefore skip
the ``warnings`` surface and defer to the existing named tests in
:class:`~demo.tests.test_retrieval_result_contract.TestMetadataTaxonomyBoundaries`
which verify the counter does not add string entries to the warnings list.
"""

from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from demo.contracts import RETRIEVAL_METADATA_SURFACE_POLICY, FieldSurfacePolicy
from demo.stages.retrieval_and_qa import run_retrieval_and_qa


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

#: Minimal live-mode config with ``dry_run=False``.
_LIVE_CONFIG = types.SimpleNamespace(
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password",
    neo4j_database=None,
    openai_model="gpt-4o-mini",
    dry_run=False,
)

#: Minimal dry-run config.  Neo4j credentials intentionally absent to prove the
#: dry-run path never opens a database connection.
_DRY_RUN_CONFIG = types.SimpleNamespace(
    openai_model="gpt-4o-mini",
    dry_run=True,
)

#: Synthetic citation token for a fully-cited answer.
_TOKEN = (
    "[CITATION|chunk_id=c1|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=0|page=1|start_char=0|end_char=50]"
)

#: A fully cited single-sentence answer.
_CITED_ANSWER = f"A fully supported claim. {_TOKEN}"

#: Retrieval-item metadata for the live-path tests.  All optional citation fields
#: are present so no "missing optional fields" warning is emitted.
_LIVE_ITEM_METADATA: dict[str, object] = {
    "citation_token": _TOKEN,
    "chunk_id": "c1",
    "citation_object": {
        "chunk_id": "c1",
        "run_id": "r1",
        "source_uri": "file:///doc.pdf",
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 50,
    },
}


# ---------------------------------------------------------------------------
# Result-shape factories
# ---------------------------------------------------------------------------


def _make_live_result() -> dict[str, object]:
    """Return a live, fully-cited result from ``run_retrieval_and_qa()``.

    Uses a mocked Neo4j driver and RAG component so no real network connections
    are made.  The answer is fully cited so no warnings are emitted, keeping the
    result deterministic for value-equality assertions.
    """
    mock_items = [MagicMock(content="chunk text", metadata=_LIVE_ITEM_METADATA)]
    mock_rag_result = MagicMock()
    mock_rag_result.answer = _CITED_ANSWER
    mock_rag_result.retriever_result.items = mock_items
    mock_rag = MagicMock()
    mock_rag.search.return_value = mock_rag_result

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
        patch("neo4j.GraphDatabase.driver"),
        patch("demo.stages.retrieval_and_qa._build_retriever_and_rag") as mock_build,
    ):
        mock_build.return_value = (MagicMock(), mock_rag)
        return run_retrieval_and_qa(
            _LIVE_CONFIG,
            all_runs=True,
            question="What is the claim?",
        )


def _make_dry_run_result() -> dict[str, object]:
    """Return a dry-run early-return result from ``run_retrieval_and_qa()``."""
    return run_retrieval_and_qa(_DRY_RUN_CONFIG, run_id="dr-parity-1", source_uri=None)


def _make_retrieval_skipped_result() -> dict[str, object]:
    """Return a retrieval-skipped early-return result from ``run_retrieval_and_qa()``.

    Uses an invalid (empty-string) Neo4j URI to prove the retrieval-skipped path
    never opens a database connection.
    """
    cfg = types.SimpleNamespace(
        dry_run=False,
        openai_model="gpt-4o-mini",
        neo4j_uri="",
        neo4j_username="",
        neo4j_password="",
        neo4j_database=None,
    )
    return run_retrieval_and_qa(cfg, run_id="skip-parity-1", source_uri=None, question=None)


# ---------------------------------------------------------------------------
# Surface-aware helpers
# ---------------------------------------------------------------------------

#: Surfaces whose values are stored as dict keys in the result dict and can be
#: checked with the same key-presence / key-access logic.
_DICT_SURFACES: frozenset[str] = frozenset({"top_level", "citation_quality", "debug_view", "telemetry"})

#: Surfaces that are lists of strings rather than dicts; key-based checks do not
#: apply and are skipped in the generic parametric tests.
_LIST_SURFACES: frozenset[str] = frozenset({"warnings"})


def _surface_dict(result: dict[str, object], surface: str) -> dict[str, object]:
    """Return the dict that backs the given surface.

    - ``"top_level"`` and ``"telemetry"`` → the top-level result dict.
    - ``"citation_quality"`` → the nested ``citation_quality`` dict.
    - ``"debug_view"`` → the nested ``debug_view`` dict.

    Raises :exc:`KeyError` if the nested surface dict is missing from *result*.
    """
    if surface in ("top_level", "telemetry"):
        return result  # type: ignore[return-value]
    return result[surface]  # type: ignore[return-value]


def _effective_name(canonical_key: str, surface: str, policy: FieldSurfacePolicy) -> str:
    """Return the field name under which *canonical_key* appears on *surface*.

    Returns ``canonical_key`` when no alias is declared for *surface* in
    ``policy.field_name_by_surface``.
    """
    return policy.field_name_by_surface.get(surface, canonical_key)


def _field_present_on_surface(
    result: dict[str, object],
    surface: str,
    canonical_key: str,
    policy: FieldSurfacePolicy,
) -> bool:
    """Return ``True`` if the field is present on *surface* in *result*.

    For dict-backed surfaces uses a key-presence check with the correct alias.
    For list surfaces (``warnings``) always returns ``False``; those surfaces are
    not checked by the generic parametric tests.
    """
    if surface in _LIST_SURFACES:
        return False  # not applicable for list surfaces
    name = _effective_name(canonical_key, surface, policy)
    return name in _surface_dict(result, surface)


def _field_value_from_surface(
    result: dict[str, object],
    surface: str,
    canonical_key: str,
    policy: FieldSurfacePolicy,
) -> object:
    """Return the value of the field from *surface* in *result*.

    Uses ``field_name_by_surface`` to resolve the correct alias.
    """
    name = _effective_name(canonical_key, surface, policy)
    return _surface_dict(result, surface)[name]


# ---------------------------------------------------------------------------
# Parametrize helpers
# ---------------------------------------------------------------------------

#: All (canonical_key, policy_entry) pairs from the shared policy.
_POLICY_PARAMS: list[tuple[str, FieldSurfacePolicy]] = list(
    RETRIEVAL_METADATA_SURFACE_POLICY.items()
)

#: Result-shape factories and their labels.
#: Each entry is (label, factory_fn) where factory_fn() → result dict.
_RESULT_SHAPE_FACTORIES: list[tuple[str, object]] = [
    ("live", _make_live_result),
    ("dry_run", _make_dry_run_result),
    ("retrieval_skipped", _make_retrieval_skipped_result),
]

#: (label, policy_entry, shape_label, factory_fn) combinations for full cross-product
#: parametrization.  Each row uniquely identifies one (field, shape) pair.
_FIELD_SHAPE_PARAMS: list[tuple[str, FieldSurfacePolicy, str, object]] = [
    (canonical_key, pol, shape_label, factory_fn)
    for canonical_key, pol in _POLICY_PARAMS
    for shape_label, factory_fn in _RESULT_SHAPE_FACTORIES
]

#: pytest parametrize ids matching _FIELD_SHAPE_PARAMS row order.
_FIELD_SHAPE_IDS: list[str] = [
    f"{canonical_key}_{shape_label}"
    for canonical_key, _pol, shape_label, _fn in _FIELD_SHAPE_PARAMS
]

#: All (canonical_key, policy, mirror_surface, shape_label, factory_fn) rows for
#: mirror-surface parametrization.  Only fields that have at least one mirror surface
#: and where the mirror surface is dict-backed are included.
_MIRROR_PARAMS: list[tuple[str, FieldSurfacePolicy, str, str, object]] = [
    (canonical_key, pol, mirror_surface, shape_label, factory_fn)
    for canonical_key, pol in _POLICY_PARAMS
    for mirror_surface in pol.mirrored_in
    if mirror_surface in _DICT_SURFACES
    for shape_label, factory_fn in _RESULT_SHAPE_FACTORIES
]

_MIRROR_IDS: list[str] = [
    f"{canonical_key}_{mirror_surface}_{shape_label}"
    for canonical_key, _pol, mirror_surface, shape_label, _fn in _MIRROR_PARAMS
]

#: All (canonical_key, policy, forbidden_surface, shape_label, factory_fn) rows for
#: forbidden-surface parametrization.  Only dict-backed forbidden surfaces are included;
#: list surfaces (``warnings``) are excluded (see module docstring).
_FORBIDDEN_PARAMS: list[tuple[str, FieldSurfacePolicy, str, str, object]] = [
    (canonical_key, pol, forbidden_surface, shape_label, factory_fn)
    for canonical_key, pol in _POLICY_PARAMS
    for forbidden_surface in pol.forbidden_in
    if forbidden_surface in _DICT_SURFACES
    for shape_label, factory_fn in _RESULT_SHAPE_FACTORIES
]

_FORBIDDEN_IDS: list[str] = [
    f"{canonical_key}_{forbidden_surface}_{shape_label}"
    for canonical_key, _pol, forbidden_surface, shape_label, _fn in _FORBIDDEN_PARAMS
]

#: All (canonical_key, policy, aliased_surface, alias, shape_label, factory_fn) rows for
#: alias parametrization.  Only rows where field_name_by_surface has an entry for a
#: dict-backed surface are included.
_ALIAS_PARAMS: list[tuple[str, FieldSurfacePolicy, str, str, str, object]] = [
    (canonical_key, pol, aliased_surface, alias, shape_label, factory_fn)
    for canonical_key, pol in _POLICY_PARAMS
    for aliased_surface, alias in pol.field_name_by_surface.items()
    if aliased_surface in _DICT_SURFACES
    for shape_label, factory_fn in _RESULT_SHAPE_FACTORIES
]

_ALIAS_IDS: list[str] = [
    f"{canonical_key}_{aliased_surface}_{shape_label}"
    for canonical_key, _pol, aliased_surface, _alias, shape_label, _fn in _ALIAS_PARAMS
]


# ---------------------------------------------------------------------------
# TestPolicyVsRuntimeProjectionParity
# ---------------------------------------------------------------------------


class TestPolicyVsRuntimeProjectionParity:
    """Generic policy-vs-runtime parity tests driven by RETRIEVAL_METADATA_SURFACE_POLICY.

    Every test method is parametrized over all policy fields and all three result shapes
    so that:

    - adding a new field to the policy automatically extends coverage across every
      test method;
    - changing the surface ownership of an existing field causes exactly the affected
      tests to fail with an actionable message identifying the field, the surface, and
      the nature of the violation.

    The five contract aspects checked here match the acceptance criteria in the issue:

    1. **Canonical presence** — the field is present on its declared canonical surface.
    2. **Mirror presence** — the field (possibly aliased) is present on every declared
       mirror surface.
    3. **Mirror value equality** — the mirror value equals the canonical value.
    4. **Forbidden absence** — the field is absent from every declared forbidden
       dict-backed surface.  (The ``warnings`` list surface is excluded; see module
       docstring.)
    5. **Alias correctness** — when ``field_name_by_surface`` declares a different name
       for a surface, only the alias exists there; the canonical key does NOT.
    """

    # ------------------------------------------------------------------
    # 1. Canonical presence
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "canonical_key,pol,shape_label,result_fn",
        _FIELD_SHAPE_PARAMS,
        ids=_FIELD_SHAPE_IDS,
    )
    def test_canonical_field_present_on_canonical_surface(
        self,
        canonical_key: str,
        pol: FieldSurfacePolicy,
        shape_label: str,
        result_fn: object,
    ) -> None:
        """Every policy field must be present on its declared canonical surface.

        Failure here means the runtime result does not project the field onto its
        canonical owning surface, making it invisible to callers that follow the
        policy.  The failure message identifies the field, the canonical surface, and
        the result shape that violates the rule.
        """
        result = result_fn()  # type: ignore[call-arg]
        surface_dict = _surface_dict(result, pol.canonical_surface)
        canonical_name = _effective_name(canonical_key, pol.canonical_surface, pol)
        assert canonical_name in surface_dict, (
            f"[{shape_label}] Policy field {canonical_key!r} missing from its canonical "
            f"surface {pol.canonical_surface!r}.  "
            f"Expected key {canonical_name!r} in {pol.canonical_surface!r} but it was "
            f"absent.  Check that the runtime projection writes this field to the "
            f"declared canonical surface."
        )

    # ------------------------------------------------------------------
    # 2. Mirror presence
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "canonical_key,pol,mirror_surface,shape_label,result_fn",
        _MIRROR_PARAMS,
        ids=_MIRROR_IDS,
    )
    def test_mirrored_field_present_on_mirror_surface(
        self,
        canonical_key: str,
        pol: FieldSurfacePolicy,
        mirror_surface: str,
        shape_label: str,
        result_fn: object,
    ) -> None:
        """Every policy-declared mirror must be present in the mirror surface dict.

        Failure identifies the field, the missing mirror surface, and the alias that
        should have been used.  Early-return paths (dry_run, retrieval_skipped) are
        required to maintain the same projection structure even with zero/default values.
        """
        result = result_fn()  # type: ignore[call-arg]
        mirror_dict = _surface_dict(result, mirror_surface)
        mirror_name = _effective_name(canonical_key, mirror_surface, pol)
        assert mirror_name in mirror_dict, (
            f"[{shape_label}] Policy field {canonical_key!r} must be mirrored in "
            f"{mirror_surface!r} under the key {mirror_name!r}, but it was absent.  "
            f"Canonical surface: {pol.canonical_surface!r}.  "
            f"Check that the runtime projection writes the mirror value to "
            f"{mirror_surface!r}[{mirror_name!r}]."
        )

    # ------------------------------------------------------------------
    # 3. Mirror value equality
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "canonical_key,pol,mirror_surface,shape_label,result_fn",
        _MIRROR_PARAMS,
        ids=_MIRROR_IDS,
    )
    def test_mirrored_value_matches_canonical_value(
        self,
        canonical_key: str,
        pol: FieldSurfacePolicy,
        mirror_surface: str,
        shape_label: str,
        result_fn: object,
    ) -> None:
        """Mirror values must equal the canonical value (no additional hidden state).

        Mirroring is a convenience feature — the mirror surface must expose
        exactly the same value as the canonical surface, not a derived or stale copy.
        Failure identifies the field, both surfaces, and the actual vs expected values.
        """
        result = result_fn()  # type: ignore[call-arg]
        canonical_value = _field_value_from_surface(result, pol.canonical_surface, canonical_key, pol)
        mirror_value = _field_value_from_surface(result, mirror_surface, canonical_key, pol)
        mirror_name = _effective_name(canonical_key, mirror_surface, pol)
        canonical_name = _effective_name(canonical_key, pol.canonical_surface, pol)
        assert mirror_value == canonical_value, (
            f"[{shape_label}] Policy field {canonical_key!r}: "
            f"mirror value on {mirror_surface!r}[{mirror_name!r}] does not equal "
            f"canonical value on {pol.canonical_surface!r}[{canonical_name!r}].  "
            f"Canonical={canonical_value!r}, mirror={mirror_value!r}.  "
            f"Mirroring must carry no additional hidden state — both surfaces must "
            f"expose identical values."
        )

    # ------------------------------------------------------------------
    # 4. Forbidden absence (dict-backed surfaces only)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "canonical_key,pol,forbidden_surface,shape_label,result_fn",
        _FORBIDDEN_PARAMS,
        ids=_FORBIDDEN_IDS,
    )
    def test_field_absent_from_forbidden_surface(
        self,
        canonical_key: str,
        pol: FieldSurfacePolicy,
        forbidden_surface: str,
        shape_label: str,
        result_fn: object,
    ) -> None:
        """Policy-forbidden fields must not appear on their forbidden surfaces.

        The ``forbidden_in`` list records deliberate surface-boundary decisions:
        placing a field on a forbidden surface would create ambiguity or violate
        the §2.6 taxonomy rules.  Failure identifies the field, the forbidden surface,
        and the key that was found there unexpectedly.

        The ``warnings`` list surface is not checked here; it is handled by
        :class:`~demo.tests.test_retrieval_result_contract.TestMetadataTaxonomyBoundaries`.
        """
        result = result_fn()  # type: ignore[call-arg]
        # Use the canonical key name for the forbidden-surface check; the field should
        # not appear under any name on this surface.
        forbidden_dict = _surface_dict(result, forbidden_surface)
        # Check both the canonical key and any alias that the field declares for this
        # surface (in case someone accidentally added an aliased entry).
        keys_to_check = {canonical_key}
        if forbidden_surface in pol.field_name_by_surface:
            keys_to_check.add(pol.field_name_by_surface[forbidden_surface])
        for key in keys_to_check:
            assert key not in forbidden_dict, (
                f"[{shape_label}] Policy field {canonical_key!r} (key {key!r}) must NOT "
                f"appear on forbidden surface {forbidden_surface!r}.  "
                f"Canonical surface: {pol.canonical_surface!r}.  "
                f"Placing it on {forbidden_surface!r} violates the §2.6 taxonomy rule "
                f"encoded in RETRIEVAL_METADATA_SURFACE_POLICY[{canonical_key!r}].forbidden_in."
            )

    # ------------------------------------------------------------------
    # 5. Alias correctness
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "canonical_key,pol,aliased_surface,alias,shape_label,result_fn",
        _ALIAS_PARAMS,
        ids=_ALIAS_IDS,
    )
    def test_alias_used_on_surface_when_names_differ(
        self,
        canonical_key: str,
        pol: FieldSurfacePolicy,
        aliased_surface: str,
        alias: str,
        shape_label: str,
        result_fn: object,
    ) -> None:
        """When the policy declares an alias for a surface, only the alias key exists there.

        The canonical key name must NOT appear on the surface when an alias is declared;
        only the alias name should be present.  Failure identifies the field, the surface,
        the expected alias, and (if present) the incorrect canonical key that was found.

        This test is particularly important for ``all_answers_cited`` / ``all_cited``:
        the canonical key (``all_answers_cited``) must not appear in ``citation_quality``
        or ``debug_view``; only the alias (``all_cited``) should be present there.
        """
        result = result_fn()  # type: ignore[call-arg]
        surface_dict = _surface_dict(result, aliased_surface)

        # The alias key must be present.
        assert alias in surface_dict, (
            f"[{shape_label}] Policy field {canonical_key!r} must appear on "
            f"{aliased_surface!r} under the alias {alias!r}, but the alias key was "
            f"absent.  "
            f"Check that the runtime projection uses the correct per-surface name."
        )

        # The canonical key must NOT be present on this surface (alias replaces it).
        if alias != canonical_key:
            assert canonical_key not in surface_dict, (
                f"[{shape_label}] Policy field {canonical_key!r} must appear on "
                f"{aliased_surface!r} under the alias {alias!r} — NOT under the "
                f"canonical key name {canonical_key!r}.  "
                f"The canonical key was unexpectedly found on {aliased_surface!r}, "
                f"indicating the alias was not applied correctly."
            )


# ---------------------------------------------------------------------------
# TestPolicyVsRuntimeProjectionParityAliasHandling
# ---------------------------------------------------------------------------


class TestPolicyVsRuntimeProjectionParityAliasHandling:
    """Named explicit tests for the ``all_answers_cited`` / ``all_cited`` alias.

    The ``all_answers_cited`` / ``all_cited`` alias is the most important naming
    distinction in the policy (§2.9 field classification table):

    - ``all_answers_cited`` is the canonical public top-level key.
    - ``all_cited`` is the inspection-only name used inside ``citation_quality``
      and ``debug_view``.
    - The bare name ``all_cited`` must NOT appear as a direct top-level key.

    These named tests make the alias contract visible and readable at a glance,
    complementing the generic alias parametrization in
    :class:`TestPolicyVsRuntimeProjectionParity`.
    """

    # ------------------------------------------------------------------
    # Live path
    # ------------------------------------------------------------------

    def test_live_top_level_uses_all_answers_cited_not_all_cited(self) -> None:
        """Live result: canonical top-level key is ``all_answers_cited``, not ``all_cited``."""
        result = _make_live_result()
        assert "all_answers_cited" in result, (
            "all_answers_cited must be present as a top-level key on the live path"
        )
        assert "all_cited" not in result, (
            "all_cited must NOT appear as a direct top-level key (inspection-only name; §2.9).  "
            "The public alias is all_answers_cited."
        )

    def test_live_citation_quality_uses_all_cited_alias(self) -> None:
        """Live result: ``citation_quality`` exposes ``all_cited``, not ``all_answers_cited``."""
        result = _make_live_result()
        cq = result["citation_quality"]
        assert "all_cited" in cq, (
            "citation_quality must expose all_cited (alias for all_answers_cited on this surface)"
        )
        assert "all_answers_cited" not in cq, (
            "citation_quality must NOT use the canonical key all_answers_cited; "
            "the alias all_cited must be used instead (§2.9 field_name_by_surface)"
        )

    def test_live_debug_view_uses_all_cited_alias(self) -> None:
        """Live result: ``debug_view`` exposes ``all_cited``, not ``all_answers_cited``."""
        result = _make_live_result()
        dv = result["debug_view"]
        assert "all_cited" in dv, (
            "debug_view must expose all_cited (alias for all_answers_cited on this surface)"
        )
        assert "all_answers_cited" not in dv, (
            "debug_view must NOT use the canonical key all_answers_cited; "
            "the alias all_cited must be used instead (§2.9 field_name_by_surface)"
        )

    def test_live_all_cited_in_citation_quality_mirrors_top_level_all_answers_cited(self) -> None:
        """Live result: ``citation_quality["all_cited"]`` mirrors ``all_answers_cited``."""
        result = _make_live_result()
        assert result["citation_quality"]["all_cited"] == result["all_answers_cited"], (
            "citation_quality[all_cited] must mirror the top-level all_answers_cited value.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"citation_quality={result['citation_quality']['all_cited']!r}"
        )

    def test_live_all_cited_in_debug_view_mirrors_top_level_all_answers_cited(self) -> None:
        """Live result: ``debug_view["all_cited"]`` mirrors ``all_answers_cited``."""
        result = _make_live_result()
        assert result["debug_view"]["all_cited"] == result["all_answers_cited"], (
            "debug_view[all_cited] must mirror the top-level all_answers_cited value.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"debug_view={result['debug_view']['all_cited']!r}"
        )

    # ------------------------------------------------------------------
    # Dry-run early-return path
    # ------------------------------------------------------------------

    def test_dry_run_top_level_uses_all_answers_cited_not_all_cited(self) -> None:
        """Dry-run result: canonical top-level key is ``all_answers_cited``, not ``all_cited``."""
        result = _make_dry_run_result()
        assert "all_answers_cited" in result, (
            "all_answers_cited must be present as a top-level key on the dry_run path"
        )
        assert "all_cited" not in result, (
            "all_cited must NOT appear as a direct top-level key on the dry_run path"
        )

    def test_dry_run_citation_quality_uses_all_cited_alias(self) -> None:
        """Dry-run result: ``citation_quality`` uses the ``all_cited`` alias."""
        result = _make_dry_run_result()
        cq = result["citation_quality"]
        assert "all_cited" in cq, (
            "dry_run citation_quality must expose all_cited (default False)"
        )
        assert "all_answers_cited" not in cq, (
            "dry_run citation_quality must NOT use the canonical key all_answers_cited"
        )

    def test_dry_run_all_cited_mirrors_top_level_all_answers_cited(self) -> None:
        """Dry-run result: ``citation_quality["all_cited"]`` mirrors top-level ``all_answers_cited``."""
        result = _make_dry_run_result()
        assert result["citation_quality"]["all_cited"] == result["all_answers_cited"], (
            "dry_run citation_quality[all_cited] must mirror all_answers_cited.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"citation_quality={result['citation_quality']['all_cited']!r}"
        )

    def test_dry_run_debug_view_all_cited_mirrors_top_level_all_answers_cited(self) -> None:
        """Dry-run result: ``debug_view["all_cited"]`` mirrors top-level ``all_answers_cited``."""
        result = _make_dry_run_result()
        assert result["debug_view"]["all_cited"] == result["all_answers_cited"], (
            "dry_run debug_view[all_cited] must mirror all_answers_cited.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"debug_view={result['debug_view']['all_cited']!r}"
        )

    # ------------------------------------------------------------------
    # Retrieval-skipped early-return path
    # ------------------------------------------------------------------

    def test_retrieval_skipped_top_level_uses_all_answers_cited_not_all_cited(self) -> None:
        """Retrieval-skipped result: canonical top-level key is ``all_answers_cited``."""
        result = _make_retrieval_skipped_result()
        assert "all_answers_cited" in result, (
            "all_answers_cited must be present as a top-level key on the retrieval_skipped path"
        )
        assert "all_cited" not in result, (
            "all_cited must NOT appear as a direct top-level key on the retrieval_skipped path"
        )

    def test_retrieval_skipped_citation_quality_uses_all_cited_alias(self) -> None:
        """Retrieval-skipped result: ``citation_quality`` uses the ``all_cited`` alias."""
        result = _make_retrieval_skipped_result()
        cq = result["citation_quality"]
        assert "all_cited" in cq, (
            "retrieval_skipped citation_quality must expose all_cited (default False)"
        )
        assert "all_answers_cited" not in cq, (
            "retrieval_skipped citation_quality must NOT use the canonical key all_answers_cited"
        )

    def test_retrieval_skipped_all_cited_mirrors_top_level_all_answers_cited(self) -> None:
        """Retrieval-skipped: ``citation_quality["all_cited"]`` mirrors ``all_answers_cited``."""
        result = _make_retrieval_skipped_result()
        assert result["citation_quality"]["all_cited"] == result["all_answers_cited"], (
            "retrieval_skipped citation_quality[all_cited] must mirror all_answers_cited.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"citation_quality={result['citation_quality']['all_cited']!r}"
        )

    def test_retrieval_skipped_debug_view_all_cited_mirrors_top_level_all_answers_cited(self) -> None:
        """Retrieval-skipped: ``debug_view["all_cited"]`` mirrors ``all_answers_cited``."""
        result = _make_retrieval_skipped_result()
        assert result["debug_view"]["all_cited"] == result["all_answers_cited"], (
            "retrieval_skipped debug_view[all_cited] must mirror all_answers_cited.  "
            f"top-level={result['all_answers_cited']!r}, "
            f"debug_view={result['debug_view']['all_cited']!r}"
        )


# ---------------------------------------------------------------------------
# TestPolicyVsRuntimeProjectionParityEarlyReturnDefaults
# ---------------------------------------------------------------------------


class TestPolicyVsRuntimeProjectionParityEarlyReturnDefaults:
    """Verify that policy-covered fields on early-return paths obey projection rules.

    Fields on dry-run and retrieval-skipped paths carry zero or default values
    (``False``, ``0``, empty list, ``"no_answer"``), but the declared projection
    structure — which surface owns the field, which surfaces mirror it, which
    surfaces forbid it — must still hold exactly as declared in the policy.

    These named tests complement the generic parametric tests by explicitly
    documenting and asserting the default values that policy-covered fields must
    carry on each early-return path.
    """

    # ------------------------------------------------------------------
    # Fields forbidden at top_level: evidence_level, warning_count, citation_warnings
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_evidence_level_not_top_level_key_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``evidence_level`` must not appear as a direct top-level key on early-return paths.

        It is a ``citation_quality``-canonical field (§2.9 Inspection-only) forbidden at
        the top level.  The default early-return value (``"no_answer"``) must be accessed
        via ``citation_quality["evidence_level"]`` or ``debug_view["evidence_level"]``.
        """
        result = result_fn()  # type: ignore[call-arg]
        assert "evidence_level" not in result, (
            f"[{path_label}] evidence_level must not be a direct top-level key "
            f"(forbidden_in top_level per policy).  Default value on this path is "
            f"'no_answer' and must be accessed via citation_quality['evidence_level']."
        )
        assert result["citation_quality"]["evidence_level"] == "no_answer", (
            f"[{path_label}] citation_quality.evidence_level default must be 'no_answer'"
        )

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_warning_count_not_top_level_key_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``warning_count`` must not appear as a direct top-level key on early-return paths."""
        result = result_fn()  # type: ignore[call-arg]
        assert "warning_count" not in result, (
            f"[{path_label}] warning_count must not be a direct top-level key "
            f"(forbidden_in top_level per policy).  Default value is 0 and must be "
            f"accessed via citation_quality['warning_count']."
        )
        assert result["citation_quality"]["warning_count"] == 0, (
            f"[{path_label}] citation_quality.warning_count default must be 0"
        )

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_citation_warnings_not_top_level_key_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``citation_warnings`` key must not appear as a direct top-level key on early-return paths."""
        result = result_fn()  # type: ignore[call-arg]
        assert "citation_warnings" not in result, (
            f"[{path_label}] citation_warnings must not be a direct top-level key "
            f"(forbidden_in top_level per policy).  Default is [] and must be "
            f"accessed via citation_quality['citation_warnings']."
        )
        assert result["citation_quality"]["citation_warnings"] == [], (
            f"[{path_label}] citation_quality.citation_warnings default must be []"
        )

    # ------------------------------------------------------------------
    # malformed_diagnostics_count: forbidden in citation_quality
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_malformed_diagnostics_count_not_in_citation_quality_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``malformed_diagnostics_count`` must not appear in ``citation_quality`` on early-return paths.

        It is a telemetry counter (canonical on the ``telemetry`` surface) that is explicitly
        forbidden in the ``citation_quality`` bundle.  On early-return paths its default value
        is 0 and must be read directly from the top-level result.
        """
        result = result_fn()  # type: ignore[call-arg]
        assert "malformed_diagnostics_count" not in result["citation_quality"], (
            f"[{path_label}] malformed_diagnostics_count must not appear in citation_quality "
            f"(forbidden_in citation_quality per policy).  It is a telemetry counter accessed "
            f"directly from the top-level result."
        )
        assert result["malformed_diagnostics_count"] == 0, (
            f"[{path_label}] malformed_diagnostics_count default must be 0"
        )

    # ------------------------------------------------------------------
    # citation_repair_attempted / applied / fallback: forbidden in citation_quality
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_citation_repair_attempted_not_in_citation_quality_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``citation_repair_attempted`` must not appear in ``citation_quality`` on early-return paths."""
        result = result_fn()  # type: ignore[call-arg]
        assert "citation_repair_attempted" not in result["citation_quality"], (
            f"[{path_label}] citation_repair_attempted must not appear in citation_quality "
            f"(forbidden_in citation_quality per policy, §2.6 rule 2)."
        )
        assert result["citation_repair_attempted"] is False, (
            f"[{path_label}] citation_repair_attempted default must be False"
        )

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_citation_repair_applied_not_in_citation_quality_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``citation_repair_applied`` must not appear in ``citation_quality`` on early-return paths."""
        result = result_fn()  # type: ignore[call-arg]
        assert "citation_repair_applied" not in result["citation_quality"], (
            f"[{path_label}] citation_repair_applied must not appear in citation_quality "
            f"(forbidden_in citation_quality per policy)."
        )
        assert result["citation_repair_applied"] is False, (
            f"[{path_label}] citation_repair_applied default must be False"
        )

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_citation_fallback_applied_not_in_citation_quality_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """``citation_fallback_applied`` must not appear in ``citation_quality`` on early-return paths."""
        result = result_fn()  # type: ignore[call-arg]
        assert "citation_fallback_applied" not in result["citation_quality"], (
            f"[{path_label}] citation_fallback_applied must not appear in citation_quality "
            f"(forbidden_in citation_quality per policy)."
        )
        assert result["citation_fallback_applied"] is False, (
            f"[{path_label}] citation_fallback_applied default must be False"
        )

    # ------------------------------------------------------------------
    # debug_view present with correct projection on early-return paths
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_debug_view_mirrors_present_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """All policy-declared ``debug_view`` mirrors must be present on early-return paths.

        The ``debug_view`` surface must carry the same key structure on every result shape,
        even when all values carry defaults.  This ensures inspection tooling works
        consistently regardless of how the function was called.
        """
        result = result_fn()  # type: ignore[call-arg]
        dv = result.get("debug_view")
        assert isinstance(dv, dict), (
            f"[{path_label}] debug_view must be a dict (present and not None)"
        )
        for canonical_key, pol in RETRIEVAL_METADATA_SURFACE_POLICY.items():
            if "debug_view" not in pol.mirrored_in:
                continue
            dv_name = pol.field_name_by_surface.get("debug_view", canonical_key)
            assert dv_name in dv, (
                f"[{path_label}] Policy field {canonical_key!r} must be mirrored in "
                f"debug_view under key {dv_name!r} on the {path_label!r} path, "
                f"but it was absent.  Early-return paths must maintain the same "
                f"debug_view structure as the live path (with zero/default values)."
            )

    @pytest.mark.parametrize(
        "path_label,result_fn",
        [("dry_run", _make_dry_run_result), ("retrieval_skipped", _make_retrieval_skipped_result)],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_citation_quality_mirrors_present_on_early_return_paths(
        self, path_label: str, result_fn: object
    ) -> None:
        """All policy-declared ``citation_quality`` mirrors/canonical fields must be present
        on early-return paths.

        The ``citation_quality`` bundle must carry the same key structure on every result
        shape.  Fields that are canonical on ``citation_quality`` or mirrored there must
        appear on both the live and early-return paths.
        """
        result = result_fn()  # type: ignore[call-arg]
        cq = result.get("citation_quality")
        assert isinstance(cq, dict), (
            f"[{path_label}] citation_quality must be a dict (present and not None)"
        )
        for canonical_key, pol in RETRIEVAL_METADATA_SURFACE_POLICY.items():
            if pol.canonical_surface != "citation_quality" and "citation_quality" not in pol.mirrored_in:
                continue
            cq_name = pol.field_name_by_surface.get("citation_quality", canonical_key)
            assert cq_name in cq, (
                f"[{path_label}] Policy field {canonical_key!r} must be present in "
                f"citation_quality under key {cq_name!r} on the {path_label!r} path, "
                f"but it was absent.  Early-return paths must maintain the same "
                f"citation_quality structure as the live path (with zero/default values)."
            )
