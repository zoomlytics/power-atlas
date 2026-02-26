#!/usr/bin/env python3
"""Sync vendor version metadata with the submodule gitlink SHA."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMODULE_PATH = "vendor/neo4j-graphrag-python"
VERSION_FILE = REPO_ROOT / "docs/vendor/neo4j-graphrag-python.version.json"


def get_gitlink_sha(repo_root: Path = REPO_ROOT, submodule_path: str = SUBMODULE_PATH) -> str:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", submodule_path],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    line = result.stdout.strip()
    if not line:
        raise RuntimeError(f"No gitlink entry found for {submodule_path}")

    parts = line.split()
    if len(parts) < 2:
        raise RuntimeError(f"Unexpected gitlink format: {line}")
    return parts[1]


def sync_version_file(version_file: Path = VERSION_FILE, gitlink_sha: str | None = None, check_only: bool = False) -> int:
    sha = gitlink_sha or get_gitlink_sha()

    data = json.loads(version_file.read_text(encoding="utf-8"))
    current_sha = data.get("pinned_commit_sha")
    if current_sha == sha:
        print(f"{version_file} already in sync ({sha})")
        return 0

    if check_only:
        print(
            f"{version_file} is out of sync: pinned_commit_sha={current_sha} gitlink_sha={sha}",
            file=sys.stderr,
        )
        return 1

    data["pinned_commit_sha"] = sha
    version_file.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")
    print(f"Updated {version_file} pinned_commit_sha to {sha}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the version file is out of sync")
    args = parser.parse_args()
    return sync_version_file(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
