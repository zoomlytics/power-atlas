from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

from power_atlas.api import BackendAppOptions, create_backend_app
from power_atlas.contracts import resolve_dataset_root


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
    repo_root = Path(__file__).resolve().parents[1]
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


def test_public_api_facade_supports_consumer_app_smoke() -> None:
    consumer_app = create_backend_app(
        BackendAppOptions(version="2.0.0-test"),
        environ={},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            root_response = await client.get("/")
            assert root_response.status_code == 200
            assert root_response.json() == {
                "message": "Power Atlas API",
                "version": "2.0.0-test",
                "docs": "/docs",
            }

            health_response = await client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json() == {
                "status": "ok",
                "message": "Backend is healthy",
            }

            datasets_response = await client.get("/datasets")
            assert datasets_response.status_code == 200
            expected_datasets = []
            for dataset_name in ("demo_dataset_v1", "demo_dataset_v2"):
                dataset_root = resolve_dataset_root(dataset_name, environ={})
                expected_datasets.append(
                    {
                        "dataset_id": dataset_root.dataset_id,
                        "manifest_path": str(dataset_root.manifest_path),
                        "name": dataset_name,
                        "pdf_filename": dataset_root.pdf_filename,
                        "root_path": str(dataset_root.root),
                    }
                )
            assert datasets_response.json() == {
                "datasets": expected_datasets,
                "detail": "Multiple datasets are available. Set POWER_ATLAS_DATASET or FIXTURE_DATASET to select one explicitly.",
                "selected_dataset": None,
                "selection_mode": "ambiguous",
            }

            runs_response = await client.get("/runs")
            assert runs_response.status_code == 200
            runs_payload = runs_response.json()
            assert set(runs_payload) == {"output_dir", "runs_root", "runs", "detail"}
            assert isinstance(runs_payload["runs"], list)
            assert runs_payload["output_dir"] == str(Path("artifacts").resolve())
            assert runs_payload["runs_root"] == str((Path("artifacts") / "runs").resolve())

            missing_run_response = await client.get("/runs/unstructured_ingest-test-run")
            assert missing_run_response.status_code == 404
            assert "was not found" in missing_run_response.json()["detail"]

            graph_status_response = await client.get("/graph/status")
            assert graph_status_response.status_code == 503
            assert graph_status_response.json() == {
                "status": "not_configured",
                "detail": "Neo4j password is not configured",
                "neo4j_uri": "neo4j://localhost:7687",
                "database": "neo4j",
            }

    asyncio.run(_exercise_app())


def test_public_api_facade_imports_from_outside_repo_when_installed(tmp_path: Path) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
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
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
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
    try:
        distribution = importlib.metadata.distribution("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
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
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
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
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    repo_root = Path(__file__).resolve().parents[1]
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


def test_backend_api_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "backend_api_consumer.py")],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas Consumer Example",
        "version": "0.1.0-example",
        "paths": ["/", "/consumer-info", "/datasets", "/graph/status", "/health", "/runs", "/runs/current", "/runs/current/{stage_prefix}", "/runs/{run_id}"],
    }


def test_backend_api_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

    completed = _run_example_script_from_outside_repo_when_installed(
        "backend_api_consumer.py",
        tmp_path,
    )

    assert json.loads(completed.stdout) == {
        "title": "Power Atlas Consumer Example",
        "version": "0.1.0-example",
        "paths": ["/", "/consumer-info", "/datasets", "/graph/status", "/health", "/runs", "/runs/current", "/runs/current/{stage_prefix}", "/runs/{run_id}"],
    }


def test_retrieval_benchmark_package_module_help_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "power_atlas.cli.retrieval_benchmark", "--help"],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "Run the post-hybrid retrieval benchmark and write a JSON artifact." in completed.stdout
    assert "--dataset-id" in completed.stdout
    assert "--neo4j-password" in completed.stdout


def test_graph_health_diagnostics_package_module_help_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "power_atlas.cli.graph_health_diagnostics", "--help"],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "Generate a repeatable graph-health diagnostics artifact." in completed.stdout
    assert "--alignment-version" in completed.stdout
    assert "--neo4j-password" in completed.stdout


def test_retrieval_policy_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "examples" / "retrieval_policy_consumer.py")],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_retrieval_policy_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_market_trade_retrieval_policy_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "market_trade_retrieval_policy_consumer.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_market_trade_retrieval_policy_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_market_trade_entity_resolution_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "market_trade_entity_resolution_consumer.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_market_trade_entity_resolution_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_domain_pack_starter_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "domain_pack_starter.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_domain_pack_starter_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_claim_extraction_diagnostics_report_consumer_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "claim_extraction_diagnostics_report_consumer.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_claim_extraction_diagnostics_report_consumer_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_claim_extraction_diagnostics_report_script_runs_for_run_and_current(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    selected_dataset_id = resolve_dataset_root("demo_dataset_v1", environ={}).dataset_id
    run_id = "unstructured_ingest-20260512T000000Z-a"

    manifest_path = tmp_path / "runs" / run_id / "claim_extraction" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dataset_id": selected_dataset_id,
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    artifact_path = (
        tmp_path
        / "runs"
        / run_id
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "status": "dry_run",
                "generated_at": "2026-05-13T12:00:00+00:00",
                "run_id": run_id,
                "source_uri": "file:///script/source.pdf",
                "artifact_path": "ignored-by-reader",
                "participation_summary": {
                    "total_edges": 0,
                    "edges_by_role": {},
                    "total_claims": 0,
                    "claims_with_zero_edges": 0,
                    "claim_coverage_pct": None,
                },
                "match_summary": {
                    "total_edges_with_match_method": 0,
                    "edges_by_match_method": {},
                },
                "warnings": ["script warning"],
            }
        ),
        encoding="utf-8",
    )

    base_env = os.environ.copy()
    base_env["POWER_ATLAS_OUTPUT_DIR"] = str(tmp_path)
    base_env["POWER_ATLAS_DATASET"] = "demo_dataset_v1"

    run_scoped = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipelines" / "query" / "claim_extraction_diagnostics_report.py"),
            "--run-id",
            run_id,
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=base_env,
        capture_output=True,
        check=True,
        text=True,
    )
    current = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipelines" / "query" / "claim_extraction_diagnostics_report.py"),
            "--current",
            "--stage-prefix",
            "unstructured_ingest",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=base_env,
        capture_output=True,
        check=True,
        text=True,
    )

    run_lines = [line for line in run_scoped.stdout.splitlines() if line]
    current_lines = [line for line in current.stdout.splitlines() if line]
    assert "Status        : dry_run" in run_lines
    assert "Source URI    : file:///script/source.pdf" in run_lines
    assert json.loads(run_lines[-1]) == {
        "run_id": run_id,
        "artifact_path": str(artifact_path.resolve()),
        "status": "dry_run",
    }
    assert "Status        : dry_run" in current_lines
    assert "Source URI    : file:///script/source.pdf" in current_lines
    assert json.loads(current_lines[-1]) == {
        "run_id": run_id,
        "artifact_path": str(artifact_path.resolve()),
        "status": "dry_run",
        "inferred_dataset_id": "demo_dataset_v1",
    }


def test_claim_extraction_diagnostics_report_module_runs_for_run_and_current(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    selected_dataset_id = resolve_dataset_root("demo_dataset_v1", environ={}).dataset_id
    run_id = "unstructured_ingest-20260512T000000Z-a"

    manifest_path = tmp_path / "runs" / run_id / "claim_extraction" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dataset_id": selected_dataset_id,
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    artifact_path = (
        tmp_path
        / "runs"
        / run_id
        / "claim_extraction_diagnostics"
        / "claim_extraction_diagnostics.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "status": "dry_run",
                "generated_at": "2026-05-13T12:00:00+00:00",
                "run_id": run_id,
                "source_uri": "file:///module/source.pdf",
                "artifact_path": "ignored-by-reader",
                "participation_summary": {
                    "total_edges": 0,
                    "edges_by_role": {},
                    "total_claims": 0,
                    "claims_with_zero_edges": 0,
                    "claim_coverage_pct": None,
                },
                "match_summary": {
                    "total_edges_with_match_method": 0,
                    "edges_by_match_method": {},
                },
                "warnings": ["module warning"],
            }
        ),
        encoding="utf-8",
    )

    base_env = os.environ.copy()
    base_env["POWER_ATLAS_OUTPUT_DIR"] = str(tmp_path)
    base_env["POWER_ATLAS_DATASET"] = "demo_dataset_v1"

    run_scoped = subprocess.run(
        [
            sys.executable,
            "-m",
            "power_atlas.cli.claim_extraction_diagnostics_report",
            "--run-id",
            run_id,
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=base_env,
        capture_output=True,
        check=True,
        text=True,
    )
    current = subprocess.run(
        [
            sys.executable,
            "-m",
            "power_atlas.cli.claim_extraction_diagnostics_report",
            "--current",
            "--stage-prefix",
            "unstructured_ingest",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env=base_env,
        capture_output=True,
        check=True,
        text=True,
    )

    run_lines = [line for line in run_scoped.stdout.splitlines() if line]
    current_lines = [line for line in current.stdout.splitlines() if line]
    assert "Status        : dry_run" in run_lines
    assert "Source URI    : file:///module/source.pdf" in run_lines
    assert json.loads(run_lines[-1]) == {
        "run_id": run_id,
        "artifact_path": str(artifact_path.resolve()),
        "status": "dry_run",
    }
    assert "Status        : dry_run" in current_lines
    assert "Source URI    : file:///module/source.pdf" in current_lines
    assert json.loads(current_lines[-1]) == {
        "run_id": run_id,
        "artifact_path": str(artifact_path.resolve()),
        "status": "dry_run",
        "inferred_dataset_id": "demo_dataset_v1",
    }


def test_public_api_facade_supports_run_detail_endpoint_when_output_dir_has_runs(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-test"
    manifest_path = run_root / "pdf_ingest" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_root.name,
                "dataset_id": "demo_dataset_v1",
                "started_at": "2026-05-12T00:00:00+00:00",
                "finished_at": "2026-05-12T00:01:00+00:00",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    consumer_app = create_backend_app(
        BackendAppOptions(version="2.1.0-test"),
        environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/runs/{run_root.name}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["run"]["run_id"] == run_root.name
            assert payload["run"]["dataset_id"] == "demo_dataset_v1"
            assert payload["stages"][0]["stage_name"] == "pdf_ingest"
            assert payload["stages"][0]["manifest_path"] == str(manifest_path.resolve())

    asyncio.run(_exercise_app())


def test_public_api_facade_supports_filtered_run_queries_when_output_dir_has_runs(
    tmp_path: Path,
) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_pdf_manifest_path = newer_run_root / "pdf_ingest" / "manifest.json"
    newer_pdf_manifest_path.parent.mkdir(parents=True)
    newer_pdf_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )
    newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_claim_manifest_path.parent.mkdir(parents=True)
    newer_claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
    structured_manifest_path.parent.mkdir(parents=True)
    structured_manifest_path.write_text(
        json.dumps(
            {
                "run_id": structured_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    consumer_app = create_backend_app(
        BackendAppOptions(version="2.2.0-test"),
        environ={"POWER_ATLAS_OUTPUT_DIR": str(tmp_path)},
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            by_dataset = await client.get("/runs", params={"dataset_id": "demo_dataset_v1"})
            assert by_dataset.status_code == 200
            assert [run["run_id"] for run in by_dataset.json()["runs"]] == [
                newer_run_root.name,
                older_run_root.name,
            ]

            by_stage = await client.get("/runs", params={"stage_name": "claim_extraction"})
            assert by_stage.status_code == 200
            assert [run["run_id"] for run in by_stage.json()["runs"]] == [newer_run_root.name]

            latest_per_prefix = await client.get(
                "/runs",
                params={"latest_per_stage_prefix": "true"},
            )
            assert latest_per_prefix.status_code == 200
            assert [run["run_id"] for run in latest_per_prefix.json()["runs"]] == [
                newer_run_root.name,
                structured_run_root.name,
            ]

            detail_by_stage = await client.get(
                f"/runs/{newer_run_root.name}",
                params={"stage_name": "claim_extraction"},
            )
            assert detail_by_stage.status_code == 200
            detail_payload = detail_by_stage.json()
            assert detail_payload["run"]["stage_names"] == ["claim_extraction", "pdf_ingest"]
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

    asyncio.run(_exercise_app())


def test_public_api_facade_defaults_current_run_queries_to_configured_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000000Z-a"
    older_manifest_path = older_run_root / "pdf_ingest" / "manifest.json"
    older_manifest_path.parent.mkdir(parents=True)
    older_manifest_path.write_text(
        json.dumps(
            {
                "run_id": older_run_root.name,
                "dataset_id": "demo_dataset_v1",
                "stages": {"pdf_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    newer_run_root = tmp_path / "runs" / "unstructured_ingest-20260512T000100Z-b"
    newer_claim_manifest_path = newer_run_root / "claim_extraction" / "manifest.json"
    newer_claim_manifest_path.parent.mkdir(parents=True)
    newer_claim_manifest_path.write_text(
        json.dumps(
            {
                "run_id": newer_run_root.name,
                "dataset_id": "resolved-demo-dataset",
                "stages": {"claim_extraction": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    structured_run_root = tmp_path / "runs" / "structured_ingest-20260512T000050Z-c"
    structured_manifest_path = structured_run_root / "structured_ingest" / "manifest.json"
    structured_manifest_path.parent.mkdir(parents=True)
    structured_manifest_path.write_text(
        json.dumps(
            {
                "run_id": structured_run_root.name,
                "dataset_id": "demo_dataset_v2",
                "stages": {"structured_ingest": {"status": "live"}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "power_atlas.backend_run_catalog.resolve_backend_dataset_catalog",
        lambda settings: importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogResult(
            datasets=[],
            selected_dataset=importlib.import_module("power_atlas.backend_dataset_catalog").DatasetCatalogEntry(
                name="demo_dataset_v1",
                dataset_id="resolved-demo-dataset",
                pdf_filename="example.pdf",
                manifest_path="/tmp/manifest.json",
                root_path="/tmp/dataset",
            ),
            selection_mode="configured",
        ),
    )

    consumer_app = create_backend_app(
        BackendAppOptions(version="2.3.0-test"),
        environ={
            "POWER_ATLAS_OUTPUT_DIR": str(tmp_path),
            "POWER_ATLAS_DATASET": "demo_dataset_v1",
        },
    )

    async def _exercise_app() -> None:
        transport = httpx.ASGITransport(app=consumer_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            current_runs = await client.get("/runs/current")
            assert current_runs.status_code == 200
            assert [run["run_id"] for run in current_runs.json()["runs"]] == [
                newer_run_root.name
            ]

            current_run_detail = await client.get(
                "/runs/current/unstructured_ingest",
                params={"stage_name": "claim_extraction"},
            )
            assert current_run_detail.status_code == 200
            detail_payload = current_run_detail.json()
            assert detail_payload["run"]["run_id"] == newer_run_root.name
            assert [stage["stage_name"] for stage in detail_payload["stages"]] == [
                "claim_extraction"
            ]

    asyncio.run(_exercise_app())


def test_backend_api_custom_graph_queries_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_custom_graph_queries.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_backend_api_custom_graph_queries_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_backend_api_composed_app_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_composed_app.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_backend_api_composed_app_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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


def test_backend_api_guarded_app_example_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "examples" / "backend_api_guarded_app.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
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


def test_backend_api_guarded_app_runs_from_outside_repo_when_installed(
    tmp_path: Path,
) -> None:
    try:
        importlib.metadata.version("power-atlas")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("requires power-atlas to be installed in the active environment")

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