from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _require_installed_power_atlas() -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_without_repo_pythonpath(repo_root: Path) -> dict[str, str]:
    repo_src = repo_root / "src"
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    if pythonpath:
        filtered_entries = []
        for raw_entry in pythonpath.split(os.pathsep):
            if not raw_entry:
                continue
            try:
                resolved_entry = Path(raw_entry).resolve()
            except OSError:
                filtered_entries.append(raw_entry)
                continue
            if resolved_entry in {repo_root.resolve(), repo_src.resolve()}:
                continue
            filtered_entries.append(raw_entry)
        if filtered_entries:
            env["PYTHONPATH"] = os.pathsep.join(filtered_entries)
        else:
            env.pop("PYTHONPATH", None)
    return env


def _run_example_script_from_outside_repo_when_installed(
    example_name: str,
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)
    example_source = repo_root / "examples" / example_name
    script_path = tmp_path / example_name
    script_path.write_text(example_source.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )


def test_public_api_facade_imports_from_outside_repo_when_installed(tmp_path: Path) -> None:
    _require_installed_power_atlas()

    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)

    script = "\n".join(
        [
            "import json",
            "from power_atlas.api import BackendAppOptions, create_backend_app",
            "app = create_backend_app(BackendAppOptions(version='3.0.0-installed-test'), environ={})",
            "payload = {",
            "    'title': app.title,",
            "    'version': app.version,",
            "    'paths': sorted(",
            "        route.path",
            "        for route in app.routes",
            "        if getattr(route, 'path', None) in {'/', '/datasets', '/runs', '/runs/current', '/runs/current/{stage_prefix}', '/runs/{run_id}', '/health', '/graph/status'}",
            "    ),",
            "}",
            "print(json.dumps(payload, sort_keys=True))",
        ]
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas API",
        "version": "3.0.0-installed-test",
        "paths": ["/", "/datasets", "/graph/status", "/health", "/runs", "/runs/current", "/runs/current/{stage_prefix}", "/runs/{run_id}"],
    }


def test_reusable_core_domain_pack_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)
    script_path = tmp_path / "installed_domain_pack_consumer.py"
    script_path.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import re
            from dataclasses import replace

            from neo4j_graphrag.generation import RagTemplate

            from power_atlas.bootstrap import DomainPackDescriptor, build_app_context, build_request_context
            from power_atlas.contracts import (
                EntityResolutionAlignmentContract,
                EntityResolutionAlignmentStep,
                EntityResolutionCanonicalLookupContract,
                EntityResolutionDatasetSelectionContract,
                EntityResolutionGraphContract,
                RetrievalOntology,
                RetrievalPolicy,
            )
            from power_atlas.entity_resolution_entrypoint import (
                RESOLUTION_MODE_HYBRID,
                run_entity_resolution,
                run_entity_resolution_request_context,
            )
            from power_atlas.retrieval_request_context_adapters import run_retrieval_request_context


            domain_pack = DomainPackDescriptor(
                name="installed_research",
                version="v1",
                provides=(
                    "retrieval_policy",
                    "entity_resolution_graph_contract",
                    "entity_resolution_canonical_lookup_contract",
                    "entity_resolution_alignment_contract",
                    "entity_resolution_dataset_selection_contract",
                ),
                examples=("consumer/installed_domain_pack_consumer.py",),
            )

            retrieval_policy = RetrievalPolicy(
                ontology=RetrievalOntology(
                    claim_label="InstalledClaim",
                    mention_label="InstalledMention",
                    cluster_label="InstalledCluster",
                    canonical_label="InstalledEntity",
                    supported_by_relationship="SUPPORTED_BY_INSTALLED_SOURCE",
                    mentioned_in_relationship="MENTIONED_IN_INSTALLED_SOURCE",
                    has_participant_relationship="HAS_INSTALLED_PARTICIPANT",
                    resolves_to_relationship="RESOLVES_TO_INSTALLED_ENTITY",
                    member_of_relationship="MEMBER_OF_INSTALLED_CLUSTER",
                    aligned_with_relationship="ALIGNED_WITH_INSTALLED_ENTITY",
                ),
                qa_prompt_id="installed_qa_v1",
                rag_template=RagTemplate(
                    template=(
                        "Installed context:\\n{context}\\n"
                        "Examples:\\n{examples}\\n"
                        "Question:\\n{query_text}\\n"
                    ),
                    system_instructions="Answer with installed research evidence.",
                ),
                default_expand_graph=True,
                default_cluster_aware=True,
            )
            graph_contract = EntityResolutionGraphContract(
                mention_label="InstalledMention",
                canonical_label="InstalledEntity",
                cluster_label="InstalledCluster",
                resolves_to_relationship="RESOLVES_TO_INSTALLED_ENTITY",
                member_of_relationship="MEMBER_OF_INSTALLED_CLUSTER",
                candidate_match_relationship="CANDIDATE_INSTALLED_MATCH",
                aligned_with_relationship="ALIGNED_WITH_INSTALLED_ENTITY",
            )
            canonical_lookup = EntityResolutionCanonicalLookupContract(
                canonical_entity_id_field="installed_id",
                canonical_run_id_field="installed_run_id",
                canonical_name_field="installed_name",
                canonical_aliases_field="installed_aliases",
                qid_pattern=re.compile(r"^IR\\d+$"),
                qid_exact_method="installed_id_exact",
                label_exact_method="installed_label_exact",
                alias_exact_method="installed_alias_exact",
                unresolved_method="installed_cluster",
                aligned_status="aligned",
            )
            alignment_contract = EntityResolutionAlignmentContract(
                steps=(
                    EntityResolutionAlignmentStep(
                        lookup_table="alias",
                        cluster_keys=lambda cluster: (cluster["normalized_text"].removeprefix("memo:"),),
                        method="installed_alias",
                        score=0.96,
                        status="aligned",
                    ),
                    EntityResolutionAlignmentStep(
                        lookup_table="label",
                        method="installed_label_exact",
                        score=0.9,
                        status="tentative",
                    ),
                )
            )
            dataset_selection = EntityResolutionDatasetSelectionContract(
                select_dataset_id=lambda config, dataset_id, dataset_name: (
                    dataset_id
                    or f"installed-canonicals::{dataset_name or getattr(config, 'dataset_name', 'missing')}"
                )
            )

            app_context = build_app_context(environ={"POWER_ATLAS_DATASET": "installed_dataset_v1"})
            app_context = replace(
                app_context,
                policies=replace(app_context.policies, retrieval=retrieval_policy),
            )

            retrieval_request_context = build_request_context(
                app_context,
                command="ask",
                dry_run=True,
                question="Which installed retrieval policy was forwarded?",
                run_id="installed-retrieval-run",
                source_uri="file:///installed/source.pdf",
            )
            entity_resolution_request_context = build_request_context(
                app_context,
                command="resolve",
                dry_run=True,
                resolution_mode=RESOLUTION_MODE_HYBRID,
                run_id="installed-resolution-run",
                source_uri="file:///installed/source.pdf",
            )

            retrieval_result = run_retrieval_request_context(
                retrieval_request_context,
                top_k=2,
                index_name=None,
                question=None,
                expand_graph=None,
                cluster_aware=None,
                message_history=None,
                interactive=False,
                run_impl=lambda config, **kwargs: {
                    "question": kwargs["question"],
                    "run_id": kwargs["run_id"],
                    "qa_prompt_id": kwargs["retrieval_policy"].qa_prompt_id,
                    "claim_label": kwargs["retrieval_policy"].ontology.claim_label,
                    "cluster_aware": kwargs["retrieval_policy"].default_cluster_aware,
                },
            )

            def _runtime_runner(**kwargs: object) -> dict[str, object]:
                runtime_graph = kwargs["entity_resolution_graph"]
                runtime_lookup = kwargs["entity_resolution_canonical_lookup"]
                runtime_alignment = kwargs["entity_resolution_alignment"]
                return {
                    "run_id": kwargs["run_id"],
                    "resolution_mode": kwargs["resolution_mode"],
                    "effective_dataset_id": kwargs["effective_dataset_id"],
                    "canonical_label": runtime_graph.canonical_label,
                    "entity_id_field": runtime_lookup.canonical_entity_id_field,
                    "alignment_methods": [step.method for step in runtime_alignment.steps],
                }

            def _config_runner(config: object, **kwargs: object) -> dict[str, object]:
                return run_entity_resolution(
                    config,
                    runtime_runner=_runtime_runner,
                    **kwargs,
                )

            entity_resolution_result = run_entity_resolution_request_context(
                entity_resolution_request_context,
                resolution_mode=RESOLUTION_MODE_HYBRID,
                entity_resolution_dataset_selection=dataset_selection,
                entity_resolution_alignment=alignment_contract,
                entity_resolution_canonical_lookup=canonical_lookup,
                entity_resolution_graph=graph_contract,
                config_runner=_config_runner,
            )

            print(
                json.dumps(
                    {
                        "domain_pack": {
                            "name": domain_pack.name,
                            "version": domain_pack.version,
                            "provides": list(domain_pack.provides),
                        },
                        "retrieval": retrieval_result,
                        "entity_resolution": entity_resolution_result,
                    },
                    sort_keys=True,
                )
            )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "domain_pack": {
            "name": "installed_research",
            "provides": [
                "retrieval_policy",
                "entity_resolution_graph_contract",
                "entity_resolution_canonical_lookup_contract",
                "entity_resolution_alignment_contract",
                "entity_resolution_dataset_selection_contract",
            ],
            "version": "v1",
        },
        "entity_resolution": {
            "alignment_methods": ["installed_alias", "installed_label_exact"],
            "canonical_label": "InstalledEntity",
            "effective_dataset_id": "installed-canonicals::installed_dataset_v1",
            "entity_id_field": "installed_id",
            "resolution_mode": "hybrid",
            "run_id": "installed-resolution-run",
        },
        "retrieval": {
            "claim_label": "InstalledClaim",
            "cluster_aware": True,
            "qa_prompt_id": "installed_qa_v1",
            "question": "Which installed retrieval policy was forwarded?",
            "run_id": "installed-retrieval-run",
        },
    }


def test_installed_console_script_set_matches_public_cli_contract() -> None:
    _require_installed_power_atlas()

    distribution = importlib.metadata.distribution("power-atlas")
    console_scripts = sorted(
        entry_point.name
        for entry_point in distribution.entry_points
        if entry_point.group == "console_scripts"
    )

    assert console_scripts == [
        "power-atlas-claim-diagnostics-report",
        "power-atlas-graph-health-diagnostics",
        "power-atlas-retrieval-benchmark",
    ]


def test_graph_health_cli_runs_from_outside_repo_when_installed(tmp_path: Path) -> None:
    _require_installed_power_atlas()

    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)

    completed = subprocess.run(
        ["power-atlas-graph-health-diagnostics", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "Generate a repeatable graph-health diagnostics artifact." in completed.stdout
    assert "--alignment-version" in completed.stdout
    assert "--neo4j-password" in completed.stdout


def test_retrieval_benchmark_cli_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)

    completed = subprocess.run(
        ["power-atlas-retrieval-benchmark", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "Run the post-hybrid retrieval benchmark and write a JSON artifact." in completed.stdout
    assert "--dataset-id" in completed.stdout
    assert "--neo4j-password" in completed.stdout


def test_claim_diagnostics_cli_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    repo_root = _repo_root()
    env = _env_without_repo_pythonpath(repo_root)

    completed = subprocess.run(
        ["power-atlas-claim-diagnostics-report", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "Read and format a persisted claim-extraction diagnostics artifact." in completed.stdout
    assert "--current" in completed.stdout
    assert "--output-dir" in completed.stdout


def test_backend_api_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas Consumer Example",
        "version": "0.1.0-example",
        "paths": ["/", "/consumer-info", "/datasets", "/graph/status", "/health", "/runs", "/runs/current", "/runs/current/{stage_prefix}", "/runs/{run_id}"],
    }


def test_retrieval_policy_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "retrieval_policy_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "all_runs": False,
        "consumer": "retrieval_policy_consumer",
        "ontology": {
            "claim_label": "ConsumerClaim",
            "mentioned_in_relationship": "OBSERVED_WITHIN",
            "supported_by_relationship": "SUPPORTED_EXTERNALLY_BY",
        },
        "qa_prompt_id": "consumer_alt_qa_v1",
        "question": "Which retrieval policy was forwarded?",
        "run_id": "consumer-run-id",
        "source_uri": "file:///consumer/source.pdf",
    }


def test_market_trade_retrieval_policy_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "market_trade_retrieval_policy_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "all_runs": False,
        "consumer": "market_trade_retrieval_policy_consumer",
        "ontology": {
            "canonical_label": "Security",
            "claim_label": "MarketClaim",
            "mentioned_in_relationship": "MENTIONED_IN_MARKET_SOURCE",
        },
        "qa_prompt_id": "market_trade_qa_v1",
        "question": "Which market/trade retrieval policy was forwarded?",
        "run_id": "market-trade-run-id",
        "source_uri": "file:///market/trade/source.pdf",
        "traversal_defaults": {
            "cluster_aware": True,
            "expand_graph": True,
        },
    }


def test_market_trade_entity_resolution_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "market_trade_entity_resolution_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "alignment_steps": [
            {
                "lookup_table": "alias",
                "method": "ticker_symbol_alias",
                "score": 0.97,
                "status": "tentative",
            },
            {
                "lookup_table": "label",
                "method": "security_label_exact",
                "score": 0.9,
                "status": "aligned",
            },
        ],
        "canonical_lookup": {
            "aliases_field": "ticker_aliases",
            "entity_id_field": "security_id",
            "qid_exact_method": "security_id_exact",
        },
        "consumer": "market_trade_entity_resolution_consumer",
        "effective_dataset_id": "market-canonicals::market_trade_dataset_v1",
        "graph": {
            "aligned_with_relationship": "ALIGNED_WITH_SECURITY",
            "canonical_label": "Security",
            "member_of_relationship": "MEMBER_OF_SECURITY_CLUSTER",
        },
        "resolution_mode": "hybrid",
        "run_id": "market-trade-entity-resolution-run-id",
        "source_uri": "file:///market/trade/source.pdf",
    }


def test_domain_pack_starter_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "domain_pack_starter.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "consumer": "domain_pack_starter",
        "domain_pack": {
            "examples": ["examples/domain_pack_starter.py"],
            "name": "research_memo",
            "provides": [
                "retrieval_policy",
                "entity_resolution_graph_contract",
                "entity_resolution_canonical_lookup_contract",
                "entity_resolution_alignment_contract",
                "entity_resolution_dataset_selection_contract",
            ],
            "version": "v0",
        },
        "entity_resolution": {
            "alignment_steps": [
                {
                    "lookup_table": "alias",
                    "method": "memo_alias",
                    "score": 0.95,
                    "status": "aligned",
                },
                {
                    "lookup_table": "label",
                    "method": "research_label_exact",
                    "score": 0.88,
                    "status": "tentative",
                },
            ],
            "canonical_lookup": {
                "entity_id_field": "research_id",
                "qid_exact_method": "research_id_exact",
            },
            "effective_dataset_id": "research-memo-canonicals::research_memo_dataset_v1",
            "graph": {
                "aligned_with_relationship": "ALIGNED_WITH_RESEARCH_ENTITY",
                "canonical_label": "ResearchEntity",
            },
            "resolution_mode": "hybrid",
            "run_id": "research-memo-entity-resolution-run-id",
        },
        "retrieval": {
            "canonical_label": "ResearchEntity",
            "claim_label": "ResearchClaim",
            "cluster_aware": False,
            "qa_prompt_id": "research_memo_qa_v0",
            "question": "Which research memo policy was forwarded?",
            "run_id": "research-memo-retrieval-run-id",
        },
    }


def test_claim_extraction_diagnostics_report_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "claim_extraction_diagnostics_report_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "consumer": "claim_extraction_diagnostics_report_consumer",
        "current": {
            "artifact_relative_path": "runs/unstructured_ingest-20260512T000000Z-a/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
            "inferred_dataset_id": "demo_dataset_v1",
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "source_uri_line": "Source URI    : file:///report/source.pdf",
            "status": "live",
            "warnings": ["report warning"],
        },
        "run_scoped": {
            "artifact_relative_path": "runs/unstructured_ingest-20260512T000000Z-a/claim_extraction_diagnostics/claim_extraction_diagnostics.json",
            "inferred_dataset_id": None,
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "source_uri_line": "Source URI    : file:///report/source.pdf",
            "status": "live",
            "warnings": ["report warning"],
        },
    }


def test_backend_api_custom_graph_queries_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_custom_graph_queries.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "consumer_info": {
            "backend_title": "Power Atlas Custom Graph Example",
            "backend_version": "0.1.0-custom-example",
            "consumer": "backend_api_custom_graph_queries",
        },
        "graph_status": {
            "database": "example",
            "detail": "Example consumer graph service is active",
            "neo4j_uri": "neo4j://example-consumer:7687",
            "status": "available",
        },
        "graph_summary": {
            "counts": {
                "canonical_entity_count": 1,
                "chunk_count": 4,
                "claim_count": 3,
                "cluster_count": 2,
                "document_count": 2,
                "mention_count": 8,
            },
            "database": "example",
            "detail": "Example consumer summary is active",
            "neo4j_uri": "neo4j://example-consumer:7687",
            "status": "available",
        },
        "title": "Power Atlas Custom Graph Example",
        "version": "0.1.0-custom-example",
    }


def test_backend_api_runtime_probe_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_runtime_probe.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "consumer": "backend_api_runtime_probe",
        "runtime": {
            "app_context_type": "AppContext",
            "dataset_name": "demo_dataset_v1",
            "graph_queries_type": "DefaultBackendGraphQueryService",
            "neo4j_database": "neo4j",
            "output_dir_name": "backend-runtime-example",
            "runtime_on_app_state": True,
        },
        "runtime_retrieved_directly": True,
        "title": "Power Atlas Runtime Probe Example",
        "version": "0.1.0-runtime-probe",
    }


def test_backend_api_composed_app_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_composed_app.py",
        tmp_path,
    )

    payload = json.loads(completed.stdout)

    assert payload == {
        "backend_current_claim_diagnostics": {
            "inferred_dataset_id": "demo_dataset_v1",
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "source_uri": "file:///mounted/source.pdf",
            "status": "dry_run",
            "warnings": ["claim extraction diagnostics skipped in dry_run mode"],
        },
        "backend_datasets": {
            "dataset_names": ["demo_dataset_v1", "demo_dataset_v2"],
            "selected_dataset_name": "demo_dataset_v1",
            "selection_mode": "configured",
        },
        "backend_current_runs": {
            "detail": None,
            "inferred_dataset_id": "demo_dataset_v1",
            "run_ids": ["unstructured_ingest-20260512T000000Z-a"],
            "runs_root": payload["backend_current_runs"]["runs_root"],
        },
        "backend_current_run_detail": {
            "inferred_dataset_id": "demo_dataset_v1",
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "run_stage_names": [
                "claim_extraction",
                "claim_extraction_diagnostics",
                "pdf_ingest",
            ],
            "stages": ["claim_extraction"],
        },
        "backend_graph_status": {
            "database": "neo4j",
            "detail": "Neo4j password is not configured",
            "neo4j_uri": "neo4j://localhost:7687",
            "status": "not_configured",
        },
        "backend_health": {
            "message": "Backend is healthy",
            "status": "ok",
        },
        "backend_root": {
            "docs": "/docs",
            "message": "Power Atlas API",
            "version": "0.1.0-mounted",
        },
        "host_info": {
            "host": "backend_api_composed_app",
            "host_title": "Host Application",
            "host_version": "1.0.0-host",
        },
    }
    assert payload["backend_current_runs"]["runs_root"].endswith("/runs")


def test_backend_api_guarded_app_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    _require_installed_power_atlas()

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_guarded_app.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "authorized_current_claim_diagnostics": {
            "inferred_dataset_id": "demo_dataset_v1",
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "source_uri": "file:///guarded/source.pdf",
            "status": "dry_run",
            "warnings": ["claim extraction diagnostics skipped in dry_run mode"],
        },
        "authorized_health": {
            "body": {
                "message": "Backend is healthy",
                "status": "ok",
            },
            "status_code": 200,
        },
        "authorized_current_run_detail": {
            "inferred_dataset_id": "demo_dataset_v1",
            "run_id": "unstructured_ingest-20260512T000000Z-a",
            "run_stage_names": [
                "claim_extraction",
                "claim_extraction_diagnostics",
                "pdf_ingest",
            ],
            "stages": ["claim_extraction"],
        },
        "authorized_current_runs": {
            "inferred_dataset_id": "demo_dataset_v1",
            "run_ids": ["unstructured_ingest-20260512T000000Z-a"],
            "stage_names": [[
                "claim_extraction",
                "claim_extraction_diagnostics",
                "pdf_ingest",
            ]],
        },
        "host_info": {
            "host": "backend_api_guarded_app",
            "host_title": "Guarded Host Application",
            "host_version": "1.0.0-guarded",
        },
        "unauthorized_health": {
            "body": {"detail": "Missing or invalid atlas token"},
            "status_code": 401,
        },
    }