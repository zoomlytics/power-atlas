from __future__ import annotations

from demo.chain_of_custody.contracts import FIXTURES_DIR


def run_retrieval_and_qa(config: object) -> dict[str, object]:
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
    citation_example = {
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
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
            "citation_token_example": example_citation_token,
            "citation_example": citation_example,
            "retrieval_query_contract": retrieval_query_contract.strip(),
        }
    return {
        "status": "configured",
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
        "citation_token_example": example_citation_token,
        "citation_example": citation_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
    }


__all__ = ["run_retrieval_and_qa"]
