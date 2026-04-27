"""Tests for the pipelines/query/graph_health_diagnostics.py CLI entry point.

These tests exercise the ``main()`` function in the CLI script directly,
verifying that WARNING-level log records are emitted via ``_logger.warning``
when the result dict contains a non-empty ``warnings`` list.

``TestGraphHealthDiagnosticsCliMainWarnings``
    Verify that ``main()`` emits WARNING-level log records for each entry in
    ``result["warnings"]``, and emits no warnings when the list is empty.

``TestGraphHealthDiagnosticsCliMainArgParsing``
    Verify that ``main()`` exits with code 1 when no Neo4j password is
    provided.
"""
from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

import pipelines.query.graph_health_diagnostics as cli_module
from pipelines.query.graph_health_diagnostics import main


def _make_result(warnings: list[str], artifact_path: str = "/tmp/gh_artifact.json") -> dict[str, Any]:
    """Return a minimal mock result dict accepted by ``main()``."""
    return {
        "status": "live",
        "run_id": None,
        "alignment_version": None,
        "artifact_path": artifact_path,
        "artifact": None,
        "warnings": warnings,
    }


class TestGraphHealthDiagnosticsCliMainWarnings(unittest.TestCase):
    """Verify that main() routes result['warnings'] through _logger.warning."""

    def _run_main_with_mock_result(
        self,
        result: dict[str, Any],
        extra_argv: list[str] | None = None,
    ) -> None:
        argv = ["--neo4j-password", "secret"] + (extra_argv or [])
        with patch.object(cli_module, "run_graph_health_diagnostics_request_context", return_value=result):
            main(argv)

    def test_single_warning_emits_warning_log(self) -> None:
        """A single-entry warnings list must produce one WARNING record."""
        result = _make_result(warnings=["run_id not scoped – results may aggregate across runs"])
        with self.assertLogs("pipelines.query.graph_health_diagnostics", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertEqual(len(warning_records), 1)
        self.assertIn("run_id not scoped", warning_records[0])

    def test_multiple_warnings_each_emit_warning_log(self) -> None:
        """Each entry in warnings must produce a separate WARNING record."""
        result = _make_result(warnings=["first warning", "second warning"])
        with self.assertLogs("pipelines.query.graph_health_diagnostics", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertEqual(len(warning_records), 2)
        messages = " ".join(warning_records)
        self.assertIn("first warning", messages)
        self.assertIn("second warning", messages)

    def test_empty_warnings_emits_no_warning_log(self) -> None:
        """An empty warnings list must not produce any WARNING records."""
        result = _make_result(warnings=[])
        with self.assertNoLogs("pipelines.query.graph_health_diagnostics", level="WARNING"):
            self._run_main_with_mock_result(result)

    def test_missing_warnings_key_emits_no_warning_log(self) -> None:
        """A result dict without a 'warnings' key must not raise and must emit no warnings."""
        result = _make_result(warnings=[])
        del result["warnings"]
        with self.assertNoLogs("pipelines.query.graph_health_diagnostics", level="WARNING"):
            self._run_main_with_mock_result(result)


class TestGraphHealthDiagnosticsCliMainArgParsing(unittest.TestCase):
    """Verify CLI argument-parsing behaviour of main()."""

    def test_missing_password_exits_with_code_1(self) -> None:
        """main() must call sys.exit(1) when no password is supplied."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main([])
            self.assertEqual(ctx.exception.code, 1)

    def test_parse_args_uses_package_settings_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://gh.test:7687",
                "NEO4J_USERNAME": "gh-user",
                "NEO4J_DATABASE": "gh-db",
            },
            clear=True,
        ):
            args = cli_module._parse_args([])

        self.assertEqual(args.neo4j_uri, "bolt://gh.test:7687")
        self.assertEqual(args.neo4j_username, "gh-user")
        self.assertEqual(args.neo4j_database, "gh-db")
        self.assertEqual(args.neo4j_password, "")

    def test_parse_args_cli_overrides_package_settings_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://gh.test:7687",
                "NEO4J_USERNAME": "gh-user",
                "NEO4J_PASSWORD": "env-secret",
                "NEO4J_DATABASE": "gh-db",
            },
            clear=True,
        ):
            args = cli_module._parse_args(
                [
                    "--neo4j-uri",
                    "bolt://override.test:7687",
                    "--neo4j-username",
                    "override-user",
                    "--neo4j-password",
                    "override-secret",
                    "--neo4j-database",
                    "override-db",
                ]
            )

        self.assertEqual(args.neo4j_uri, "bolt://override.test:7687")
        self.assertEqual(args.neo4j_username, "override-user")
        self.assertEqual(args.neo4j_password, "override-secret")
        self.assertEqual(args.neo4j_database, "override-db")


class TestGraphHealthDiagnosticsCliUnscopedWarnings(unittest.TestCase):
    """CLI regression tests: verify warning behavior for unscoped runs.

    These tests ensure that when ``main()`` is called without ``--run-id``
    and/or ``--alignment-version``, the warnings produced by
    ``run_graph_health_diagnostics_request_context`` are routed through the CLI logger.
    """

    def _run_main_with_mock_result(
        self,
        result: dict[str, Any],
        extra_argv: list[str] | None = None,
    ) -> None:
        argv = ["--neo4j-password", "secret"] + (extra_argv or [])
        with patch.object(cli_module, "run_graph_health_diagnostics_request_context", return_value=result):
            main(argv)

    def test_unscoped_run_id_warning_routed_through_cli_logger(self) -> None:
        """When result contains a run_id-scoping warning, main() must emit it
        via the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_graph_health_diagnostics: run_id is None — diagnostics will aggregate "
                "across ALL pipeline runs in the database, not just the current run. "
                "Pass run_id to scope queries to the intended pipeline execution."
            ]
        )
        with self.assertLogs("pipelines.query.graph_health_diagnostics", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("run_id" in r for r in warning_records),
            f"Expected run_id warning in CLI log output, got: {captured.output}",
        )

    def test_unscoped_alignment_version_warning_routed_through_cli_logger(self) -> None:
        """When result contains an alignment_version-scoping warning, main() must emit
        it via the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_graph_health_diagnostics: alignment_version is None — alignment "
                "metrics will aggregate across ALL alignment versions in the database, "
                "not just the current cohort. "
                "Pass alignment_version (e.g. from the hybrid entity resolution stage output) "
                "to scope queries to the intended ALIGNED_WITH edge version."
            ]
        )
        with self.assertLogs("pipelines.query.graph_health_diagnostics", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("alignment_version" in r for r in warning_records),
            f"Expected alignment_version warning in CLI log output, got: {captured.output}",
        )

    def test_truncation_warning_routed_through_cli_logger(self) -> None:
        """When result contains a truncation warning, main() must emit it via
        the CLI logger at WARNING level."""
        result = _make_result(
            warnings=[
                "run_graph_health_diagnostics: per_canonical_alignment result is at the "
                "query row limit (30 rows) — the detail table "
                "may be truncated and not reflect all canonical entities in the current scope."
            ]
        )
        with self.assertLogs("pipelines.query.graph_health_diagnostics", level="WARNING") as captured:
            self._run_main_with_mock_result(result)

        warning_records = [r for r in captured.output if "WARNING" in r]
        self.assertTrue(
            any("truncated" in r for r in warning_records),
            f"Expected truncation warning in CLI log output, got: {captured.output}",
        )

    def test_fully_scoped_run_emits_no_warnings(self) -> None:
        """When result['warnings'] is empty (all parameters scoped), main() must
        emit no WARNING-level log records."""
        result = _make_result(warnings=[])
        with self.assertNoLogs("pipelines.query.graph_health_diagnostics", level="WARNING"):
            self._run_main_with_mock_result(result)


if __name__ == "__main__":
    unittest.main()
