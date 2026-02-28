from __future__ import annotations

import argparse
import os
import re
from textwrap import shorten
from typing import Any, Mapping

import neo4j
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "testtesttest")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

INDEX_NAME = os.getenv("NEO4J_VECTOR_INDEX", "chunk_embedding_index")
TOP_K = int(os.getenv("TOP_K", "5"))
RETRIEVAL_CORPUS = os.getenv("RETRIEVAL_CORPUS", "").strip()
RETRIEVAL_DOC_TYPE = os.getenv("RETRIEVAL_DOC_TYPE", "all").strip().lower()
RETRIEVAL_DOCUMENT_PATH = os.getenv("RETRIEVAL_DOCUMENT_PATH", "").strip()
RETRIEVAL_INSPECT = os.getenv("RETRIEVAL_INSPECT", "false").strip().lower() == "true"

RETRIEVAL_QUERY = """
WITH node, score
MATCH (d:Document)<-[:FROM_DOCUMENT]-(node)
OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(prev:Chunk {index: node.index - 1})
OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(next:Chunk {index: node.index + 1})
RETURN
  coalesce(d.path, "<unknown>") AS source_path,
  node.index AS hit_chunk,
  score AS similarity_score,
  coalesce(node.text, "") AS hit_text,
  prev.index AS prev_chunk,
  coalesce(prev.text, "") AS prev_text,
  next.index AS next_chunk,
  coalesce(next.text, "") AS next_text
"""

# Vendor references:
# - result_formatter: https://github.com/neo4j/neo4j-graphrag-python/blob/main/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py
# - pre-filters: https://github.com/neo4j/neo4j-graphrag-python/blob/main/examples/customize/retrievers/use_pre_filters.py
# - custom prompt: https://github.com/neo4j/neo4j-graphrag-python/blob/main/examples/customize/answer/custom_prompt.py
QA_PROMPT_TEMPLATE = RagTemplate(
    template=(
        "You MUST answer using only the provided context.\n"
        "Return exactly 5 bullets.\n"
        "Every bullet MUST end with a citation copied exactly from the context header, "
        "like: [source: … | hitChunk: … | score: …].\n"
        "If the context is insufficient, say 'Insufficient context.' and still provide citations.\n"
        "Your bullets must cover the beginning, middle, and end of the document (chronological if possible).\n"
        "Try to use different citations across bullets when possible.\n\n"
        "Context:\n"
        "{context}\n\n"
        "Examples:\n"
        "{examples}\n\n"
        "Question:\n"
        "{query_text}\n\n"
        "Answer:\n"
    )
)


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


def _build_retriever_filters(corpus: str, doc_type: str, document_path: str) -> dict[str, str]:
    query_params = _build_query_params(corpus=corpus, doc_type=doc_type, document_path=document_path)
    return {key: value for key, value in query_params.items() if value is not None}


def _result_formatter(record: neo4j.Record | Mapping[str, Any]) -> RetrieverResultItem:
    source_path = record.get("source_path") or "<unknown>"
    hit_chunk = record.get("hit_chunk")
    score = record.get("similarity_score")
    hit_text = record.get("hit_text") or ""
    prev_chunk = record.get("prev_chunk")
    prev_text = record.get("prev_text") or ""
    next_chunk = record.get("next_chunk")
    next_text = record.get("next_text") or ""
    hit_chunk_label = hit_chunk if hit_chunk is not None else "unknown"
    score_label = score if score is not None else "n/a"

    prev_block = (
        ""
        if prev_chunk is None
        else f"[prev chunk: {prev_chunk}]\n{prev_text}\n\n"
    )
    hit_block = f"hit window (chunk {hit_chunk_label} | score: {score_label})\n{hit_text}"
    next_block = (
        ""
        if next_chunk is None
        else f"\n\n[next chunk: {next_chunk}]\n{next_text}"
    )
    content = (
        f"[source: {source_path} | hitChunk: {hit_chunk_label} | score: {score_label}]\n"
        f"{prev_block}{hit_block}{next_block}"
    )
    return RetrieverResultItem(
        content=content,
        metadata={"score": score, "source_path": source_path, "hit_chunk": hit_chunk},
    )


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
_ESCAPE_PATTERN = re.compile(r"\\n|\\r|\\t|\\\\|\\\"|\\'|\\u[0-9a-fA-F]{4}")
_UNICODE_ESCAPE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _normalize_context_text(content: str) -> str:
    """
    Normalize context text by decoding common escaped sequences.

    This targets Neo4j/Python-style escaped content while avoiding unnecessary
    transformations when there are no recognized escape patterns.
    """
    text = content.strip()
    if "\\" not in text:
        return _CONTROL_CHARS_PATTERN.sub("", text)
    if _ESCAPE_PATTERN.search(text):
        text = (
            text.replace("\\r", "\r")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\\\", "\\")
            .replace('\\"', '"')
            .replace("\\'", "'")
        )

        def _decode_unicode_escape(match: re.Match[str]) -> str:
            code_point = int(match.group(1), 16)
            if 0xD800 <= code_point <= 0xDFFF:
                return match.group(0)
            return chr(code_point)

        text = _UNICODE_ESCAPE_PATTERN.sub(_decode_unicode_escape, text)
    return _CONTROL_CHARS_PATTERN.sub("", text).strip()


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
    parser.add_argument(
        "--inspect-retrieval",
        action=argparse.BooleanOptionalAction,
        default=RETRIEVAL_INSPECT,
        help="Print retrieved contexts; fallback retrieval runs only if GraphRAG omits retriever_result.",
    )
    args = parser.parse_args()

    query_params = _build_query_params(
        corpus=args.corpus,
        doc_type=args.doc_type,
        document_path=args.document_path,
    )
    retriever_filters = _build_retriever_filters(
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
            result_formatter=_result_formatter,
            neo4j_database=DATABASE,
        )

        rag = GraphRAG(retriever=retriever, llm=llm, prompt_template=QA_PROMPT_TEMPLATE)

        user_question = (args.query or "").strip() or "Summarize the document in 5 bullets."

        print("Connected to:", URI, "db:", DATABASE)
        print("Vector index:", INDEX_NAME, "top_k:", TOP_K)
        print("Query params:", query_params)
        print("Retriever filters (applied):", retriever_filters)
        print("=" * 80)
        print("Q:", user_question)

        # 1) Generate final answer
        response = rag.search(
            query_text=user_question,
            retriever_config={"top_k": TOP_K, "filters": retriever_filters},
        )
        retriever_result = _safe_get(response, "retriever_result", None)

        if retriever_result is None and args.inspect_retrieval:
            try:
                retriever_result = retriever.search(
                    query_text=user_question,
                    top_k=TOP_K,
                    filters=retriever_filters,
                )
            except TypeError:
                retriever_result = retriever.search(
                    query_text=user_question,
                    retriever_config={"top_k": TOP_K, "filters": retriever_filters},
                )

        if retriever_result is not None:
            duplicates_removed, deduped_items = _dedupe_retrieved_items(retriever_result)
            if duplicates_removed:
                print(f"[dedupe] removed {duplicates_removed} duplicate context item(s).")
            _print_traceability(deduped_items)
            if args.inspect_retrieval:
                _print_retriever_result(retriever_result, items_override=deduped_items)

        answer = _safe_get(response, "answer", None)

        if answer is not None:
            print("\nAnswer:\n", answer)
        else:
            print("\nResponse (no .answer attribute):\n", response)


if __name__ == "__main__":
    main()
