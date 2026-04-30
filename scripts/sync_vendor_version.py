#!/usr/bin/env python3
"""Sync vendor version metadata with the submodule gitlink SHA."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from power_atlas.interfaces.cli.sync_vendor_version_entrypoint import run_sync_vendor_version_main
from power_atlas.interfaces.cli.sync_vendor_version_support import parse_sync_vendor_version_args

SUBMODULE_PATH = "vendor/neo4j-graphrag-python"
VERSION_FILE = REPO_ROOT / "docs/vendor/neo4j-graphrag-python.version.json"


def get_gitlink_sha(repo_root: Path = REPO_ROOT, submodule_path: str = SUBMODULE_PATH) -> str:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--stage", "--", submodule_path],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to query gitlink SHA for {submodule_path!r} in repository {repo_root}: {exc}"
        ) from exc

    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(f"No gitlink entry found for {submodule_path}")
    if len(lines) > 1:
        raise RuntimeError(
            f"Multiple gitlink entries found for {submodule_path}: {result.stdout!r}"
        )

    line = lines[0]
    parts = line.split()
    if len(parts) < 2:
        raise RuntimeError(f"Unexpected git output format for gitlink {submodule_path}: {line!r}")
    return parts[1]


def sync_version_file(version_file: Path = VERSION_FILE, gitlink_sha: str | None = None, check_only: bool = False) -> int:
    sha = gitlink_sha or get_gitlink_sha()

    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"Version file not found: {version_file}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in version file {version_file}: {exc}") from exc

    if "pinned_commit_sha" not in data:
        raise RuntimeError(f"Version file {version_file} is missing the 'pinned_commit_sha' field")

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
    version_file.write_text(f"{json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)}\n", encoding="utf-8")
    print(f"Updated {version_file} pinned_commit_sha to {sha}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_sync_vendor_version_main(
        parse_args=parse_sync_vendor_version_args,
        sync_version_file=sync_version_file,
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
