import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.sync_vendor_version import get_gitlink_sha, sync_version_file


class SyncVendorVersionTests(unittest.TestCase):
    def test_sync_returns_success_when_already_in_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_content = {
                "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                "pinned_commit_sha": "same-sha",
                "tag": "1.13.1",
            }
            version_file.write_text(
                json.dumps(version_content),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="same-sha")

            self.assertEqual(exit_code, 0)
            data = json.loads(version_file.read_text(encoding="utf-8"))
            self.assertEqual(data, version_content)
            self.assertEqual(list(data.keys()), list(version_content.keys()))

    def test_sync_updates_pinned_commit_sha(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            original_content = {
                "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                "pinned_commit_sha": "old",
                "tag": "1.13.1",
            }
            version_file.write_text(
                json.dumps(original_content),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="new-sha")

            self.assertEqual(exit_code, 0)
            data = json.loads(version_file.read_text(encoding="utf-8"))
            expected_content = {
                "upstream_repo_url": original_content["upstream_repo_url"],
                "pinned_commit_sha": "new-sha",
                "tag": original_content["tag"],
            }
            self.assertEqual(data, expected_content)
            self.assertEqual(list(data.keys()), list(expected_content.keys()))

    def test_check_mode_fails_when_out_of_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_content = {
                "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                "pinned_commit_sha": "old",
                "tag": "1.13.1",
            }
            version_file.write_text(
                json.dumps(version_content),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="new-sha", check_only=True)

            self.assertEqual(exit_code, 1)
            data = json.loads(version_file.read_text(encoding="utf-8"))
            self.assertEqual(data, version_content)
            self.assertEqual(list(data.keys()), list(version_content.keys()))

    def test_check_mode_succeeds_when_in_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_content = {
                "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                "pinned_commit_sha": "same-sha",
                "tag": "1.13.1",
            }
            version_file.write_text(
                json.dumps(version_content),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="same-sha", check_only=True)

            self.assertEqual(exit_code, 0)
            data = json.loads(version_file.read_text(encoding="utf-8"))
            self.assertEqual(data, version_content)

    def test_sync_raises_when_version_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "nonexistent.version.json"

            with self.assertRaises(RuntimeError) as ctx:
                sync_version_file(version_file=version_file, gitlink_sha="any-sha")

            self.assertIn("not found", str(ctx.exception))

    def test_sync_raises_when_version_file_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_file.write_text("this is not json", encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                sync_version_file(version_file=version_file, gitlink_sha="any-sha")

            self.assertIn("Invalid JSON", str(ctx.exception))

    def test_sync_raises_when_pinned_commit_sha_field_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_file.write_text(
                json.dumps({"upstream_repo_url": "https://example.com", "tag": "1.0.0"}),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError) as ctx:
                sync_version_file(version_file=version_file, gitlink_sha="any-sha")

            self.assertIn("pinned_commit_sha", str(ctx.exception))


class GetGitlinkShaTests(unittest.TestCase):
    def test_raises_when_submodule_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a bare git repo so git ls-files works but finds nothing
            subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)

            with self.assertRaises(RuntimeError) as ctx:
                get_gitlink_sha(repo_root=Path(tmpdir), submodule_path="nonexistent/path")

            self.assertIn("No gitlink entry found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
