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
    Spy-based tests that verify every ``_postprocess_answer()`` internal field is mapped
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
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

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

#: Exact set of all keys inside the nested ``_CitationQualityBundle``.
_CITATION_QUALITY_BUNDLE_KEYS: frozenset[str] = frozenset({
    "all_cited",
    "raw_answer_all_cited",
    "evidence_level",
    "warning_count",
    "citation_warnings",
})

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
        int_fields = ("top_k", "hits")
        list_fields = ("retrievers", "retrieval_results", "warnings")
        dict_fields = (
            "citation_quality", "retrieval_scope",
            "citation_object_example", "citation_example",
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

    @pytest.mark.parametrize(
        "scenario,answer,items_metadata,all_runs,run_id",
        [
            ("fully_cited", _CITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("repair_applied", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("fallback_run_scoped", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], False, "r1"),
            ("no_answer", "", [], True, None),
            ("empty_chunk_warning", _CITED_ANSWER, [_EMPTY_CHUNK_METADATA], True, None),
            ("repair_attempted_no_token", _UNCITED_ANSWER, [_HIT_METADATA_NO_TOKEN], True, None),
        ],
        ids=[
            "fully_cited", "repair_applied", "fallback_run_scoped",
            "no_answer", "empty_chunk_warning", "repair_attempted_no_token",
        ],
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
    """Verify that every ``_postprocess_answer()`` internal field is correctly mapped
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
# TestProjectPostprocessToPublic
# ---------------------------------------------------------------------------

#: Exact set of all public keys in a ``_PostprocessPublicFields`` dict,
#: derived from the values of :data:`_POSTPROCESS_FIELD_MAP` to avoid drift.
_POSTPROCESS_PUBLIC_KEYS: frozenset[str] = frozenset(_POSTPROCESS_FIELD_MAP.values())


class TestProjectPostprocessToPublic:
    """Direct unit tests for the :func:`_project_postprocess_to_public` adapter.

    These tests exercise the adapter function in isolation — calling it with
    a known :class:`_AnswerPostprocessResult` and asserting that every public
    key carries the correctly projected value.  Unlike the spy-based tests in
    :class:`TestRunRetrievalAndQaPostprocessMapping`, these tests do not go
    through the full ``run_retrieval_and_qa`` stack, making each mapping
    assertion cheaper and more explicit.
    """

    def _pp(self, answer: str, hits: list, all_runs: bool) -> dict:
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
        """After repair, ``pub['answer']`` must differ from ``pp['raw_answer']``
        because the adapter must map from ``display_answer``, not ``raw_answer``."""
        pp = self._pp(_UNCITED_ANSWER, [_HIT], all_runs=True)
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
        """After repair, ``all_answers_cited`` reflects final citation state (``all_cited``),
        not ``raw_answer_all_cited``, which reflects the original LLM output."""
        # Repair makes raw_answer_all_cited=False → all_cited=True
        pp = self._pp(_UNCITED_ANSWER, [_HIT], all_runs=True)
        pub = _project_postprocess_to_public(pp)
        assert pub["all_answers_cited"] == pp["all_cited"]
        assert pub["all_answers_cited"] is True
        assert pub["raw_answer_all_cited"] is False, (
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
        [
            ("fully_cited", _CITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("repair_applied", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], True, None),
            ("fallback_run_scoped", _UNCITED_ANSWER, [_LIVE_ITEM_METADATA], False, "r1"),
            ("no_answer", "", [], True, None),
            ("empty_chunk_warning", _CITED_ANSWER, [_EMPTY_CHUNK_METADATA], True, None),
            ("repair_attempted_no_token", _UNCITED_ANSWER, [_HIT_METADATA_NO_TOKEN], True, None),
        ],
        ids=[
            "fully_cited", "repair_applied", "fallback_run_scoped",
            "no_answer", "empty_chunk_warning", "repair_attempted_no_token",
        ],
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
        appear in the top-level ``warnings`` list (invariant §3.7)."""
        result = _run_with_mocked_retrieval(
            answer=answer,
            items_metadata=items_metadata,
            all_runs=all_runs,
            run_id=run_id,
        )
        cq = result["citation_quality"]
        for w in cq["citation_warnings"]:
            assert w in result["warnings"], (
                f"[{scenario}] citation_quality warning {w!r} missing from "
                f"top-level warnings; got {result['warnings']!r}"
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
