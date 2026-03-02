from __future__ import annotations

import argparse
import json
import tempfile
from contextlib import nullcontext
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


def main() -> None:
    args = _parse_args()
    output_dir_context = (
        nullcontext(args.output_dir)
        if args.output_dir is not None
        else tempfile.TemporaryDirectory(prefix="chain_of_custody_smoke_")
    )
    with output_dir_context as output_dir_value:
        manifest_path = run_demo(
            DemoConfig(
                dry_run=True,
                output_dir=Path(output_dir_value),
                neo4j_uri="neo4j://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="testtesttest",
                neo4j_database="neo4j",
                openai_model="gpt-4o-mini",
            )
        )
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        required_stages = {
            "structured_ingest",
            "pdf_ingest",
            "claim_and_mention_extraction",
            "retrieval_and_qa",
        }
        missing = required_stages.difference(manifest.get("stages", {}))
        if missing:
            raise SystemExit(f"Missing stages in manifest: {sorted(missing)}")

        print(f"Smoke test passed: {manifest_path}")


if __name__ == "__main__":
    main()
