from __future__ import annotations

import argparse
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path

from run_demo import DemoConfig, run_demo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chain_of_custody smoke test")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional manifest output directory; defaults to an isolated temporary directory.",
    )
    return parser.parse_args()


def _validate_manifest(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_stages = {
        "structured_ingest",
        "pdf_ingest",
        "claim_and_mention_extraction",
        "retrieval_and_qa",
    }
    missing = required_stages.difference(manifest.get("stages", {}))
    if missing:
        raise SystemExit(f"Missing stages in manifest: {sorted(missing)}")


def _build_config(output_dir: Path) -> DemoConfig:
    return DemoConfig(
        dry_run=True,
        output_dir=output_dir,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testtesttest",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )


def _run_and_validate(output_dir: Path) -> Path:
    manifest_path = run_demo(_build_config(output_dir))
    _validate_manifest(Path(manifest_path))
    return Path(manifest_path)


def main() -> None:
    args = _parse_args()
    with ExitStack() as stack:
        output_dir = args.output_dir or Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="chain_of_custody_smoke_"))
        )
        manifest_path = _run_and_validate(output_dir)
        print(f"Smoke test passed: {manifest_path}")


if __name__ == "__main__":
    main()
