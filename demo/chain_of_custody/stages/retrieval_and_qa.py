from __future__ import annotations

from demo.chain_of_custody.contracts import CHUNK_EMBEDDING_INDEX_NAME, FIXTURES_DIR, PROMPT_IDS

_DEFAULT_TOP_K = 10


def run_retrieval_and_qa(
    config: object,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
) -> dict[str, object]:
    resolved_index_name = index_name if index_name is not None else CHUNK_EMBEDDING_INDEX_NAME
    qa_model = getattr(config, "openai_model", None)
    qa_prompt_version = PROMPT_IDS["qa"]

    example_source_uri = (FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
    example_citation_token = (
        "[CITATION|chunk_id=example_chunk|run_id=example_run_id|"
        f"source_uri={example_source_uri}|chunk_index=0|page=1|start_char=0|end_char=999]"
    )
    retrieval_query_contract = """
    RETURN c.text AS chunk_text,
           c.chunk_id AS chunk_id,
           c.run_id AS run_id,
           c.source_uri AS source_uri,
           c.chunk_index AS chunk_index,
           coalesce(c.page_number, c.page) AS page,
           c.start_char AS start_char,
           c.end_char AS end_char,
           score AS similarityScore
    """
    citation_object_example = {
        "chunk_id": "example_chunk",
        "run_id": "example_run_id",
        "source_uri": example_source_uri,
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 999,
    }
    if getattr(config, "dry_run", False):
        return {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "top_k": top_k,
            "retriever_index_name": resolved_index_name,
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
            "qa_model": qa_model,
            "qa_prompt_version": qa_prompt_version,
            "all_answers_cited": False,
            "citation_token_example": example_citation_token,
            "citation_object_example": citation_object_example,
            # citation_example is retained for backward compatibility with existing manifest consumers
            "citation_example": citation_object_example,
            "retrieval_query_contract": retrieval_query_contract.strip(),
        }
    return {
        "status": "configured",
        "run_id": run_id,
        "source_uri": source_uri,
        "top_k": top_k,
        "retriever_index_name": resolved_index_name,
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
        "qa_model": qa_model,
        "qa_prompt_version": qa_prompt_version,
        "all_answers_cited": False,
        "citation_token_example": example_citation_token,
        "citation_object_example": citation_object_example,
        # citation_example is retained for backward compatibility with existing manifest consumers
        "citation_example": citation_object_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
    }


__all__ = ["run_retrieval_and_qa"]
