from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

from power_atlas.bootstrap import build_settings
from power_atlas.claim_extraction_diagnostics_artifact import (
    resolve_claim_extraction_diagnostics_artifact,
    resolve_current_claim_extraction_diagnostics_artifact,
)
from power_atlas.contracts import resolve_dataset_root
from power_atlas.interfaces.cli.claim_extraction_diagnostics_entrypoint import (
    run_claim_extraction_diagnostics_report_main,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_example_runs(output_dir: Path) -> tuple[str, str]:
    selected_dataset_id = resolve_dataset_root("demo_dataset_v1", environ={}).dataset_id
    selected_run_id = "unstructured_ingest-20260512T000000Z-a"
    other_run_id = "unstructured_ingest-20260512T000100Z-b"

    _write_json(
        output_dir / "runs" / selected_run_id / "claim_extraction" / "manifest.json",
        {
            "run_id": selected_run_id,
            "dataset_id": selected_dataset_id,
            "stages": {"claim_extraction": {"status": "live"}},
        },
    )
    _write_json(
        output_dir
        / "runs"
        / selected_run_id
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json",
        {
            "status": "live",
            "generated_at": "2026-05-13T12:00:00+00:00",
            "run_id": selected_run_id,
            "source_uri": "file:///report/source.pdf",
            "artifact_path": "ignored-by-reader",
            "participation_summary": {
                "total_edges": 4,
                "edges_by_role": {"subject": 3, "object": 1},
                "total_claims": 5,
                "claims_with_zero_edges": 1,
                "claim_coverage_pct": 80.0,
            },
            "match_summary": {
                "total_edges_with_match_method": 3,
                "edges_by_match_method": {"normalized_exact": 2, "list_split": 1},
            },
            "warnings": ["report warning"],
        },
    )
    _write_json(
        output_dir / "runs" / other_run_id / "claim_extraction" / "manifest.json",
        {
            "run_id": other_run_id,
            "dataset_id": "demo_dataset_v2",
            "stages": {"claim_extraction": {"status": "live"}},
        },
    )
    return selected_run_id, other_run_id


def _run_report(
    output_dir: Path,
    args: Namespace,
) -> dict[str, object]:
    lines: list[str] = []
    warnings: list[str] = []

    run_claim_extraction_diagnostics_report_main(
        parse_args=lambda argv: args,
        build_settings=lambda parsed_args: build_settings(
            {
                "POWER_ATLAS_OUTPUT_DIR": str(output_dir),
                "POWER_ATLAS_DATASET": "demo_dataset_v1",
            }
        ),
        resolve_artifact=resolve_claim_extraction_diagnostics_artifact,
        resolve_current_artifact=resolve_current_claim_extraction_diagnostics_artifact,
        warn=warnings.append,
        emit=lines.append,
    )

    summary = json.loads(lines[-1])
    return {
        "status": summary["status"],
        "run_id": summary["run_id"],
        "artifact_relative_path": str(
            Path(summary["artifact_path"]).resolve().relative_to(output_dir.resolve())
        ),
        "source_uri_line": next(
            line for line in lines if line.startswith("Source URI    : ")
        ),
        "warnings": warnings,
        "inferred_dataset_id": summary.get("inferred_dataset_id"),
    }


if __name__ == "__main__":
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        selected_run_id, _ = _seed_example_runs(output_dir)
        run_scoped = _run_report(
            output_dir,
            Namespace(current=False, run_id=selected_run_id),
        )
        current = _run_report(
            output_dir,
            Namespace(current=True, stage_prefix="unstructured_ingest", dataset_id=None),
        )
        print(
            json.dumps(
                {
                    "consumer": "claim_extraction_diagnostics_report_consumer",
                    "run_scoped": run_scoped,
                    "current": current,
                },
                sort_keys=True,
            )
        )