import json
import tempfile
import unittest
from pathlib import Path

from scripts.sync_vendor_version import sync_version_file


class SyncVendorVersionTests(unittest.TestCase):
    def test_sync_returns_success_when_already_in_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_file.write_text(
                json.dumps(
                    {
                        "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                        "pinned_commit_sha": "same-sha",
                        "tag": "1.13.1",
                    }
                ),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="same-sha")

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(version_file.read_text(encoding="utf-8"))["pinned_commit_sha"], "same-sha")

    def test_sync_updates_pinned_commit_sha(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_file.write_text(
                json.dumps(
                    {
                        "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                        "pinned_commit_sha": "old",
                        "tag": "1.13.1",
                    }
                ),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="new-sha")

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(version_file.read_text(encoding="utf-8"))["pinned_commit_sha"], "new-sha")

    def test_check_mode_fails_when_out_of_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "neo4j-graphrag-python.version.json"
            version_file.write_text(
                json.dumps(
                    {
                        "upstream_repo_url": "https://github.com/neo4j/neo4j-graphrag-python.git",
                        "pinned_commit_sha": "old",
                        "tag": "1.13.1",
                    }
                ),
                encoding="utf-8",
            )

            exit_code = sync_version_file(version_file=version_file, gitlink_sha="new-sha", check_only=True)

            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(version_file.read_text(encoding="utf-8"))["pinned_commit_sha"], "old")


if __name__ == "__main__":
    unittest.main()
