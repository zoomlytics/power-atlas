"""Tests for the pipelines/query/retrieval_benchmark.py CLI entry point.

These tests exercise the ``main()`` function in the CLI script directly,
verifying that WARNING-level log records are emitted via ``_logger.warning``
when the result dict contains a non-empty ``warnings`` list.

``TestRetrievalBenchmarkCliMainWarnings``
    Verify that ``main()`` emits WARNING-level log records for each entry in
    ``result["warnings"]``, and emits no warnings when the list is empty.

``TestRetrievalBenchmarkCliMainArgParsing``
    Verify that ``main()`` exits with code 1 when no Neo4j password is
    provided.
"""
from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

import pipelines.query.retrieval_benchmark as cli_module
from pipelines.query.retrieval_benchmark import main


def _make_result(warnings: list[str], artifact_path: str = "/tmp/rb_artifact.json") -> dict[str, Any]:
    """Return a minimal mock result dict accepted by ``main()``."""
    return {
        "status": "live",
        "run_id": None,
        "dataset_id": None,
        "alignment_version": None,
        "artifact_path": artifact_path,
        "artifact": None,
        "warnings": warnings,
    }


class TestRetrievalBenchmarkCliMainWarnings(unittest.TestCase):
    """Verify that main() routes result['warnings'] through _logger.warning."""

    def _run_main_with_mock_result(
        self,
        result: dict[str, Any],
        extra_argv: list[str] | None = None,
    ) -> None:
        argv = ["--neo4j-password", "secret"] + (extra_argv or [])
        with patch.object(cli_module, "run_retrieval_benchmark", return_value=result):
            main(argv)

    def test_single_warning_emits_warning_log(self) -> None:
        """A single-entry warnings list must produce one WARNING record."""
        result = _make_result(warnings=["dataset_id not scoped – results may aggregate across datasets"])
        with self.assertLogs("pipelines.query.retrieval_benchmark", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertEqual(len(warning_records), 1)
        self.assertIn("dataset_id not scoped", warning_records[0])

    def test_multiple_warnings_each_emit_warning_log(self) -> None:
        """Each entry in warnings must produce a separate WARNING record."""
        result = _make_result(warnings=["first warning", "second warning"])
        with self.assertLogs("pipelines.query.retrieval_benchmark", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertEqual(len(warning_records), 2)
        messages = " ".join(warning_records)
        self.assertIn("first warning", messages)
        self.assertIn("second warning", messages)

    def test_empty_warnings_emits_no_warning_log(self) -> None:
        """An empty warnings list must not produce any WARNING records."""
        result = _make_result(warnings=[])
        with self.assertNoLogs("pipelines.query.retrieval_benchmark", level="WARNING"):
            self._run_main_with_mock_result(result)

    def test_missing_warnings_key_emits_no_warning_log(self) -> None:
        """A result dict without a 'warnings' key must not raise and must emit no warnings."""
        result = _make_result(warnings=[])
        del result["warnings"]
        with self.assertNoLogs("pipelines.query.retrieval_benchmark", level="WARNING"):
            self._run_main_with_mock_result(result)


class TestRetrievalBenchmarkCliMainArgParsing(unittest.TestCase):
    """Verify CLI argument-parsing behaviour of main()."""

    def test_missing_password_exits_with_code_1(self) -> None:
        """main() must call sys.exit(1) when no password is supplied."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main([])
            self.assertEqual(ctx.exception.code, 1)


class TestRetrievalBenchmarkCliUnscopedWarnings(unittest.TestCase):
    """CLI regression tests: verify warning behavior for unscoped runs.

    These tests ensure that when ``main()`` is called without ``--run-id``,
    ``--dataset-id``, and/or ``--alignment-version``, the warnings produced by
    ``run_retrieval_benchmark`` are routed through the CLI logger.
    """

    def _run_main_with_mock_result(
        self,
        result: dict[str, Any],
        extra_argv: list[str] | None = None,
    ) -> None:
        argv = ["--neo4j-password", "secret"] + (extra_argv or [])
        with patch.object(cli_module, "run_retrieval_benchmark", return_value=result):
            main(argv)

    def test_unscoped_run_id_warning_routed_through_cli_logger(self) -> None:
        """When result contains a run_id-scoping warning, main() must emit it
        via the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_retrieval_benchmark: run_id is None — benchmark will aggregate "
                "across ALL pipeline runs in the database, not just the current run. "
                "Pass run_id to scope queries to the intended pipeline execution."
            ]
        )
        with self.assertLogs("pipelines.query.retrieval_benchmark", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("run_id" in r for r in warning_records),
            f"Expected run_id warning in CLI log output, got: {captured.output}",
        )

    def test_unscoped_dataset_id_warning_routed_through_cli_logger(self) -> None:
        """When result contains a dataset_id-scoping warning, main() must emit it
        via the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_retrieval_benchmark: dataset_id is None — benchmark will aggregate "
                "across ALL datasets in the database, not just the current dataset. "
                "Results are not suitable for regression baselines in a multi-dataset graph. "
                "Pass dataset_id to scope queries to the intended dataset."
            ]
        )
        with self.assertLogs("pipelines.query.retrieval_benchmark", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("dataset_id" in r for r in warning_records),
            f"Expected dataset_id warning in CLI log output, got: {captured.output}",
        )

    def test_unscoped_alignment_version_warning_routed_through_cli_logger(self) -> None:
        """When result contains an alignment_version-scoping warning, main() must emit
        it via the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_retrieval_benchmark: alignment_version is None — benchmark will aggregate "
                "across ALL alignment versions in the database, not just the current cohort. "
                "Pass alignment_version (e.g. from the hybrid entity resolution stage output) "
                "to scope queries to the intended ALIGNED_WITH edge version."
            ]
        )
        with self.assertLogs("pipelines.query.retrieval_benchmark", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("alignment_version" in r for r in warning_records),
            f"Expected alignment_version warning in CLI log output, got: {captured.output}",
        )

    def test_fully_scoped_run_emits_no_warnings(self) -> None:
        """When result['warnings'] is empty (all parameters scoped), main() must
        emit no WARNING-level log records."""
        result = _make_result(warnings=[])
        with self.assertNoLogs("pipelines.query.retrieval_benchmark", level="WARNING"):
            self._run_main_with_mock_result(result)


if __name__ == "__main__":
    unittest.main()
