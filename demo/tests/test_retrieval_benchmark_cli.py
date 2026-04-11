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

import unittest
from pathlib import Path
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
        with patch.dict("os.environ", {}, clear=True):
            # Ensure NEO4J_PASSWORD env var is absent.
            import os
            env_backup = os.environ.pop("NEO4J_PASSWORD", None)
            try:
                with self.assertRaises(SystemExit) as ctx:
                    main([])
                self.assertEqual(ctx.exception.code, 1)
            finally:
                if env_backup is not None:
                    os.environ["NEO4J_PASSWORD"] = env_backup


if __name__ == "__main__":
    unittest.main()
