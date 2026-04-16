"""Tests for power_atlas.contracts.paths.DatasetRoot and resolve_dataset_root().

These tests exercise the fixture-path abstraction layer introduced in the
multi-dataset support phase.  All assertions use the live filesystem so they
validate both the resolution logic and the actual dataset directory layout.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from power_atlas.contracts.paths import (
    AmbiguousDatasetError,
    DATASETS_CONTAINER_DIR,
    DatasetRoot,
    FIXTURES_DIR,
    list_available_datasets,
    resolve_dataset_root,
)

DEMO_DIR = Path(__file__).resolve().parents[1]


class TestDatasetRootResolution(unittest.TestCase):
    # ------------------------------------------------------------------
    # list_available_datasets
    # ------------------------------------------------------------------

    def test_list_available_datasets_returns_demo_dataset_v1(self):
        datasets = list_available_datasets()
        self.assertIn("demo_dataset_v1", datasets)

    def test_list_available_datasets_excludes_hidden_dirs(self):
        datasets = list_available_datasets()
        for name in datasets:
            self.assertFalse(name.startswith("."))

    # ------------------------------------------------------------------
    # resolve_dataset_root — explicit name
    # ------------------------------------------------------------------

    def test_resolve_by_explicit_name(self):
        dr = resolve_dataset_root("demo_dataset_v1")
        self.assertIsInstance(dr, DatasetRoot)
        self.assertEqual(dr.dataset_id, "demo_dataset_v1")
        self.assertEqual(dr.pdf_filename, "chain_of_custody.pdf")
        self.assertTrue(dr.root.is_dir())

    def test_resolve_explicit_name_not_found_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_dataset_root("nonexistent_dataset_xyz")
        self.assertIn("nonexistent_dataset_xyz", str(ctx.exception))
        self.assertIn("Available", str(ctx.exception))

    def test_resolve_dotdot_raises_value_error(self):
        """'..' as a dataset name must be rejected to prevent directory traversal."""
        with self.assertRaises(ValueError):
            resolve_dataset_root("..")

    def test_resolve_dot_raises_value_error(self):
        """'.' as a dataset name must be rejected."""
        with self.assertRaises(ValueError):
            resolve_dataset_root(".")

    def test_resolve_path_separator_raises_value_error(self):
        """Names containing path separators must be rejected."""
        with self.assertRaises(ValueError):
            resolve_dataset_root("../other_dataset")

    # ------------------------------------------------------------------
    # resolve_dataset_root — env var
    # ------------------------------------------------------------------

    def test_resolve_via_env_var(self):
        original = os.environ.pop("FIXTURE_DATASET", None)
        try:
            os.environ["FIXTURE_DATASET"] = "demo_dataset_v1"
            dr = resolve_dataset_root()
            self.assertEqual(dr.dataset_id, "demo_dataset_v1")
        finally:
            if original is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original

    def test_resolve_via_explicit_environ_mapping(self):
        dr = resolve_dataset_root(environ={"POWER_ATLAS_DATASET": "demo_dataset_v1"})
        self.assertEqual(dr.dataset_id, "demo_dataset_v1")

    def test_resolve_explicit_name_overrides_env_var(self):
        original = os.environ.pop("FIXTURE_DATASET", None)
        try:
            os.environ["FIXTURE_DATASET"] = "nonexistent_dataset_xyz"
            # Explicit name that IS valid overrides the (broken) env var.
            dr = resolve_dataset_root("demo_dataset_v1")
            self.assertEqual(dr.dataset_id, "demo_dataset_v1")
        finally:
            if original is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original

    # ------------------------------------------------------------------
    # resolve_dataset_root — auto-discovery
    # ------------------------------------------------------------------

    def test_auto_discovery_single_dataset(self):
        """With FIXTURE_DATASET unset and exactly one dataset dir, resolve succeeds."""
        original_env = os.environ.pop("FIXTURE_DATASET", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                fake_container = Path(tmpdir) / "datasets"
                single_ds = fake_container / "my_only_dataset"
                single_ds.mkdir(parents=True)
                # Provide a minimal manifest so DatasetRoot can resolve dataset_id.
                (single_ds / "manifest.json").write_text(
                    '{"dataset": "my_only_dataset", "provenance": [{"id": "p", "kind": "pdf", "path": "unstructured/doc.pdf"}]}',
                    encoding="utf-8",
                )

                import power_atlas.contracts.paths as paths_mod
                original_container = paths_mod.DATASETS_CONTAINER_DIR
                try:
                    paths_mod.DATASETS_CONTAINER_DIR = fake_container
                    dr = resolve_dataset_root()
                    self.assertEqual(dr.dataset_id, "my_only_dataset")
                    self.assertEqual(dr.root, single_ds)
                finally:
                    paths_mod.DATASETS_CONTAINER_DIR = original_container
        finally:
            if original_env is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original_env

    def test_auto_discovery_empty_container_raises(self):
        """When DATASETS_CONTAINER_DIR exists but is empty, resolve raises ValueError."""
        original_env = os.environ.pop("FIXTURE_DATASET", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                empty_container = Path(tmpdir) / "datasets"
                empty_container.mkdir()  # Exists but has no subdirectories.

                import power_atlas.contracts.paths as paths_mod
                original_container = paths_mod.DATASETS_CONTAINER_DIR
                try:
                    paths_mod.DATASETS_CONTAINER_DIR = empty_container
                    with self.assertRaises(ValueError) as ctx:
                        resolve_dataset_root()
                    self.assertIn("No dataset directories found", str(ctx.exception))
                finally:
                    paths_mod.DATASETS_CONTAINER_DIR = original_container
        finally:
            if original_env is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original_env

    def test_auto_discovery_multiple_datasets_raises(self):
        """With two dataset dirs and no selection, resolve raises AmbiguousDatasetError."""
        original_env = os.environ.pop("FIXTURE_DATASET", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                fake_container = Path(tmpdir) / "datasets"
                (fake_container / "alpha").mkdir(parents=True)
                (fake_container / "beta").mkdir(parents=True)

                # Monkey-patch the module-level constant for the duration of the call.
                import power_atlas.contracts.paths as paths_mod
                original_container = paths_mod.DATASETS_CONTAINER_DIR
                try:
                    paths_mod.DATASETS_CONTAINER_DIR = fake_container
                    with self.assertRaises(AmbiguousDatasetError) as ctx:
                        resolve_dataset_root()
                    self.assertIn("Multiple datasets", str(ctx.exception))
                    self.assertIn("--dataset", str(ctx.exception))
                finally:
                    paths_mod.DATASETS_CONTAINER_DIR = original_container
        finally:
            if original_env is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original_env

    # ------------------------------------------------------------------
    # DatasetRoot property accessors
    # ------------------------------------------------------------------

    def test_dataset_root_properties(self):
        dr = resolve_dataset_root("demo_dataset_v1")
        self.assertTrue(dr.pdf_path.is_file(), f"PDF not found at {dr.pdf_path}")
        self.assertTrue(dr.structured_dir.is_dir(), f"structured_dir not found: {dr.structured_dir}")
        self.assertTrue(dr.unstructured_dir.is_dir(), f"unstructured_dir not found: {dr.unstructured_dir}")
        self.assertTrue(dr.manifest_path.is_file(), f"manifest.json not found: {dr.manifest_path}")

    def test_dataset_root_manifest_has_correct_dataset_id(self):
        dr = resolve_dataset_root("demo_dataset_v1")
        data = json.loads(dr.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["dataset"], "demo_dataset_v1")

    def test_dataset_root_manifest_provenance_paths_are_relative(self):
        """Per-dataset manifest should use dataset-root-relative paths, not repo-absolute."""
        dr = resolve_dataset_root("demo_dataset_v1")
        data = json.loads(dr.manifest_path.read_text(encoding="utf-8"))
        for entry in data.get("provenance", []):
            path_str = entry.get("path", "")
            self.assertFalse(
                path_str.startswith("demo/"),
                f"provenance path should be dataset-root-relative, got: {path_str!r}",
            )

    def test_dataset_root_pdf_filename_matches_provenance(self):
        dr = resolve_dataset_root("demo_dataset_v1")
        data = json.loads(dr.manifest_path.read_text(encoding="utf-8"))
        pdf_entries = [e for e in data.get("provenance", []) if e.get("kind") == "pdf"]
        self.assertTrue(pdf_entries, "No pdf provenance entry found in manifest")
        expected_filename = Path(pdf_entries[0]["path"]).name
        self.assertEqual(dr.pdf_filename, expected_filename)

    def test_dataset_root_structured_csvs_exist(self):
        dr = resolve_dataset_root("demo_dataset_v1")
        for csv_name in ("entities.csv", "facts.csv", "relationships.csv", "claims.csv"):
            csv_path = dr.structured_dir / csv_name
            self.assertTrue(csv_path.is_file(), f"Expected structured CSV not found: {csv_path}")

    # ------------------------------------------------------------------
    # Legacy fallback: FIXTURES_DIR itself acts as dataset root when no
    # DATASETS_CONTAINER_DIR exists.
    # ------------------------------------------------------------------

    def test_legacy_fallback_returns_dataset_root(self):
        """When datasets/ dir is absent, FIXTURES_DIR is treated as the dataset root."""
        original_env = os.environ.pop("FIXTURE_DATASET", None)
        try:
            import power_atlas.contracts.paths as paths_mod
            original_container = paths_mod.DATASETS_CONTAINER_DIR
            try:
                # Point container to a non-existent directory.
                paths_mod.DATASETS_CONTAINER_DIR = FIXTURES_DIR / "__nonexistent__"
                dr = resolve_dataset_root()
                # Should fall back to FIXTURES_DIR itself.
                self.assertEqual(dr.root, FIXTURES_DIR)
            finally:
                paths_mod.DATASETS_CONTAINER_DIR = original_container
        finally:
            if original_env is None:
                os.environ.pop("FIXTURE_DATASET", None)
            else:
                os.environ["FIXTURE_DATASET"] = original_env

    # ------------------------------------------------------------------
    # Dataset root isolation: lint works with a custom dataset copy
    # ------------------------------------------------------------------

    def test_lint_uses_custom_fixtures_dir(self):
        """lint_and_clean_structured_csvs respects an explicit fixtures_dir."""
        from demo.stages import lint_and_clean_structured_csvs

        dr = resolve_dataset_root("demo_dataset_v1")
        with tempfile.TemporaryDirectory() as tmpdir:
            copied_dataset = Path(tmpdir) / "dataset_copy"
            # Copy only the structured/ sub-directory; lint_and_clean_structured_csvs
            # does not need any unstructured assets, so this avoids duplicating
            # large PDFs and speeds up the test.
            shutil.copytree(dr.structured_dir, copied_dataset / "structured")
            output_dir = Path(tmpdir) / "output"
            result = lint_and_clean_structured_csvs(
                run_id="test-lint-run",
                output_dir=output_dir,
                fixtures_dir=copied_dataset,
            )
            self.assertEqual(result["lint_summary"]["status"], "ok")
            self.assertIn("claims.csv", result["files"])


if __name__ == "__main__":
    unittest.main()
