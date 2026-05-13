from __future__ import annotations

from neo4j_graphrag.generation import RagTemplate

from power_atlas.contracts import RetrievalOntology, RetrievalPolicy


MARKET_TRADE_RETRIEVAL_ONTOLOGY = RetrievalOntology(
    claim_label="MarketClaim",
    mention_label="SecurityMention",
    cluster_label="SecurityCluster",
    canonical_label="Security",
    supported_by_relationship="SUPPORTED_BY_RECORD",
    mentioned_in_relationship="MENTIONED_IN_MARKET_SOURCE",
    has_participant_relationship="HAS_MARKET_PARTICIPANT",
    resolves_to_relationship="RESOLVES_TO_SECURITY",
    member_of_relationship="MEMBER_OF_SECURITY_CLUSTER",
    aligned_with_relationship="ALIGNED_WITH_SECURITY",
)

MARKET_TRADE_RETRIEVAL_POLICY = RetrievalPolicy(
    ontology=MARKET_TRADE_RETRIEVAL_ONTOLOGY,
    qa_prompt_id="market_trade_qa_v1",
    rag_template=RagTemplate(
        template=(
            "Market/trade context:\n{context}\n"
            "Examples:\n{examples}\n"
            "Question:\n{query_text}\n"
            "Answer with grounded market structure detail:"
        ),
        system_instructions=(
            "Use the supplied market and trade research context to answer with "
            "grounded structural detail."
        ),
    ),
    default_expand_graph=True,
    default_cluster_aware=True,
)


def get_market_trade_retrieval_policy() -> RetrievalPolicy:
    return MARKET_TRADE_RETRIEVAL_POLICY


__all__ = [
    "MARKET_TRADE_RETRIEVAL_ONTOLOGY",
    "MARKET_TRADE_RETRIEVAL_POLICY",
    "get_market_trade_retrieval_policy",
]