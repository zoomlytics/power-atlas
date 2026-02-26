from __future__ import annotations

import os
from textwrap import shorten
from typing import Any

import neo4j
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.retrievers import VectorCypherRetriever

URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "testtesttest")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

INDEX_NAME = os.getenv("NEO4J_VECTOR_INDEX", "chunk_embedding_index")
TOP_K = int(os.getenv("TOP_K", "5"))

RETRIEVAL_QUERY = """
WITH node, score
OPTIONAL MATCH (d:Document)<-[:FROM_DOCUMENT]-(node)
WITH node, score, coalesce(d.path, "<unknown>") AS path
RETURN
  ("[source: " + path + " | chunk: " + toString(node.index) + " | score: " + toString(score) + "]\n"
   + node.text) AS content
"""


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, default)


def _print_retriever_result(retriever_result: Any, max_chars: int = 240) -> None:
    items = _safe_get(retriever_result, "items", None)
    if not items:
        print("\n--- Retriever result (raw) ---")
        print(retriever_result)
        return

    meta = _safe_get(retriever_result, "metadata", None)
    if meta:
        print("\n--- Retriever metadata ---")
        # Avoid dumping the whole vector every time
        meta2 = dict(meta)
        if "query_vector" in meta2 and isinstance(meta2["query_vector"], list):
            meta2["query_vector"] = f"<{len(meta2['query_vector'])} dims>"
        print(meta2)

    for i, item in enumerate(items, start=1):
        raw = _safe_get(item, "content", "")
        content = _unwrap_record_content(raw)
        content = content.encode("utf-8").decode("unicode_escape")  # turn "\\n" into real newlines
        preview = shorten(content.replace("\n", " "), width=max_chars, placeholder="…")
        print(f"{i:02d}. {preview}")

def _unwrap_record_content(value: Any) -> str:
    """
    Your neo4j_graphrag version returns item.content as a string like:
      "<Record content='...'>"
    This extracts the actual content string as best-effort.
    """
    s = str(value)

    marker = "content="
    if marker not in s:
        return s

    # Take everything after "content="
    s2 = s.split(marker, 1)[1].strip()

    # Drop trailing ">" if present
    if s2.endswith(">"):
        s2 = s2[:-1].rstrip()

    # Remove a single pair of surrounding quotes if present
    if (s2.startswith("'") and s2.endswith("'")) or (s2.startswith('"') and s2.endswith('"')):
        s2 = s2[1:-1]

    return s2


def main() -> None:
    embedder = OpenAIEmbeddings()
    llm = OpenAILLM(
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
        model_params={"temperature": 0},
    )

    with neo4j.GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD)) as driver:
        retriever = VectorCypherRetriever(
            driver=driver,
            index_name=INDEX_NAME,
            embedder=embedder,
            retrieval_query=RETRIEVAL_QUERY,
            neo4j_database=DATABASE,
        )

        rag = GraphRAG(retriever=retriever, llm=llm)

        query_text = os.getenv("QUERY_TEXT", "").strip() or "Summarize the document in 5 bullets."

        print("Connected to:", URI, "db:", DATABASE)
        print("Vector index:", INDEX_NAME, "top_k:", TOP_K)
        print("=" * 80)
        print("Q:", query_text)

        # 1) Inspect retrieval directly (works even if GraphRAG response doesn't expose it)
        try:
            retriever_result = retriever.search(query_text=query_text, top_k=TOP_K)
        except TypeError:
            # Some versions use retriever.search(query_text, retriever_config={...})
            retriever_result = retriever.search(query_text=query_text, retriever_config={"top_k": TOP_K})

        _print_retriever_result(retriever_result)

        # 2) Then generate the final answer
        response = rag.search(query_text=query_text, retriever_config={"top_k": TOP_K})
        answer = _safe_get(response, "answer", None)

        if answer is not None:
            print("\nAnswer:\n", answer)
        else:
            print("\nResponse (no .answer attribute):\n", response)


if __name__ == "__main__":
    main()