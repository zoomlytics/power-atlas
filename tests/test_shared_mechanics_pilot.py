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
        "power_atlas.retrieval_runtime_bindings",
        "power_atlas.adapters.neo4j.retrieval_session",
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
        "The adapter surface can now accept RequestRuntime, but RequestContext compatibility wrappers still own that binding boundary.",
        "RequestContext compatibility wrappers remain app-owned bridges above the lower-level execution binding.",
    )


    assert deferred_notes["power_atlas.adapters.neo4j.*"] == (
        "The current pilot now includes run-scope queries and the narrow retrieval_session helper only.",
        "A broader adapters.neo4j family surface would still mix mechanics with stage/domain runtime ownership.",
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

    runtime_binding = shared_mechanics.run_retrieval_with_runtime_inputs(
        type("ConfigStub", (), {"question": "Which mechanics helper ran?"})(),
        run_id="pilot-run-id",
        source_uri="file:///pilot/source.pdf",
        top_k=4,
        index_name=None,
        question=None,
        expand_graph=None,
        cluster_aware=None,
        message_history=None,
        interactive=False,
        all_runs=False,
        pipeline_contract=type("PipelineContractStub", (), {"chunk_embedding_index_name": "pilot-index"})(),
        retrieval_policy=type("RetrievalPolicyStub", (), {"qa_prompt_id": "pilot_qa_v1"})(),
        neo4j_settings=type("Neo4jSettingsStub", (), {"database": "neo4j"})(),
        run_impl=lambda config, **kwargs: {
            "index_name": kwargs["index_name"],
            "qa_prompt_id": kwargs["retrieval_policy"].qa_prompt_id,
            "question": kwargs["question"],
            "run_id": kwargs["run_id"],
            "source_uri": kwargs["source_uri"],
        },
    )
    assert runtime_binding == {
        "index_name": "pilot-index",
        "qa_prompt_id": "pilot_qa_v1",
        "question": "Which mechanics helper ran?",
        "run_id": "pilot-run-id",
        "source_uri": "file:///pilot/source.pdf",
    }

    retriever, rag = shared_mechanics.build_retriever_and_rag(
        driver={"kind": "driver"},
        index_name="pilot-index",
        retrieval_query="MATCH (n) RETURN n",
        qa_model="gpt-5.4",
        neo4j_database="neo4j",
        embedder_model_name="text-embedding-3-large",
        result_formatter=lambda result: result,
        embedder_factory=type("EmbedderFactoryStub", (), {}),
        retriever_factory=lambda **kwargs: {
            "index_name": kwargs["index_name"],
            "retrieval_query": kwargs["retrieval_query"],
            "neo4j_database": kwargs["neo4j_database"],
        },
        rag_factory=lambda **kwargs: {
            "llm_model": kwargs["llm"]["model"],
            "prompt_template": kwargs["prompt_template"],
        },
        build_embedder=lambda model_name, *, embedder_factory: {
            "factory_name": embedder_factory.__name__,
            "model": model_name,
        },
        build_llm=lambda model_name: {"model": model_name},
        prompt_template="Answer with cited evidence.",
    )
    assert retriever == {
        "index_name": "pilot-index",
        "retrieval_query": "MATCH (n) RETURN n",
        "neo4j_database": "neo4j",
    }
    assert rag == {
        "llm_model": "gpt-5.4",
        "prompt_template": "Answer with cited evidence.",
    }


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
                    "The adapter surface can now accept RequestRuntime, but RequestContext compatibility wrappers still own that binding boundary.",
                    "RequestContext compatibility wrappers remain app-owned bridges above the lower-level execution binding.",
                ],
                "module": "power_atlas.retrieval_request_context_adapters",
            },
            {
                "hidden_assumptions": [
                    "The current pilot now includes run-scope queries and the narrow retrieval_session helper only.",
                    "A broader adapters.neo4j family surface would still mix mechanics with stage/domain runtime ownership.",
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
            "power_atlas.retrieval_runtime_bindings",
            "power_atlas.adapters.neo4j.retrieval_session",
        ],
        "runtime_surface": {
            "config_type": "Config",
            "manifest_builder": "build_stage_manifest",
            "retrieval_binding": {
                "index_name": "pilot-index",
                "qa_prompt_id": "pilot_qa_v1",
                "question": "Which mechanics helper ran?",
                "run_id": "pilot-run-id",
                "source_uri": "file:///pilot/source.pdf",
            },
            "retrieval_session": {
                "rag": {
                    "llm_model": "gpt-5.4",
                    "prompt_template": "Answer with cited evidence.",
                },
                "retriever": {
                    "index_name": "pilot-index",
                    "neo4j_database": "neo4j",
                    "retrieval_query": "MATCH (n) RETURN n",
                },
            },
        },
    }