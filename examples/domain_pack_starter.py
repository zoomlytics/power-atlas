from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from power_atlas.adapters.graphrag_types import RagTemplate

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


RESEARCH_MEMO_DOMAIN_PACK = DomainPackDescriptor(
    name="research_memo",
    version="v0",
    provides=(
        "retrieval_policy",
        "entity_resolution_graph_contract",
        "entity_resolution_canonical_lookup_contract",
        "entity_resolution_alignment_contract",
        "entity_resolution_dataset_selection_contract",
    ),
    examples=(
        "examples/domain_pack_starter.py",
    ),
)


def build_example_payload() -> dict[str, object]:
    retrieval_policy = RetrievalPolicy(
        ontology=RetrievalOntology(
            claim_label="ResearchClaim",
            mention_label="ResearchMention",
            cluster_label="ResearchCluster",
            canonical_label="ResearchEntity",
            supported_by_relationship="SUPPORTED_BY_MEMO",
            mentioned_in_relationship="MENTIONED_IN_MEMO",
            has_participant_relationship="HAS_RESEARCH_PARTICIPANT",
            resolves_to_relationship="RESOLVES_TO_RESEARCH_ENTITY",
            member_of_relationship="MEMBER_OF_RESEARCH_CLUSTER",
            aligned_with_relationship="ALIGNED_WITH_RESEARCH_ENTITY",
        ),
        qa_prompt_id="research_memo_qa_v0",
        rag_template=RagTemplate(
            template=(
                "Research memo context:\n{context}\n"
                "Examples:\n{examples}\n"
                "Question:\n{query_text}\n"
                "Answer with grounded memo synthesis:"
            ),
            system_instructions="Synthesize the supplied research memo evidence.",
        ),
        default_expand_graph=True,
        default_cluster_aware=False,
    )
    graph_contract = EntityResolutionGraphContract(
        mention_label="ResearchMention",
        canonical_label="ResearchEntity",
        cluster_label="ResearchCluster",
        resolves_to_relationship="RESOLVES_TO_RESEARCH_ENTITY",
        member_of_relationship="MEMBER_OF_RESEARCH_CLUSTER",
        candidate_match_relationship="CANDIDATE_RESEARCH_MATCH",
        aligned_with_relationship="ALIGNED_WITH_RESEARCH_ENTITY",
    )
    canonical_lookup = EntityResolutionCanonicalLookupContract(
        canonical_entity_id_field="research_id",
        canonical_run_id_field="research_run_id",
        canonical_name_field="research_name",
        canonical_aliases_field="research_aliases",
        qid_pattern=re.compile(r"^RM\d+$"),
        qid_exact_method="research_id_exact",
        label_exact_method="research_label_exact",
        alias_exact_method="research_alias_exact",
        unresolved_method="research_cluster",
        aligned_status="aligned",
    )
    alignment_contract = EntityResolutionAlignmentContract(
        steps=(
            EntityResolutionAlignmentStep(
                lookup_table="alias",
                cluster_keys=lambda cluster: (cluster["normalized_text"].removeprefix("memo:"),),
                method="memo_alias",
                score=0.95,
                status="aligned",
            ),
            EntityResolutionAlignmentStep(
                lookup_table="label",
                method="research_label_exact",
                score=0.88,
                status="tentative",
            ),
        )
    )
    dataset_selection = EntityResolutionDatasetSelectionContract(
        select_dataset_id=lambda config, dataset_id, dataset_name: (
            dataset_id
            or f"research-memo-canonicals::{dataset_name or getattr(config, 'dataset_name', 'missing')}"
        )
    )

    app_context = build_app_context(environ={"POWER_ATLAS_DATASET": "research_memo_dataset_v1"})
    app_context = replace(
        app_context,
        policies=replace(app_context.policies, retrieval=retrieval_policy),
    )

    retrieval_request_context = build_request_context(
        app_context,
        command="ask",
        dry_run=True,
        question="Which research memo policy was forwarded?",
        run_id="research-memo-retrieval-run-id",
        source_uri="file:///research/memo/source.pdf",
    )
    entity_resolution_request_context = build_request_context(
        app_context,
        command="resolve",
        dry_run=True,
        resolution_mode=RESOLUTION_MODE_HYBRID,
        run_id="research-memo-entity-resolution-run-id",
        source_uri="file:///research/memo/source.pdf",
    )

    def _retrieval_impl(config: object, **kwargs: Any) -> dict[str, object]:
        active_policy = kwargs["retrieval_policy"]
        assert isinstance(active_policy, RetrievalPolicy)
        return {
            "question": kwargs["question"],
            "run_id": kwargs["run_id"],
            "qa_prompt_id": active_policy.qa_prompt_id,
            "claim_label": active_policy.ontology.claim_label,
            "canonical_label": active_policy.ontology.canonical_label,
            "cluster_aware": active_policy.default_cluster_aware,
        }

    retrieval_result = run_retrieval_request_context(
        retrieval_request_context,
        top_k=3,
        index_name=None,
        question=None,
        expand_graph=None,
        cluster_aware=None,
        message_history=None,
        interactive=False,
        run_impl=_retrieval_impl,
    )

    def _runtime_runner(**kwargs: Any) -> dict[str, object]:
        runtime_graph = kwargs["entity_resolution_graph"]
        runtime_lookup = kwargs["entity_resolution_canonical_lookup"]
        runtime_alignment = kwargs["entity_resolution_alignment"]
        assert isinstance(runtime_graph, EntityResolutionGraphContract)
        assert isinstance(runtime_lookup, EntityResolutionCanonicalLookupContract)
        assert isinstance(runtime_alignment, EntityResolutionAlignmentContract)
        return {
            "run_id": kwargs["run_id"],
            "resolution_mode": kwargs["resolution_mode"],
            "effective_dataset_id": kwargs["effective_dataset_id"],
            "graph": {
                "canonical_label": runtime_graph.canonical_label,
                "aligned_with_relationship": runtime_graph.aligned_with_relationship,
            },
            "canonical_lookup": {
                "entity_id_field": runtime_lookup.canonical_entity_id_field,
                "qid_exact_method": runtime_lookup.qid_exact_method,
            },
            "alignment_steps": [
                {
                    "lookup_table": step.lookup_table,
                    "method": step.method,
                    "score": step.score,
                    "status": step.status,
                }
                for step in runtime_alignment.steps
            ],
        }

    def _config_runner(config: object, **kwargs: Any) -> dict[str, object]:
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

    return {
        "consumer": "domain_pack_starter",
        "domain_pack": {
            "name": RESEARCH_MEMO_DOMAIN_PACK.name,
            "version": RESEARCH_MEMO_DOMAIN_PACK.version,
            "provides": list(RESEARCH_MEMO_DOMAIN_PACK.provides),
            "examples": list(RESEARCH_MEMO_DOMAIN_PACK.examples),
        },
        "retrieval": retrieval_result,
        "entity_resolution": entity_resolution_result,
    }


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))