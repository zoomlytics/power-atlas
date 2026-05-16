from __future__ import annotations

import json

from power_atlas.shared_mechanics import (
    CITATION_FALLBACK_PREFIX,
    Config,
    SHARED_MECHANICS_PILOT,
    build_citation_fallback,
    build_retrieval_query_params,
    build_retriever_and_rag,
    build_stage_manifest,
    check_all_answers_cited,
    format_retrieval_scope_label,
    run_retrieval_with_runtime_inputs,
)


def build_example_payload() -> dict[str, object]:
    display_answer, history_answer, fallback_applied = build_citation_fallback(
        "Missing citation"
    )
    runtime_binding = run_retrieval_with_runtime_inputs(
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
    retriever, rag = build_retriever_and_rag(
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
    return {
        "consumer": "shared_mechanics_consumer",
        "included_modules": [
            record.module for record in SHARED_MECHANICS_PILOT.included_modules
        ],
        "deferred_modules": [
            {
                "module": record.module,
                "hidden_assumptions": list(record.hidden_assumptions),
            }
            for record in SHARED_MECHANICS_PILOT.deferred_modules
        ],
        "runtime_surface": {
            "config_type": Config.__name__,
            "manifest_builder": build_stage_manifest.__name__,
            "retrieval_binding": runtime_binding,
            "retrieval_session": {
                "rag": rag,
                "retriever": retriever,
            },
        },
        "helpers": {
            "scope_label": format_retrieval_scope_label("pilot-run-id", False),
            "query_params": build_retrieval_query_params(
                run_id="pilot-run-id",
                source_uri="file:///pilot/source.pdf",
                all_runs=False,
                cluster_aware=True,
                alignment_version="align-v1",
            ),
            "all_cited": check_all_answers_cited(
                "Supported claim [CITATION|demo-run|file:///pilot/source.pdf|0|1|0|42]"
            ),
            "fallback": {
                "display_answer": display_answer,
                "history_answer": history_answer,
                "applied": fallback_applied,
                "prefix": CITATION_FALLBACK_PREFIX,
            },
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))