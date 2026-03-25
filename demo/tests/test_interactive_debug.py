"""Tests for the interactive debug output surface in :func:`run_interactive_qa`.

These tests verify that:

- When ``debug=True``, a compact postprocessing summary is printed after each
  answer, sourced from the shared :class:`_AnswerPostprocessResult` contract.
- When ``debug=False`` (default), no debug output is emitted.
- The summary produced by :func:`_format_postprocess_debug_summary` reflects
  the correct values from the postprocessing result for representative
  scenarios.

Structure
---------
``TestFormatPostprocessDebugSummary``
    Unit tests for :func:`_format_postprocess_debug_summary` directly, covering
    the key scenarios the issue calls for (fully cited, repair applied, fallback
    applied, warnings present).

``TestRunInteractiveQaDebugFlag``
    Integration tests that drive :func:`run_interactive_qa` with a fully mocked
    Neo4j / LLM stack and assert whether debug lines appear in stdout depending
    on the *debug* flag.
"""
from __future__ import annotations

import io
import types
from unittest.mock import MagicMock, patch

from demo.stages.retrieval_and_qa import (
    _format_postprocess_debug_summary,
    _postprocess_answer,
    run_interactive_qa,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

#: Minimal config that satisfies all live-retrieval field validations.
_LIVE_CONFIG = types.SimpleNamespace(
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password",
    neo4j_database=None,
    openai_model="gpt-4o-mini",
    dry_run=False,
)

#: A valid synthetic citation token.
_TOKEN = (
    "[CITATION|chunk_id=c1|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=0|page=1|start_char=0|end_char=50]"
)

#: A single retrieval hit carrying _TOKEN.
_HIT: dict[str, object] = {"metadata": {"citation_token": _TOKEN, "chunk_id": "c1"}}


# ---------------------------------------------------------------------------
# TestFormatPostprocessDebugSummary
# ---------------------------------------------------------------------------


class TestFormatPostprocessDebugSummary:
    """Unit tests for _format_postprocess_debug_summary.

    Each test asserts that the summary line correctly reflects the values in
    the _AnswerPostprocessResult it receives, covering the key fields the
    issue requires: raw/final citation state, repair/fallback applied,
    evidence level, and warning count.
    """

    def test_fully_cited_answer_summary(self) -> None:
        """Summary correctly reflects a fully cited answer with no repair or fallback."""
        answer = f"A fully cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(pp)

        assert "[debug]" in summary
        assert "raw_cited=True" in summary
        assert "final_cited=True" in summary
        assert "repair_applied=False" in summary
        assert "fallback_applied=False" in summary
        assert "evidence=full" in summary
        assert "warnings=0" in summary

    def test_repair_applied_summary(self) -> None:
        """Summary reflects citation_repair_applied=True when repair changes the answer text."""
        answer = "An uncited claim needing repair."
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        # Repair should be applied in all-runs mode with a hit available.
        assert pp["citation_repair_applied"] is True

        summary = _format_postprocess_debug_summary(pp)

        assert "repair_applied=True" in summary
        assert "raw_cited=False" in summary
        assert "final_cited=True" in summary
        assert "fallback_applied=False" in summary
        assert "evidence=full" in summary

    def test_fallback_applied_summary(self) -> None:
        """Summary reflects citation_fallback_applied=True when no repair token is available."""
        answer = "An uncited claim with no hits."
        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["citation_fallback_applied"] is True

        summary = _format_postprocess_debug_summary(pp)

        assert "fallback_applied=True" in summary
        assert "repair_applied=False" in summary
        assert "raw_cited=False" in summary
        assert "final_cited=False" in summary
        assert "evidence=degraded" in summary

    def test_warning_count_in_summary(self) -> None:
        """Summary shows warning_count > 0 when citation warnings are present."""
        answer = "An uncited claim."
        # No hits → fallback applied → at least one citation warning expected.
        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["warning_count"] > 0

        summary = _format_postprocess_debug_summary(pp)

        assert f"warnings={pp['warning_count']}" in summary

    def test_warning_details_line_present_when_warnings_exist(self) -> None:
        """A second [debug] line with warning details appears when warning_count > 0."""
        answer = "An uncited claim."
        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["citation_warnings"], "Expected at least one citation warning for this scenario"

        summary = _format_postprocess_debug_summary(pp)

        assert "[debug] warning_details:" in summary

    def test_no_warning_details_line_when_no_warnings(self) -> None:
        """No second [debug] line when warning_count == 0 (fully cited answer)."""
        answer = f"A fully cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        assert pp["warning_count"] == 0

        summary = _format_postprocess_debug_summary(pp)

        assert "warning_details" not in summary

    def test_summary_starts_with_debug_prefix(self) -> None:
        """The first line of the summary always starts with '[debug]'."""
        answer = f"Cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(pp)

        assert summary.startswith("[debug] ")

    def test_evidence_no_answer_for_empty_input(self) -> None:
        """evidence=no_answer is reflected correctly in the summary for empty answers."""
        pp = _postprocess_answer("", [], all_runs=False)

        summary = _format_postprocess_debug_summary(pp)

        assert "evidence=no_answer" in summary


# ---------------------------------------------------------------------------
# TestRunInteractiveQaDebugFlag
# ---------------------------------------------------------------------------


class TestRunInteractiveQaDebugFlag:
    """Integration tests for the debug flag in run_interactive_qa.

    These tests drive the full run_interactive_qa code path with a mocked
    Neo4j driver and LLM stack, then assert whether debug lines appear in
    captured stdout depending on the debug flag value.

    The mock setup mirrors the pattern used in test_retrieval_parity.py:
    patch the Neo4j driver and the retrieval/rag objects so no real network
    calls are made.
    """

    def _make_rag_result(self, answer: str, token: str | None = None) -> MagicMock:
        """Build a mock RAG result with one retrieval item."""
        mock_item = MagicMock()
        mock_item.metadata = {"citation_token": token, "chunk_id": "c1"} if token else {}
        mock_result = MagicMock()
        mock_result.answer = answer
        mock_result.retriever_result = MagicMock()
        mock_result.retriever_result.items = [mock_item]
        return mock_result

    def _run_one_turn(
        self,
        answer: str,
        token: str | None,
        *,
        debug: bool,
        all_runs: bool = True,
    ) -> str:
        """Run run_interactive_qa for one question turn and return captured stdout."""
        mock_rag_result = self._make_rag_result(answer, token)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured = io.StringIO()

        def _capture_print(*args: object, sep: str = " ", end: str = "\n", **_kw: object) -> None:
            captured.write(sep.join(str(a) for a in args) + end)

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__ = lambda s: s
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa(
                _LIVE_CONFIG,
                all_runs=all_runs,
                debug=debug,
            )

        return captured.getvalue()

    def test_debug_true_prints_debug_line(self) -> None:
        """When debug=True, a [debug] line is printed after the answer."""
        output = self._run_one_turn(
            f"Cited answer. {_TOKEN}",
            token=_TOKEN,
            debug=True,
        )
        assert "[debug]" in output

    def test_debug_false_does_not_print_debug_line(self) -> None:
        """When debug=False (default), no [debug] line is printed."""
        output = self._run_one_turn(
            f"Cited answer. {_TOKEN}",
            token=_TOKEN,
            debug=False,
        )
        assert "[debug]" not in output

    def test_debug_default_is_false(self) -> None:
        """run_interactive_qa's debug parameter defaults to False (no debug output)."""
        # Call without passing debug= at all to exercise the default.
        mock_rag_result = self._make_rag_result(f"Cited answer. {_TOKEN}", token=_TOKEN)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured = io.StringIO()

        def _capture_print(*args: object, sep: str = " ", end: str = "\n", **_kw: object) -> None:
            captured.write(sep.join(str(a) for a in args) + end)

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__ = lambda s: s
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            # No debug= passed — should default to False.
            run_interactive_qa(_LIVE_CONFIG, all_runs=True)

        assert "[debug]" not in captured.getvalue()

    def test_debug_true_summary_values_match_postprocess_result(self) -> None:
        """Debug output contains the correct field values for a fully cited answer."""
        answer = f"A fully cited answer. {_TOKEN}"
        output = self._run_one_turn(answer, token=_TOKEN, debug=True)

        assert "raw_cited=True" in output
        assert "final_cited=True" in output
        assert "repair_applied=False" in output
        assert "fallback_applied=False" in output
        assert "evidence=full" in output
        assert "warnings=0" in output

    def test_debug_true_fallback_scenario_summary(self) -> None:
        """Debug output reflects fallback_applied=True when the answer is uncited."""
        output = self._run_one_turn("Uncited answer with no token.", token=None, debug=True)

        assert "fallback_applied=True" in output
        assert "evidence=degraded" in output
