from __future__ import annotations

import json
from pathlib import Path

from run_demo import ARTIFACTS_DIR, DemoConfig, run_demo


def main() -> None:
    manifest_path = run_demo(
        DemoConfig(
            dry_run=True,
            output_dir=ARTIFACTS_DIR,
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
