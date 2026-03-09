from __future__ import annotations

import textwrap

from neo4j_graphrag.generation import RagTemplate

PROMPT_IDS = {
    "claim_extraction": "claims_v1",
    "narrative_extraction": "narrative_claims_v1",
    "qa": "qa_v2",
}

# Power Atlas GraphRAG Q&A prompt template.
# Enforces retrieval-grounded, citation-complete answers aligned with vendor RagTemplate.
# Each sentence or materially distinct claim must include at least one [CITATION|...] token
# copied verbatim from the provided context.
#
# The {examples} placeholder is inherited from the vendor RagTemplate base class
# (neo4j_graphrag.generation.RagTemplate).  It is left empty by default but may be
# used to inject few-shot citation examples when calling GraphRAG.search(examples=...).
#
# Vendor alignment: neo4j_graphrag.generation.RagTemplate / PromptTemplate extension pattern.
# Reference: vendor-resources/examples/customize/answer/custom_prompt.py
POWER_ATLAS_RAG_TEMPLATE = RagTemplate(
    template=textwrap.dedent("""\
        You are a Power Atlas evidence analyst. Your task is to answer the user's question
        using ONLY the provided context. Every sentence or materially distinct claim in your
        answer MUST include at least one citation token copied verbatim from the context.

        Citation tokens have the form [CITATION|chunk_id=...|run_id=...|source_uri=...|...].
        Copy the full token exactly as it appears at the end of each context snippet.

        Rules:
        - Answer only from the provided context.
        - Do NOT introduce facts not present in the context.
        - Every sentence or bullet MUST end with at least one citation token.
        - If the context is insufficient to answer reliably, say so explicitly and cite
          whatever was retrieved (e.g. "The retrieved context does not contain sufficient
          information to answer this question. [CITATION|...]").
        - If the context contains conflicting evidence, describe the conflict explicitly
          and cite all relevant sides. Do not collapse conflicting evidence into a single
          conclusion.
        - Prefer low-temperature, stable, deterministic phrasing.
        - Message history (prior conversation turns) provides conversational context ONLY.
          Do NOT cite or treat any prior assistant turn as evidence. All answer evidence
          must come exclusively from the retrieved context snippets provided above.

        Context:
        {context}

        Examples:
        {examples}

        Question:
        {query_text}

        Answer (every sentence must include a [CITATION|...] token):
        """),
    system_instructions=(
        "You are a strict evidence analyst. Answer only from provided context. "
        "Every claim must be cited with a verbatim [CITATION|...] token from the context. "
        "Message history provides conversational context only, never evidence. "
        "Do not source any answer evidence from prior assistant turns."
    ),
)

__all__ = ["PROMPT_IDS", "POWER_ATLAS_RAG_TEMPLATE"]
