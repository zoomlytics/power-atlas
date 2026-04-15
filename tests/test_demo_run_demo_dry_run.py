from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_demo_run_demo_dry_run_ingest_pdf_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("UNSTRUCTURED_RUN_ID", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "demo.run_demo",
            "ingest-pdf",
            "--dry-run",
            "--dataset",
            "demo_dataset_v1",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    prefix = "Independent run manifest written to: "
    manifest_line = next(
        line for line in result.stdout.splitlines() if line.startswith(prefix)
    )
    manifest_path = Path(manifest_line.removeprefix(prefix).strip())

    assert manifest_path.is_file()
    assert manifest_path.is_relative_to(tmp_path)


def test_demo_run_demo_dry_run_ask_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("UNSTRUCTURED_RUN_ID", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "demo.run_demo",
            "ask",
            "--dry-run",
            "--dataset",
            "demo_dataset_v1",
            "--run-id",
            "unstructured_ingest-test-12345678",
            "--question",
            "What does the document say about Endeavor?",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Using retrieval scope: run=unstructured_ingest-test-12345678" in result.stdout
    prefix = "Independent run manifest written to: "
    manifest_line = next(
        line for line in result.stdout.splitlines() if line.startswith(prefix)
    )
    manifest_path = Path(manifest_line.removeprefix(prefix).strip())

    assert manifest_path.is_file()
    assert manifest_path.is_relative_to(tmp_path)