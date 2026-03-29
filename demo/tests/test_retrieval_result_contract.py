"""Result-level contract tests for retrieval answer postprocessing metadata.

These tests assert the exact postprocessing/result semantics surfaced by
``_postprocess_answer()`` and ``run_retrieval_and_qa()`` across the core documented
scenarios.  They are intended to serve as executable contract documentation for those
scenarios so that future refactors cannot silently change surfaced metadata or the
relationships between top-level fields and nested ``citation_quality`` data without a
test failure.

Structure
---------
``TestPostprocessAnswerResultContract``
    Table-driven tests that call ``_postprocess_answer()`` directly and assert the
    full result shape for each scenario:

    - fully cited answer
    - uncited answer repaired (text changed)
    - citation fallback applied (run-scoped mode, no repair)
    - citation fallback applied (all-runs mode, no hits available)
    - empty / whitespace-only answer
    - preexisting warnings combined with citation warnings
    - preexisting warnings alongside a fully-cited answer

``TestPostprocessAnswerInvariants``
    Individual tests that protect named invariants stated in the contract document:

    - ``citation_repair_applied`` is True only when the answer text actually changed.
    - ``citation_repair_strategy`` and ``citation_repair_source_chunk_id`` are ``None``
      when repair was not applied, and non-``None`` when it was.
    - ``raw_answer_all_cited`` may differ from ``all_cited`` after repair.
    - ``raw_answer`` is never modified by postprocessing.
    - Preexisting warnings appear first in ``citation_warnings`` in their original order,
      and the caller's list is never mutated.
    - Fallback display/history answer semantics.
    - ``evidence_level`` is ``"no_answer"`` for empty input, ``"full"`` only when fully
      cited with no warnings, and ``"degraded"`` otherwise.

``TestCitationQualityCoherence``
    Tests that verify ``citation_quality`` (the nested bundle) stays consistent with
    the top-level convenience fields across all scenarios.

``TestRunRetrievalAndQaResultContract``
    Tests that call ``run_retrieval_and_qa()`` through the full live code path (with
    Neo4j driver and RAG mocked) and assert that postprocessing metadata is correctly
    surfaced in the returned result dict — including coherence between top-level keys
    and the ``citation_quality`` bundle.

``TestRunRetrievalAndQaPublicKeyContract``
    Asserts the complete public output contract for ``run_retrieval_and_qa()``:

    - The live postprocessed result contains **exactly** the documented required key set
      (no extra, no missing keys), verified across multiple scenarios.
    - Every required field has the expected runtime type.
    - The nested ``citation_quality`` bundle and ``retrieval_scope`` dicts each carry
      their documented key sets.

``TestRunRetrievalAndQaPostprocessMapping``
    Spy-based tests that verify every entry in :data:`_POSTPROCESS_FIELD_MAP` is mapped
    to the correct public key in the ``run_retrieval_and_qa()`` result dict.  Uses
    :data:`_POSTPROCESS_FIELD_MAP` as the authoritative mapping registry.

``TestRunRetrievalAndQaDocumentedScenarios``
    Table-driven end-to-end tests that drive ``run_retrieval_and_qa()`` through each
    scenario described in §4 of the canonical contract document
    (``docs/architecture/retrieval-citation-result-contract-v0.1.md``) and assert the
    complete set of postprocessing-related public fields, verifying that the runtime
    interface matches the documented contract:

    - §4.1 Full citation — no repair, no fallback
    - §4.2 Degraded citation — fallback applied (run-scoped mode)
    - §4.3 Repair applied — citation fixed, no fallback
    - §4.5 No answer generated
    - §4.6 Empty chunk text — degraded evidence with retrieval-time warning
    - §4.7 Repair attempted but not applied — no candidate token found

``TestRunRetrievalAndQaWarningsContract``
    Tests that protect the ``warnings`` / ``citation_warnings`` propagation invariants
    across the public result surface:

    - Every entry in ``citation_quality["citation_warnings"]`` is also present in the
      top-level ``warnings`` list.
    - Empty-chunk-text warnings appear in **both** ``warnings`` and
      ``citation_quality["citation_warnings"]``.
    - Operational warnings that are not citation-quality issues appear only in the
      top-level ``warnings`` list, not in ``citation_quality["citation_warnings"]``.

``TestRunRetrievalAndQaEarlyReturnContract``
    Contract tests for the two early-return (non-live) paths documented in §5 of the
    canonical contract document:

    - ``dry_run=True``: status is ``"dry_run"``; retrieval/LLM never run; the key set
      is the shared base plus ``status``/``retrievers``/``qa`` and excludes
      ``hits``, ``retrieval_results``, ``warnings``, and ``retrieval_skipped``.
    - ``question=None`` in live mode (retrieval skipped): status is ``"live"``,
      ``retrieval_skipped=True``; the key set extends the dry-run set with ``hits``,
      ``retrieval_results``, ``warnings``, and ``retrieval_skipped``.
    - Default field values (answer, citation_quality, etc.) in both paths.
    - Caller distinction invariant: ``status="dry_run"`` vs ``retrieval_skipped=True``.
    - Skip warning appears in ``warnings`` but not in ``citation_quality["citation_warnings"]``.

``TestMixedEarlyReturnSentinelEdge``
    Contract tests for mixed early-return inputs and sentinel-edge behavior.  The
    precedence rules asserted here are backed by the centralized
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` policy in
    ``demo/contracts/retrieval_early_return_policy.py``.

``TestEarlyReturnPrecedencePolicy``
    Direct unit tests for the centralized
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` policy itself.  Verifies that:

    - The policy contains exactly two rules with unique priorities 1 and 2.
    - The dry-run rule (priority 1) uses ``outcome_status="dry_run"`` and lists
      ``"retrieval_skipped"`` in its ``wins_over`` set.
    - The retrieval-skipped rule (priority 2) uses ``outcome_status="live"`` and
      has an empty ``wins_over`` set.
    - The ``absent_keys`` / ``exclusive_keys`` fields on each rule are consistent
      with the :data:`_DRY_RUN_RESULT_REQUIRED_KEYS` and
      :data:`_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS` constants — i.e. the policy
      can be used to *derive* those constants from :data:`_LIVE_RESULT_REQUIRED_KEYS`.
    - All ``wins_over`` references resolve to known rule names.

``TestEarlyReturnRulePayloadCorrespondence``
    Policy-backed correspondence tests that verify the runtime payload returned by
    ``run_retrieval_and_qa()`` matches the structured metadata declared in each
    :class:`~demo.contracts.EarlyReturnRule` entry in
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE`.  For each current rule this
    layer checks:

    - ``result["status"]`` equals ``rule.outcome_status``.
    - Every key in ``rule.absent_keys`` is absent from the returned payload.
    - Every key in ``rule.exclusive_keys`` is present in the returned payload.
    - ``resolve_early_return_rule(...)`` returns the matching rule for the
      triggering inputs (resolver ↔ runtime alignment).
    - Exclusive keys of one rule do not leak into the other rule's payload.
    - Retrieval-mode modifiers (``all_runs``, ``expand_graph``, ``cluster_aware``)
      alongside ``dry_run=True`` do not inject any of ``dry_run.absent_keys``.

``TestProjectPostprocessToPublic``
    Direct unit tests for the :func:`_project_postprocess_to_public` adapter that
    maps an :class:`_AnswerPostprocessResult` to the public result surface.  Tests
    the adapter in isolation (without going through ``run_retrieval_and_qa``):

    - The returned key set exactly matches ``_PostprocessPublicFields``.
    - ``display_answer`` is renamed to ``answer``.
    - ``all_cited`` is renamed to ``all_answers_cited``.
    - All pass-through fields are forwarded unchanged.
    - The mapping holds across all postprocessing scenarios.
    - ``citation_quality`` is the same dict object (no copy).

``TestMetadataTaxonomyBoundaries``
    Tests that enforce the four-surface metadata taxonomy defined in §2.6 of the
    canonical contract document.  Covers representative, ambiguous, and combined
    examples so future contributors cannot accidentally migrate a field to the
    wrong surface without a test failure:

    - Telemetry (`malformed_diagnostics_count > 0`) does **not** add entries to
      ``warnings`` or ``citation_quality["citation_warnings"]`` (§3.10).
    - ``debug_view`` keys are isolated inside their nested dict and do not appear
      at the top level of the result (§3.11) — tested for the live path,
      and parametrized across both early-return paths (dry_run and retrieval_skipped).
    - Combined scenario: empty-chunk warning + uncited-answer warning both appear
      in ``warnings`` **and** ``citation_quality["citation_warnings"]`` (ambiguous
      multi-surface case — both warnings are citation-quality issues per rule 1).
    - ``debug_view`` mirrors the same postprocessing state as the public surface
      (no additional hidden state; it is a convenience view, not extra data) —
      tested for a single scenario and parametrized across all six documented live scenarios.
    - ``all_answers_cited`` is the public top-level alias; ``all_cited`` is the
      inspection-only name used inside ``debug_view`` (and ``citation_quality``) —
      the name distinction and non-leakage invariant are explicitly tested (§2.9 table).
    - **Mixed-warning superset contract** — ``test_mixed_citation_and_operational_warnings_superset_contract``:
      a result containing **both** a citation-quality warning (uncited-answer) and an
      operational warning (missing optional citation fields) proves the full superset
      invariant (§3.7 / ``propagates_to``): citation warnings propagate upward to
      top-level ``warnings``; operational warnings remain top-level-only;
      ``warning_count`` tracks citation-quality warnings, not the total
      ``len(result["warnings"])``; ``debug_view["citation_warnings"]`` mirrors the
      citation-quality surface, not the operational top-level entries.
    - Operational warnings (non-citation-quality) appear only in ``warnings``,
      not in ``citation_quality["citation_warnings"]`` (skip warning example).

``TestProjectionPolicySurfaceOwnership``
    Projection-policy tests that verify each signal is owned by exactly the correct
    surface(s) and cannot silently migrate to a wrong destination.  Organized around
    the four taxonomy decision rules from §2.6:

    - Rule 1 (citation-quality warning strings) — ``test_citation_quality_warning_strings_dual_surfaced``:
      for every documented citation-quality warning type the warning string must appear
      on **both** ``citation_quality["citation_warnings"]`` and top-level ``warnings``.
    - Rule 2 (citation-quality fields forbidden as top-level keys) — ``test_citation_quality_fields_forbidden_as_top_level_keys``:
      citation-quality values (``evidence_level``, ``warning_count``) and the rule-1
      warning-string list (``citation_warnings``) must not appear as direct top-level keys;
      they belong in the ``citation_quality`` bundle.
    - Rule 3 (telemetry counters) — ``test_telemetry_counter_not_in_citation_quality_bundle``:
      ``malformed_diagnostics_count`` must not appear inside the ``citation_quality`` bundle.
    - Rule 4 (operational warnings) — ``test_operational_warnings_not_in_citation_warnings``:
      operational (non-citation-quality) warnings must not propagate to
      ``citation_quality["citation_warnings"]``.
    - **Exact key-set invariants** — ``test_debug_view_has_exactly_documented_key_set`` and
      ``test_citation_quality_bundle_has_exactly_documented_key_set`` (both parametrized
      across all six live scenarios) ensure ``debug_view`` carries no undocumented hidden
      state and ``citation_quality`` carries no extra fields beyond its documented bundle.
    - **Ambiguous case** — ``test_ambiguous_evidence_level_surface_classification`` explicitly
      names the ``evidence_level`` ambiguity (§2.6 ambiguous-examples table) and verifies
      it is correctly classified as a ``citation_quality``-bundle metric (not a top-level key).
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from demo.contracts import RETRIEVAL_METADATA_SURFACE_POLICY
from demo.contracts import (
    EARLY_RETURN_PRECEDENCE,
    EARLY_RETURN_RULE_BY_NAME,
    resolve_early_return_rule,
)
from demo.stages.retrieval_and_qa import (
    _CITATION_FALLBACK_PREFIX,
    _POSTPROCESS_FIELD_MAP,
    _PostprocessPublicFields,
    _postprocess_answer,
    _project_postprocess_to_public,
    run_retrieval_and_qa,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

#: Minimal config that satisfies all live-retrieval field validations without
#: making real Neo4j or OpenAI connections.
_LIVE_CONFIG = types.SimpleNamespace(
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password",
    neo4j_database=None,
    openai_model="gpt-4o-mini",
    dry_run=False,
)

#: Minimal config for dry-run early-return tests.  Neo4j credentials are
#: intentionally absent to prove the dry-run path never touches them.
_DRY_RUN_CONFIG = types.SimpleNamespace(
    openai_model="gpt-4o-mini",
    dry_run=True,
)

#: A valid synthetic citation token shared across tests.
_TOKEN = (
    "[CITATION|chunk_id=c1|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=0|page=1|start_char=0|end_char=50]"
)

#: A second citation token from a different chunk, for multi-hit tests.
_TOKEN_2 = (
    "[CITATION|chunk_id=c2|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=1|page=2|start_char=51|end_char=100]"
)

#: Single retrieval hit carrying _TOKEN; standard fixture for most tests.
_HIT: dict[str, object] = {"metadata": {"citation_token": _TOKEN, "chunk_id": "c1"}}

#: A fully cited single-sentence answer using _TOKEN.
_CITED_ANSWER = f"This claim is well-supported. {_TOKEN}"

#: A single uncited sentence with no citation token.
_UNCITED_ANSWER = "An uncited claim that needs a citation."

#: The repaired form of _UNCITED_ANSWER after the "append_first_retrieved_token" strategy.
_REPAIRED_UNCITED_ANSWER = f"{_UNCITED_ANSWER} {_TOKEN}"

#: The fallback display answer for an uncited _UNCITED_ANSWER (no repair possible).
_FALLBACK_DISPLAY_UNCITED = f"{_CITATION_FALLBACK_PREFIX}: {_UNCITED_ANSWER}"

#: The standard warning message appended when the final answer is not fully cited.
_UNCITED_WARNING = "Not all answer sentences or bullets end with a citation token."

#: The exact warning message emitted when retrieval is skipped (no question provided).
_SKIP_WARNING = "No question provided; skipping vector retrieval."

#: Exact set of all top-level keys in an ``_AnswerPostprocessResult``.
_POSTPROCESS_RESULT_KEYS: frozenset[str] = frozenset({
    "raw_answer",
    "raw_answer_all_cited",
    "repaired_answer",
    "citation_repair_attempted",
    "citation_repair_applied",
    "citation_repair_strategy",
    "citation_repair_source_chunk_id",
    "display_answer",
    "history_answer",
    "citation_fallback_applied",
    "all_cited",
    "evidence_level",
    "citation_warnings",
    "warning_count",
    "citation_quality",
})


def _policy_surface_key_set(surface: str) -> frozenset[str]:
    """Derive the expected field-name set for *surface* from the shared policy.

    For each field in :data:`RETRIEVAL_METADATA_SURFACE_POLICY` that is either
    canonical on *surface* or mirrored there, returns the name under which the
    field appears on that surface (using ``field_name_by_surface`` when the name
    differs from the canonical key).
    """
    return frozenset(
        pol.field_name_by_surface.get(surface, canonical_key)
        for canonical_key, pol in RETRIEVAL_METADATA_SURFACE_POLICY.items()
        if pol.canonical_surface == surface or surface in pol.mirrored_in
    )


#: Exact set of all keys inside the nested ``_CitationQualityBundle``.
#: Derived from :data:`RETRIEVAL_METADATA_SURFACE_POLICY` so this constant
#: stays automatically in sync when the policy changes.
_CITATION_QUALITY_BUNDLE_KEYS: frozenset[str] = _policy_surface_key_set("citation_quality")

#: Exact set of required keys in the ``debug_view`` nested dict returned by
#: ``run_retrieval_and_qa()``.  Derived from :data:`RETRIEVAL_METADATA_SURFACE_POLICY`
#: so the constant stays automatically in sync with the shared policy.
_DEBUG_VIEW_REQUIRED_KEYS: frozenset[str] = _policy_surface_key_set("debug_view")

#: A realistic retrieval-item metadata dict for live-path (``run_retrieval_and_qa``) tests.
#: Includes ``citation_object`` with all optional fields (page, start_char, end_char) populated
#: so no "missing optional citation fields" warnings are emitted by the live code path.
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


#: Exact set of required top-level keys in a live postprocessed result from
#: ``run_retrieval_and_qa()``.  Any field addition, rename, or removal will
#: cause ``TestRunRetrievalAndQaPublicKeyContract`` tests to fail.
_LIVE_RESULT_REQUIRED_KEYS: frozenset[str] = frozenset({
    # --- identity / config ---
    "run_id",
    "source_uri",
    "top_k",
    "retriever_type",
    "retriever_index_name",
    "question",
    "qa_model",
    "qa_prompt_version",
    # --- retrieval configuration ---
    "expand_graph",
    "cluster_aware",
    "retrieval_scope",
    "retrieval_query_contract",
    "interactive_mode",
    "message_history_enabled",
    # --- retrieval runtime ---
    "status",
    "retrievers",
    "qa",
    "hits",
    "retrieval_results",
    "retrieval_path_summary",
    "malformed_diagnostics_count",
    # --- citation examples ---
    "citation_token_example",
    "citation_object_example",
    "citation_example",
    # --- answer / postprocessing (mapped from _postprocess_answer result) ---
    "answer",
    "raw_answer",
    "all_answers_cited",
    "raw_answer_all_cited",
    "citation_fallback_applied",
    "citation_repair_attempted",
    "citation_repair_applied",
    "citation_repair_strategy",
    "citation_repair_source_chunk_id",
    "citation_quality",
    # --- typed inspection/debug view (shared across interactive and single-shot paths) ---
    "debug_view",
    # --- warnings ---
    "warnings",
})

#: Required keys in the ``retrieval_scope`` nested dict.
_RETRIEVAL_SCOPE_REQUIRED_KEYS: frozenset[str] = frozenset({
    "run_id",
    "source_uri",
    "scope_widened",
    "all_runs",
})

#: Exact set of required top-level keys for the ``dry_run`` early-return path.
#: The dry-run result omits fields that only exist when retrieval actually ran
#: (``hits``, ``retrieval_results``, ``warnings``, ``retrieval_skipped``).
#: All other base fields plus ``status``, ``retrievers``, and ``qa`` are present.
#: See §5.1 of the canonical contract document.
_DRY_RUN_RESULT_REQUIRED_KEYS: frozenset[str] = (
    _LIVE_RESULT_REQUIRED_KEYS
    - {"hits", "retrieval_results", "warnings", "retrieval_skipped"}
)

#: Exact set of required top-level keys when retrieval is skipped because no
#: question was provided (``question=None`` in live mode).
#: Extends the live key set with ``retrieval_skipped`` to signal the skip.
#: See §5.2 of the canonical contract document.
_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS: frozenset[str] = (
    _LIVE_RESULT_REQUIRED_KEYS | {"retrieval_skipped"}
)

#: Metadata for a hit that triggers an empty-chunk-text citation warning.
#: All optional citation fields are present so no "missing optional fields"
#: warning is emitted alongside the empty-chunk warning.  Represents §4.6.
_EMPTY_CHUNK_METADATA: dict[str, object] = {
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
    "empty_chunk_text": True,
}

#: Metadata for a hit with no citation token — repair is attempted (preconditions
#: met) but cannot find a token to apply.  Represents §4.7.
_HIT_METADATA_NO_TOKEN: dict[str, object] = {"chunk_id": "c-no-token"}

#: Metadata for a hit with a malformed ``retrieval_path_diagnostics`` payload.
#: The diagnostics value is a plain string instead of a dict, which triggers
#: ``malformed_diagnostics_count = 1`` in the live path.  All citation fields are
#: fully populated so no citation warnings are emitted alongside the telemetry
#: counter — keeping warning counts deterministic for taxonomy boundary tests.
_MALFORMED_DIAGNOSTICS_METADATA: dict[str, object] = {
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
    "retrieval_path_diagnostics": "not-a-dict",  # malformed: root must be a dict
}

#: Metadata for a hit with missing optional citation fields (``page``, ``start_char``,
#: ``end_char`` absent from ``citation_object``).  The live code path emits an
#: **operational** informational warning for each chunk with absent optional fields
#: and adds it to the top-level ``warnings`` list **only** — it is intentionally
#: NOT propagated to ``citation_quality["citation_warnings"]`` (§2.6 rule 4).
#: Used in the mixed-warning superset-contract test to produce an operational warning
#: alongside a citation-quality warning.
_MISSING_OPTIONAL_FIELDS_METADATA: dict[str, object] = {
    "citation_token": _TOKEN,
    "chunk_id": "c2",
    "citation_object": {
        "chunk_id": "c2",
        "run_id": "r1",
        "source_uri": "file:///doc.pdf",
        "chunk_index": 0,
        # page, start_char, end_char intentionally absent → operational warning
    },
}

#: Expected operational warning text produced for ``_MISSING_OPTIONAL_FIELDS_METADATA``.
#: Matches the format emitted by the live retrieval loop for chunks whose
#: ``citation_object`` is missing one or more optional fields.
_MISSING_OPTIONAL_FIELDS_WARNING: str = (
    "Chunk 'c2' missing optional citation fields: page, start_char, end_char"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rag_result(answer: str, items_metadata: list[dict[str, object]]) -> MagicMock:
    """Build a mock RAG search result with the given answer text and retrieval items."""
    mock_items = [
        MagicMock(content=f"chunk_content_{i}", metadata=meta)
        for i, meta in enumerate(items_metadata)
    ]
    mock_result = MagicMock()
    mock_result.answer = answer
    mock_result.retriever_result.items = mock_items
    return mock_result


def _run_with_mocked_retrieval(
    answer: str,
    items_metadata: list[dict[str, object]],
    *,
    all_runs: bool = True,
    question: str = "What is the claim?",
    run_id: str | None = None,
) -> dict[str, object]:
    """Drive ``run_retrieval_and_qa`` with mocked Neo4j / RAG, returning the result dict.

    Parameters
    ----------
    answer:
        The answer text the mocked RAG will return.
    items_metadata:
        List of metadata dicts, one per mock retrieval item.
    all_runs:
        Whether to invoke the all-runs code path.
    question:
        The question to pass to the function.
    run_id:
        Required when ``all_runs=False``.
    """
    if not all_runs and run_id is None:
        raise ValueError("run_id is required when all_runs is False")
    mock_rag = MagicMock()
    mock_rag.search.return_value = _make_rag_result(answer, items_metadata)

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
        patch("neo4j.GraphDatabase.driver"),
        patch("demo.stages.retrieval_and_qa._build_retriever_and_rag") as mock_build,
    ):
        mock_build.return_value = (MagicMock(), mock_rag)
        return run_retrieval_and_qa(
            _LIVE_CONFIG,
            all_runs=all_runs,
            run_id=run_id,
            question=question,
        )


def _assert_debug_view_mirrors_policy(
    result: dict[str, object], scenario: str
) -> None:
    """Assert every policy-defined ``debug_view`` mirror holds for *result*.

    Iterates :data:`RETRIEVAL_METADATA_SURFACE_POLICY` and, for each field
    mirrored in ``debug_view``, verifies the stored value equals the value on
    the canonical source surface.  Uses ``field_name_by_surface`` to resolve
    name differences (e.g. ``all_answers_cited`` at the top level is ``all_cited``
    in ``debug_view``).

    This helper is the policy-driven equivalent of enumerating mirror assertions
    by hand — adding a field to the policy automatically extends the check here.
    """
    dv = result["debug_view"]
    cq = result["citation_quality"]
    for canonical_key, pol in RETRIEVAL_METADATA_SURFACE_POLICY.items():
        if "debug_view" not in pol.mirrored_in:
            continue
        dv_name = pol.field_name_by_surface.get("debug_view", canonical_key)
        if pol.canonical_surface in ("top_level", "telemetry"):
            # Both top_level and telemetry fields are direct top-level keys in the
            # result dict under the canonical key name (no top-level rename in policy).
            expected = result[canonical_key]
            source_desc = f"result[{canonical_key!r}]"
        elif pol.canonical_surface == "citation_quality":
            cq_name = pol.field_name_by_surface.get("citation_quality", canonical_key)
            expected = cq[cq_name]
            source_desc = f"citation_quality[{cq_name!r}]"
        else:
            raise AssertionError(
                f"Policy field {canonical_key!r} is mirrored in debug_view but its "
                f"canonical_surface {pol.canonical_surface!r} is not handled by "
                f"_assert_debug_view_mirrors_policy.  Update the helper to support "
                f"this new canonical surface."
            )
        assert dv[dv_name] == expected, (
            f"[{scenario}] debug_view[{dv_name!r}] (policy field: {canonical_key!r}) "
            f"must mirror {source_desc}: expected {expected!r}, got {dv[dv_name]!r}"
        )


# ---------------------------------------------------------------------------
# TestPostprocessAnswerResultContract
# ---------------------------------------------------------------------------

# Parametrize IDs: every scenario string must be a valid pytest ID.
_POSTPROCESS_SCENARIOS: list[tuple[str, str, list, bool, list | None, dict]] = [
    # --- fully cited answer; repair and fallback both skipped ---
    (
        "fully_cited",
        _CITED_ANSWER,
        [_HIT],
        True,
        None,
        {
            "raw_answer": _CITED_ANSWER,
            "raw_answer_all_cited": True,
            "repaired_answer": _CITED_ANSWER,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": _CITED_ANSWER,
            "history_answer": _CITED_ANSWER,
            "citation_fallback_applied": False,
            "all_cited": True,
            "evidence_level": "full",
            "citation_warnings": [],
            "warning_count": 0,
        },
    ),
    # --- uncited answer repaired in all-runs mode; text changed ---
    (
        "repair_applied_text_changed",
        _UNCITED_ANSWER,
        [_HIT],
        True,
        None,
        {
            "raw_answer": _UNCITED_ANSWER,
            "raw_answer_all_cited": False,
            "repaired_answer": _REPAIRED_UNCITED_ANSWER,
            "citation_repair_attempted": True,
            "citation_repair_applied": True,
            "citation_repair_strategy": "append_first_retrieved_token",
            "citation_repair_source_chunk_id": "c1",
            "display_answer": _REPAIRED_UNCITED_ANSWER,
            "history_answer": _REPAIRED_UNCITED_ANSWER,
            "citation_fallback_applied": False,
            "all_cited": True,
            "evidence_level": "full",
            "citation_warnings": [],
            "warning_count": 0,
        },
    ),
    # --- repair not applicable: run-scoped mode → fallback applied ---
    (
        "fallback_run_scoped_no_repair",
        _UNCITED_ANSWER,
        [_HIT],
        False,
        None,
        {
            "raw_answer": _UNCITED_ANSWER,
            "raw_answer_all_cited": False,
            "repaired_answer": _UNCITED_ANSWER,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": _FALLBACK_DISPLAY_UNCITED,
            "history_answer": _CITATION_FALLBACK_PREFIX,
            "citation_fallback_applied": True,
            "all_cited": False,
            "evidence_level": "degraded",
            "citation_warnings": [_UNCITED_WARNING],
            "warning_count": 1,
        },
    ),
    # --- repair not applicable: all-runs mode but no hits → fallback applied ---
    (
        "fallback_all_runs_no_hits",
        _UNCITED_ANSWER,
        [],
        True,
        None,
        {
            "raw_answer": _UNCITED_ANSWER,
            "raw_answer_all_cited": False,
            "repaired_answer": _UNCITED_ANSWER,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": _FALLBACK_DISPLAY_UNCITED,
            "history_answer": _CITATION_FALLBACK_PREFIX,
            "citation_fallback_applied": True,
            "all_cited": False,
            "evidence_level": "degraded",
            "citation_warnings": [_UNCITED_WARNING],
            "warning_count": 1,
        },
    ),
    # --- empty answer: no repair, no fallback, evidence_level=no_answer ---
    (
        "empty_answer",
        "",
        [],
        True,
        None,
        {
            "raw_answer": "",
            "raw_answer_all_cited": False,
            "repaired_answer": "",
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": "",
            "history_answer": "",
            "citation_fallback_applied": False,
            "all_cited": False,
            "evidence_level": "no_answer",
            "citation_warnings": [],
            "warning_count": 0,
        },
    ),
    # --- whitespace-only answer treated the same as empty ---
    (
        "whitespace_answer",
        "   \n  ",
        [],
        True,
        None,
        {
            "raw_answer": "   \n  ",
            "raw_answer_all_cited": False,
            "repaired_answer": "   \n  ",
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": "",
            "history_answer": "",
            "citation_fallback_applied": False,
            "all_cited": False,
            "evidence_level": "no_answer",
            "citation_warnings": [],
            "warning_count": 0,
        },
    ),
    # --- preexisting warning + uncited answer warning combined ---
    (
        "preexisting_plus_uncited_warning",
        _UNCITED_ANSWER,
        [],
        False,
        ["chunk 'c0' has empty text"],
        {
            "raw_answer": _UNCITED_ANSWER,
            "raw_answer_all_cited": False,
            "repaired_answer": _UNCITED_ANSWER,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": _FALLBACK_DISPLAY_UNCITED,
            "history_answer": _CITATION_FALLBACK_PREFIX,
            "citation_fallback_applied": True,
            "all_cited": False,
            "evidence_level": "degraded",
            "citation_warnings": ["chunk 'c0' has empty text", _UNCITED_WARNING],
            "warning_count": 2,
        },
    ),
    # --- preexisting warnings + fully cited answer: evidence level is degraded ---
    (
        "preexisting_warning_fully_cited_degrades",
        _CITED_ANSWER,
        [_HIT],
        True,
        ["pre-existing warning from retrieval loop"],
        {
            "raw_answer": _CITED_ANSWER,
            "raw_answer_all_cited": True,
            "repaired_answer": _CITED_ANSWER,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "display_answer": _CITED_ANSWER,
            "history_answer": _CITED_ANSWER,
            "citation_fallback_applied": False,
            "all_cited": True,
            # Preexisting citation warning degrades evidence_level even when fully cited.
            "evidence_level": "degraded",
            "citation_warnings": ["pre-existing warning from retrieval loop"],
            "warning_count": 1,
        },
    ),
]


class TestPostprocessAnswerResultContract:
    """Table-driven contract tests for ``_postprocess_answer()`` result shape.

    Each parametrized case exercises a distinct scenario and asserts every
    postprocessing-related field in the returned dict.  This serves as executable
    documentation of the full postprocessing contract so reviewers can read the
    table to understand what the function guarantees for each input pattern.
    """

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs,existing_warnings,expected",
        _POSTPROCESS_SCENARIOS,
        ids=[row[0] for row in _POSTPROCESS_SCENARIOS],
    )
    def test_result_fields(
        self,
        scenario: str,
        answer: str,
        hits: list,
        all_runs: bool,
        existing_warnings: list | None,
        expected: dict,
    ) -> None:
        """Every field listed in *expected* must match the returned result exactly,
        and the returned dict must contain exactly the documented postprocessing key set."""
        pp = _postprocess_answer(
            answer, hits, all_runs=all_runs, existing_citation_warnings=existing_warnings
        )
        assert set(pp.keys()) == _POSTPROCESS_RESULT_KEYS, (
            f"[{scenario}] Result key set mismatch: "
            f"extra={set(pp.keys()) - _POSTPROCESS_RESULT_KEYS!r}, "
            f"missing={_POSTPROCESS_RESULT_KEYS - set(pp.keys())!r}"
        )
        for key, value in expected.items():
            assert pp[key] == value, (
                f"[{scenario}] Field {key!r}: expected {value!r}, got {pp[key]!r}"
            )

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs,existing_warnings,expected",
        _POSTPROCESS_SCENARIOS,
        ids=[row[0] for row in _POSTPROCESS_SCENARIOS],
    )
    def test_citation_quality_bundle_mirrors_top_level(
        self,
        scenario: str,
        answer: str,
        hits: list,
        all_runs: bool,
        existing_warnings: list | None,
        expected: dict,  # noqa: ARG002  (consumed by parametrize; bundle key-set checked below)
    ) -> None:
        """``citation_quality`` must mirror each corresponding top-level field, and its
        key set must match the documented ``_CitationQualityBundle`` contract exactly."""
        pp = _postprocess_answer(
            answer, hits, all_runs=all_runs, existing_citation_warnings=existing_warnings
        )
        cq = pp["citation_quality"]

        assert set(cq.keys()) == _CITATION_QUALITY_BUNDLE_KEYS, (
            f"[{scenario}] citation_quality key set mismatch: "
            f"extra={set(cq.keys()) - _CITATION_QUALITY_BUNDLE_KEYS!r}, "
            f"missing={_CITATION_QUALITY_BUNDLE_KEYS - set(cq.keys())!r}"
        )
        assert cq["all_cited"] == pp["all_cited"], (
            f"[{scenario}] citation_quality.all_cited diverged from top-level all_cited"
        )
        assert cq["raw_answer_all_cited"] == pp["raw_answer_all_cited"], (
            f"[{scenario}] citation_quality.raw_answer_all_cited diverged"
        )
        assert cq["evidence_level"] == pp["evidence_level"], (
            f"[{scenario}] citation_quality.evidence_level diverged"
        )
        assert cq["warning_count"] == pp["warning_count"], (
            f"[{scenario}] citation_quality.warning_count diverged"
        )
        assert cq["citation_warnings"] == pp["citation_warnings"], (
            f"[{scenario}] citation_quality.citation_warnings diverged"
        )
        assert cq["warning_count"] == len(cq["citation_warnings"]), (
            f"[{scenario}] citation_quality.warning_count != len(citation_warnings)"
        )


# ---------------------------------------------------------------------------
# TestPostprocessAnswerInvariants
# ---------------------------------------------------------------------------


class TestPostprocessAnswerInvariants:
    """Named invariants from the citation result contract, each tested individually."""

    def test_repair_applied_true_iff_answer_text_changed(self) -> None:
        """``citation_repair_applied=True`` iff ``repaired_answer != raw_answer``."""
        pp_repaired = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp_repaired["citation_repair_applied"] is True
        assert pp_repaired["repaired_answer"] != pp_repaired["raw_answer"], (
            "citation_repair_applied=True must mean the answer text was modified"
        )

        pp_no_repair = _postprocess_answer(_CITED_ANSWER, [_HIT], all_runs=True)
        assert pp_no_repair["citation_repair_applied"] is False
        assert pp_no_repair["repaired_answer"] == pp_no_repair["raw_answer"], (
            "citation_repair_applied=False must mean repaired_answer equals raw_answer"
        )

    def test_repair_strategy_and_chunk_id_only_when_repair_applied(self) -> None:
        """``citation_repair_strategy`` is ``None`` when repair was not applied, and
        non-``None`` when it was.  ``citation_repair_source_chunk_id`` follows the same
        rule for ``strategy``, but may also be ``None`` when repair is applied and the
        winning hit has no ``chunk_id`` to propagate."""
        pp_no_repair = _postprocess_answer(_CITED_ANSWER, [_HIT], all_runs=True)
        assert pp_no_repair["citation_repair_strategy"] is None
        assert pp_no_repair["citation_repair_source_chunk_id"] is None

        pp_repair = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp_repair["citation_repair_strategy"] is not None
        # source_chunk_id is present here because _HIT has a non-empty chunk_id.
        assert pp_repair["citation_repair_source_chunk_id"] is not None

        # When repair is applied but the winning hit has no chunk_id, source_chunk_id
        # is None even though citation_repair_applied is True.
        hit_no_chunk = {
            "metadata": {
                "citation_token": _TOKEN,
                "chunk_id": "",
            }
        }
        pp_repair_no_chunk = _postprocess_answer(_UNCITED_ANSWER, [hit_no_chunk], all_runs=True)
        assert pp_repair_no_chunk["citation_repair_applied"] is True
        assert pp_repair_no_chunk["citation_repair_strategy"] is not None
        assert pp_repair_no_chunk["citation_repair_source_chunk_id"] is None

    def test_repair_skipped_when_raw_answer_already_all_cited(self) -> None:
        """When the raw answer is already fully cited, repair is skipped, but
        ``citation_repair_applied`` remains ``False`` and ``raw_answer_all_cited`` is ``True``."""
        # Answer is already fully cited; repair logic short-circuits and is not invoked.
        pp = _postprocess_answer(_CITED_ANSWER, [_HIT], all_runs=True)
        assert pp["citation_repair_applied"] is False
        assert pp["raw_answer_all_cited"] is True

    def test_raw_answer_all_cited_may_differ_from_final_all_cited(self) -> None:
        """``raw_answer_all_cited`` may be ``False`` while ``all_cited`` is ``True``
        when repair successfully completes citation coverage."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp["citation_repair_applied"] is True
        assert pp["raw_answer_all_cited"] is False
        assert pp["all_cited"] is True, (
            "all_cited should reflect the final (post-repair) state"
        )

    def test_raw_answer_is_never_modified(self) -> None:
        """``raw_answer`` always equals the original input text, regardless of repair."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp["raw_answer"] == _UNCITED_ANSWER

    def test_preexisting_warnings_appear_first_in_order(self) -> None:
        """Preexisting warnings occupy the first positions in ``citation_warnings``
        in their original order."""
        pre = ["warning-alpha", "warning-beta"]
        pp = _postprocess_answer(
            _UNCITED_ANSWER, [], all_runs=False, existing_citation_warnings=pre
        )
        assert pp["citation_warnings"][:2] == pre, (
            "Preexisting warnings must appear first, in their original order"
        )

    def test_caller_list_not_mutated(self) -> None:
        """``_postprocess_answer`` must not mutate the caller's
        ``existing_citation_warnings`` list."""
        pre: list[str] = ["existing-warning"]
        _postprocess_answer(
            _UNCITED_ANSWER, [], all_runs=False, existing_citation_warnings=pre
        )
        assert pre == ["existing-warning"], "Caller's list must not be mutated"

    def test_fallback_display_answer_starts_with_prefix(self) -> None:
        """When fallback is applied, ``display_answer`` starts with
        ``_CITATION_FALLBACK_PREFIX``."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [], all_runs=False)
        assert pp["citation_fallback_applied"] is True
        assert pp["display_answer"].startswith(_CITATION_FALLBACK_PREFIX)

    def test_fallback_history_answer_is_bare_prefix(self) -> None:
        """When fallback is applied, ``history_answer`` is exactly the bare prefix
        (no uncited content leaked into history)."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [], all_runs=False)
        assert pp["history_answer"] == _CITATION_FALLBACK_PREFIX
        assert _UNCITED_ANSWER not in pp["history_answer"]

    def test_no_fallback_when_repair_makes_answer_fully_cited(self) -> None:
        """When repair makes the answer fully cited, fallback must not be applied."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp["citation_repair_applied"] is True
        assert pp["citation_fallback_applied"] is False

    def test_evidence_level_no_answer_for_empty_and_whitespace(self) -> None:
        """``evidence_level`` is ``'no_answer'`` for empty or whitespace-only text."""
        for empty in ["", " ", "  \n\t  "]:
            pp = _postprocess_answer(empty, [], all_runs=True)
            assert pp["evidence_level"] == "no_answer", (
                f"Expected no_answer for {empty!r}, got {pp['evidence_level']!r}"
            )
            assert pp["warning_count"] == 0

    def test_evidence_level_full_requires_fully_cited_and_no_warnings(self) -> None:
        """``evidence_level='full'`` only when fully cited AND no citation warnings."""
        pp = _postprocess_answer(_CITED_ANSWER, [_HIT], all_runs=True)
        assert pp["evidence_level"] == "full"
        assert pp["all_cited"] is True
        assert pp["warning_count"] == 0

    def test_evidence_level_degraded_when_uncited(self) -> None:
        """``evidence_level='degraded'`` when the final answer is not fully cited."""
        pp = _postprocess_answer(_UNCITED_ANSWER, [], all_runs=False)
        assert pp["evidence_level"] == "degraded"
        assert pp["all_cited"] is False

    def test_evidence_level_degraded_when_preexisting_warning_even_if_fully_cited(self) -> None:
        """A preexisting citation warning degrades ``evidence_level`` even when
        the answer is fully cited, because the warning reflects a data quality issue."""
        pp = _postprocess_answer(
            _CITED_ANSWER,
            [_HIT],
            all_runs=True,
            existing_citation_warnings=["pre-existing quality warning"],
        )
        assert pp["all_cited"] is True
        assert pp["evidence_level"] == "degraded", (
            "Preexisting citation warning must degrade evidence_level even when fully cited"
        )

    def test_repair_source_chunk_id_matches_first_hit(self) -> None:
        """When repair is applied, ``citation_repair_source_chunk_id`` is the
        ``chunk_id`` of the first hit whose token was used."""
        hit_a = {"metadata": {"citation_token": _TOKEN, "chunk_id": "first-chunk"}}
        hit_b = {"metadata": {"citation_token": _TOKEN_2, "chunk_id": "second-chunk"}}
        pp = _postprocess_answer(_UNCITED_ANSWER, [hit_a, hit_b], all_runs=True)
        assert pp["citation_repair_applied"] is True
        assert pp["citation_repair_source_chunk_id"] == "first-chunk", (
            "Repair must use the first hit's token, so source_chunk_id must be 'first-chunk'"
        )


# ---------------------------------------------------------------------------
# TestCitationQualityCoherence
# ---------------------------------------------------------------------------


class TestCitationQualityCoherence:
    """Verify ``citation_quality`` bundle stays coherent with top-level fields
    across all evidence-level transitions."""

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs",
        [
            ("no_answer", "", [], True),
            ("full_evidence", _CITED_ANSWER, [_HIT], True),
            ("degraded_uncited_fallback", _UNCITED_ANSWER, [], False),
            ("degraded_run_scoped_with_hit", _UNCITED_ANSWER, [_HIT], False),
            ("repaired_to_full", _UNCITED_ANSWER, [_HIT], True),
        ],
        ids=["no_answer", "full_evidence", "degraded_uncited_fallback",
             "degraded_run_scoped_with_hit", "repaired_to_full"],
    )
    def test_bundle_mirrors_top_level_fields(
        self, scenario: str, answer: str, hits: list, all_runs: bool
    ) -> None:
        """``citation_quality`` bundle fields must equal the corresponding top-level
        convenience fields on the same result object."""
        pp = _postprocess_answer(answer, hits, all_runs=all_runs)
        cq = pp["citation_quality"]

        assert cq["all_cited"] == pp["all_cited"], (
            f"[{scenario}] citation_quality.all_cited != top-level all_cited"
        )
        assert cq["raw_answer_all_cited"] == pp["raw_answer_all_cited"], (
            f"[{scenario}] citation_quality.raw_answer_all_cited != top-level raw_answer_all_cited"
        )
        assert cq["evidence_level"] == pp["evidence_level"], (
            f"[{scenario}] citation_quality.evidence_level != top-level evidence_level"
        )
        assert cq["warning_count"] == pp["warning_count"], (
            f"[{scenario}] citation_quality.warning_count != top-level warning_count"
        )
        assert cq["citation_warnings"] == pp["citation_warnings"], (
            f"[{scenario}] citation_quality.citation_warnings != top-level citation_warnings"
        )
        assert cq["warning_count"] == len(cq["citation_warnings"]), (
            f"[{scenario}] citation_quality.warning_count != len(citation_warnings)"
        )

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs,expected_level",
        [
            ("no_answer", "", [], True, "no_answer"),
            ("full_evidence", _CITED_ANSWER, [_HIT], True, "full"),
            ("degraded_fallback", _UNCITED_ANSWER, [], False, "degraded"),
            ("repaired_full", _UNCITED_ANSWER, [_HIT], True, "full"),
        ],
        ids=["no_answer", "full_evidence", "degraded_fallback", "repaired_full"],
    )
    def test_evidence_level_transitions(
        self,
        scenario: str,
        answer: str,
        hits: list,
        all_runs: bool,
        expected_level: str,
    ) -> None:
        """``evidence_level`` transitions correctly for each input scenario."""
        pp = _postprocess_answer(answer, hits, all_runs=all_runs)
        assert pp["evidence_level"] == expected_level, (
            f"[{scenario}] evidence_level: expected {expected_level!r}, "
            f"got {pp['evidence_level']!r}"
        )
        # Bundle must agree with top-level.
        assert pp["citation_quality"]["evidence_level"] == expected_level, (
            f"[{scenario}] citation_quality.evidence_level diverged from top-level"
        )


# ---------------------------------------------------------------------------
# TestRunRetrievalAndQaResultContract
# ---------------------------------------------------------------------------


class TestRunRetrievalAndQaResultContract:
    """Result-dict contract tests for ``run_retrieval_and_qa()``.

    Uses mocked Neo4j driver and RAG infrastructure to drive the full live code
    path, injecting a controlled answer text and retrieval items.  Asserts that
    postprocessing metadata is correctly surfaced in the returned dict, including:

    - top-level postprocessing keys match postprocessing semantics
    - ``citation_quality`` bundle is coherent with top-level convenience fields
    - repair/fallback/no-answer metadata is correct for each scenario
    """

    def test_fully_cited_answer_result_shape(self) -> None:
        """A fully cited answer produces the expected top-level and citation_quality fields."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )

        assert result["all_answers_cited"] is True
        assert result["raw_answer_all_cited"] is True
        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None
        assert result["citation_fallback_applied"] is False
        assert result["answer"] == _CITED_ANSWER

        cq = result["citation_quality"]
        assert cq["all_cited"] is True
        assert cq["evidence_level"] == "full"
        assert cq["warning_count"] == 0

    def test_uncited_answer_repaired_result_shape(self) -> None:
        """An uncited answer in all-runs mode is repaired; result fields reflect repair."""
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )

        assert result["citation_repair_applied"] is True
        assert result["citation_repair_strategy"] == "append_first_retrieved_token"
        assert result["citation_repair_source_chunk_id"] == "c1"
        assert result["citation_fallback_applied"] is False
        assert result["all_answers_cited"] is True
        assert result["raw_answer_all_cited"] is False
        # Repaired token must appear in the surfaced answer.
        assert _TOKEN in result["answer"]
        # Raw answer must remain unchanged.
        assert result["raw_answer"] == _UNCITED_ANSWER

        cq = result["citation_quality"]
        assert cq["all_cited"] is True
        assert cq["evidence_level"] == "full"

    def test_citation_fallback_applied_result_shape(self) -> None:
        """An uncited answer in run-scoped mode (no repair) produces fallback fields."""
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=False,
            run_id="r1",
        )

        assert result["citation_fallback_applied"] is True
        assert result["citation_repair_applied"] is False
        assert result["all_answers_cited"] is False
        assert result["answer"].startswith(_CITATION_FALLBACK_PREFIX)

        cq = result["citation_quality"]
        assert cq["all_cited"] is False
        assert cq["evidence_level"] == "degraded"
        assert cq["warning_count"] >= 1
        # Citation warnings must be propagated to the top-level warnings list.
        for w in cq["citation_warnings"]:
            assert w in result["warnings"], (
                f"citation_quality warning {w!r} missing from top-level warnings"
            )

    def test_no_answer_from_rag_result_shape(self) -> None:
        """An empty answer from the RAG produces a no_answer evidence level."""
        result = _run_with_mocked_retrieval(
            answer="",
            items_metadata=[],
            all_runs=True,
        )

        assert result["answer"] == ""
        assert result["all_answers_cited"] is False
        assert result["raw_answer_all_cited"] is False
        assert result["citation_repair_applied"] is False
        assert result["citation_fallback_applied"] is False

        cq = result["citation_quality"]
        assert cq["evidence_level"] == "no_answer"
        assert cq["warning_count"] == 0

    def test_citation_quality_bundle_coherent_with_top_level(self) -> None:
        """For all surfaced scenarios, ``citation_quality`` must mirror top-level fields."""
        scenarios = [
            (_CITED_ANSWER, [_LIVE_ITEM_METADATA]),
            (_UNCITED_ANSWER, [_LIVE_ITEM_METADATA]),
            (_UNCITED_ANSWER, []),
            ("", []),
        ]
        for answer, items_metadata in scenarios:
            result = _run_with_mocked_retrieval(
                answer=answer, items_metadata=items_metadata, all_runs=True
            )
            cq = result["citation_quality"]

            assert cq["all_cited"] == result["all_answers_cited"], (
                f"citation_quality.all_cited diverged from all_answers_cited "
                f"for answer={answer!r}"
            )
            assert cq["raw_answer_all_cited"] == result["raw_answer_all_cited"], (
                f"citation_quality.raw_answer_all_cited diverged for answer={answer!r}"
            )
            assert cq["warning_count"] == len(cq["citation_warnings"]), (
                f"citation_quality.warning_count != len(citation_warnings) "
                f"for answer={answer!r}"
            )
            # citation_quality.citation_warnings must be a subset of the top-level
            # warnings list so callers see a unified, complete warnings surface.
            for w in cq["citation_warnings"]:
                assert w in result["warnings"], (
                    f"citation_quality warning {w!r} missing from top-level warnings "
                    f"for answer={answer!r}"
                )

    def test_repair_applied_false_when_run_scoped(self) -> None:
        """Repair is never applied in run-scoped mode (all_runs=False)."""
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=False,
            run_id="r1",
        )

        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None
        # Fallback is applied instead.
        assert result["citation_fallback_applied"] is True

    def test_repair_strategy_and_chunk_id_absent_when_not_applied(self) -> None:
        """``citation_repair_strategy`` and ``citation_repair_source_chunk_id`` are
        ``None`` when repair was not applied."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )

        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None


# ---------------------------------------------------------------------------
# Shared live-scenario parameter matrix
# ---------------------------------------------------------------------------

#: Canonical six-scenario parameter matrix used by multiple parametrized tests.
#: Each tuple is ``(scenario_id, answer, items_metadata, all_runs, run_id)``.
#: Adding or renaming a scenario here propagates to every test that uses this constant.
_LIVE_SCENARIOS: list[tuple] = [
    ("fully_cited", _CITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
    ("repair_applied", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
    ("fallback_run_scoped", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], False, "r1"),
    ("no_answer", "", [], True, None),
    ("empty_chunk_warning", _CITED_ANSWER, [_EMPTY_CHUNK_METADATA], True, None),
    ("repair_attempted_no_token", _UNCITED_ANSWER, [_HIT_METADATA_NO_TOKEN], True, None),
]

#: pytest ``ids`` list corresponding to :data:`_LIVE_SCENARIOS`.
_LIVE_SCENARIO_IDS: list[str] = [row[0] for row in _LIVE_SCENARIOS]


# ---------------------------------------------------------------------------
# TestRunRetrievalAndQaPublicKeyContract
# ---------------------------------------------------------------------------


class TestRunRetrievalAndQaPublicKeyContract:
    """Assert the complete public output contract for ``run_retrieval_and_qa()``.

    These tests verify:

    - The live postprocessed result contains **exactly** the documented required
      key set (neither extra nor missing keys).  This acts as an executable
      registry that will catch any silent field addition, rename, or removal.
    - Every required field has the expected runtime type.
    - The nested ``citation_quality`` bundle and ``retrieval_scope`` dicts
      each carry their documented key sets.
    - The key set is stable across all core postprocessing scenarios.
    """

    def test_live_result_contains_exactly_required_keys(self) -> None:
        """Live result must contain EXACTLY the documented required key set —
        no extra, no missing keys."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        extra = set(result.keys()) - _LIVE_RESULT_REQUIRED_KEYS
        missing = _LIVE_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"Key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_live_result_status_is_live(self) -> None:
        """Live (non-dry-run) results must carry ``status='live'``."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        assert result["status"] == "live"

    def test_live_result_field_types(self) -> None:
        """Every required field must have the documented runtime type."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        str_fields = (
            "run_id", "source_uri", "retriever_type", "qa_model", "qa_prompt_version",
            "answer", "raw_answer", "qa", "status", "retrieval_path_summary",
            "retrieval_query_contract", "citation_token_example",
        )
        bool_fields = (
            "all_answers_cited", "raw_answer_all_cited", "citation_fallback_applied",
            "citation_repair_attempted", "citation_repair_applied",
            "expand_graph", "cluster_aware", "interactive_mode", "message_history_enabled",
        )
        int_fields = ("top_k", "hits", "malformed_diagnostics_count")
        list_fields = ("retrievers", "retrieval_results", "warnings")
        dict_fields = (
            "citation_quality", "retrieval_scope",
            "citation_object_example", "citation_example",
            "debug_view",
        )
        for key in str_fields:
            assert isinstance(result[key], str), (
                f"Field {key!r} expected str, got {type(result[key]).__name__}"
            )
        for key in bool_fields:
            assert isinstance(result[key], bool), (
                f"Field {key!r} expected bool, got {type(result[key]).__name__}"
            )
        for key in int_fields:
            assert isinstance(result[key], int), (
                f"Field {key!r} expected int, got {type(result[key]).__name__}"
            )
        for key in list_fields:
            assert isinstance(result[key], list), (
                f"Field {key!r} expected list, got {type(result[key]).__name__}"
            )
        for key in dict_fields:
            assert isinstance(result[key], dict), (
                f"Field {key!r} expected dict, got {type(result[key]).__name__}"
            )
        # Nullable fields: str or None
        for key in ("citation_repair_strategy", "citation_repair_source_chunk_id",
                    "retriever_index_name", "question"):
            assert result[key] is None or isinstance(result[key], str), (
                f"Field {key!r} expected str | None, got {type(result[key]).__name__}"
            )

    def test_citation_quality_bundle_has_required_keys(self) -> None:
        """``citation_quality`` must contain exactly the documented bundle key set."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        cq = result["citation_quality"]
        extra = set(cq.keys()) - _CITATION_QUALITY_BUNDLE_KEYS
        missing = _CITATION_QUALITY_BUNDLE_KEYS - set(cq.keys())
        assert not extra and not missing, (
            f"citation_quality key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_retrieval_scope_has_required_keys(self) -> None:
        """``retrieval_scope`` must contain exactly the documented key set."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        scope = result["retrieval_scope"]
        extra = set(scope.keys()) - _RETRIEVAL_SCOPE_REQUIRED_KEYS
        missing = _RETRIEVAL_SCOPE_REQUIRED_KEYS - set(scope.keys())
        assert not extra and not missing, (
            f"retrieval_scope key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_debug_view_has_required_keys(self) -> None:
        """``debug_view`` must contain exactly the documented key set."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        dv = result["debug_view"]
        extra = set(dv.keys()) - _DEBUG_VIEW_REQUIRED_KEYS
        missing = _DEBUG_VIEW_REQUIRED_KEYS - set(dv.keys())
        assert not extra and not missing, (
            f"debug_view key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        _LIVE_SCENARIOS,
        ids=_LIVE_SCENARIO_IDS,
    )
    def test_required_key_set_is_stable_across_scenarios(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """The required key set must be identical for every live postprocessed result,
        regardless of the postprocessing path taken."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        extra = set(result.keys()) - _LIVE_RESULT_REQUIRED_KEYS
        missing = _LIVE_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"[{scenario}] Key set mismatch — extra={extra!r}, missing={missing!r}"
        )


# ---------------------------------------------------------------------------
# TestRunRetrievalAndQaPostprocessMapping
# ---------------------------------------------------------------------------


class TestRunRetrievalAndQaPostprocessMapping:
    """Verify that every entry in :data:`_POSTPROCESS_FIELD_MAP` is correctly mapped
    to the public ``run_retrieval_and_qa()`` result dict.

    Uses a spy to capture the exact ``_postprocess_answer`` return value used
    internally, then asserts each entry in :data:`_POSTPROCESS_FIELD_MAP`
    holds: ``result[public_key] == pp[pp_key]``.  This makes the mapping
    contract explicit and ensures that renaming an internal field without updating
    the public surface causes a test failure.
    """

    def _run_and_capture_postprocess(
        self,
        answer: str,
        items_metadata: list,
        *,
        all_runs: bool,
        run_id: str | None = None,
    ) -> tuple[dict, dict]:
        """Drive ``run_retrieval_and_qa`` with a spy on ``_postprocess_answer``,
        returning ``(result, pp)`` where *pp* is the captured internal result."""
        captured: list[dict] = []

        def spy_pp(*args: object, **kwargs: object) -> dict[str, object]:
            r = _postprocess_answer(*args, **kwargs)  # type: ignore[arg-type]
            captured.append(dict(r))
            return r

        with patch("demo.stages.retrieval_and_qa._postprocess_answer", side_effect=spy_pp):
            result = _run_with_mocked_retrieval(
                answer=answer,
                items_metadata=items_metadata,
                all_runs=all_runs,
                run_id=run_id,
            )
        assert len(captured) == 1, "Expected _postprocess_answer to be called exactly once"
        return result, captured[0]

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        [
            ("fully_cited", _CITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("repair_applied", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("fallback_run_scoped", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], False, "r1"),
            ("no_answer", "", [], True, None),
        ],
        ids=["fully_cited", "repair_applied", "fallback_run_scoped", "no_answer"],
    )
    def test_all_postprocess_fields_mapped_to_public_result(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """Every entry in ``_POSTPROCESS_FIELD_MAP`` must hold for the live
        result: ``result[public_key] == pp[pp_key]``."""
        result, pp = self._run_and_capture_postprocess(
            answer, items_metadata, all_runs=all_runs, run_id=run_id
        )
        for pp_key, public_key in _POSTPROCESS_FIELD_MAP.items():
            assert result[public_key] == pp[pp_key], (
                f"[{scenario}] Mapping {pp_key!r} → {public_key!r} failed: "
                f"result[{public_key!r}]={result[public_key]!r}, "
                f"pp[{pp_key!r}]={pp[pp_key]!r}"
            )

    def test_answer_comes_from_display_answer_not_raw_answer(self) -> None:
        """``result['answer']`` must equal ``pp['display_answer']`` (not ``raw_answer``).
        After repair, ``display_answer`` is the repaired text; after fallback,
        it carries the fallback prefix — confirming the mapping uses the right key."""
        # Repair: display_answer != raw_answer (repaired text replaces raw)
        result_repair, pp_repair = self._run_and_capture_postprocess(
            _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], all_runs=True
        )
        assert result_repair["answer"] == pp_repair["display_answer"]
        assert result_repair["answer"] != pp_repair["raw_answer"], (
            "After repair, answer must equal display_answer, not raw_answer"
        )

        # Fallback: display_answer starts with the fallback prefix
        result_fallback, pp_fallback = self._run_and_capture_postprocess(
            _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], all_runs=False, run_id="r1"
        )
        assert result_fallback["answer"] == pp_fallback["display_answer"]
        assert result_fallback["answer"].startswith(_CITATION_FALLBACK_PREFIX), (
            "After fallback, answer must start with the fallback prefix"
        )

    def test_all_answers_cited_comes_from_all_cited_not_raw_answer_all_cited(self) -> None:
        """``result['all_answers_cited']`` must equal ``pp['all_cited']``, which
        reflects the *final delivered* answer (after repair), not ``raw_answer_all_cited``
        (which reflects the original LLM output before repair)."""
        result, pp = self._run_and_capture_postprocess(
            _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], all_runs=True
        )
        # After repair: all_cited=True (repair fixed it), raw_answer_all_cited=False
        assert result["all_answers_cited"] == pp["all_cited"]
        assert result["raw_answer_all_cited"] == pp["raw_answer_all_cited"]
        assert result["all_answers_cited"] is True
        assert result["raw_answer_all_cited"] is False, (
            "raw_answer_all_cited must reflect the original LLM output, not the repaired answer"
        )


# ---------------------------------------------------------------------------
# TestRunRetrievalAndQaDocumentedScenarios
# ---------------------------------------------------------------------------

#: Empty-chunk-text warning string derived from ``_EMPTY_CHUNK_METADATA`` so
#: the expected message always stays consistent with the fixture chunk_id.
_EMPTY_CHUNK_WARNING_MSG: str = (
    "Chunk {!r} has empty or whitespace-only text.".format(
        _EMPTY_CHUNK_METADATA["citation_object"]["chunk_id"]  # type: ignore[index]
    )
)

#: Parametrized scenario table for TestRunRetrievalAndQaDocumentedScenarios.
#: Each row:
#:   (id, answer, items_metadata, all_runs, run_id,
#:    expected_fields, evidence_level, expected_citation_warnings, required_in_warnings)
#: where:
#:   - expected_fields is a dict of {public_key: expected_value}
#:   - evidence_level is the expected ``citation_quality["evidence_level"]`` string
#:   - expected_citation_warnings is the exact list expected in
#:     ``citation_quality["citation_warnings"]``
#:   - required_in_warnings is the list of warnings that must appear in the
#:     top-level ``warnings`` list (subset check)
_DOCUMENTED_SCENARIOS: list[tuple] = [
    # §4.1 Full citation — no repair, no fallback.
    # The LLM produced a fully cited answer from the start.
    (
        "s4_1_full_citation",
        _CITED_ANSWER,
        [_LIVE_ITEM_METADATA],
        True,
        None,
        {
            "answer": _CITED_ANSWER,
            "raw_answer": _CITED_ANSWER,
            "all_answers_cited": True,
            "raw_answer_all_cited": True,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
        },
        "full",   # expected evidence_level
        [],       # expected citation_warnings (empty)
        [],       # expected warnings that must be present (subset check)
    ),
    # §4.2 Degraded citation — fallback applied (run-scoped, no repair).
    # The LLM omitted citation tokens and repair did not run (run-scoped mode).
    (
        "s4_2_degraded_fallback",
        _UNCITED_ANSWER,
        [_LIVE_ITEM_METADATA],
        False,
        "r1",
        {
            "answer": _FALLBACK_DISPLAY_UNCITED,
            "raw_answer": _UNCITED_ANSWER,
            "all_answers_cited": False,
            "raw_answer_all_cited": False,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": True,
        },
        "degraded",
        [_UNCITED_WARNING],
        [_UNCITED_WARNING],
    ),
    # §4.3 Repair applied — citation fixed, no fallback.
    # All-runs mode: the LLM omitted a citation token, repair appended the
    # first retrieved token, and the answer became fully cited.
    (
        "s4_3_repair_applied",
        _UNCITED_ANSWER,
        [_LIVE_ITEM_METADATA],
        True,
        None,
        {
            "answer": _REPAIRED_UNCITED_ANSWER,
            "raw_answer": _UNCITED_ANSWER,
            "all_answers_cited": True,
            "raw_answer_all_cited": False,
            "citation_repair_attempted": True,
            "citation_repair_applied": True,
            "citation_repair_strategy": "append_first_retrieved_token",
            "citation_repair_source_chunk_id": "c1",
            "citation_fallback_applied": False,
        },
        "full",
        [],
        [],
    ),
    # §4.5 No answer generated.
    # The LLM returned an empty string.
    (
        "s4_5_no_answer",
        "",
        [],
        True,
        None,
        {
            "answer": "",
            "raw_answer": "",
            "all_answers_cited": False,
            "raw_answer_all_cited": False,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
        },
        "no_answer",
        [],
        [],
    ),
    # §4.6 Empty chunk text — degraded evidence with retrieval-time warning.
    # A retrieved chunk had empty text.  The answer is fully cited, but the
    # empty-chunk warning degrades evidence_level to "degraded".
    (
        "s4_6_empty_chunk",
        _CITED_ANSWER,
        [_EMPTY_CHUNK_METADATA],
        True,
        None,
        {
            "answer": _CITED_ANSWER,
            "raw_answer": _CITED_ANSWER,
            "all_answers_cited": True,
            "raw_answer_all_cited": True,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
        },
        "degraded",
        [_EMPTY_CHUNK_WARNING_MSG],
        [_EMPTY_CHUNK_WARNING_MSG],
    ),
    # §4.7 Repair attempted but not applied — no candidate token found.
    # All-runs mode: repair preconditions were met (uncited answer, hits provided)
    # but no retrieved hit contained a usable citation token.
    (
        "s4_7_repair_attempted_no_token",
        _UNCITED_ANSWER,
        [_HIT_METADATA_NO_TOKEN],
        True,
        None,
        {
            "answer": _FALLBACK_DISPLAY_UNCITED,
            "raw_answer": _UNCITED_ANSWER,
            "all_answers_cited": False,
            "raw_answer_all_cited": False,
            "citation_repair_attempted": True,
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": True,
        },
        "degraded",
        [_UNCITED_WARNING],
        [_UNCITED_WARNING],
    ),
]


class TestRunRetrievalAndQaDocumentedScenarios:
    """End-to-end tests that drive ``run_retrieval_and_qa()`` through each scenario
    described in §4 of the canonical contract document and assert the complete set of
    postprocessing-related public fields.

    This class serves as an executable copy of the contract document §4 scenario
    table: if a field value diverges from the documented expectation, the test fails
    and a reviewer must explicitly decide whether the documentation or the
    implementation needs to be updated.
    """

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_fields,"
        "expected_evidence_level,expected_citation_warnings,required_in_warnings",
        _DOCUMENTED_SCENARIOS,
        ids=[row[0] for row in _DOCUMENTED_SCENARIOS],
    )
    def test_postprocessing_fields_match_contract(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_fields: dict,
        expected_evidence_level: str,
        expected_citation_warnings: list,
        required_in_warnings: list,
    ) -> None:
        """Every documented public field must match the scenario expectation from §4."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        for key, expected_value in expected_fields.items():
            assert result[key] == expected_value, (
                f"[{scenario}] result[{key!r}]: expected {expected_value!r}, "
                f"got {result[key]!r}"
            )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_fields,"
        "expected_evidence_level,expected_citation_warnings,required_in_warnings",
        _DOCUMENTED_SCENARIOS,
        ids=[row[0] for row in _DOCUMENTED_SCENARIOS],
    )
    def test_evidence_level_matches_contract(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_fields: dict,
        expected_evidence_level: str,
        expected_citation_warnings: list,
        required_in_warnings: list,
    ) -> None:
        """``citation_quality['evidence_level']`` must match the scenario's documented value."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        assert cq["evidence_level"] == expected_evidence_level, (
            f"[{scenario}] citation_quality.evidence_level: "
            f"expected {expected_evidence_level!r}, got {cq['evidence_level']!r}"
        )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_fields,"
        "expected_evidence_level,expected_citation_warnings,required_in_warnings",
        _DOCUMENTED_SCENARIOS,
        ids=[row[0] for row in _DOCUMENTED_SCENARIOS],
    )
    def test_citation_warnings_match_contract(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_fields: dict,
        expected_evidence_level: str,
        expected_citation_warnings: list,
        required_in_warnings: list,
    ) -> None:
        """``citation_quality['citation_warnings']`` must contain exactly the
        documented warnings for each scenario."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        assert cq["citation_warnings"] == expected_citation_warnings, (
            f"[{scenario}] citation_quality.citation_warnings: "
            f"expected {expected_citation_warnings!r}, got {cq['citation_warnings']!r}"
        )
        assert cq["warning_count"] == len(expected_citation_warnings), (
            f"[{scenario}] citation_quality.warning_count: "
            f"expected {len(expected_citation_warnings)}, got {cq['warning_count']}"
        )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_fields,"
        "expected_evidence_level,expected_citation_warnings,required_in_warnings",
        _DOCUMENTED_SCENARIOS,
        ids=[row[0] for row in _DOCUMENTED_SCENARIOS],
    )
    def test_required_warnings_in_top_level_list(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_fields: dict,
        expected_evidence_level: str,
        expected_citation_warnings: list,
        required_in_warnings: list,
    ) -> None:
        """Every warning in ``required_in_warnings`` must appear in the top-level
        ``warnings`` list (citation_warnings must be a subset of warnings)."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        for w in required_in_warnings:
            assert w in result["warnings"], (
                f"[{scenario}] Warning {w!r} missing from top-level warnings; "
                f"got {result['warnings']!r}"
            )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_fields,"
        "expected_evidence_level,expected_citation_warnings,required_in_warnings",
        _DOCUMENTED_SCENARIOS,
        ids=[row[0] for row in _DOCUMENTED_SCENARIOS],
    )
    def test_citation_quality_mirrors_top_level_for_all_scenarios(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_fields: dict,
        expected_evidence_level: str,
        expected_citation_warnings: list,
        required_in_warnings: list,
    ) -> None:
        """For every documented scenario, ``citation_quality`` must mirror the
        corresponding top-level convenience fields."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        assert cq["all_cited"] == result["all_answers_cited"], (
            f"[{scenario}] citation_quality.all_cited != all_answers_cited"
        )
        assert cq["raw_answer_all_cited"] == result["raw_answer_all_cited"], (
            f"[{scenario}] citation_quality.raw_answer_all_cited != raw_answer_all_cited"
        )
        assert cq["evidence_level"] == expected_evidence_level, (
            f"[{scenario}] citation_quality.evidence_level mismatch"
        )
        assert cq["warning_count"] == len(cq["citation_warnings"]), (
            f"[{scenario}] citation_quality.warning_count != len(citation_warnings)"
        )

    def test_s4_4_repair_applied_answer_still_degraded(self) -> None:
        """§4.4: Repair applied but answer still degraded.

        All-runs mode: repair ran and the answer text changed, but the repaired
        answer still has uncited segments (so fallback is also applied).

        Note: The current ``_repair_uncited_answer`` implementation appends the
        retrieved token to *every* uncited sentence, which means a normal
        two-sentence uncited input always becomes fully cited after repair.  §4.4
        is therefore unreachable through purely end-to-end inputs with the
        current heuristic.  This test patches ``_apply_citation_repair`` to
        return the partially-repaired answer described in the contract document
        §4.4, verifying that ``run_retrieval_and_qa`` correctly handles this
        path (repair applied, fallback also applied, evidence_level degraded)
        regardless of which specific repair algorithm produces it.
        """
        # A two-sentence answer where repair appended the token only once
        # (to the last sentence), leaving the first sentence uncited.
        # "Claim A." is the uncited first sentence; "Claim B. [TOKEN]" is cited.
        raw_two_sentence = "Claim A. Claim B."
        partially_repaired = f"Claim A. Claim B. {_TOKEN}"

        def _mock_repair(
            answer_text: str,
            hits: list,
            *,
            all_runs: bool,
            raw_answer_all_cited: bool,
        ) -> tuple:
            # Simulate a partial repair: token appended once (at end), not per-sentence.
            if all_runs and hits and answer_text.strip() and not raw_answer_all_cited:
                return partially_repaired, True, True, "append_first_retrieved_token", "c1"
            return answer_text, False, False, None, None

        expected_fallback_answer = f"{_CITATION_FALLBACK_PREFIX}: {partially_repaired}"

        mock_rag = MagicMock()
        mock_rag.search.return_value = _make_rag_result(
            raw_two_sentence, [_LIVE_ITEM_METADATA]
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
            patch("neo4j.GraphDatabase.driver"),
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag"
            ) as mock_build,
            patch(
                "demo.stages.retrieval_and_qa._apply_citation_repair",
                side_effect=_mock_repair,
            ),
        ):
            mock_build.return_value = (MagicMock(), mock_rag)
            result = run_retrieval_and_qa(
                _LIVE_CONFIG,
                all_runs=True,
                question="What is the claim?",
            )

        # Both repair AND fallback are applied (repair changed the text but the
        # repaired answer still has uncited segments → fallback prefix is prepended).
        assert result["answer"] == expected_fallback_answer, (
            f"answer: expected {expected_fallback_answer!r}, got {result['answer']!r}"
        )
        assert result["raw_answer"] == raw_two_sentence
        assert result["all_answers_cited"] is False
        assert result["raw_answer_all_cited"] is False
        assert result["citation_repair_attempted"] is True
        assert result["citation_repair_applied"] is True
        assert result["citation_repair_strategy"] == "append_first_retrieved_token"
        assert result["citation_repair_source_chunk_id"] == "c1"
        assert result["citation_fallback_applied"] is True

        cq = result["citation_quality"]
        assert cq["evidence_level"] == "degraded"
        assert cq["all_cited"] is False
        assert _UNCITED_WARNING in cq["citation_warnings"]
        assert _UNCITED_WARNING in result["warnings"]
        assert cq["warning_count"] == len(cq["citation_warnings"])


# ---------------------------------------------------------------------------
# TestRunRetrievalAndQaEarlyReturnContract
# ---------------------------------------------------------------------------


class TestRunRetrievalAndQaEarlyReturnContract:
    """Contract tests for the early-return (non-live) paths documented in §5 of the
    canonical contract document.

    Two early-return paths exist in ``run_retrieval_and_qa()``:

    1. **dry_run** (§5.1) — ``config.dry_run=True`` short-circuits before any retrieval
       or LLM call.  The result carries ``status="dry_run"`` and omits
       ``hits``, ``retrieval_results``, ``warnings``, and ``retrieval_skipped``.

    2. **retrieval skipped / no question** (§5.2) — ``question=None`` in live mode
       short-circuits before any Neo4j or LLM call.  The result carries
       ``status="live"``, ``retrieval_skipped=True``, and includes
       ``hits=0``, ``retrieval_results=[]``, and ``warnings`` containing
       the skip message.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_result(**kwargs) -> dict[str, object]:
        """Return a dry-run result.  Extra keyword args are forwarded to ``run_retrieval_and_qa``."""
        return run_retrieval_and_qa(_DRY_RUN_CONFIG, run_id="dr-run-1", source_uri=None, **kwargs)

    @staticmethod
    def _skip_result(**kwargs) -> dict[str, object]:
        """Return a retrieval-skipped (no-question) result.

        Uses invalid Neo4j credentials to prove the skip path never opens a driver.
        """
        cfg = types.SimpleNamespace(
            dry_run=False,
            openai_model="gpt-4o-mini",
            neo4j_uri="",
            neo4j_username="",
            neo4j_password="",
            neo4j_database=None,
        )
        return run_retrieval_and_qa(cfg, run_id="skip-run-1", source_uri=None, question=None, **kwargs)

    # ------------------------------------------------------------------
    # §5.1  dry_run key-set contract
    # ------------------------------------------------------------------

    def test_dry_run_contains_exactly_required_keys(self) -> None:
        """dry_run result must contain EXACTLY the documented required key set —
        no extra, no missing keys."""
        result = self._dry_run_result()
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_status_is_dry_run(self) -> None:
        """dry_run result must carry ``status='dry_run'``."""
        assert self._dry_run_result()["status"] == "dry_run"

    def test_dry_run_omits_hits(self) -> None:
        """``hits`` must be absent from the dry_run result (retrieval never ran)."""
        assert "hits" not in self._dry_run_result()

    def test_dry_run_omits_retrieval_results(self) -> None:
        """``retrieval_results`` must be absent from the dry_run result."""
        assert "retrieval_results" not in self._dry_run_result()

    def test_dry_run_omits_warnings(self) -> None:
        """``warnings`` must be absent from the dry_run result (no operational warnings)."""
        assert "warnings" not in self._dry_run_result()

    def test_dry_run_omits_retrieval_skipped(self) -> None:
        """``retrieval_skipped`` must be absent from the dry_run result (it is only
        set on the no-question path)."""
        assert "retrieval_skipped" not in self._dry_run_result()

    def test_dry_run_retrievers_default(self) -> None:
        """dry_run with no expand_graph/cluster_aware flags must report
        ``retrievers=['VectorCypherRetriever']``."""
        result = self._dry_run_result()
        assert result["retrievers"] == ["VectorCypherRetriever"]

    def test_dry_run_retrievers_expand_graph(self) -> None:
        """dry_run with ``expand_graph=True`` must include ``'graph expansion'``
        in the retrievers list."""
        result = self._dry_run_result(expand_graph=True)
        assert "graph expansion" in result["retrievers"]
        assert "cluster traversal" not in result["retrievers"]

    def test_dry_run_retrievers_cluster_aware(self) -> None:
        """dry_run with ``cluster_aware=True`` must include both ``'graph expansion'``
        and ``'cluster traversal'`` in the retrievers list."""
        result = self._dry_run_result(cluster_aware=True)
        assert "graph expansion" in result["retrievers"]
        assert "cluster traversal" in result["retrievers"]

    def test_dry_run_qa_label_run_scoped(self) -> None:
        """dry_run in run-scoped mode (``all_runs=False``) must carry the run-scoped qa label."""
        result = self._dry_run_result(all_runs=False)
        assert result["qa"] == "GraphRAG run-scoped citations"

    def test_dry_run_qa_label_all_runs(self) -> None:
        """dry_run in all-runs mode (``all_runs=True``) must carry the all-runs qa label."""
        result = self._dry_run_result(all_runs=True)
        assert result["qa"] == "GraphRAG all-runs citations"

    def test_dry_run_default_answer_fields(self) -> None:
        """dry_run result must carry default (empty/False) answer fields because
        no LLM call was made."""
        result = self._dry_run_result()
        assert result["answer"] == ""
        assert result["raw_answer"] == ""
        assert result["all_answers_cited"] is False
        assert result["raw_answer_all_cited"] is False
        assert result["citation_fallback_applied"] is False
        assert result["citation_repair_attempted"] is False
        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None

    def test_dry_run_citation_quality_defaults(self) -> None:
        """dry_run ``citation_quality`` must carry default no_answer values."""
        cq = self._dry_run_result()["citation_quality"]
        assert isinstance(cq, dict)
        assert cq["evidence_level"] == "no_answer"
        assert cq["all_cited"] is False
        assert cq["raw_answer_all_cited"] is False
        assert cq["warning_count"] == 0
        assert cq["citation_warnings"] == []

    def test_dry_run_retrieval_path_summary_empty(self) -> None:
        """``retrieval_path_summary`` must be the empty string in dry_run (no retrieval ran)."""
        assert self._dry_run_result()["retrieval_path_summary"] == ""

    def test_dry_run_malformed_diagnostics_count_zero(self) -> None:
        """``malformed_diagnostics_count`` must be 0 in dry_run (no hits retrieved)."""
        assert self._dry_run_result()["malformed_diagnostics_count"] == 0

    # ------------------------------------------------------------------
    # §5.2  retrieval-skipped (no-question) key-set contract
    # ------------------------------------------------------------------

    def test_retrieval_skipped_contains_exactly_required_keys(self) -> None:
        """Retrieval-skipped result must contain EXACTLY the documented required key set —
        no extra, no missing keys."""
        result = self._skip_result()
        extra = set(result.keys()) - _RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS
        missing = _RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"retrieval_skipped key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_retrieval_skipped_status_is_live(self) -> None:
        """Retrieval-skipped result must carry ``status='live'`` (not ``'dry_run'``)."""
        assert self._skip_result()["status"] == "live"

    def test_retrieval_skipped_flag_is_true(self) -> None:
        """``retrieval_skipped`` must be ``True`` when ``question=None``."""
        assert self._skip_result()["retrieval_skipped"] is True

    def test_retrieval_skipped_hits_zero(self) -> None:
        """``hits`` must be ``0`` on the retrieval-skipped path."""
        assert self._skip_result()["hits"] == 0

    def test_retrieval_skipped_retrieval_results_empty(self) -> None:
        """``retrieval_results`` must be ``[]`` on the retrieval-skipped path."""
        assert self._skip_result()["retrieval_results"] == []

    def test_retrieval_skipped_retrievers_empty(self) -> None:
        """``retrievers`` must be ``[]`` when retrieval was skipped (nothing ran)."""
        assert self._skip_result()["retrievers"] == []

    def test_retrieval_skipped_warnings_contains_skip_message(self) -> None:
        """``warnings`` must contain exactly the skip message and nothing else."""
        result = self._skip_result()
        assert result["warnings"] == [_SKIP_WARNING], (
            f"Expected warnings=[{_SKIP_WARNING!r}]; got {result['warnings']!r}"
        )

    def test_retrieval_skipped_default_answer_fields(self) -> None:
        """Retrieval-skipped result must carry default (empty/False/None) answer fields."""
        result = self._skip_result()
        assert result["answer"] == ""
        assert result["raw_answer"] == ""
        assert result["raw_answer_all_cited"] is False
        assert result["all_answers_cited"] is False
        assert result["citation_repair_attempted"] is False
        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None
        assert result["citation_fallback_applied"] is False

    def test_retrieval_skipped_citation_quality_defaults(self) -> None:
        """Retrieval-skipped ``citation_quality`` must carry default no_answer values."""
        cq = self._skip_result()["citation_quality"]
        assert cq["evidence_level"] == "no_answer"
        assert cq["all_cited"] is False
        assert cq["warning_count"] == 0
        assert cq["citation_warnings"] == []

    def test_retrieval_skipped_warning_not_in_citation_warnings(self) -> None:
        """The skip warning is an operational warning (§2.5.2) — it must appear in
        ``warnings`` but must NOT appear in ``citation_quality["citation_warnings"]``."""
        result = self._skip_result()
        assert _SKIP_WARNING in result["warnings"]
        cq = result["citation_quality"]
        assert _SKIP_WARNING not in cq["citation_warnings"], (
            "Skip warning must not propagate to citation_quality.citation_warnings "
            "(it is an operational warning, not a citation-quality issue)"
        )

    def test_retrieval_skipped_retrieval_path_summary_empty(self) -> None:
        """``retrieval_path_summary`` must be the empty string when retrieval was skipped."""
        assert self._skip_result()["retrieval_path_summary"] == ""

    def test_retrieval_skipped_malformed_diagnostics_count_zero(self) -> None:
        """``malformed_diagnostics_count`` must be 0 when retrieval was skipped."""
        assert self._skip_result()["malformed_diagnostics_count"] == 0

    # ------------------------------------------------------------------
    # §5.3  caller-distinction invariants
    # ------------------------------------------------------------------

    def test_dry_run_distinguished_by_status(self) -> None:
        """Callers can distinguish dry_run results by checking ``status == 'dry_run'``."""
        assert self._dry_run_result()["status"] == "dry_run"

    def test_retrieval_skipped_distinguished_by_flag(self) -> None:
        """Callers can distinguish retrieval-skipped results by checking
        ``result.get('retrieval_skipped') is True``."""
        result = self._skip_result()
        assert result.get("retrieval_skipped") is True

    def test_dry_run_has_no_retrieval_skipped_flag(self) -> None:
        """``retrieval_skipped`` must be absent from the dry_run result — callers must not
        confuse dry_run with the no-question path."""
        result = self._dry_run_result()
        assert result.get("retrieval_skipped") is None  # absent

    # ------------------------------------------------------------------
    # §5.1 / §5.2  debug_view invariants
    # ------------------------------------------------------------------

    def test_dry_run_debug_view_present(self) -> None:
        """``debug_view`` must be present in the dry_run result (§5.1)."""
        assert "debug_view" in self._dry_run_result()

    def test_dry_run_debug_view_has_required_keys(self) -> None:
        """``debug_view`` in the dry_run result must contain exactly the documented
        key set (§5.1 / §2.9)."""
        dv = self._dry_run_result()["debug_view"]
        assert isinstance(dv, dict)
        extra = set(dv) - _DEBUG_VIEW_REQUIRED_KEYS
        missing = _DEBUG_VIEW_REQUIRED_KEYS - set(dv)
        assert not extra and not missing, (
            f"debug_view key set mismatch (dry_run) — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_debug_view_all_zero_defaults(self) -> None:
        """All ``debug_view`` values must carry all-zero defaults on the dry_run
        path — no postprocessing ran so no real data is available (§5.1)."""
        dv = self._dry_run_result()["debug_view"]
        assert dv["raw_answer_all_cited"] is False
        assert dv["all_cited"] is False
        assert dv["citation_repair_attempted"] is False
        assert dv["citation_repair_applied"] is False
        assert dv["citation_fallback_applied"] is False
        assert dv["evidence_level"] == "no_answer"
        assert dv["warning_count"] == 0
        assert dv["citation_warnings"] == []
        assert dv["malformed_diagnostics_count"] == 0

    def test_retrieval_skipped_debug_view_present(self) -> None:
        """``debug_view`` must be present in the retrieval-skipped result (§5.2)."""
        assert "debug_view" in self._skip_result()

    def test_retrieval_skipped_debug_view_has_required_keys(self) -> None:
        """``debug_view`` in the retrieval-skipped result must contain exactly the
        documented key set (§5.2 / §2.9)."""
        dv = self._skip_result()["debug_view"]
        assert isinstance(dv, dict)
        extra = set(dv) - _DEBUG_VIEW_REQUIRED_KEYS
        missing = _DEBUG_VIEW_REQUIRED_KEYS - set(dv)
        assert not extra and not missing, (
            f"debug_view key set mismatch (retrieval_skipped) — extra={extra!r}, missing={missing!r}"
        )

    def test_retrieval_skipped_debug_view_all_zero_defaults(self) -> None:
        """All ``debug_view`` values must carry all-zero defaults when retrieval was
        skipped — no postprocessing ran so no real data is available (§5.2)."""
        dv = self._skip_result()["debug_view"]
        assert dv["raw_answer_all_cited"] is False
        assert dv["all_cited"] is False
        assert dv["citation_repair_attempted"] is False
        assert dv["citation_repair_applied"] is False
        assert dv["citation_fallback_applied"] is False
        assert dv["evidence_level"] == "no_answer"
        assert dv["warning_count"] == 0
        assert dv["citation_warnings"] == []
        assert dv["malformed_diagnostics_count"] == 0


# ---------------------------------------------------------------------------
# TestMixedEarlyReturnSentinelEdge
# ---------------------------------------------------------------------------


class TestMixedEarlyReturnSentinelEdge:
    """Contract tests for mixed early-return inputs and sentinel-edge behavior.

    These tests lock down precedence rules and edge-case short-circuit semantics
    that sit just outside the canonical ``dry_run`` / ``question=None`` happy
    paths already covered by :class:`TestRunRetrievalAndQaEarlyReturnContract`.

    The precedence rules encoded here are backed by the centralized
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` policy
    (``demo/contracts/retrieval_early_return_policy.py``).  See
    :class:`TestEarlyReturnPrecedencePolicy` for direct unit tests of the policy
    structure itself.

    Key invariants verified here:

    1. **dry_run wins over question=None** — ``config.dry_run=True`` is checked
       before the ``question is None`` guard.  When both conditions are true the
       result must be the ``dry_run`` shape, not the ``retrieval_skipped`` shape.
       (``EARLY_RETURN_RULE_BY_NAME["dry_run"].wins_over`` contains
       ``"retrieval_skipped"``.)

    2. **dry_run wins over question=""** — an empty-string question does not
       trigger the retrieval-skipped early return; ``dry_run=True`` still returns
       the dry-run payload.

    3. **question="" is not treated as a retrieval-skipping sentinel in these
       tests** — only ``None`` activates the ``retrieval_skipped`` short-circuit
       in the mixed ``dry_run`` scenarios covered here; an empty string behaves
       like any other non-``None`` question along these code paths.

    4. **dry_run + retrieval-mode modifiers preserve the dry_run key set** —
       passing ``all_runs=True``, ``expand_graph=True``, or ``cluster_aware=True``
       alongside ``dry_run=True`` must not inject any non-dry-run keys (``hits``,
       ``retrieval_results``, ``warnings``, ``retrieval_skipped``) into the result.

    5. **debug_view zero-defaults are preserved across mixed dry_run paths** —
       all ``debug_view`` values must remain all-zero regardless of which
       modifiers accompany ``dry_run=True``.

    6. **question field is recorded faithfully** — the ``question`` key in the
       result always mirrors the value passed to ``run_retrieval_and_qa``,
       including ``None`` and ``""``.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_result(**kwargs) -> dict[str, object]:
        """Return a dry-run result using the shared early-return helper."""
        return TestRunRetrievalAndQaEarlyReturnContract._dry_run_result(**kwargs)

    # ------------------------------------------------------------------
    # §1  Precedence: dry_run > question=None
    # ------------------------------------------------------------------

    def test_dry_run_with_question_none_status_is_dry_run(self) -> None:
        """When ``dry_run=True`` and ``question=None``, the result must carry
        ``status='dry_run'`` — the dry_run check runs before the question guard."""
        result = self._dry_run_result(question=None)
        assert result["status"] == "dry_run"

    def test_dry_run_with_question_none_no_retrieval_skipped(self) -> None:
        """``retrieval_skipped`` must be absent when ``dry_run=True``, even if
        ``question=None`` — dry_run wins and its result shape omits that flag."""
        result = self._dry_run_result(question=None)
        assert "retrieval_skipped" not in result

    def test_dry_run_with_question_none_exact_key_set(self) -> None:
        """``dry_run=True`` + ``question=None`` must produce exactly the dry_run
        required key set — no extra retrieval-skipped or live-only keys."""
        result = self._dry_run_result(question=None)
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run+question=None key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_with_question_none_records_none(self) -> None:
        """The ``question`` field in the dry_run result must be ``None`` when
        ``question=None`` was passed — the value is recorded faithfully."""
        result = self._dry_run_result(question=None)
        assert result["question"] is None

    # ------------------------------------------------------------------
    # §2  Precedence: dry_run > question=""
    # ------------------------------------------------------------------

    def test_dry_run_with_empty_question_status_is_dry_run(self) -> None:
        """When ``dry_run=True`` and ``question=""``, the result must still carry
        ``status='dry_run'`` — an empty string does not change the dry-run path."""
        result = self._dry_run_result(question="")
        assert result["status"] == "dry_run"

    def test_dry_run_with_empty_question_exact_key_set(self) -> None:
        """``dry_run=True`` + ``question=""`` must produce exactly the dry_run
        required key set — no leakage from the live or retrieval-skipped paths."""
        result = self._dry_run_result(question="")
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run+question='' key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_with_empty_question_records_empty_string(self) -> None:
        """The ``question`` field must be ``""`` when ``question=""`` was passed —
        no coercion to ``None`` occurs on the dry-run path."""
        result = self._dry_run_result(question="")
        assert result["question"] == ""

    # ------------------------------------------------------------------
    # §3  Sentinel distinction: question="" is not question=None
    # ------------------------------------------------------------------

    def test_empty_question_is_not_retrieval_skipped_sentinel(self) -> None:
        """In dry_run mode, ``question=None`` and ``question=""`` both return
        ``status='dry_run'``, but their ``question`` fields differ — confirming
        that ``""`` is not silently coerced to ``None`` or vice-versa."""
        result_none = self._dry_run_result(question=None)
        result_empty = self._dry_run_result(question="")
        # Both are dry_run — but the recorded values must differ
        assert result_none["question"] is None
        assert result_empty["question"] == ""
        assert result_none["question"] != result_empty["question"]

    # ------------------------------------------------------------------
    # §4  dry_run + retrieval-mode modifiers preserve the dry_run key set
    # ------------------------------------------------------------------

    def test_dry_run_with_all_runs_exact_key_set(self) -> None:
        """``dry_run=True`` + ``all_runs=True`` must produce exactly the dry_run
        required key set — no live-only keys injected by the all-runs modifier."""
        result = self._dry_run_result(all_runs=True)
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run+all_runs key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_with_expand_graph_exact_key_set(self) -> None:
        """``dry_run=True`` + ``expand_graph=True`` must produce exactly the dry_run
        required key set — graph-expansion modifier must not add live-only keys."""
        result = self._dry_run_result(expand_graph=True)
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run+expand_graph key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    def test_dry_run_with_cluster_aware_exact_key_set(self) -> None:
        """``dry_run=True`` + ``cluster_aware=True`` must produce exactly the dry_run
        required key set — cluster modifier must not add live-only keys."""
        result = self._dry_run_result(cluster_aware=True)
        extra = set(result.keys()) - _DRY_RUN_RESULT_REQUIRED_KEYS
        missing = _DRY_RUN_RESULT_REQUIRED_KEYS - set(result.keys())
        assert not extra and not missing, (
            f"dry_run+cluster_aware key set mismatch — extra={extra!r}, missing={missing!r}"
        )

    # ------------------------------------------------------------------
    # §5  debug_view zero-defaults preserved across mixed dry_run paths
    # ------------------------------------------------------------------

    def _assert_debug_view_early_return_defaults(self, dv: object, label: str) -> None:
        """Assert that a ``debug_view`` dict carries the early-return default values
        (all boolean fields False, evidence_level 'no_answer', counts zero, lists empty).
        """
        assert isinstance(dv, dict), f"{label}: debug_view must be a dict"
        assert dv["raw_answer_all_cited"] is False, label
        assert dv["all_cited"] is False, label
        assert dv["citation_repair_attempted"] is False, label
        assert dv["citation_repair_applied"] is False, label
        assert dv["citation_fallback_applied"] is False, label
        assert dv["evidence_level"] == "no_answer", label
        assert dv["warning_count"] == 0, label
        assert dv["citation_warnings"] == [], label
        assert dv["malformed_diagnostics_count"] == 0, label

    def test_dry_run_with_question_none_debug_view_early_return_defaults(self) -> None:
        """``debug_view`` must carry early-return defaults when ``dry_run=True`` and
        ``question=None`` — no postprocessing ran on either path."""
        result = self._dry_run_result(question=None)
        self._assert_debug_view_early_return_defaults(result["debug_view"], "dry_run+question=None")

    def test_dry_run_with_empty_question_debug_view_early_return_defaults(self) -> None:
        """``debug_view`` must carry early-return defaults when ``dry_run=True`` and
        ``question=""`` — the dry_run short-circuit runs before any retrieval."""
        result = self._dry_run_result(question="")
        self._assert_debug_view_early_return_defaults(result["debug_view"], "dry_run+question=''")

    def test_dry_run_with_all_runs_debug_view_early_return_defaults(self) -> None:
        """``debug_view`` must carry early-return defaults when ``dry_run=True`` and
        ``all_runs=True`` — the all-runs modifier does not run retrieval in dry-run."""
        result = self._dry_run_result(all_runs=True)
        self._assert_debug_view_early_return_defaults(result["debug_view"], "dry_run+all_runs")

    def test_dry_run_with_expand_graph_debug_view_early_return_defaults(self) -> None:
        """``debug_view`` must carry early-return defaults when ``dry_run=True`` and
        ``expand_graph=True`` — graph expansion is not executed in dry-run."""
        result = self._dry_run_result(expand_graph=True)
        self._assert_debug_view_early_return_defaults(result["debug_view"], "dry_run+expand_graph")

    def test_dry_run_with_cluster_aware_debug_view_early_return_defaults(self) -> None:
        """``debug_view`` must carry early-return defaults when ``dry_run=True`` and
        ``cluster_aware=True`` — cluster traversal is not executed in dry-run."""
        result = self._dry_run_result(cluster_aware=True)
        self._assert_debug_view_early_return_defaults(result["debug_view"], "dry_run+cluster_aware")


# ---------------------------------------------------------------------------
# TestEarlyReturnPrecedencePolicy
# ---------------------------------------------------------------------------


class TestEarlyReturnPrecedencePolicy:
    """Direct unit tests for the centralized :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` policy.

    These tests verify the *policy structure* itself — not the runtime behaviour
    (which is covered by :class:`TestMixedEarlyReturnSentinelEdge` and
    :class:`TestRunRetrievalAndQaEarlyReturnContract`).  The goal is to ensure that:

    - The policy is complete: exactly the two documented early-return rules exist.
    - The ordering is correct: dry_run (priority 1) comes before retrieval_skipped
      (priority 2).
    - Precedence metadata is accurate: ``wins_over`` reflects the runtime order.
    - The policy is *self-consistent* with the test-level key-set constants
      (:data:`_DRY_RUN_RESULT_REQUIRED_KEYS` and
      :data:`_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS`), meaning the constants can
      be *derived* from the policy + :data:`_LIVE_RESULT_REQUIRED_KEYS`.

    If any of these tests fail after a new early-return branch is added, update
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` and the corresponding key-set
    constants to keep the policy and the runtime in sync.
    """

    # ------------------------------------------------------------------
    # §1  Policy structure
    # ------------------------------------------------------------------

    def test_exactly_two_rules(self) -> None:
        """Policy must contain exactly two early-return rules (dry_run and retrieval_skipped)."""
        assert len(EARLY_RETURN_PRECEDENCE) == 2

    def test_priorities_are_unique(self) -> None:
        """Every rule must have a distinct priority value."""
        priorities = [r.priority for r in EARLY_RETURN_PRECEDENCE]
        assert len(priorities) == len(set(priorities))

    def test_rules_ordered_ascending_by_priority(self) -> None:
        """Rules in the tuple must appear in ascending priority order (index 0 = highest)."""
        priorities = [r.priority for r in EARLY_RETURN_PRECEDENCE]
        assert priorities == sorted(priorities)

    def test_rule_names_are_non_empty(self) -> None:
        """Every rule must carry a non-empty name string."""
        for rule in EARLY_RETURN_PRECEDENCE:
            assert rule.name, f"Rule at priority {rule.priority} has an empty name"

    def test_section_refs_are_present(self) -> None:
        """Every rule must carry a non-empty section_ref for cross-document traceability."""
        for rule in EARLY_RETURN_PRECEDENCE:
            assert rule.section_ref, f"Rule {rule.name!r} is missing section_ref"

    def test_rule_by_name_lookup_covers_all_rules(self) -> None:
        """``EARLY_RETURN_RULE_BY_NAME`` must map exactly the same rules as the tuple."""
        assert set(EARLY_RETURN_RULE_BY_NAME.keys()) == {r.name for r in EARLY_RETURN_PRECEDENCE}

    def test_wins_over_references_all_resolve(self) -> None:
        """All ``wins_over`` entries must reference a known rule name."""
        known = {r.name for r in EARLY_RETURN_PRECEDENCE}
        for rule in EARLY_RETURN_PRECEDENCE:
            unresolved = rule.wins_over - known
            assert not unresolved, (
                f"Rule {rule.name!r} wins_over references unknown name(s): {unresolved!r}"
            )

    # ------------------------------------------------------------------
    # §2  dry_run rule specifics (priority 1)
    # ------------------------------------------------------------------

    def test_first_rule_is_dry_run(self) -> None:
        """The first rule in EARLY_RETURN_PRECEDENCE (index 0) must be ``dry_run``."""
        assert EARLY_RETURN_PRECEDENCE[0].name == "dry_run"

    def test_dry_run_priority_is_1(self) -> None:
        """``dry_run`` rule must have priority 1 (highest precedence)."""
        assert EARLY_RETURN_RULE_BY_NAME["dry_run"].priority == 1

    def test_dry_run_outcome_status(self) -> None:
        """``dry_run`` rule must produce ``outcome_status="dry_run"``."""
        assert EARLY_RETURN_RULE_BY_NAME["dry_run"].outcome_status == "dry_run"

    def test_dry_run_wins_over_retrieval_skipped(self) -> None:
        """``dry_run.wins_over`` must contain ``"retrieval_skipped"`` — confirming that
        when both conditions are simultaneously true, the dry_run shape is returned."""
        assert "retrieval_skipped" in EARLY_RETURN_RULE_BY_NAME["dry_run"].wins_over

    def test_dry_run_absent_keys_contains_retrieval_skipped_key(self) -> None:
        """``dry_run.absent_keys`` must include ``"retrieval_skipped"`` — the flag is
        absent from the dry_run result shape (§5.1)."""
        assert "retrieval_skipped" in EARLY_RETURN_RULE_BY_NAME["dry_run"].absent_keys

    def test_dry_run_absent_keys_contains_hits(self) -> None:
        """``dry_run.absent_keys`` must include ``"hits"`` (no retrieval ran — §5.1)."""
        assert "hits" in EARLY_RETURN_RULE_BY_NAME["dry_run"].absent_keys

    def test_dry_run_absent_keys_contains_retrieval_results(self) -> None:
        """``dry_run.absent_keys`` must include ``"retrieval_results"`` (§5.1)."""
        assert "retrieval_results" in EARLY_RETURN_RULE_BY_NAME["dry_run"].absent_keys

    def test_dry_run_absent_keys_contains_warnings(self) -> None:
        """``dry_run.absent_keys`` must include ``"warnings"`` — no operational
        warnings are raised in dry-run mode (§5.1)."""
        assert "warnings" in EARLY_RETURN_RULE_BY_NAME["dry_run"].absent_keys

    # ------------------------------------------------------------------
    # §3  retrieval_skipped rule specifics (priority 2)
    # ------------------------------------------------------------------

    def test_second_rule_is_retrieval_skipped(self) -> None:
        """The second rule in EARLY_RETURN_PRECEDENCE (index 1) must be ``retrieval_skipped``."""
        assert EARLY_RETURN_PRECEDENCE[1].name == "retrieval_skipped"

    def test_retrieval_skipped_priority_is_2(self) -> None:
        """``retrieval_skipped`` rule must have priority 2."""
        assert EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"].priority == 2

    def test_retrieval_skipped_outcome_status_is_live(self) -> None:
        """``retrieval_skipped`` rule must produce ``outcome_status="live"`` — the
        result carries ``status="live"`` to distinguish it from the dry_run path (§5.3)."""
        assert EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"].outcome_status == "live"

    def test_retrieval_skipped_wins_over_nothing(self) -> None:
        """``retrieval_skipped.wins_over`` must be empty — it has the lowest priority
        among early-return rules and does not preempt any other condition."""
        assert not EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"].wins_over

    def test_retrieval_skipped_exclusive_keys_contains_retrieval_skipped_flag(self) -> None:
        """``retrieval_skipped.exclusive_keys`` must include ``"retrieval_skipped"`` —
        the flag is the canonical caller signal for this path (§5.3)."""
        assert "retrieval_skipped" in EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"].exclusive_keys

    # ------------------------------------------------------------------
    # §4  Cross-reference with test key-set constants
    # ------------------------------------------------------------------

    def test_dry_run_absent_keys_consistent_with_key_set_constant(self) -> None:
        """Applying ``dry_run.absent_keys`` to :data:`_LIVE_RESULT_REQUIRED_KEYS` must
        produce exactly :data:`_DRY_RUN_RESULT_REQUIRED_KEYS`.

        This cross-reference confirms that the policy's ``absent_keys`` set is the
        authoritative, in-one-place definition of what the key-set constant encodes.
        """
        rule = EARLY_RETURN_RULE_BY_NAME["dry_run"]
        derived = _LIVE_RESULT_REQUIRED_KEYS - rule.absent_keys
        assert derived == _DRY_RUN_RESULT_REQUIRED_KEYS, (
            "dry_run.absent_keys is inconsistent with _DRY_RUN_RESULT_REQUIRED_KEYS; "
            f"derived={derived - _DRY_RUN_RESULT_REQUIRED_KEYS!r} extra, "
            f"missing={_DRY_RUN_RESULT_REQUIRED_KEYS - derived!r}"
        )

    def test_retrieval_skipped_exclusive_keys_consistent_with_key_set_constant(self) -> None:
        """Applying ``retrieval_skipped.exclusive_keys`` to :data:`_LIVE_RESULT_REQUIRED_KEYS`
        must produce exactly :data:`_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS`.

        This cross-reference confirms that the policy's ``exclusive_keys`` set is the
        authoritative definition of what :data:`_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS`
        encodes relative to the live key set.
        """
        rule = EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]
        derived = _LIVE_RESULT_REQUIRED_KEYS | rule.exclusive_keys
        assert derived == _RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS, (
            "retrieval_skipped.exclusive_keys is inconsistent with "
            "_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS; "
            f"derived={derived - _RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS!r} extra, "
            f"missing={_RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS - derived!r}"
        )


# ---------------------------------------------------------------------------
# TestResolveEarlyReturnRule
# ---------------------------------------------------------------------------


class TestResolveEarlyReturnRule:
    """Unit tests for :func:`~demo.contracts.resolve_early_return_rule`.

    These tests verify that the resolver correctly maps runtime inputs to the
    matching :class:`~demo.contracts.EarlyReturnRule` (or ``None``) by
    evaluating conditions in :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE`
    order.  They do not go through ``run_retrieval_and_qa()`` — they exercise
    the helper in isolation.
    """

    # ------------------------------------------------------------------
    # No-match (live) path
    # ------------------------------------------------------------------

    def test_returns_none_when_no_rule_matches(self) -> None:
        """When ``is_dry_run=False`` and ``question`` is a non-None string,
        the resolver must return ``None`` (live retrieval should proceed)."""
        assert resolve_early_return_rule(is_dry_run=False, question="some question") is None

    def test_returns_none_for_empty_string_question(self) -> None:
        """An empty-string question with ``is_dry_run=False`` must return ``None`` —
        ``question=""`` is not a retrieval-skipping sentinel."""
        assert resolve_early_return_rule(is_dry_run=False, question="") is None

    # ------------------------------------------------------------------
    # dry_run rule (priority 1)
    # ------------------------------------------------------------------

    def test_returns_dry_run_when_is_dry_run_true(self) -> None:
        """When ``is_dry_run=True`` the resolver must return the ``dry_run`` rule."""
        rule = resolve_early_return_rule(is_dry_run=True, question="any question")
        assert rule is not None
        assert rule.name == "dry_run"

    def test_dry_run_beats_question_none(self) -> None:
        """When ``is_dry_run=True`` and ``question=None``, the resolver must return
        the ``dry_run`` rule — dry_run has higher priority than retrieval_skipped."""
        rule = resolve_early_return_rule(is_dry_run=True, question=None)
        assert rule is not None
        assert rule.name == "dry_run"

    def test_dry_run_beats_empty_question(self) -> None:
        """When ``is_dry_run=True`` and ``question=""``, the resolver must return
        the ``dry_run`` rule."""
        rule = resolve_early_return_rule(is_dry_run=True, question="")
        assert rule is not None
        assert rule.name == "dry_run"

    def test_dry_run_rule_outcome_status(self) -> None:
        """The returned ``dry_run`` rule must carry ``outcome_status='dry_run'``."""
        rule = resolve_early_return_rule(is_dry_run=True, question=None)
        assert rule is not None
        assert rule.outcome_status == "dry_run"

    # ------------------------------------------------------------------
    # retrieval_skipped rule (priority 2)
    # ------------------------------------------------------------------

    def test_returns_retrieval_skipped_when_question_is_none(self) -> None:
        """When ``is_dry_run=False`` and ``question=None``, the resolver must return
        the ``retrieval_skipped`` rule."""
        rule = resolve_early_return_rule(is_dry_run=False, question=None)
        assert rule is not None
        assert rule.name == "retrieval_skipped"

    def test_retrieval_skipped_rule_outcome_status(self) -> None:
        """The returned ``retrieval_skipped`` rule must carry ``outcome_status='live'``."""
        rule = resolve_early_return_rule(is_dry_run=False, question=None)
        assert rule is not None
        assert rule.outcome_status == "live"

    # ------------------------------------------------------------------
    # Returned object is the policy object (identity / reference check)
    # ------------------------------------------------------------------

    def test_returned_rule_is_from_precedence_table(self) -> None:
        """The resolver must return the same object instance as the matching entry
        in :data:`EARLY_RETURN_PRECEDENCE`, not a copy."""
        rule = resolve_early_return_rule(is_dry_run=True, question=None)
        assert rule is EARLY_RETURN_RULE_BY_NAME["dry_run"]

    def test_returned_retrieval_skipped_rule_is_from_precedence_table(self) -> None:
        """Resolver must return the same object instance as the ``retrieval_skipped``
        entry in :data:`EARLY_RETURN_PRECEDENCE`."""
        rule = resolve_early_return_rule(is_dry_run=False, question=None)
        assert rule is EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]


# ---------------------------------------------------------------------------
# TestEarlyReturnRulePayloadCorrespondence
# ---------------------------------------------------------------------------


class TestEarlyReturnRulePayloadCorrespondence:
    """Policy-backed correspondence tests: each early-return rule's declared metadata
    must align with the actual runtime payload returned by ``run_retrieval_and_qa()``.

    This class is the explicit **rule ↔ payload** seam.  For each current rule in
    :data:`~demo.contracts.EARLY_RETURN_PRECEDENCE` it drives
    ``run_retrieval_and_qa()`` with the canonical triggering inputs and asserts that:

    - ``result["status"]`` equals ``rule.outcome_status``
    - every key in ``rule.absent_keys`` is absent from the returned payload
    - every key in ``rule.exclusive_keys`` is present in the returned payload
    - :func:`~demo.contracts.resolve_early_return_rule` returns the same rule for
      those inputs (resolver ↔ runtime alignment)

    Failures report which rule fired and which invariant (status / absent / exclusive)
    was violated, making regressions from future rule additions immediately actionable.

    **Scope** — current rules covered:

    - ``dry_run`` (§5.1): ``dry_run=True`` + ``question=None``
    - ``retrieval_skipped`` (§5.2): ``dry_run=False`` + ``question=None``

    ``question=""`` is **not** covered here — it does not trigger any early-return
    rule and belongs to the live-retrieval path.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_result(**kwargs) -> dict[str, object]:
        """Return a dry-run result with ``question=None`` (canonical trigger for §5.1)."""
        return run_retrieval_and_qa(
            _DRY_RUN_CONFIG, run_id="dr-corr-1", source_uri=None, question=None, **kwargs
        )

    @staticmethod
    def _retrieval_skipped_result(**kwargs) -> dict[str, object]:
        """Return a retrieval-skipped result (``dry_run=False``, ``question=None``).

        The config intentionally uses empty/invalid Neo4j credentials so that, if the
        early-return for ``question is None`` regressed to occur after live config
        validation or driver creation, this path would start failing.

        Delegates to ``TestRunRetrievalAndQaEarlyReturnContract._skip_result`` to ensure
        a single source of truth for the skip-result configuration.
        """
        return TestRunRetrievalAndQaEarlyReturnContract._skip_result(**kwargs)

    # ------------------------------------------------------------------
    # §1  Resolver alignment — resolver agrees with the triggering inputs
    # ------------------------------------------------------------------

    def test_dry_run_resolver_returns_dry_run_rule(self) -> None:
        """``resolve_early_return_rule(is_dry_run=True, question=None)`` must return
        the ``dry_run`` rule — aligning the resolver with the dry-run runtime path."""
        rule = resolve_early_return_rule(is_dry_run=True, question=None)
        assert rule is not None, "Expected dry_run rule; resolver returned None"
        assert rule.name == "dry_run", (
            f"Expected rule name 'dry_run'; got {rule.name!r}"
        )

    def test_retrieval_skipped_resolver_returns_retrieval_skipped_rule(self) -> None:
        """``resolve_early_return_rule(is_dry_run=False, question=None)`` must return
        the ``retrieval_skipped`` rule — aligning the resolver with the skip runtime path."""
        rule = resolve_early_return_rule(is_dry_run=False, question=None)
        assert rule is not None, "Expected retrieval_skipped rule; resolver returned None"
        assert rule.name == "retrieval_skipped", (
            f"Expected rule name 'retrieval_skipped'; got {rule.name!r}"
        )

    def test_empty_string_question_is_not_an_early_return_trigger(self) -> None:
        """``question=""`` must not match any early-return rule.

        Confirms that this input is correctly excluded from the early-return suite
        and should proceed to the live-retrieval path.
        """
        rule = resolve_early_return_rule(is_dry_run=False, question="")
        assert rule is None, (
            f"question='' must not trigger any early-return rule; got {rule.name!r}"
        )

    # ------------------------------------------------------------------
    # §2  Status correspondence — result["status"] == rule.outcome_status
    # ------------------------------------------------------------------

    def test_dry_run_result_status_matches_rule_outcome_status(self) -> None:
        """The dry-run runtime payload ``status`` must equal ``dry_run.outcome_status``."""
        rule = EARLY_RETURN_RULE_BY_NAME["dry_run"]
        result = self._dry_run_result()
        assert result["status"] == rule.outcome_status, (
            f"[{rule.name}] status mismatch: "
            f"got {result['status']!r}, rule declares {rule.outcome_status!r} "
            f"({rule.section_ref})"
        )

    def test_retrieval_skipped_result_status_matches_rule_outcome_status(self) -> None:
        """The retrieval-skipped runtime payload ``status`` must equal
        ``retrieval_skipped.outcome_status``."""
        rule = EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]
        result = self._retrieval_skipped_result()
        assert result["status"] == rule.outcome_status, (
            f"[{rule.name}] status mismatch: "
            f"got {result['status']!r}, rule declares {rule.outcome_status!r} "
            f"({rule.section_ref})"
        )

    # ------------------------------------------------------------------
    # §3  Absent-key correspondence — rule.absent_keys ∩ result.keys() == ∅
    # ------------------------------------------------------------------

    def test_dry_run_absent_keys_are_absent_from_runtime_payload(self) -> None:
        """Every key in ``dry_run.absent_keys`` must be absent from the dry-run
        runtime payload."""
        rule = EARLY_RETURN_RULE_BY_NAME["dry_run"]
        result = self._dry_run_result()
        present = rule.absent_keys & set(result.keys())
        assert not present, (
            f"[{rule.name}] absent_keys present in runtime payload: {present!r} "
            f"({rule.section_ref})"
        )

    def test_retrieval_skipped_absent_keys_are_absent_from_runtime_payload(self) -> None:
        """Every key in ``retrieval_skipped.absent_keys`` must be absent from the
        retrieval-skipped runtime payload.

        The set is currently empty for this rule; this test guards against a future
        regression where a key is added to ``absent_keys`` without updating the
        runtime payload construction.
        """
        rule = EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]
        result = self._retrieval_skipped_result()
        present = rule.absent_keys & set(result.keys())
        assert not present, (
            f"[{rule.name}] absent_keys present in runtime payload: {present!r} "
            f"({rule.section_ref})"
        )

    # ------------------------------------------------------------------
    # §4  Exclusive-key correspondence — rule.exclusive_keys ⊆ result.keys()
    # ------------------------------------------------------------------

    def test_dry_run_exclusive_keys_are_present_in_runtime_payload(self) -> None:
        """Every key in ``dry_run.exclusive_keys`` must be present in the dry-run
        runtime payload.

        The set is currently empty for this rule; this test guards against a future
        regression where a key is added to ``exclusive_keys`` without updating the
        runtime payload construction.
        """
        rule = EARLY_RETURN_RULE_BY_NAME["dry_run"]
        result = self._dry_run_result()
        missing = rule.exclusive_keys - set(result.keys())
        assert not missing, (
            f"[{rule.name}] exclusive_keys missing from runtime payload: {missing!r} "
            f"({rule.section_ref})"
        )

    def test_retrieval_skipped_exclusive_keys_are_present_in_runtime_payload(self) -> None:
        """Every key in ``retrieval_skipped.exclusive_keys`` must be present in the
        retrieval-skipped runtime payload.

        Specifically, ``retrieval_skipped=True`` must appear as the caller-visible
        signal for this path (§5.3).
        """
        rule = EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]
        result = self._retrieval_skipped_result()
        missing = rule.exclusive_keys - set(result.keys())
        assert not missing, (
            f"[{rule.name}] exclusive_keys missing from runtime payload: {missing!r} "
            f"({rule.section_ref})"
        )

    # ------------------------------------------------------------------
    # §5  Exclusivity symmetry — one rule's exclusive keys absent from other's payload
    # ------------------------------------------------------------------

    def test_retrieval_skipped_exclusive_keys_absent_from_dry_run_payload(self) -> None:
        """``retrieval_skipped``'s exclusive keys must not appear in the dry-run
        runtime payload — the two rule paths must be disjoint for these keys."""
        rule = EARLY_RETURN_RULE_BY_NAME["retrieval_skipped"]
        result = self._dry_run_result()
        leaked = rule.exclusive_keys & set(result.keys())
        assert not leaked, (
            f"[dry_run] retrieval_skipped exclusive_keys leaked into dry_run payload: "
            f"{leaked!r}"
        )

    # ------------------------------------------------------------------
    # §6  Mixed dry-run modifiers preserve absent-key semantics
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "modifier",
        [
            {"all_runs": True},
            {"expand_graph": True},
            {"cluster_aware": True},
        ],
        ids=["all_runs", "expand_graph", "cluster_aware"],
    )
    def test_dry_run_absent_keys_preserved_with_retrieval_modifier(
        self, modifier: dict[str, bool]
    ) -> None:
        """Passing retrieval-mode modifiers alongside ``dry_run=True`` must not inject
        any of ``dry_run.absent_keys`` into the runtime payload.

        The dry-run short-circuit runs before any retrieval logic, so these modifiers
        must have no effect on the returned key set.
        """
        rule = EARLY_RETURN_RULE_BY_NAME["dry_run"]
        result = self._dry_run_result(**modifier)
        present = rule.absent_keys & set(result.keys())
        modifier_name = next(iter(modifier))
        assert not present, (
            f"[dry_run+{modifier_name}] absent_keys injected into payload: {present!r} "
            f"({rule.section_ref})"
        )


# ---------------------------------------------------------------------------
# TestProjectPostprocessToPublic
# ---------------------------------------------------------------------------

#: Exact set of all public keys in a ``_PostprocessPublicFields`` dict.
#: Derived from the TypedDict's own annotations so that any drift between
#: the TypedDict definition and :data:`_POSTPROCESS_FIELD_MAP` is caught
#: at import time by the assertion immediately below.
_POSTPROCESS_PUBLIC_KEYS: frozenset[str] = frozenset(
    _PostprocessPublicFields.__annotations__
)
assert _POSTPROCESS_PUBLIC_KEYS == frozenset(_POSTPROCESS_FIELD_MAP.values()), (
    "_PostprocessPublicFields annotations do not match _POSTPROCESS_FIELD_MAP values; "
    f"extra in TypedDict={_POSTPROCESS_PUBLIC_KEYS - frozenset(_POSTPROCESS_FIELD_MAP.values())!r}, "
    f"missing from TypedDict={frozenset(_POSTPROCESS_FIELD_MAP.values()) - _POSTPROCESS_PUBLIC_KEYS!r}"
)


class TestProjectPostprocessToPublic:
    """Direct unit tests for the :func:`_project_postprocess_to_public` adapter.

    These tests exercise the adapter function in isolation — calling it with
    a known :class:`_AnswerPostprocessResult` and asserting that every public
    key carries the correctly projected value.  Unlike the spy-based tests in
    :class:`TestRunRetrievalAndQaPostprocessMapping`, these tests do not go
    through the full ``run_retrieval_and_qa`` stack, making each mapping
    assertion cheaper and more explicit.
    """

    def _pp(self, answer: str, hits: list, all_runs: bool):
        """Return a ``_postprocess_answer`` result for the given inputs."""
        return _postprocess_answer(answer, hits, all_runs=all_runs)

    def test_returns_postprocess_public_fields_key_set(self) -> None:
        """``_project_postprocess_to_public`` must return exactly the documented
        ``_PostprocessPublicFields`` key set — no extra, no missing keys."""
        pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        assert set(pub.keys()) == _POSTPROCESS_PUBLIC_KEYS, (
            f"Key set mismatch: extra={set(pub.keys()) - _POSTPROCESS_PUBLIC_KEYS!r}, "
            f"missing={_POSTPROCESS_PUBLIC_KEYS - set(pub.keys())!r}"
        )

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs",
        [
            ("fully_cited", _CITED_ANSWER, [_HIT], True),
            ("repair_applied", _UNCITED_ANSWER, [_HIT], True),
            ("fallback_run_scoped", _UNCITED_ANSWER, [_HIT], False),
            ("fallback_all_runs_no_hits", _UNCITED_ANSWER, [], True),
            ("empty_answer", "", [], True),
        ],
        ids=["fully_cited", "repair_applied", "fallback_run_scoped",
             "fallback_all_runs_no_hits", "empty_answer"],
    )
    def test_key_set_is_stable_across_scenarios(
        self, scenario: str, answer: str, hits: list, all_runs: bool
    ) -> None:
        """The returned key set must be identical for every scenario."""
        pp = self._pp(answer, hits, all_runs=all_runs)
        pub = _project_postprocess_to_public(pp)
        assert set(pub.keys()) == _POSTPROCESS_PUBLIC_KEYS, (
            f"[{scenario}] Key set mismatch: "
            f"extra={set(pub.keys()) - _POSTPROCESS_PUBLIC_KEYS!r}, "
            f"missing={_POSTPROCESS_PUBLIC_KEYS - set(pub.keys())!r}"
        )

    def test_answer_maps_from_display_answer(self) -> None:
        """``pub['answer']`` must equal ``pp['display_answer']`` (the rename)."""
        pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        assert pub["answer"] == pp["display_answer"]

    def test_answer_is_not_raw_answer(self) -> None:
        """``pub['answer']`` must come from ``display_answer``, not ``raw_answer``.

        Uses a synthetic *pp* where ``display_answer`` is intentionally set to
        differ from ``raw_answer``, so the assertion does not depend on any
        specific repair or fallback behavior.
        """
        base_pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pp = dict(base_pp)
        pp["raw_answer"] = "original raw answer"
        pp["display_answer"] = "different display answer"
        pub = _project_postprocess_to_public(pp)
        assert pub["answer"] == pp["display_answer"]
        assert pub["answer"] != pp["raw_answer"], (
            "pub['answer'] must come from display_answer, not raw_answer"
        )

    def test_all_answers_cited_maps_from_all_cited(self) -> None:
        """``pub['all_answers_cited']`` must equal ``pp['all_cited']`` (the rename)."""
        pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        assert pub["all_answers_cited"] == pp["all_cited"]

    def test_all_answers_cited_is_not_raw_answer_all_cited(self) -> None:
        """``all_answers_cited`` reflects final citation state (``all_cited``),
        not ``raw_answer_all_cited``, which reflects the original LLM output.

        Uses a synthetic *pp* where ``all_cited`` and ``raw_answer_all_cited``
        are intentionally set to differ, so the assertion does not depend on any
        specific repair behavior.
        """
        base_pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pp = dict(base_pp)
        pp["all_cited"] = True
        pp["raw_answer_all_cited"] = False
        pub = _project_postprocess_to_public(pp)
        assert pub["all_answers_cited"] == pp["all_cited"]
        assert pub["all_answers_cited"] is True
        assert pp["raw_answer_all_cited"] is False, (
            "raw_answer_all_cited must reflect the original LLM output, not the repaired result"
        )

    def test_pass_through_fields_match_exactly(self) -> None:
        """Fields that are not renamed must be passed through unchanged from *pp*.

        Uses ``_POSTPROCESS_FIELD_MAP`` to identify pass-through fields
        (those where the internal key equals the public key) to avoid
        maintaining a duplicate mapping here.
        """
        pp = self._pp(_UNCITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        pass_through = {
            pp_key: pub_key
            for pp_key, pub_key in _POSTPROCESS_FIELD_MAP.items()
            if pp_key == pub_key  # identity mappings only (no renames)
        }
        for pp_key, pub_key in pass_through.items():
            assert pub[pub_key] == pp[pp_key], (
                f"Pass-through field {pub_key!r}: "
                f"expected {pp[pp_key]!r}, got {pub[pub_key]!r}"
            )

    @pytest.mark.parametrize(
        "scenario,answer,hits,all_runs",
        [
            ("fully_cited", _CITED_ANSWER, [_HIT], True),
            ("repair_applied", _UNCITED_ANSWER, [_HIT], True),
            ("fallback_run_scoped", _UNCITED_ANSWER, [_HIT], False),
            ("fallback_all_runs_no_hits", _UNCITED_ANSWER, [], True),
            ("empty_answer", "", [], True),
        ],
        ids=["fully_cited", "repair_applied", "fallback_run_scoped",
             "fallback_all_runs_no_hits", "empty_answer"],
    )
    def test_all_field_mappings_hold_for_all_scenarios(
        self, scenario: str, answer: str, hits: list, all_runs: bool
    ) -> None:
        """Every entry in ``_POSTPROCESS_FIELD_MAP`` must hold for the
        projected result: ``pub[public_key] == pp[pp_key]``."""
        pp = self._pp(answer, hits, all_runs=all_runs)
        pub = _project_postprocess_to_public(pp)
        for pp_key, public_key in _POSTPROCESS_FIELD_MAP.items():
            assert pub[public_key] == pp[pp_key], (
                f"[{scenario}] Mapping {pp_key!r} → {public_key!r} failed: "
                f"pub[{public_key!r}]={pub[public_key]!r}, "
                f"pp[{pp_key!r}]={pp[pp_key]!r}"
            )

    def test_fallback_answer_carries_prefix_in_public_answer(self) -> None:
        """When fallback is applied, ``pub['answer']`` must start with the fallback
        prefix because the adapter maps ``display_answer`` (which carries the prefix)."""
        pp = self._pp(_UNCITED_ANSWER, [], all_runs=False)
        pub = _project_postprocess_to_public(pp)
        assert pp["citation_fallback_applied"] is True
        assert pub["answer"].startswith(_CITATION_FALLBACK_PREFIX), (
            "pub['answer'] must carry the fallback prefix when citation_fallback_applied=True"
        )

    def test_citation_quality_bundle_identity(self) -> None:
        """``pub['citation_quality']`` must be the exact same dict object as
        ``pp['citation_quality']`` (no copy, no re-packing)."""
        pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        assert pub["citation_quality"] is pp["citation_quality"], (
            "citation_quality should be the same dict object (no deep-copy)"
        )

    def test_return_type_annotation_matches_postprocess_public_fields(self) -> None:
        """The result of ``_project_postprocess_to_public`` must be an instance
        (structural) of ``_PostprocessPublicFields`` — i.e. a plain dict with the
        exact documented key set."""
        pp = self._pp(_CITED_ANSWER, [_HIT], all_runs=True)
        pub: _PostprocessPublicFields = _project_postprocess_to_public(pp)
        # TypedDicts are plain dicts at runtime; verify the key set is sufficient.
        assert isinstance(pub, dict)
        assert set(pub.keys()) == _POSTPROCESS_PUBLIC_KEYS


class TestRunRetrievalAndQaWarningsContract:
    """Protect the ``warnings`` / ``citation_warnings`` propagation invariants.

    From §2.5.2 of the contract document:
    - ``warnings`` is the top-level operational warnings list (superset).
    - ``citation_quality["citation_warnings"]`` contains **only** citation-quality
      warnings.
    - Every entry in ``citation_warnings`` must also appear in ``warnings``.
    - ``warnings`` may contain additional operational warnings not in
      ``citation_warnings`` (e.g. missing optional citation fields).
    """

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        _LIVE_SCENARIOS,
        ids=_LIVE_SCENARIO_IDS,
    )
    def test_citation_warnings_are_subset_of_top_level_warnings(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """Every warning in ``citation_quality['citation_warnings']`` must also
        appear on every surface in ``propagates_to`` (invariant §3.7).

        Propagation targets are read from
        :data:`~demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY`
        ``["citation_warnings"].propagates_to`` so this assertion stays anchored
        to the policy declaration rather than hard-coded surface names.
        """
        propagates_to = RETRIEVAL_METADATA_SURFACE_POLICY["citation_warnings"].propagates_to
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        for surface in propagates_to:
            assert surface in result, (
                f"[{scenario}] surface {surface!r} missing from result "
                f"(policy propagates_to={list(propagates_to)!r}); "
                f"got keys={list(result.keys())!r}"
            )
            surface_values = result[surface]
            for w in cq["citation_warnings"]:
                assert w in surface_values, (
                    f"[{scenario}] citation_quality warning {w!r} missing from "
                    f"{surface!r} (policy propagates_to={list(propagates_to)!r}); "
                    f"got {surface}={surface_values!r}"
                )

    def test_empty_chunk_warning_appears_in_both_lists(self) -> None:
        """An empty-chunk-text warning must appear in both ``warnings`` and
        ``citation_quality['citation_warnings']`` because it represents a
        citation-quality issue (the cited chunk carried no usable text evidence)."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_EMPTY_CHUNK_METADATA],
            all_runs=True,
        )
        assert _EMPTY_CHUNK_WARNING_MSG in result["warnings"], (
            f"Empty-chunk warning missing from top-level warnings; "
            f"got {result['warnings']!r}"
        )
        cq = result["citation_quality"]
        assert _EMPTY_CHUNK_WARNING_MSG in cq["citation_warnings"], (
            f"Empty-chunk warning missing from citation_quality.citation_warnings; "
            f"got {cq['citation_warnings']!r}"
        )
        assert cq["evidence_level"] == "degraded", (
            "evidence_level must be 'degraded' when an empty-chunk warning exists, "
            "even if the answer is fully cited"
        )

    def test_uncited_answer_warning_propagated_to_top_level_warnings(self) -> None:
        """The uncited-answer warning added by ``_postprocess_answer`` must be
        propagated to the top-level ``warnings`` list."""
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[],
            all_runs=False,
            run_id="r1",
        )
        assert _UNCITED_WARNING in result["warnings"], (
            f"Uncited-answer warning missing from top-level warnings; "
            f"got {result['warnings']!r}"
        )
        assert _UNCITED_WARNING in result["citation_quality"]["citation_warnings"], (
            f"Uncited-answer warning missing from citation_quality.citation_warnings; "
            f"got {result['citation_quality']['citation_warnings']!r}"
        )

    def test_warnings_type_is_list_of_str(self) -> None:
        """``warnings`` must be a list of strings for all scenarios."""
        scenarios = [
            (_CITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            (_UNCITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            (_UNCITED_ANSWER, [], False, "r1"),
            ("", [], True, None),
        ]
        for answer, meta, all_runs, run_id in scenarios:
            result = _run_with_mocked_retrieval(
                answer=answer, items_metadata=meta, all_runs=all_runs, run_id=run_id
            )
            assert isinstance(result["warnings"], list), (
                f"warnings expected list for answer={answer!r}"
            )
            for item in result["warnings"]:
                assert isinstance(item, str), (
                    f"warnings entry expected str, got {type(item).__name__} "
                    f"for answer={answer!r}"
                )

    def test_fully_cited_answer_no_warnings(self) -> None:
        """A fully cited answer with no retrieval-time issues must produce
        empty ``warnings`` and ``citation_quality['citation_warnings']`` lists."""
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        assert result["warnings"] == [], (
            f"Expected empty warnings for fully cited answer; got {result['warnings']!r}"
        )
        cq = result["citation_quality"]
        assert cq["citation_warnings"] == [], (
            f"Expected empty citation_warnings; got {cq['citation_warnings']!r}"
        )
        assert cq["warning_count"] == 0


# ---------------------------------------------------------------------------
# TestMetadataTaxonomyBoundaries
# ---------------------------------------------------------------------------


class TestMetadataTaxonomyBoundaries:
    """Enforce the four-surface metadata taxonomy defined in §2.6 of the contract document.

    The four surfaces are:
    - ``warnings`` (top-level operational warnings list; superset for all warning strings)
    - ``citation_quality`` bundle (citation-quality details; its ``citation_warnings`` list
      is a subset of ``warnings``)
    - ``malformed_diagnostics_count`` (telemetry counter, NOT a warning)
    - ``debug_view`` (supported inspection-oriented surface, NOT a top-level API surface)

    These tests cover representative, ambiguous, and combined scenarios to prevent
    future contributors from accidentally migrating a field to the wrong surface.
    See §2.6, §3.10, §3.11, and §2.9 of the canonical contract document.

    In addition to the four-surface taxonomy, this class enforces the ``debug_view``
    field-level mirroring rules from §2.9:
    - Mirrored fields (same name at top-level and in ``debug_view``) carry identical values.
    - Inspection-only fields (``all_cited``, ``evidence_level``, ``warning_count``,
      ``citation_warnings``) must not appear as direct top-level keys on any result shape.
    - The ``all_answers_cited`` / ``all_cited`` name distinction is explicitly tested:
      ``all_answers_cited`` is the public alias; ``all_cited`` is the inspection-only name.
    """

    def test_malformed_diagnostics_count_nonzero_does_not_add_to_warnings(self) -> None:
        """Telemetry counter must not pollute ``warnings`` (invariant §3.10).

        When ``malformed_diagnostics_count > 0``, no entry is added to the
        top-level ``warnings`` list.  The counter is a machine-readable alerting
        signal; callers must read it directly from the integer field.
        """
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_MALFORMED_DIAGNOSTICS_METADATA],
            all_runs=True,
        )
        assert result["malformed_diagnostics_count"] > 0, (
            "Expected malformed_diagnostics_count > 0 for hit with malformed diagnostics; "
            f"got {result['malformed_diagnostics_count']!r}"
        )
        assert result["warnings"] == [], (
            "Telemetry counter malformed_diagnostics_count must not add entries to "
            f"warnings; got {result['warnings']!r}"
        )
        assert result["citation_quality"]["citation_warnings"] == [], (
            "Telemetry counter malformed_diagnostics_count must not add entries to "
            f"citation_quality.citation_warnings; got "
            f"{result['citation_quality']['citation_warnings']!r}"
        )

    def test_debug_view_keys_not_in_top_level_result(self) -> None:
        """``debug_view`` must not introduce new top-level keys (invariant §3.11).

        ``debug_view`` intentionally mirrors some top-level keys — specifically
        those that appear in both ``_DEBUG_VIEW_REQUIRED_KEYS`` and
        ``_LIVE_RESULT_REQUIRED_KEYS`` (see §2.9 mirroring convention and
        §3.11).  Other ``debug_view`` keys use internal names (e.g.
        ``all_cited``) that differ from the public aliases at the top level
        (e.g. ``all_answers_cited``) and must NOT appear at the top level.

        The key invariant is that ``debug_view`` must not cause any extra keys
        to appear at the top level of the result beyond those in
        ``_LIVE_RESULT_REQUIRED_KEYS``.
        """
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        top_level_keys = set(result.keys()) - {"debug_view"}
        debug_view_keys = set(result["debug_view"].keys())
        # Derive the set of intentionally shared keys from the intersection of the
        # two documented key-set constants rather than hardcoding them here.  This
        # ensures the test stays in sync automatically if either constant changes.
        allowed_shared_keys: frozenset[str] = _DEBUG_VIEW_REQUIRED_KEYS & _LIVE_RESULT_REQUIRED_KEYS
        # Enforce the mirroring convention: all allowed shared keys must be present
        # both at the top level and inside debug_view.
        assert allowed_shared_keys <= top_level_keys, (
            "Shared keys documented by the mirroring convention must be present at "
            f"the top level; missing={allowed_shared_keys - top_level_keys!r}"
        )
        assert allowed_shared_keys <= debug_view_keys, (
            "Shared keys documented by the mirroring convention must be present in "
            f"debug_view; missing={allowed_shared_keys - debug_view_keys!r}"
        )
        # debug_view-exclusive keys (those that are NOT already top-level fields)
        # must never appear as new direct top-level keys.
        forbidden_overlap = (debug_view_keys & top_level_keys) - allowed_shared_keys
        assert not forbidden_overlap, (
            "debug_view-exclusive keys must not appear as direct top-level keys in "
            f"the result dict; forbidden overlap={forbidden_overlap!r}"
        )
        # The overall top-level key set must equal the documented required set —
        # debug_view must not have introduced any extra top-level keys.
        assert set(result.keys()) == _LIVE_RESULT_REQUIRED_KEYS, (
            "debug_view must not introduce new top-level keys beyond the documented set; "
            f"extra={set(result.keys()) - _LIVE_RESULT_REQUIRED_KEYS!r}"
        )

    def test_combined_empty_chunk_and_uncited_answer_both_in_citation_warnings(
        self,
    ) -> None:
        """Combined ambiguous scenario: empty-chunk warning + uncited-answer warning.

        Both warnings are citation-quality issues (§2.6 taxonomy rule 1).  In
        all-runs mode with an empty-chunk hit and an uncited answer, repair is
        attempted but yields a fully cited result (token appended).  To produce
        both warnings simultaneously, use run-scoped mode (no repair) so the
        uncited-answer warning is also raised.

        Both warnings must appear in ``warnings`` **and** in
        ``citation_quality["citation_warnings"]``.
        """
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_EMPTY_CHUNK_METADATA],
            all_runs=False,
            run_id="r1",
        )
        cq = result["citation_quality"]
        assert _EMPTY_CHUNK_WARNING_MSG in result["warnings"], (
            f"Empty-chunk warning missing from top-level warnings; "
            f"got {result['warnings']!r}"
        )
        assert _EMPTY_CHUNK_WARNING_MSG in cq["citation_warnings"], (
            f"Empty-chunk warning missing from citation_quality.citation_warnings; "
            f"got {cq['citation_warnings']!r}"
        )
        assert _UNCITED_WARNING in result["warnings"], (
            f"Uncited-answer warning missing from top-level warnings; "
            f"got {result['warnings']!r}"
        )
        assert _UNCITED_WARNING in cq["citation_warnings"], (
            f"Uncited-answer warning missing from citation_quality.citation_warnings; "
            f"got {cq['citation_warnings']!r}"
        )
        assert cq["evidence_level"] == "degraded", (
            "evidence_level must be 'degraded' when citation warnings exist"
        )

    def test_debug_view_mirrors_public_postprocessing_state(self) -> None:
        """``debug_view`` consolidates the same postprocessing state as the public surface.

        The fields in ``debug_view`` are derived from ``_AnswerPostprocessResult``
        (the same source as the public result dict).  This test verifies that the
        values in ``debug_view`` are consistent with the corresponding public fields
        so the debug surface cannot silently drift from the live result.
        """
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        dv = result["debug_view"]
        assert dv["all_cited"] == result["all_answers_cited"], (
            "debug_view.all_cited must mirror top-level all_answers_cited"
        )
        assert dv["raw_answer_all_cited"] == result["raw_answer_all_cited"], (
            "debug_view.raw_answer_all_cited must mirror top-level raw_answer_all_cited"
        )
        assert dv["citation_repair_attempted"] == result["citation_repair_attempted"], (
            "debug_view.citation_repair_attempted must mirror top-level field"
        )
        assert dv["citation_repair_applied"] == result["citation_repair_applied"], (
            "debug_view.citation_repair_applied must mirror top-level field"
        )
        assert dv["citation_fallback_applied"] == result["citation_fallback_applied"], (
            "debug_view.citation_fallback_applied must mirror top-level field"
        )
        assert dv["evidence_level"] == result["citation_quality"]["evidence_level"], (
            "debug_view.evidence_level must mirror citation_quality.evidence_level"
        )
        assert dv["warning_count"] == result["citation_quality"]["warning_count"], (
            "debug_view.warning_count must mirror citation_quality.warning_count"
        )
        assert dv["citation_warnings"] == result["citation_quality"]["citation_warnings"], (
            "debug_view.citation_warnings must mirror citation_quality.citation_warnings"
        )
        assert dv["malformed_diagnostics_count"] == result["malformed_diagnostics_count"], (
            "debug_view.malformed_diagnostics_count must mirror top-level field"
        )

    def test_all_answers_cited_is_public_alias_all_cited_is_inspection_only(self) -> None:
        """``all_answers_cited`` is the public top-level alias; ``all_cited`` is the
        inspection-only name used inside ``debug_view`` (and ``citation_quality``).

        The naming distinction is deliberate (§2.9 field classification table):
        - ``all_answers_cited`` is the public key at the top level.
        - ``all_cited`` is the internal/inspection name and must NOT appear as a
          direct top-level key.
        - ``debug_view["all_cited"]`` and ``result["all_answers_cited"]`` mirror the
          same value under different names.

        This test exercises both a True and a False case to confirm the mirror holds
        regardless of the specific citation outcome.
        """
        # Fully cited — all_answers_cited=True, debug_view.all_cited=True
        result_cited = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        assert "all_answers_cited" in result_cited, (
            "all_answers_cited must be present at the top level"
        )
        assert "all_cited" not in result_cited, (
            "all_cited must NOT appear as a direct top-level key (it is inspection-only)"
        )
        assert result_cited["debug_view"]["all_cited"] == result_cited["all_answers_cited"], (
            "debug_view.all_cited must mirror top-level all_answers_cited (True case)"
        )
        assert result_cited["all_answers_cited"] is True

        # Uncited — all_answers_cited=False (repair applied but still uncited impossible in
        # one-hit all-runs: repair makes it cited; use run-scoped so repair doesn't run)
        result_uncited = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=False,
            run_id="r1",
        )
        assert "all_answers_cited" in result_uncited, (
            "all_answers_cited must be present at the top level (uncited case)"
        )
        assert "all_cited" not in result_uncited, (
            "all_cited must NOT appear as a direct top-level key (uncited case)"
        )
        assert result_uncited["debug_view"]["all_cited"] == result_uncited["all_answers_cited"], (
            "debug_view.all_cited must mirror top-level all_answers_cited (False case)"
        )
        assert result_uncited["all_answers_cited"] is False

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        _LIVE_SCENARIOS,
        ids=_LIVE_SCENARIO_IDS,
    )
    def test_debug_view_mirrors_values_consistent_across_live_scenarios(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """For every documented live scenario, ``debug_view`` values must be consistent
        with their corresponding top-level and ``citation_quality`` counterparts.

        Delegates to :func:`_assert_debug_view_mirrors_policy` which derives all
        mirroring relationships from :data:`RETRIEVAL_METADATA_SURFACE_POLICY`,
        so that adding a new field to the policy automatically extends coverage here.
        """
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        _assert_debug_view_mirrors_policy(result, scenario)

    @pytest.mark.parametrize(
        "path_label,required_keys",
        [
            ("dry_run", _DRY_RUN_RESULT_REQUIRED_KEYS),
            ("retrieval_skipped", _RETRIEVAL_SKIPPED_RESULT_REQUIRED_KEYS),
        ],
        ids=["dry_run", "retrieval_skipped"],
    )
    def test_debug_view_exclusive_keys_not_in_top_level_for_early_return_paths(
        self,
        path_label: str,
        required_keys: frozenset[str],
    ) -> None:
        """``debug_view``-exclusive keys must not appear as direct top-level keys
        for early-return paths (dry_run and retrieval_skipped), mirroring the
        invariant already enforced for the live path (§3.11).

        The same mirroring convention applies across all result shapes: keys that
        are inspection-only in ``debug_view`` (e.g. ``all_cited``, ``evidence_level``,
        ``warning_count``, ``citation_warnings``) must never leak to the top level.
        """
        helper = TestRunRetrievalAndQaEarlyReturnContract()
        result = (
            helper._dry_run_result()
            if path_label == "dry_run"
            else helper._skip_result()
        )
        top_level_keys = set(result.keys()) - {"debug_view"}
        debug_view_keys = set(result["debug_view"].keys())
        # Mirrored top-level keys: debug_view fields that legitimately appear at both
        # the top level and inside debug_view (the intentional mirroring convention, §2.9).
        mirrored_top_level_keys: frozenset[str] = _DEBUG_VIEW_REQUIRED_KEYS & required_keys
        # Forbidden overlap: debug_view-exclusive keys appearing at the top level
        forbidden_overlap = (debug_view_keys & top_level_keys) - mirrored_top_level_keys
        assert not forbidden_overlap, (
            f"[{path_label}] debug_view-exclusive keys must not appear as direct top-level keys; "
            f"forbidden overlap={forbidden_overlap!r}"
        )
        # The top-level key set must equal the documented required set for this path
        assert set(result.keys()) == required_keys, (
            f"[{path_label}] debug_view must not introduce new top-level keys beyond the "
            f"documented set; extra={set(result.keys()) - required_keys!r}, "
            f"missing={required_keys - set(result.keys())!r}"
        )

    def test_mixed_citation_and_operational_warnings_superset_contract(self) -> None:
        """Mixed-warning scenario: top-level ``warnings`` is a **strict superset** of
        ``citation_quality["citation_warnings"]`` when both warning types coexist.

        This is the runtime-facing contract for the ``propagates_to`` semantics
        introduced in the retrieval metadata policy (§3.7 superset invariant).

        Scenario
        --------
        A single retrieval result contains:

        - One **citation-quality** warning — the uncited-answer warning added by
          ``_postprocess_answer()`` when no sentence carries a citation token.
          This warning must appear in **both** ``citation_quality["citation_warnings"]``
          **and** top-level ``warnings`` (§2.6 rule 1 / propagates_to).
        - One **operational** informational warning — a chunk-level warning for a
          hit whose ``citation_object`` is missing optional fields (``page``,
          ``start_char``, ``end_char``).  This warning is added to top-level
          ``warnings`` only; it must **not** appear in
          ``citation_quality["citation_warnings"]`` (§2.6 rule 4).

        Together these two warnings prove the superset relationship: every entry in
        ``citation_quality["citation_warnings"]`` propagates to top-level ``warnings``,
        but top-level ``warnings`` may contain additional operational entries that are
        not citation-quality problems.

        Assertions are anchored to
        :data:`~demo.contracts.RETRIEVAL_METADATA_SURFACE_POLICY`
        ``["citation_warnings"].propagates_to`` so the test stays in sync with the
        policy model rather than hard-coding surface names.
        """
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[_MISSING_OPTIONAL_FIELDS_METADATA],
            all_runs=False,
            run_id="r1",
        )
        cq = result["citation_quality"]
        dv = result["debug_view"]

        # Fixture preconditions: the scenario must contain at least one citation
        # warning and at least one operational warning so the superset is strict.
        assert _UNCITED_WARNING in cq["citation_warnings"], (
            f"Fixture precondition failed: expected uncited-answer citation warning; "
            f"got citation_warnings={cq['citation_warnings']!r}"
        )
        assert _MISSING_OPTIONAL_FIELDS_WARNING in result["warnings"], (
            f"Fixture precondition failed: expected operational warning for missing "
            f"optional fields; got warnings={result['warnings']!r}"
        )
        assert _MISSING_OPTIONAL_FIELDS_WARNING not in cq["citation_warnings"], (
            f"Fixture precondition failed: operational warning must NOT be in "
            f"citation_warnings; got citation_warnings={cq['citation_warnings']!r}"
        )

        # ── Core superset invariant (§3.7) ──────────────────────────────────────
        # Every citation warning must appear on every surface listed in propagates_to.
        # Anchored to the policy so surface changes are caught automatically.
        propagates_to = RETRIEVAL_METADATA_SURFACE_POLICY["citation_warnings"].propagates_to
        for surface in propagates_to:
            surface_values = result[surface]
            for w in cq["citation_warnings"]:
                assert w in surface_values, (
                    f"Citation warning {w!r} missing from propagation target "
                    f"{surface!r} (policy propagates_to={list(propagates_to)!r}); "
                    f"got {surface}={surface_values!r}"
                )

        # Top-level warnings is a strict superset of citation_warnings.
        assert set(cq["citation_warnings"]) <= set(result["warnings"]), (
            "citation_quality['citation_warnings'] must be a subset of top-level "
            f"warnings; citation_warnings={cq['citation_warnings']!r}, "
            f"warnings={result['warnings']!r}"
        )
        assert len(result["warnings"]) > len(cq["citation_warnings"]), (
            "top-level warnings must contain additional operational entries beyond "
            "citation_warnings in the mixed-warning scenario; "
            f"warnings={result['warnings']!r}, "
            f"citation_warnings={cq['citation_warnings']!r}"
        )

        # ── debug_view mirrors citation_quality, not the full top-level warnings ─
        assert dv["citation_warnings"] == cq["citation_warnings"], (
            "debug_view['citation_warnings'] must mirror "
            "citation_quality['citation_warnings'] exactly — "
            "it does not mirror the full top-level warnings list; "
            f"debug_view citation_warnings={dv['citation_warnings']!r}, "
            f"citation_quality citation_warnings={cq['citation_warnings']!r}"
        )

        # ── warning_count tracks citation-quality warnings, not total warnings ───
        assert cq["warning_count"] == len(cq["citation_warnings"]), (
            "citation_quality['warning_count'] must equal "
            "len(citation_quality['citation_warnings']); "
            f"warning_count={cq['warning_count']!r}, "
            f"len(citation_warnings)={len(cq['citation_warnings'])!r}"
        )
        assert len(result["warnings"]) >= cq["warning_count"], (
            "len(top-level warnings) must be >= citation_quality['warning_count'] "
            "because warnings is the superset; "
            f"len(warnings)={len(result['warnings'])!r}, "
            f"warning_count={cq['warning_count']!r}"
        )
        # Crucially, warning_count must NOT equal len(result["warnings"]) here,
        # since there is an additional operational warning at the top level.
        assert cq["warning_count"] < len(result["warnings"]), (
            "warning_count must be strictly less than len(top-level warnings) in "
            "the mixed-warning scenario — warning_count counts citation-quality "
            "warnings only, not the total number of top-level warnings; "
            f"warning_count={cq['warning_count']!r}, "
            f"len(warnings)={len(result['warnings'])!r}"
        )

        # ── Operational warning must not leak into citation_quality ──────────────
        assert _MISSING_OPTIONAL_FIELDS_WARNING not in cq["citation_warnings"], (
            "Operational (non-citation-quality) warning must not appear in "
            "citation_quality['citation_warnings'] (§2.6 rule 4); "
            f"got citation_warnings={cq['citation_warnings']!r}"
        )
        assert _MISSING_OPTIONAL_FIELDS_WARNING not in dv["citation_warnings"], (
            "Operational warning must not appear in debug_view['citation_warnings'] "
            "(debug_view mirrors citation_quality, which excludes operational warnings); "
            f"got debug_view citation_warnings={dv['citation_warnings']!r}"
        )

    def test_operational_skip_warning_in_warnings_not_citation_warnings(self) -> None:
        """Operational (non-citation-quality) warning must appear only in ``warnings``.

        The retrieval-skipped warning is an operational signal (§2.6 taxonomy rule 4):
        it indicates that no retrieval ran, which is not a citation-quality problem.
        It must appear in the top-level ``warnings`` list but must **not** be
        propagated to ``citation_quality["citation_warnings"]``.
        """
        helper = TestRunRetrievalAndQaEarlyReturnContract()
        result = helper._skip_result()
        assert _SKIP_WARNING in result["warnings"], (
            f"Skip warning missing from top-level warnings; got {result['warnings']!r}"
        )
        cq = result["citation_quality"]
        assert _SKIP_WARNING not in cq["citation_warnings"], (
            f"Skip warning must not appear in citation_quality.citation_warnings; "
            f"got {cq['citation_warnings']!r}"
        )


# ---------------------------------------------------------------------------
# TestProjectionPolicySurfaceOwnership
# ---------------------------------------------------------------------------

#: Human-readable surface labels used in projection-policy assertion messages so
#: that a failing test immediately names the wrong destination surface.
_SURFACE_WARNINGS = "top-level warnings"
_SURFACE_CITATION_WARNINGS = "citation_quality['citation_warnings']"
_SURFACE_CITATION_QUALITY = "citation_quality bundle"
_SURFACE_TELEMETRY = "telemetry integer field (malformed_diagnostics_count)"
_SURFACE_DEBUG_VIEW = "debug_view"
_SURFACE_TOP_LEVEL = "direct top-level key"

#: Fields that the policy says are canonical on the ``citation_quality`` surface,
#: mirrored in ``debug_view``, and explicitly forbidden from appearing as direct
#: top-level keys.  Derived from :data:`RETRIEVAL_METADATA_SURFACE_POLICY` so that
#: any new field added to the policy with those same characteristics is automatically
#: covered by the parametrized test below.
#:
#: Filtering to ``canonical_surface == "citation_quality"`` and
#: ``"debug_view" in mirrored_in`` keeps the parametrization aligned with the test's
#: assertions (that the field is present in both ``citation_quality`` and ``debug_view``)
#: and prevents surprising failures if a future policy entry forbids ``top_level`` for
#: some other reason or surface combination.
_POLICY_FIELDS_FORBIDDEN_AT_TOP_LEVEL: list[str] = sorted(
    canonical_key
    for canonical_key, pol in RETRIEVAL_METADATA_SURFACE_POLICY.items()
    if "top_level" in pol.forbidden_in
    and pol.canonical_surface == "citation_quality"
    and "debug_view" in pol.mirrored_in
)


class TestProjectionPolicySurfaceOwnership:
    """Projection-policy tests: each signal must be owned by exactly the correct surface(s).

    These tests are organized around the four taxonomy decision rules from §2.6 of the
    contract document and target future contributor drift risks not already pinned by the
    mirroring/isolation tests in :class:`TestMetadataTaxonomyBoundaries`.

    Decision rules tested explicitly:

    - **Rule 1** — citation-quality warning *strings* → both ``citation_warnings`` and
      ``warnings``.
    - **Rule 2** — citation-quality *metrics/flags* (``evidence_level``, ``warning_count``)
      → ``citation_quality`` bundle only; must not be direct top-level keys.
    - **Rule 1 / top-level key** — ``citation_warnings`` is a warning-string field (rule 1)
      that is dual-surfaced via ``citation_quality`` and ``warnings``, but must also not
      appear as a *key* at the top level.  Covered by
      :data:`_POLICY_FIELDS_FORBIDDEN_AT_TOP_LEVEL` alongside the rule-2 metric fields.
      Parametrized test:
      :meth:`test_citation_quality_fields_forbidden_as_top_level_keys`.
    - **Rule 3** — machine-readable telemetry counters (``malformed_diagnostics_count``)
      → integer field only; must not appear inside ``citation_quality``.
    - **Rule 4** — operational (non-citation-quality) warnings → top-level ``warnings``
      only; must not propagate to ``citation_quality["citation_warnings"]``.

    In addition, two exact-key-set invariants guard against hidden-state drift:

    - ``debug_view`` must contain **exactly** :data:`_DEBUG_VIEW_REQUIRED_KEYS`.
    - The ``citation_quality`` bundle must contain **exactly**
      :data:`_CITATION_QUALITY_BUNDLE_KEYS`.

    Both are parametrized across all six documented live scenarios.
    """

    # ------------------------------------------------------------------
    # Exact key-set invariants (no hidden state; no extra bundle fields)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        _LIVE_SCENARIOS,
        ids=_LIVE_SCENARIO_IDS,
    )
    def test_debug_view_has_exactly_documented_key_set(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """``debug_view`` must contain **exactly** the documented key set across all scenarios.

        ``debug_view`` is a supported inspection surface, not an escape hatch for
        introducing semantically new state (§2.9).  If a contributor adds an extra key
        to ``debug_view`` without updating :data:`RETRIEVAL_METADATA_SURFACE_POLICY` and
        the contract document, this test will fail with an actionable message naming the
        extra key and the surface where it was mistakenly placed.
        """
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        actual_keys = set(result["debug_view"].keys())
        extra = actual_keys - _DEBUG_VIEW_REQUIRED_KEYS
        missing = _DEBUG_VIEW_REQUIRED_KEYS - actual_keys
        assert actual_keys == _DEBUG_VIEW_REQUIRED_KEYS, (
            f"[{scenario}] {_SURFACE_DEBUG_VIEW} key set mismatch — "
            f"extra={sorted(extra)!r}, missing={sorted(missing)!r}. "
            f"debug_view must not introduce undocumented state (§2.9). "
            f"If a new key is intentional, update RETRIEVAL_METADATA_SURFACE_POLICY and the "
            f"contract document."
        )

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        _LIVE_SCENARIOS,
        ids=_LIVE_SCENARIO_IDS,
    )
    def test_citation_quality_bundle_has_exactly_documented_key_set(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
    ) -> None:
        """``citation_quality`` bundle must contain **exactly** the documented key set.

        The ``citation_quality`` bundle is the authoritative citation-quality surface
        (§2.6 rule 2).  Extra keys would indicate a signal was silently migrated to
        the wrong surface without a contract update.
        """
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        actual_keys = set(result["citation_quality"].keys())
        extra = actual_keys - _CITATION_QUALITY_BUNDLE_KEYS
        missing = _CITATION_QUALITY_BUNDLE_KEYS - actual_keys
        assert actual_keys == _CITATION_QUALITY_BUNDLE_KEYS, (
            f"[{scenario}] {_SURFACE_CITATION_QUALITY} key set mismatch — "
            f"extra={sorted(extra)!r}, missing={sorted(missing)!r}. "
            f"If a new key is intentional, update RETRIEVAL_METADATA_SURFACE_POLICY and the "
            f"contract document."
        )

    # ------------------------------------------------------------------
    # Rule 2 + top-level key: citation_quality fields forbidden as direct top-level keys
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "field_name",
        _POLICY_FIELDS_FORBIDDEN_AT_TOP_LEVEL,
        ids=_POLICY_FIELDS_FORBIDDEN_AT_TOP_LEVEL,
    )
    def test_citation_quality_fields_forbidden_as_top_level_keys(
        self,
        field_name: str,
    ) -> None:
        """``citation_quality`` fields must not appear as direct top-level keys.

        Parametrized from :data:`_POLICY_FIELDS_FORBIDDEN_AT_TOP_LEVEL`, which is derived
        from :data:`RETRIEVAL_METADATA_SURFACE_POLICY` — specifically fields with
        ``canonical_surface="citation_quality"``, ``"debug_view" in mirrored_in``, and
        ``"top_level" in forbidden_in``.

        The covered fields include:

        - ``evidence_level`` and ``warning_count`` — citation-quality metrics/flags
          (§2.6 rule 2) that must not be promoted to direct top-level keys.
        - ``citation_warnings`` — a rule-1 warning-string list that is dual-surfaced
          through ``citation_quality`` and ``warnings``, but whose *key name* must also
          not appear as a direct top-level key (it would conflict with the canonical
          ``citation_quality["citation_warnings"]`` access path).

        Adding a new field to the policy with the same surface combination will
        automatically extend coverage here without a manual update to this test.
        """
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        assert field_name not in result, (
            f"{field_name!r} must not appear as a {_SURFACE_TOP_LEVEL} "
            f"(policy forbidden_in). It belongs in the {_SURFACE_CITATION_QUALITY} — "
            f"access it via citation_quality[{field_name!r}] for production logic, or via "
            f"debug_view[{field_name!r}] for inspection."
        )
        # Confirm the field is correctly placed on its designated canonical surface.
        assert field_name in result["citation_quality"], (
            f"{field_name!r} must be present in the {_SURFACE_CITATION_QUALITY}"
        )
        assert field_name in result["debug_view"], (
            f"{field_name!r} must be present in {_SURFACE_DEBUG_VIEW} (mirrored from "
            f"citation_quality per §2.9)"
        )

    # ------------------------------------------------------------------
    # Rule 3: telemetry counters must not appear inside citation_quality
    # ------------------------------------------------------------------

    def test_telemetry_counter_not_in_citation_quality_bundle(self) -> None:
        """``malformed_diagnostics_count`` must not appear inside ``citation_quality``.

        It is a machine-readable alerting counter (§2.6 rule 3, §2.7).  Adding it to
        the ``citation_quality`` bundle would misclassify it as a citation-quality metric
        and expose it on the wrong surface.  Callers that need this signal read the
        integer field directly at the top level.
        """
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_MALFORMED_DIAGNOSTICS_METADATA],
            all_runs=True,
        )
        assert result["malformed_diagnostics_count"] > 0, (
            "Fixture precondition: expected malformed_diagnostics_count > 0; "
            f"got {result['malformed_diagnostics_count']!r}"
        )
        assert "malformed_diagnostics_count" not in result["citation_quality"], (
            f"malformed_diagnostics_count must not appear in the {_SURFACE_CITATION_QUALITY}. "
            f"It is a {_SURFACE_TELEMETRY} (§2.6 rule 3). "
            f"Moving it into citation_quality would erode the telemetry/citation-quality "
            f"surface boundary."
        )

    # ------------------------------------------------------------------
    # Rule 1: citation-quality warning strings must be dual-surfaced
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id,expected_warning",
        [
            (
                "uncited_answer",
                _UNCITED_ANSWER,
                [_LIVE_ITEM_METADATA],
                False,
                "r1",
                _UNCITED_WARNING,
            ),
            (
                "empty_chunk_text",
                _CITED_ANSWER,
                [_EMPTY_CHUNK_METADATA],
                True,
                None,
                _EMPTY_CHUNK_WARNING_MSG,
            ),
        ],
        ids=["uncited_answer", "empty_chunk_text"],
    )
    def test_citation_quality_warning_strings_dual_surfaced(
        self,
        scenario: str,
        answer: str,
        items_metadata: list,
        all_runs: bool,
        run_id: str | None,
        expected_warning: str,
    ) -> None:
        """Citation-quality warning strings must appear on both surfaces (rule 1).

        Per §2.6 rule 1, any signal that reflects a citation-quality problem **and**
        is expressed as a human-readable warning string must be added to
        ``citation_quality["citation_warnings"]`` **and** propagated to top-level
        ``warnings``.  This test explicitly verifies each documented citation-quality
        warning type to prevent a future contributor from routing the warning to only
        one surface.
        """
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        assert expected_warning in result["warnings"], (
            f"[{scenario}] Citation-quality warning {expected_warning!r} missing from "
            f"{_SURFACE_WARNINGS}. Per §2.6 rule 1 it must appear on both "
            f"{_SURFACE_WARNINGS} and {_SURFACE_CITATION_WARNINGS}."
        )
        assert expected_warning in cq["citation_warnings"], (
            f"[{scenario}] Citation-quality warning {expected_warning!r} missing from "
            f"{_SURFACE_CITATION_WARNINGS}. Per §2.6 rule 1 it must appear on both "
            f"{_SURFACE_WARNINGS} and {_SURFACE_CITATION_WARNINGS}."
        )

    # ------------------------------------------------------------------
    # Rule 4: operational warnings must not propagate to citation_warnings
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_label,operational_warning",
        [
            ("retrieval_skipped", _SKIP_WARNING),
        ],
        ids=["retrieval_skipped"],
    )
    def test_operational_warnings_not_in_citation_warnings(
        self,
        path_label: str,
        operational_warning: str,
    ) -> None:
        """Operational (non-citation-quality) warnings must not propagate to
        ``citation_quality["citation_warnings"]`` (rule 4).

        Rule 4 of §2.6: warnings that represent operational context (e.g. retrieval
        was skipped) must go to top-level ``warnings`` only.  Propagating them to
        ``citation_warnings`` would misclassify an operational signal as a
        citation-quality problem and pollute the citation-quality surface.
        """
        result = TestRunRetrievalAndQaEarlyReturnContract._skip_result()
        assert operational_warning in result["warnings"], (
            f"[{path_label}] Operational warning {operational_warning!r} missing from "
            f"{_SURFACE_WARNINGS}; got {result['warnings']!r}"
        )
        assert operational_warning not in result["citation_quality"]["citation_warnings"], (
            f"[{path_label}] Operational warning {operational_warning!r} must not appear "
            f"in {_SURFACE_CITATION_WARNINGS} (§2.6 rule 4). "
            f"It is operational context, not a citation-quality problem."
        )

    # ------------------------------------------------------------------
    # Ambiguous case: evidence_level (§2.6 ambiguous-examples table)
    # ------------------------------------------------------------------

    def test_ambiguous_evidence_level_surface_classification(self) -> None:
        """Ambiguous case: ``evidence_level`` must be classified as a citation-quality
        metric, not a top-level key (§2.6 ambiguous-examples table).

        ``evidence_level`` is a structured flag (§2.8) that could plausibly be treated
        as a top-level field.  The §2.6 taxonomy resolves this via rule 2: it is a
        citation-quality metric, not a warning string → it belongs in the
        ``citation_quality`` bundle and must not appear as a direct top-level key.
        It is additionally mirrored in ``debug_view`` for inspection tooling (§2.9).

        This test names the ambiguity explicitly so the intended classification is
        self-documenting and any future migration to the wrong surface fails loudly.
        """
        result = _run_with_mocked_retrieval(
            answer=_CITED_ANSWER,
            items_metadata=[_LIVE_ITEM_METADATA],
            all_runs=True,
        )
        # Must NOT be a direct top-level key (rule 2: citation-quality metric).
        assert "evidence_level" not in result, (
            f"evidence_level must not be a {_SURFACE_TOP_LEVEL} (§2.6 rule 2). "
            f"It is a citation-quality metric — access it via "
            f"citation_quality['evidence_level'] for production logic."
        )
        # Must be present in the citation_quality bundle.
        assert "evidence_level" in result["citation_quality"], (
            f"evidence_level must be present in the {_SURFACE_CITATION_QUALITY}"
        )
        # Must be mirrored in debug_view for inspection (§2.9).
        assert "evidence_level" in result["debug_view"], (
            f"evidence_level must be present in {_SURFACE_DEBUG_VIEW} (mirrored from "
            f"citation_quality per §2.9)"
        )
        # Must NOT appear in citation_warnings (it is a metric, not a warning string).
        assert "evidence_level" not in result["citation_quality"]["citation_warnings"], (
            f"evidence_level must not appear in {_SURFACE_CITATION_WARNINGS}. "
            f"It is a structured flag (§2.8), not a human-readable warning string."
        )
        # Must NOT appear in top-level warnings.
        assert "evidence_level" not in result["warnings"], (
            f"evidence_level must not appear in {_SURFACE_WARNINGS}. "
            f"It is a citation-quality metric, not a warning string (§2.6 rule 2)."
        )
