from __future__ import annotations

import argparse
import os
import re
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
RETRIEVAL_CORPUS = os.getenv("RETRIEVAL_CORPUS", "").strip()
RETRIEVAL_DOC_TYPE = os.getenv("RETRIEVAL_DOC_TYPE", "all").strip().lower()
RETRIEVAL_DOCUMENT_PATH = os.getenv("RETRIEVAL_DOCUMENT_PATH", "").strip()

RETRIEVAL_QUERY = """
WITH node, score
OPTIONAL MATCH (d:Document)<-[:FROM_DOCUMENT]-(node)
WITH node, score, d, coalesce(d.path, "<unknown>") AS path
WHERE d IS NOT NULL
  AND ($corpus IS NULL OR d.corpus = $corpus)
  AND ($doc_type IS NULL OR d.doc_type = $doc_type)
  AND ($document_path IS NULL OR d.path = $document_path)

// Neighbor window: previous and next chunks from the same document, by index
OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(prev:Chunk {index: node.index - 1})
OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(next:Chunk {index: node.index + 1})

WITH node, score, path, prev, next
WITH
  node,
  score,
  path,
  (
    CASE
      WHEN prev IS NULL THEN ""
      ELSE ("[prev chunk: " + toString(prev.index) + "]\n" + coalesce(prev.text, "") + "\n\n")
    END
    +
    ("[hit chunk: " + toString(node.index) + " | score: " + toString(score) + "]\n" + coalesce(node.text, ""))
    +
    CASE
      WHEN next IS NULL THEN ""
      ELSE ("\n\n[next chunk: " + toString(next.index) + "]\n" + coalesce(next.text, ""))
    END
  ) AS window_text

RETURN
  (
    "[source: " + path + " | hitChunk: " + toString(node.index) + " | score: " + toString(score) + "]\n"
    + window_text
  ) AS content
"""


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, default)


def _print_retriever_result(
    retriever_result: Any,
    max_chars: int = 400,
    items_override: list[Any] | None = None,
) -> None:
    items = items_override if items_override is not None else _safe_get(retriever_result, "items", None)
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
        content = _normalize_context_text(content)
        preview = shorten(content.replace("\n", " "), width=max_chars, placeholder="…")
        print(f"{i:02d}. {preview}")


def _normalize_doc_type(value: str) -> str | None:
    cleaned = value.strip().lower()
    if cleaned in {"", "all"}:
        return None
    if cleaned not in {"facts", "narrative"}:
        raise ValueError(f"Unsupported doc_type: {value!r}. Expected 'facts', 'narrative', or 'all'.")
    return cleaned


def _normalize_optional_filter(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _build_query_params(corpus: str, doc_type: str, document_path: str) -> dict[str, str | None]:
    return {
        "corpus": _normalize_optional_filter(corpus),
        "doc_type": _normalize_doc_type(doc_type),
        "document_path": _normalize_optional_filter(document_path),
    }


def _dedupe_retrieved_items(retriever_result: Any) -> tuple[int, list[Any]]:
    items = list(_safe_get(retriever_result, "items", None) or [])
    deduped: list[Any] = []
    seen: set[str] = set()
    for item in items:
        content = _unwrap_record_content(_safe_get(item, "content", ""))
        key = _normalize_context_text(content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return len(items) - len(deduped), deduped


_TRACE_HEADER = re.compile(r"^\[source: (?P<source>.+?) \| hitChunk: (?P<hit_chunk>\d+) \|")


def _normalize_context_text(content: str) -> str:
    return content.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t").strip()


def _print_traceability(items: list[Any]) -> None:
    traces: list[str] = []
    for item in items:
        content = _unwrap_record_content(_safe_get(item, "content", ""))
        text = _normalize_context_text(content)
        match = _TRACE_HEADER.search(text)
        if match:
            traces.append(f"{match.group('source')}#chunk{match.group('hit_chunk')}")
    unique_traces: list[str] = []
    seen: set[str] = set()
    for trace in traces:
        if trace in seen:
            continue
        seen.add(trace)
        unique_traces.append(trace)
    if unique_traces:
        print("\n--- Retrieval trace (document#chunk) ---")
        for idx, trace in enumerate(unique_traces, start=1):
            print(f"{idx:02d}. {trace}")


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
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve evidence with optional corpus/doc_type/document filters.\n"
            "Examples:\n"
            "  python examples/retrieve/local_pdf_graphrag.py --query \"Summarize the document in 5 bullets.\"\n"
            "  python examples/retrieve/local_pdf_graphrag.py --doc-type facts --query \"What evidence mentions Lina Park and the Harbor Grid Upgrade Hearing?\""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--query", default=os.getenv("QUERY_TEXT", "").strip(), help="Question/prompt to answer.")
    parser.add_argument("--corpus", default=RETRIEVAL_CORPUS, help="Filter by Document.corpus (or empty for all).")
    parser.add_argument(
        "--doc-type",
        default=RETRIEVAL_DOC_TYPE,
        help="Filter by Document.doc_type: facts, narrative, or all.",
    )
    parser.add_argument(
        "--document-path",
        default=RETRIEVAL_DOCUMENT_PATH,
        help="Optional absolute Document.path filter for per-document debugging.",
    )
    args = parser.parse_args()

    query_params = _build_query_params(
        corpus=args.corpus,
        doc_type=args.doc_type,
        document_path=args.document_path,
    )

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

        user_question = args.query or "Summarize the document in 5 bullets."

        # Force citation behavior using ONLY the headers we embed in retrieved context.
        query_text = (
            "You MUST answer using only the provided context.\n"
            "Return exactly 5 bullets.\n"
            "Every bullet MUST end with a citation copied exactly from the context header, "
            "like: [source: … | hitChunk: …].\n"
            "If the context is insufficient, say 'Insufficient context.' and still provide citations.\n\n"
            "Your bullets must cover the beginning, middle, and end of the document (chronological if possible).\n"
            "Try to use different citations across bullets when possible.\n"
            f"Question: {user_question}"
        )

        print("Connected to:", URI, "db:", DATABASE)
        print("Vector index:", INDEX_NAME, "top_k:", TOP_K)
        print("Filters:", query_params)
        print("=" * 80)
        print("Q:", query_text)

        # 1) Inspect retrieval directly (works even if GraphRAG response doesn't expose it)
        try:
            retriever_result = retriever.search(
                query_text=query_text,
                top_k=TOP_K,
                query_params=query_params,
            )
        except TypeError:
            # Some versions use retriever.search(query_text, retriever_config={...})
            retriever_result = retriever.search(
                query_text=query_text,
                retriever_config={"top_k": TOP_K, "query_params": query_params},
            )

        duplicates_removed, deduped_items = _dedupe_retrieved_items(retriever_result)
        if duplicates_removed:
            print(f"[dedupe] removed {duplicates_removed} duplicate context item(s).")
        _print_traceability(deduped_items)

        _print_retriever_result(retriever_result, items_override=deduped_items)

        # 2) Then generate the final answer
        response = rag.search(
            query_text=query_text,
            retriever_config={"top_k": TOP_K, "query_params": query_params},
        )
        answer = _safe_get(response, "answer", None)

        if answer is not None:
            print("\nAnswer:\n", answer)
        else:
            print("\nResponse (no .answer attribute):\n", response)


if __name__ == "__main__":
    main()
