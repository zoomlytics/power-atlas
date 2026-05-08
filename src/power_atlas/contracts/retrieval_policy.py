from __future__ import annotations

from dataclasses import dataclass

from neo4j_graphrag.generation import RagTemplate

from power_atlas.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE, PROMPT_IDS


@dataclass(frozen=True)
class RetrievalOntology:
    claim_label: str = "ExtractedClaim"
    mention_label: str = "EntityMention"
    cluster_label: str = "ResolvedEntityCluster"
    canonical_label: str = "CanonicalEntity"
    supported_by_relationship: str = "SUPPORTED_BY"
    mentioned_in_relationship: str = "MENTIONED_IN"
    has_participant_relationship: str = "HAS_PARTICIPANT"
    resolves_to_relationship: str = "RESOLVES_TO"
    member_of_relationship: str = "MEMBER_OF"
    aligned_with_relationship: str = "ALIGNED_WITH"


@dataclass(frozen=True)
class RetrievalPolicy:
    ontology: RetrievalOntology
    qa_prompt_id: str
    rag_template: RagTemplate
    default_expand_graph: bool = False
    default_cluster_aware: bool = False


POWER_ATLAS_RETRIEVAL_ONTOLOGY = RetrievalOntology()
POWER_ATLAS_RETRIEVAL_POLICY = RetrievalPolicy(
    ontology=POWER_ATLAS_RETRIEVAL_ONTOLOGY,
    qa_prompt_id=PROMPT_IDS["qa"],
    rag_template=POWER_ATLAS_RAG_TEMPLATE,
)


def get_default_retrieval_policy() -> RetrievalPolicy:
    return POWER_ATLAS_RETRIEVAL_POLICY


__all__ = [
    "POWER_ATLAS_RETRIEVAL_ONTOLOGY",
    "POWER_ATLAS_RETRIEVAL_POLICY",
    "RetrievalOntology",
    "RetrievalPolicy",
    "get_default_retrieval_policy",
]