from __future__ import annotations

import argparse
import json
import os
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
    retrieval_stage = manifest["stages"]["retrieval_and_qa"]
    token = retrieval_stage.get("citation_token_example")
    if not isinstance(token, str):
        raise SystemExit("Missing citation_token_example in retrieval_and_qa stage")
    if not token.startswith("[CITATION|") or not token.endswith("]"):
        raise SystemExit("Citation token must start with '[CITATION|' and end with ']'")
    body = token[len("[CITATION|") : -1]
    parts = body.split("|")
    parsed = {}
    for part in parts:
        if "=" not in part:
            raise SystemExit(f"Malformed citation segment (expected key=value): {part!r}")
        try:
            key, value = part.split("=", 1)
        except ValueError as exc:
            raise SystemExit(f"Malformed citation segment (expected key=value): {part!r}") from exc
        if not key:
            raise SystemExit("Citation segment key must be non-empty")
        parsed[key] = value
    required_keys = {
        "chunk_id",
        "run_id",
        "source_uri",
        "chunk_index",
        "page",
        "start_char",
        "end_char",
    }
    missing_keys = required_keys.difference(parsed)
    if missing_keys:
        raise SystemExit(f"Missing citation fields in token: {sorted(missing_keys)}")
    for key in required_keys:
        value = parsed.get(key)
        if value is None or value == "":
            raise SystemExit(f"Citation field {key!r} must be non-empty")
    citation_example = retrieval_stage.get("citation_example")
    if not isinstance(citation_example, dict):
        raise SystemExit("Missing citation_example in retrieval_and_qa stage")
    if required_keys.difference(citation_example):
        missing_example = sorted(required_keys.difference(citation_example))
        raise SystemExit(f"citation_example missing required citation fields: {missing_example}")


def _build_config(output_dir: Path) -> DemoConfig:
    return DemoConfig(
        dry_run=True,
        output_dir=output_dir,
        neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "CHANGE_ME_BEFORE_USE"),
        neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
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
