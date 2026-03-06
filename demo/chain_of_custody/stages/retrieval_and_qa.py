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
    question: str | None = None,
) -> dict[str, object]:
    resolved_index_name = index_name if index_name is not None else CHUNK_EMBEDDING_INDEX_NAME
    qa_model = getattr(config, "openai_model", None)
    qa_prompt_version = PROMPT_IDS["qa"]

    # Use provided run_id/source_uri in citation examples so provenance fields align with stage metadata;
    # fall back to placeholder values only when those parameters are absent.
    _fallback_source_uri = (FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
    citation_run_id = run_id if run_id is not None else "example_run_id"
    citation_source_uri = source_uri if source_uri is not None else _fallback_source_uri

    citation_token_example = (
        f"[CITATION|chunk_id=example_chunk|run_id={citation_run_id}|"
        f"source_uri={citation_source_uri}|chunk_index=0|page=1|start_char=0|end_char=999]"
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
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 999,
    }

    # Build shared base dict; only status/retrievers/qa differ between dry-run and configured.
    # Use citation_run_id/citation_source_uri (which include fallbacks) so stage metadata is
    # always consistent with the provenance fields in citation_object_example.
    base: dict[str, object] = {
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "top_k": top_k,
        "retriever_index_name": resolved_index_name,
        "question": question,
        "qa_model": qa_model,
        "qa_prompt_version": qa_prompt_version,
        "all_answers_cited": False,
        "citation_token_example": citation_token_example,
        "citation_object_example": citation_object_example,
        # citation_example is retained for backward compatibility with existing manifest consumers
        "citation_example": citation_object_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
    }
    if getattr(config, "dry_run", False):
        return {
            **base,
            "status": "dry_run",
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
        }
    return {
        **base,
        "status": "configured",
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
    }


__all__ = ["run_retrieval_and_qa"]
