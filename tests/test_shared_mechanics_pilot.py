from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_shared_mechanics_pilot_surface_classifies_candidates() -> None:
    shared_mechanics = importlib.import_module("power_atlas.shared_mechanics")

    assert [
        record.module for record in shared_mechanics.SHARED_MECHANICS_PILOT.included_modules
    ] == [
        "power_atlas.contracts.runtime",
        "power_atlas.contracts.manifest",
        "power_atlas.neo4j_io",
        "power_atlas.run_scope_queries",
        "power_atlas.retrieval_postprocessing",
        "power_atlas.retrieval_request_helpers",
    ]
    assert [
        record.module for record in shared_mechanics.SHARED_MECHANICS_PILOT.deferred_modules
    ] == [
        "power_atlas.context",
        "power_atlas.retrieval_request_context_adapters",
        "power_atlas.adapters.neo4j.*",
    ]

    deferred_notes = {
        record.module: record.hidden_assumptions
        for record in shared_mechanics.SHARED_MECHANICS_PILOT.deferred_modules
    }
    assert deferred_notes["power_atlas.context"] == (
        "AppContext and RequestContext still depend on AppSettings-backed runtime state.",
        "Default app-policy construction is still coupled to the current Power Atlas policy set.",
    )
    assert deferred_notes["power_atlas.retrieval_request_context_adapters"] == (
        "The adapter API currently requires RequestContext from power_atlas.context.",
        "Runtime forwarding still assumes app-owned retrieval policy and settings ownership.",
    )

    assert shared_mechanics.Config.__name__ == "Config"
    assert shared_mechanics.build_stage_manifest.__name__ == "build_stage_manifest"
    assert (
        shared_mechanics.format_retrieval_scope_label("pilot-run-id", False)
        == "run=pilot-run-id"
    )
    assert shared_mechanics.build_retrieval_query_params(
        run_id="pilot-run-id",
        source_uri="file:///pilot/source.pdf",
        all_runs=False,
        cluster_aware=True,
        alignment_version="align-v1",
    ) == {
        "alignment_version": "align-v1",
        "run_id": "pilot-run-id",
        "source_uri": "file:///pilot/source.pdf",
    }
    assert shared_mechanics.check_all_answers_cited(
        "Supported claim [CITATION|demo-run|file:///pilot/source.pdf|0|1|0|42]"
    )

    display_answer, history_answer, fallback_applied = (
        shared_mechanics.build_citation_fallback("Missing citation")
    )
    assert display_answer == "Insufficient citations detected: Missing citation"
    assert history_answer == shared_mechanics.CITATION_FALLBACK_PREFIX
    assert fallback_applied is True


def test_shared_mechanics_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "shared_mechanics_consumer.py")],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "consumer": "shared_mechanics_consumer",
        "deferred_modules": [
            {
                "hidden_assumptions": [
                    "AppContext and RequestContext still depend on AppSettings-backed runtime state.",
                    "Default app-policy construction is still coupled to the current Power Atlas policy set.",
                ],
                "module": "power_atlas.context",
            },
            {
                "hidden_assumptions": [
                    "The adapter API currently requires RequestContext from power_atlas.context.",
                    "Runtime forwarding still assumes app-owned retrieval policy and settings ownership.",
                ],
                "module": "power_atlas.retrieval_request_context_adapters",
            },
            {
                "hidden_assumptions": [
                    "The current pilot includes run-scope query mechanics via power_atlas.run_scope_queries only.",
                    "A broader adapters.neo4j family surface would currently mix mechanics with stage/domain runtime ownership.",
                ],
                "module": "power_atlas.adapters.neo4j.*",
            },
        ],
        "helpers": {
            "all_cited": True,
            "fallback": {
                "applied": True,
                "display_answer": "Insufficient citations detected: Missing citation",
                "history_answer": "Insufficient citations detected",
                "prefix": "Insufficient citations detected",
            },
            "query_params": {
                "alignment_version": "align-v1",
                "run_id": "pilot-run-id",
                "source_uri": "file:///pilot/source.pdf",
            },
            "scope_label": "run=pilot-run-id",
        },
        "included_modules": [
            "power_atlas.contracts.runtime",
            "power_atlas.contracts.manifest",
            "power_atlas.neo4j_io",
            "power_atlas.run_scope_queries",
            "power_atlas.retrieval_postprocessing",
            "power_atlas.retrieval_request_helpers",
        ],
        "runtime_surface": {
            "config_type": "Config",
            "manifest_builder": "build_stage_manifest",
        },
    }