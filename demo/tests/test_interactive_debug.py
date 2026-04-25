"""Tests for the interactive debug output surface in :func:`run_interactive_qa_request_context`.

These tests verify that:

- When ``debug=True``, a compact postprocessing summary is printed after each
  answer, sourced from the shared :class:`_RetrievalDebugView` contract.
- When ``debug=False`` (default), no debug output is emitted.
- The summary produced by :func:`_format_postprocess_debug_summary` reflects
  the correct values from the debug view for representative scenarios.
- :func:`_build_retrieval_debug_view` correctly projects an
  :class:`_AnswerPostprocessResult` into a :class:`_RetrievalDebugView`.

Structure
---------
``TestBuildRetrievalDebugView``
    Unit tests for :func:`_build_retrieval_debug_view`, covering baseline
    construction, repair-applied scenario, and malformed-diagnostics propagation.

``TestFormatPostprocessDebugSummary``
    Unit tests for :func:`_format_postprocess_debug_summary` directly, covering
    the key scenarios the issue calls for (fully cited, repair applied, fallback
    applied, warnings present, malformed diagnostics).

``TestRunInteractiveQaDebugFlag``
    Integration tests that drive :func:`run_interactive_qa_request_context` with a fully mocked
    Neo4j / LLM stack and assert whether debug lines appear in stdout depending
    on the *debug* flag.
"""
from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from demo.stages.retrieval_and_qa import (
    _RetrievalDebugView,
    _build_retrieval_debug_view,
    _format_postprocess_debug_summary,
    _postprocess_answer,
    run_interactive_qa_request_context,
)
from power_atlas.bootstrap import build_app_context, build_request_context
from power_atlas.orchestration.context_builder import build_request_context_from_config
from power_atlas.contracts import Config as _RuntimeConfig
from power_atlas.contracts.pipeline import (
    get_pipeline_contract_config_data,
    get_pipeline_contract_snapshot,
)
from power_atlas.settings import AppSettings, Neo4jSettings

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

def _make_live_config() -> _RuntimeConfig:
    output_dir = Path("artifacts")
    return _RuntimeConfig(
        dry_run=False,
        output_dir=output_dir,
        settings=AppSettings(
            neo4j=Neo4jSettings(
                uri="bolt://localhost:7687",
                username="neo4j",
                password="password",
                database=None,
            ),
            openai_model="gpt-4o-mini",
            output_dir=output_dir,
        ),
        pipeline_contract=get_pipeline_contract_snapshot(),
        pipeline_contract_config_data=get_pipeline_contract_config_data(),
    )


#: Minimal config that satisfies all live-retrieval field validations.
_LIVE_CONFIG = _make_live_config()

#: A valid synthetic citation token.
_TOKEN = (
    "[CITATION|chunk_id=c1|run_id=r1|source_uri=file%3A%2F%2F%2Fdoc.pdf"
    "|chunk_index=0|page=1|start_char=0|end_char=50]"
)

#: A single retrieval hit carrying _TOKEN.
_HIT: dict[str, object] = {"metadata": {"citation_token": _TOKEN, "chunk_id": "c1"}}


def test_run_interactive_qa_request_context_forwards_pipeline_contract() -> None:
    app_context = build_app_context(settings=_LIVE_CONFIG.settings)
    request_context = build_request_context(
        app_context,
        command="ask",
        dry_run=False,
        output_dir=_LIVE_CONFIG.output_dir,
        run_id="interactive-run-1",
        source_uri="file:///interactive/doc.pdf",
    )
    captured: dict[str, object] = {}

    def _fake_run_interactive_qa_impl(config, **kwargs):
        captured["config"] = config
        captured.update(kwargs)

    with patch(
        "demo.stages.retrieval_and_qa._run_interactive_qa_impl",
        side_effect=_fake_run_interactive_qa_impl,
    ):
        run_interactive_qa_request_context(request_context)

    assert captured["config"] is request_context.config
    assert captured["pipeline_contract"] is request_context.pipeline_contract
    assert captured["neo4j_settings"] is request_context.settings.neo4j


# ---------------------------------------------------------------------------
# TestBuildRetrievalDebugView
# ---------------------------------------------------------------------------


class TestBuildRetrievalDebugView:
    """Unit tests for _build_retrieval_debug_view.

    Verifies that the factory correctly projects _AnswerPostprocessResult
    fields into _RetrievalDebugView, including the repair-applied scenario
    and malformed-diagnostics propagation.
    """

    def test_baseline_fully_cited(self) -> None:
        """All fields are populated correctly for a fully cited answer."""
        answer = f"A fully cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        view = _build_retrieval_debug_view(pp)

        assert view["raw_answer_all_cited"] is True
        assert view["all_cited"] is True
        assert view["citation_repair_applied"] is False
        assert view["citation_fallback_applied"] is False
        assert view["evidence_level"] == "full"
        assert view["warning_count"] == 0
        assert view["citation_warnings"] == []
        assert view["malformed_diagnostics_count"] == 0

    def test_repair_applied_scenario(self) -> None:
        """citation_repair_applied is True when repair changes the answer text."""
        answer = "An uncited claim needing repair."
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        assert pp["citation_repair_applied"] is True, "Precondition: repair must be applied"

        view = _build_retrieval_debug_view(pp)

        assert view["citation_repair_applied"] is True
        assert view["raw_answer_all_cited"] is False
        assert view["all_cited"] is True
        assert view["citation_fallback_applied"] is False
        assert view["evidence_level"] == "full"

    def test_malformed_diagnostics_count_propagated(self) -> None:
        """malformed_diagnostics_count is taken from the keyword argument, not recomputed."""
        answer = f"A cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        view = _build_retrieval_debug_view(pp, malformed_diagnostics_count=3)

        assert view["malformed_diagnostics_count"] == 3

    def test_malformed_diagnostics_default_is_zero(self) -> None:
        """malformed_diagnostics_count defaults to 0 when not provided."""
        answer = f"A cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        view = _build_retrieval_debug_view(pp)

        assert view["malformed_diagnostics_count"] == 0

    def test_view_is_retrieval_debug_view_type(self) -> None:
        """_build_retrieval_debug_view returns a dict with the _RetrievalDebugView keys."""
        answer = f"Cited. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        view = _build_retrieval_debug_view(pp)

        assert set(view.keys()) == set(_RetrievalDebugView.__annotations__)

    def test_citation_warnings_forwarded(self) -> None:
        """citation_warnings from the postprocess result are present in the view."""
        # No hits → fallback → citation warning expected.
        pp = _postprocess_answer("An uncited answer.", [], all_runs=False)

        assert pp["citation_warnings"], "Precondition: at least one warning expected"

        view = _build_retrieval_debug_view(pp)

        assert view["citation_warnings"] == pp["citation_warnings"]
        assert view["warning_count"] == pp["warning_count"]


# ---------------------------------------------------------------------------
# TestFormatPostprocessDebugSummary
# ---------------------------------------------------------------------------


class TestFormatPostprocessDebugSummary:
    """Unit tests for _format_postprocess_debug_summary.

    Each test builds a _RetrievalDebugView via _build_retrieval_debug_view and
    then asserts that the summary line correctly reflects the values in the view,
    covering: raw/final citation state, repair/fallback applied, evidence level,
    warning count, and malformed-diagnostics count.
    """

    def test_fully_cited_answer_summary(self) -> None:
        """Summary correctly reflects a fully cited answer with no repair or fallback."""
        answer = f"A fully cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert "[debug]" in summary
        assert "raw_cited=True" in summary
        assert "final_cited=True" in summary
        assert "repair_applied=False" in summary
        assert "fallback_applied=False" in summary
        assert "evidence=full" in summary
        assert "warnings=0" in summary
        assert "malformed_diagnostics=0" in summary

    def test_repair_applied_summary(self) -> None:
        """Summary reflects citation_repair_applied=True when repair changes the answer text."""
        answer = "An uncited claim needing repair."
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        # Repair should be applied in all-runs mode with a hit available.
        assert pp["citation_repair_applied"] is True

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

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

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

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

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert f"warnings={pp['warning_count']}" in summary

    def test_warning_details_line_present_when_warnings_exist(self) -> None:
        """A second [debug] line with warning details appears when warning_count > 0."""
        answer = "An uncited claim."
        pp = _postprocess_answer(answer, [], all_runs=False)

        assert pp["citation_warnings"], "Expected at least one citation warning for this scenario"

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert "[debug] warning_details:" in summary

    def test_no_warning_details_line_when_no_warnings(self) -> None:
        """No second [debug] line when warning_count == 0 (fully cited answer)."""
        answer = f"A fully cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        assert pp["warning_count"] == 0

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert "warning_details" not in summary

    def test_summary_starts_with_debug_prefix(self) -> None:
        """The first line of the summary always starts with '[debug]'."""
        answer = f"Cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert summary.startswith("[debug] ")

    def test_evidence_no_answer_for_empty_input(self) -> None:
        """evidence=no_answer is reflected correctly in the summary for empty answers."""
        pp = _postprocess_answer("", [], all_runs=False)

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert "evidence=no_answer" in summary

    def test_malformed_diagnostics_nonzero_in_summary(self) -> None:
        """malformed_diagnostics count is shown in the summary when non-zero."""
        answer = f"A cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(
            _build_retrieval_debug_view(pp, malformed_diagnostics_count=2)
        )

        assert "malformed_diagnostics=2" in summary

    def test_malformed_diagnostics_zero_in_summary(self) -> None:
        """malformed_diagnostics=0 is shown in the summary when all diagnostics are well-formed."""
        answer = f"A cited answer. {_TOKEN}"
        pp = _postprocess_answer(answer, [_HIT], all_runs=True)

        summary = _format_postprocess_debug_summary(_build_retrieval_debug_view(pp))

        assert "malformed_diagnostics=0" in summary


# ---------------------------------------------------------------------------
# TestRunInteractiveQaDebugFlag
# ---------------------------------------------------------------------------


class TestRunInteractiveQaDebugFlag:
    """Integration tests for the debug flag in run_interactive_qa_request_context.

    These tests drive the full request-context interactive QA code path with a mocked
    Neo4j driver and LLM stack, then assert whether debug lines appear in
    captured stdout depending on the debug flag value.

    The mock setup mirrors the pattern used in test_retrieval_parity.py:
    patch the Neo4j driver and the retrieval/rag objects so no real network
    calls are made.
    """

    @staticmethod
    def _make_capture() -> tuple[io.StringIO, Callable[..., None]]:
        """Return (captured_sio, capture_fn) for patching builtins.print."""
        captured = io.StringIO()

        def _capture_print(*args: object, sep: str = " ", end: str = "\n", **_kw: object) -> None:
            captured.write(sep.join(str(a) for a in args) + end)

        return captured, _capture_print

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
        """Run run_interactive_qa_request_context for one question turn and return captured stdout."""
        mock_rag_result = self._make_rag_result(answer, token)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None if all_runs else "interactive-debug-run",
            all_runs=all_runs,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__.return_value = (
                mock_neo4j.GraphDatabase.driver.return_value
            )
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa_request_context(request_context, debug=debug)

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
        """run_interactive_qa_request_context's debug parameter defaults to False (no debug output)."""
        # Call without passing debug= at all to exercise the default.
        mock_rag_result = self._make_rag_result(f"Cited answer. {_TOKEN}", token=_TOKEN)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None,
            all_runs=True,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            driver_mock = mock_neo4j.GraphDatabase.driver.return_value
            driver_mock.__enter__.return_value = driver_mock
            driver_mock.__exit__.return_value = False
            # No debug= passed — should default to False.
            run_interactive_qa_request_context(request_context)

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
        assert "malformed_diagnostics=0" in output

    def test_debug_true_fallback_scenario_summary(self) -> None:
        """Debug output reflects fallback_applied=True when the answer is uncited."""
        output = self._run_one_turn("Uncited answer with no token.", token=None, debug=True)

        assert "fallback_applied=True" in output
        assert "evidence=degraded" in output

    def test_debug_values_sourced_from_postprocess_result_not_recomputed(self) -> None:
        """Debug output values come from _postprocess_answer, not independently recomputed.

        This test patches _postprocess_answer to return a controlled result and
        verifies that the exact values from that result appear in the debug output,
        proving the debug surface reads from the shared postprocessing contract
        rather than recomputing citation quality independently.
        """
        import demo.stages.retrieval_and_qa as _raq_mod

        controlled_pp: _raq_mod._AnswerPostprocessResult = {
            "raw_answer": "some answer",
            "raw_answer_all_cited": False,
            "repaired_answer": "some answer (repaired)",
            "citation_repair_attempted": True,
            "citation_repair_applied": True,
            "citation_repair_strategy": "first_hit",
            "citation_repair_source_chunk_id": "cx99",
            "display_answer": "some answer (repaired)",
            "history_answer": "some answer (repaired)",
            "citation_fallback_applied": False,
            "all_cited": True,
            "evidence_level": "full",
            "citation_warnings": [],
            "warning_count": 0,
            "citation_quality": {
                "all_cited": True,
                "raw_answer_all_cited": False,
                "evidence_level": "full",
                "warning_count": 0,
                "citation_warnings": [],
            },
        }

        mock_rag_result = self._make_rag_result(f"Cited answer. {_TOKEN}", token=_TOKEN)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None,
            all_runs=True,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
            patch(
                "demo.stages.retrieval_and_qa._postprocess_answer",
                return_value=controlled_pp,
            ),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__.return_value = (
                mock_neo4j.GraphDatabase.driver.return_value
            )
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa_request_context(request_context, debug=True)

        output = captured.getvalue()
        # Verify the debug line reflects the controlled pp values, not recomputed ones.
        assert "raw_cited=False" in output
        assert "final_cited=True" in output
        assert "repair_applied=True" in output
        assert "fallback_applied=False" in output
        assert "evidence=full" in output
        assert "warnings=0" in output
        assert "malformed_diagnostics=0" in output

    def test_debug_malformed_diagnostics_reflected_in_output(self) -> None:
        """Debug output shows malformed_diagnostics_count when hits have malformed diagnostics.

        Patches _count_malformed_diagnostics to return 1 and verifies that the
        value propagates through _build_retrieval_debug_view into the debug line.
        """
        mock_rag_result = self._make_rag_result(f"Cited answer. {_TOKEN}", token=_TOKEN)
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None,
            all_runs=True,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
            patch(
                "demo.stages.retrieval_and_qa._count_malformed_diagnostics",
                return_value=1,
            ),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__.return_value = (
                mock_neo4j.GraphDatabase.driver.return_value
            )
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa_request_context(request_context, debug=True)

        output = captured.getvalue()
        assert "malformed_diagnostics=1" in output

    def test_debug_robustness_no_retriever_result(self) -> None:
        """Debug output is emitted without error when retriever_result is None."""
        mock_rag_result = MagicMock()
        mock_rag_result.answer = "An answer with no retriever result."
        mock_rag_result.retriever_result = None
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None,
            all_runs=True,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__.return_value = (
                mock_neo4j.GraphDatabase.driver.return_value
            )
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa_request_context(request_context, debug=True)

        output = captured.getvalue()
        assert "[debug]" in output

    def test_debug_robustness_empty_retriever_items(self) -> None:
        """Debug output is emitted without error when retriever_result.items is empty."""
        mock_rag_result = MagicMock()
        mock_rag_result.answer = "An answer with no retrieval hits."
        mock_rag_result.retriever_result = MagicMock()
        mock_rag_result.retriever_result.items = []
        mock_rag = MagicMock()
        mock_rag.search.return_value = mock_rag_result

        captured, _capture_print = self._make_capture()
        request_context = build_request_context_from_config(
            _LIVE_CONFIG,
            command="ask",
            run_id=None,
            all_runs=True,
        )

        with (
            patch("demo.stages.retrieval_and_qa.neo4j") as mock_neo4j,
            patch(
                "demo.stages.retrieval_and_qa._build_retriever_and_rag",
                return_value=(MagicMock(), mock_rag),
            ),
            patch("demo.stages.retrieval_and_qa.os.getenv", return_value="fake-api-key"),
            patch("builtins.input", side_effect=["test question", EOFError()]),
            patch("builtins.print", side_effect=_capture_print),
        ):
            mock_neo4j.GraphDatabase.driver.return_value.__enter__.return_value = (
                mock_neo4j.GraphDatabase.driver.return_value
            )
            mock_neo4j.GraphDatabase.driver.return_value.__exit__ = MagicMock(return_value=False)
            run_interactive_qa_request_context(request_context, debug=True)

        output = captured.getvalue()
        assert "[debug]" in output
