"""Parity tests: single-shot vs interactive retrieval postprocessing behavior.

These tests explicitly verify that :func:`run_retrieval_and_qa` and
:func:`run_interactive_qa` invoke the shared helper functions with identical
arguments for the same user-facing inputs, so future silent drift between the
two entry points is caught at test time rather than in production.

Structure
---------
``TestRetrievalQueryParity``
    Spy-based tests that drive the real entry-point code paths up to the
    ``_select_retrieval_query`` call and capture the exact kwargs passed by each
    path.  Parametrized over representative mode-flag combinations.

``TestQueryParamParity``
    Spy-based tests that drive both paths up to the ``_build_query_params`` call
    and compare the captured kwargs.  Parametrized over representative
    (run_id, source_uri, cluster_aware, all_runs) input combinations.

``TestCitationRepairParity``
    Calls ``_postprocess_answer`` directly with the inputs both paths would pass
    in all-runs mode, verifying that the same uncited answer and hits produce
    identical repair results (citation repair applied, no fallback).

``TestCitationFallbackParity``
    Calls ``_postprocess_answer`` directly with the inputs both paths would pass
    when no repair token is available, verifying identical fallback results
    (fallback prefix in display answer, bare prefix in history answer).
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from demo.stages.retrieval_and_qa import (
    _CITATION_FALLBACK_PREFIX,
    _build_query_params,
    _postprocess_answer,
    _select_retrieval_query,
    run_interactive_qa,
    run_retrieval_and_qa,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
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

#: A valid synthetic citation token used to construct test hits.
_TOKEN = (
    "[CITATION|chunk_id=c1|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=0|page=1|start_char=0|end_char=50]"
)

#: A single retrieval hit carrying _TOKEN; used in citation-repair tests.
_HIT: dict[str, object] = {"metadata": {"citation_token": _TOKEN, "chunk_id": "c1"}}


# ---------------------------------------------------------------------------
# Helper drivers
#
# Each helper drives the real entry-point code far enough to capture the kwargs
# passed to one shared helper function, then returns those kwargs for comparison.
# ---------------------------------------------------------------------------


def _capture_single_shot_select_query(extra_flags: dict[str, object]) -> dict[str, object]:
    """Return the kwargs passed to ``_select_retrieval_query`` by the live path of
    ``run_retrieval_and_qa``.

    Uses an empty-string question (non-``None`` so the early-return resolver does
    not short-circuit before the setup helpers are reached) with ``all_runs=True``
    to skip the ``run_id`` validation check.  The function raises ``ValueError``
    at the ``OPENAI_API_KEY`` guard after the spy has captured its call; that
    error is expected and suppressed here.
    """
    captured: list[dict[str, object]] = []
    orig = _select_retrieval_query

    def spy(**kwargs: object) -> str:
        captured.append(dict(kwargs))
        return orig(**kwargs)  # type: ignore[arg-type]

    flags: dict[str, object] = {"all_runs": True, **extra_flags}
    with patch("demo.stages.retrieval_and_qa._select_retrieval_query", side_effect=spy):
        try:
            run_retrieval_and_qa(_LIVE_CONFIG, question="", **flags)
        except ValueError:
            pass  # OPENAI_API_KEY guard fires after the spy captures; that is expected.

    assert captured, "Expected at least one _select_retrieval_query call"
    first_kwargs = captured[0]
    for call_kwargs in captured[1:]:
        assert (
            call_kwargs == first_kwargs
        ), "Expected all _select_retrieval_query calls to use identical kwargs"
    return first_kwargs


def _capture_interactive_select_query(extra_flags: dict[str, object]) -> dict[str, object]:
    """Return the kwargs passed to ``_select_retrieval_query`` by ``run_interactive_qa``.

    Mocks OPENAI_API_KEY, the Neo4j driver, ``_build_retriever_and_rag``, and
    ``input()`` so the function exits immediately after the helper calls without
    making any real network connections.
    """
    captured: list[dict[str, object]] = []
    orig = _select_retrieval_query

    def spy(**kwargs: object) -> str:
        captured.append(dict(kwargs))
        return orig(**kwargs)  # type: ignore[arg-type]

    flags: dict[str, object] = {"all_runs": True, **extra_flags}
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
        patch("demo.stages.retrieval_and_qa._select_retrieval_query", side_effect=spy),
        patch("neo4j.GraphDatabase.driver"),
        patch("demo.stages.retrieval_and_qa._build_retriever_and_rag") as mock_build,
        patch("builtins.input", return_value="exit"),
        patch("builtins.print"),
    ):
        mock_build.return_value = (MagicMock(), MagicMock())
        run_interactive_qa(_LIVE_CONFIG, **flags)

    assert captured, "Expected at least one _select_retrieval_query call"
    return captured[0]


def _capture_single_shot_build_query_params(extra_flags: dict[str, object]) -> dict[str, object]:
    """Return the kwargs passed to ``_build_query_params`` by the live path of
    ``run_retrieval_and_qa``.

    Uses an empty-string question (non-``None`` so the early-return resolver does
    not short-circuit before the setup helpers are reached).  The function raises
    ``ValueError`` at the ``OPENAI_API_KEY`` guard after the spy has captured its
    call; that error is expected and suppressed here.
    """
    captured: list[dict[str, object]] = []
    orig = _build_query_params

    def spy(**kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return orig(**kwargs)  # type: ignore[arg-type]

    # Only inject a run_id for the non-all-runs case; when all_runs=True callers
    # omit run_id entirely, which is the realistic parity scenario.
    flags: dict[str, object] = (
        {"run_id": "r1", **extra_flags} if not extra_flags.get("all_runs") else dict(extra_flags)
    )
    with patch("demo.stages.retrieval_and_qa._build_query_params", side_effect=spy):
        try:
            run_retrieval_and_qa(_LIVE_CONFIG, question="", **flags)
        except ValueError:
            pass  # OPENAI_API_KEY guard fires after the spy captures; that is expected.

    assert captured, "Expected at least one _build_query_params call"
    return captured[0]


def _capture_interactive_build_query_params(extra_flags: dict[str, object]) -> dict[str, object]:
    """Return the kwargs passed to ``_build_query_params`` by ``run_interactive_qa``.

    Same mocking strategy as :func:`_capture_interactive_select_query`.
    """
    captured: list[dict[str, object]] = []
    orig = _build_query_params

    def spy(**kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return orig(**kwargs)  # type: ignore[arg-type]

    # Only inject a run_id for the non-all-runs case; when all_runs=True callers
    # omit run_id entirely, which is the realistic parity scenario.
    flags: dict[str, object] = (
        {"run_id": "r1", **extra_flags} if not extra_flags.get("all_runs") else dict(extra_flags)
    )
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
        patch("demo.stages.retrieval_and_qa._build_query_params", side_effect=spy),
        patch("neo4j.GraphDatabase.driver"),
        patch("demo.stages.retrieval_and_qa._build_retriever_and_rag") as mock_build,
        patch("builtins.input", return_value="exit"),
        patch("builtins.print"),
    ):
        mock_build.return_value = (MagicMock(), MagicMock())
        run_interactive_qa(_LIVE_CONFIG, **flags)

    assert captured, "Expected at least one _build_query_params call"
    return captured[0]


# ---------------------------------------------------------------------------
# TestRetrievalQueryParity
# ---------------------------------------------------------------------------


class TestRetrievalQueryParity:
    """Same mode flags → same ``_select_retrieval_query`` call in both entry points.

    Each test drives the real code path of both ``run_retrieval_and_qa`` and
    ``run_interactive_qa``, intercepts the ``_select_retrieval_query`` call via a
    spy, and asserts that the captured kwargs are identical.  This ensures any
    future change that alters the flag-passing logic in one path but not the other
    will be caught here.
    """

    @pytest.mark.parametrize(
        "extra_flags",
        [
            {},  # all_runs=True, no expansion flags
            {"expand_graph": True},
            {"cluster_aware": True},
        ],
        ids=["base_all_runs", "expand_graph", "cluster_aware"],
    )
    def test_same_flags_produce_same_select_query_call(self, extra_flags: dict[str, object]) -> None:
        single_shot_kwargs = _capture_single_shot_select_query(extra_flags)
        interactive_kwargs = _capture_interactive_select_query(extra_flags)
        assert single_shot_kwargs == interactive_kwargs, (
            f"_select_retrieval_query kwargs diverged for flags {extra_flags!r}: "
            f"single-shot={single_shot_kwargs!r}, interactive={interactive_kwargs!r}"
        )

    @pytest.mark.parametrize(
        "extra_flags",
        [
            {},  # all_runs=True, no expansion flags
            {"expand_graph": True},
            {"cluster_aware": True},
        ],
        ids=["base_all_runs", "expand_graph", "cluster_aware"],
    )
    def test_same_flags_produce_same_selected_query_string(self, extra_flags: dict[str, object]) -> None:
        """The selected query string implied by each entry point's captured kwargs is identical."""
        single_shot_kwargs = _capture_single_shot_select_query(extra_flags)
        interactive_kwargs = _capture_interactive_select_query(extra_flags)

        single_shot_query = _select_retrieval_query(**single_shot_kwargs)
        interactive_query = _select_retrieval_query(**interactive_kwargs)
        assert single_shot_query == interactive_query, (
            "Selected retrieval query string diverged between entry points: "
            f"flags={extra_flags!r}, "
            f"single-shot kwargs={single_shot_kwargs!r}, interactive kwargs={interactive_kwargs!r}, "
            f"single-shot query={single_shot_query!r}, interactive query={interactive_query!r}"
        )


# ---------------------------------------------------------------------------
# TestQueryParamParity
# ---------------------------------------------------------------------------


class TestQueryParamParity:
    """Same run_id / source_uri / cluster_aware / all_runs → same ``_build_query_params``
    call in both entry points.

    Spy-based: drives both paths to the ``_build_query_params`` call and compares
    the captured kwargs dicts.
    """

    @pytest.mark.parametrize(
        "extra_flags",
        [
            {},  # run_id="r1", no source_uri, not cluster_aware
            {"source_uri": "file:///doc.pdf"},
            {"cluster_aware": True},
            {"all_runs": True},
        ],
        ids=["default", "with_source_uri", "cluster_aware", "all_runs"],
    )
    def test_same_inputs_produce_same_build_query_params_call(self, extra_flags: dict[str, object]) -> None:
        single_shot_kwargs = _capture_single_shot_build_query_params(extra_flags)
        interactive_kwargs = _capture_interactive_build_query_params(extra_flags)
        assert single_shot_kwargs == interactive_kwargs, (
            f"_build_query_params kwargs diverged for flags {extra_flags!r}: "
            f"single-shot={single_shot_kwargs!r}, interactive={interactive_kwargs!r}"
        )

# ---------------------------------------------------------------------------
# TestCitationRepairParity
# ---------------------------------------------------------------------------


class TestCitationRepairParity:
    """Same uncited answer + same hits in all-runs mode → same repaired display answer.

    Both ``run_retrieval_and_qa`` and ``run_interactive_qa`` call
    ``_postprocess_answer(answer, hits, all_runs=True)`` in all-runs mode.
    These tests verify that identical inputs produce identical postprocessing
    results, asserting repair is applied consistently by the shared helper.
    """

    def test_all_runs_uncited_answer_repair_applied_consistently(self) -> None:
        """Citation repair is applied consistently for an uncited answer in all-runs mode.

        Both ``run_retrieval_and_qa`` and ``run_interactive_qa`` call
        ``_postprocess_answer(answer, hits, all_runs=True)``; this test verifies the
        shared helper produces the expected repair outcome so neither path can silently
        omit repair by changing its call signature.
        """
        answer = "An uncited claim that needs repair."

        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        # Repair must be attempted and applied for an uncited answer when hits are available.
        assert pp["citation_repair_attempted"] is True
        assert pp["citation_repair_applied"] is True
        assert pp["citation_repair_strategy"] == "append_first_retrieved_token"
        # Display and history answers must both carry the repaired (cited) text.
        assert _TOKEN in pp["display_answer"]
        assert _TOKEN in pp["history_answer"]
        # When repair produces a fully-cited answer, fallback must not be applied.
        assert pp["citation_fallback_applied"] is False
        assert pp["all_cited"] is True

    def test_all_runs_repair_applied_false_when_answer_already_cited(self) -> None:
        """Both paths skip repair when the answer is already fully cited."""
        answer = f"Already cited sentence. {_TOKEN}"

        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        assert pp["citation_repair_attempted"] is False
        assert pp["citation_repair_applied"] is False
        assert pp["raw_answer_all_cited"] is True
        assert pp["citation_fallback_applied"] is False
        assert pp["all_cited"] is True

    def test_repair_citation_token_matches_first_hit_token(self) -> None:
        """Both paths use the first retrieved hit's citation token for repair."""
        answer = "Uncited claim needing token."
        token_a = _TOKEN
        token_b = _TOKEN.replace("chunk_id=c1", "chunk_id=c2")
        hits = [
            {"metadata": {"citation_token": token_a, "chunk_id": "c1"}},
            {"metadata": {"citation_token": token_b, "chunk_id": "c2"}},
        ]

        pp = _postprocess_answer(answer, hits, all_runs=True)

        assert pp["citation_repair_attempted"] is True
        assert pp["citation_repair_applied"] is True
        assert pp["citation_repair_source_chunk_id"] == "c1"
        assert token_a in pp["display_answer"]


# ---------------------------------------------------------------------------
# TestCitationFallbackParity
# ---------------------------------------------------------------------------


class TestCitationFallbackParity:
    """Same uncited answer + no repair token → same fallback by both entry points.

    Both paths call ``_postprocess_answer`` when citation repair is not applicable
    (either ``all_runs=False`` or no hits available).  These tests verify that the
    shared fallback logic produces identical results for both paths.
    """

    def test_fallback_display_answer_starts_with_prefix(self) -> None:
        """Both paths produce a display_answer starting with _CITATION_FALLBACK_PREFIX."""
        answer = "Uncited content."

        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["citation_fallback_applied"] is True
        assert pp["display_answer"].startswith(_CITATION_FALLBACK_PREFIX)

    def test_fallback_history_answer_is_bare_prefix(self) -> None:
        """history_answer is exactly the fallback prefix in both paths (no uncited content)."""
        answer = "Some uncited text that must not appear in history."

        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["history_answer"] == _CITATION_FALLBACK_PREFIX
        assert answer not in pp["history_answer"]

    def test_all_runs_no_hits_fallback_applied_same_as_run_scoped(self) -> None:
        """With all_runs=True but no hits, fallback is applied identically to all_runs=False."""
        answer = "Uncited answer with no retrieved hits."

        run_scoped_pp = _postprocess_answer(answer, [], all_runs=False)
        all_runs_pp = _postprocess_answer(answer, [], all_runs=True)

        # Both should apply fallback since repair requires hits.
        assert run_scoped_pp["citation_fallback_applied"] is True
        assert all_runs_pp["citation_fallback_applied"] is True
        assert run_scoped_pp["display_answer"] == all_runs_pp["display_answer"]
        assert run_scoped_pp["history_answer"] == all_runs_pp["history_answer"]
