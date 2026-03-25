"""Result-level contract tests for retrieval answer postprocessing metadata.

These tests assert the exact postprocessing/result semantics surfaced by
``_postprocess_answer()`` and ``run_retrieval_and_qa()`` across every documented
scenario.  They are intended to serve as executable contract documentation so that
future refactors cannot silently change surfaced metadata or the relationships
between top-level fields and nested ``citation_quality`` data without a test failure.

Structure
---------
``TestPostprocessAnswerResultContract``
    Table-driven tests that call ``_postprocess_answer()`` directly and assert the
    full result shape for each scenario:

    - fully cited answer
    - uncited answer repaired (text changed)
    - uncited answer where repair is attempted but produces no change (no-op)
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
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from demo.stages.retrieval_and_qa import (
    _CITATION_FALLBACK_PREFIX,
    _postprocess_answer,
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
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
            "all_cited": True,
            "raw_answer_all_cited": True,
            "evidence_level": "full",
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
            "citation_repair_applied": True,
            "citation_repair_strategy": "append_first_retrieved_token",
            "citation_repair_source_chunk_id": "c1",
            "citation_fallback_applied": False,
            "all_cited": True,
            "raw_answer_all_cited": False,
            "evidence_level": "full",
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
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": True,
            "all_cited": False,
            "raw_answer_all_cited": False,
            "evidence_level": "degraded",
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
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": True,
            "all_cited": False,
            "raw_answer_all_cited": False,
            "evidence_level": "degraded",
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
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
            "all_cited": False,
            "raw_answer_all_cited": False,
            "evidence_level": "no_answer",
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
            "citation_repair_applied": False,
            "citation_repair_strategy": None,
            "citation_repair_source_chunk_id": None,
            "citation_fallback_applied": False,
            "all_cited": False,
            "raw_answer_all_cited": False,
            "evidence_level": "no_answer",
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
            "citation_repair_applied": False,
            "citation_fallback_applied": True,
            "all_cited": False,
            "raw_answer_all_cited": False,
            "evidence_level": "degraded",
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
            "citation_repair_applied": False,
            "citation_fallback_applied": False,
            "all_cited": True,
            "raw_answer_all_cited": True,
            # Preexisting citation warning degrades evidence_level even when fully cited.
            "evidence_level": "degraded",
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
        """Every field listed in *expected* must match the returned result exactly."""
        pp = _postprocess_answer(
            answer, hits, all_runs=all_runs, existing_citation_warnings=existing_warnings
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
        expected: dict,
    ) -> None:
        """``citation_quality`` must mirror each corresponding top-level field."""
        pp = _postprocess_answer(
            answer, hits, all_runs=all_runs, existing_citation_warnings=existing_warnings
        )
        cq = pp["citation_quality"]

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
        """``citation_repair_strategy`` and ``citation_repair_source_chunk_id`` are ``None``
        when repair was not applied, and non-``None`` when it was."""
        pp_no_repair = _postprocess_answer(_CITED_ANSWER, [_HIT], all_runs=True)
        assert pp_no_repair["citation_repair_strategy"] is None
        assert pp_no_repair["citation_repair_source_chunk_id"] is None

        pp_repair = _postprocess_answer(_UNCITED_ANSWER, [_HIT], all_runs=True)
        assert pp_repair["citation_repair_strategy"] is not None
        assert pp_repair["citation_repair_source_chunk_id"] is not None

    def test_repair_applied_false_when_no_change_to_text(self) -> None:
        """When repair logic runs but the text would not change, ``citation_repair_applied``
        is ``False`` (the flag reflects text change, not invocation)."""
        # Answer is already cited; repair logic will detect no change is needed.
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
            items_metadata=[{"citation_token": _TOKEN, "chunk_id": "c1"}],
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
            items_metadata=[{"citation_token": _TOKEN, "chunk_id": "c1"}],
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
            items_metadata=[],
            all_runs=True,
        )

        assert result["citation_fallback_applied"] is True
        assert result["citation_repair_applied"] is False
        assert result["all_answers_cited"] is False
        assert result["answer"].startswith(_CITATION_FALLBACK_PREFIX)

        cq = result["citation_quality"]
        assert cq["all_cited"] is False
        assert cq["evidence_level"] == "degraded"
        assert cq["warning_count"] >= 1

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
            (_CITED_ANSWER, [{"citation_token": _TOKEN, "chunk_id": "c1"}]),
            (_UNCITED_ANSWER, [{"citation_token": _TOKEN, "chunk_id": "c1"}]),
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

    def test_repair_applied_false_when_run_scoped(self) -> None:
        """Repair is never applied in run-scoped mode (all_runs=False)."""
        result = _run_with_mocked_retrieval(
            answer=_UNCITED_ANSWER,
            items_metadata=[{"citation_token": _TOKEN, "chunk_id": "c1"}],
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
            items_metadata=[{"citation_token": _TOKEN, "chunk_id": "c1"}],
            all_runs=True,
        )

        assert result["citation_repair_applied"] is False
        assert result["citation_repair_strategy"] is None
        assert result["citation_repair_source_chunk_id"] is None
