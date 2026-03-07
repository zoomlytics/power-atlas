from __future__ import annotations

import logging
import os
import re

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.message_history import InMemoryMessageHistory, MessageHistory
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import LLMMessage, RetrieverResultItem

from demo.contracts import CHUNK_EMBEDDING_INDEX_NAME, EMBEDDER_MODEL_NAME, FIXTURES_DIR, PROMPT_IDS
from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE

_DEFAULT_TOP_K = 10
_logger = logging.getLogger(__name__)

# Retrieval query: run-scoped by default. `node` is the Chunk matched by the vector index;
# `score` is the similarity score from the index search. The null-conditional on $source_uri
# means the filter is skipped when source_uri is passed as None.
# Aligned with vendor pattern from vendor-resources/examples/retrieve/vector_cypher_retriever.py.
_RETRIEVAL_QUERY_BASE = """
WITH node AS c, score
WHERE c.run_id = $run_id
  AND ($source_uri IS NULL OR c.source_uri = $source_uri)
RETURN coalesce(c.text, c.body, c.content) AS chunk_text,
       c.chunk_id AS chunk_id,
       c.run_id AS run_id,
       c.source_uri AS source_uri,
       c.chunk_index AS chunk_index,
       coalesce(c.page_number, c.page) AS page,
       c.start_char AS start_char,
       c.end_char AS end_char,
       score AS similarityScore
"""

# Graph-expanded retrieval: adds related ExtractedClaim, EntityMention, and canonical entity
# context via optional graph traversal from the retrieved Chunk node.
# Pattern comprehensions are used for each expansion target to avoid row multiplication
# (cartesian products) that would result from chained OPTIONAL MATCH clauses.
_RETRIEVAL_QUERY_WITH_EXPANSION = """
WITH node AS c, score
WHERE c.run_id = $run_id
  AND ($source_uri IS NULL OR c.source_uri = $source_uri)
RETURN coalesce(c.text, c.body, c.content) AS chunk_text,
       c.chunk_id AS chunk_id,
       c.run_id AS run_id,
       c.source_uri AS source_uri,
       c.chunk_index AS chunk_index,
       coalesce(c.page_number, c.page) AS page,
       c.start_char AS start_char,
       c.end_char AS end_char,
       score AS similarityScore,
       [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) WHERE claim.run_id = $run_id | claim.claim_text] AS claims,
       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) WHERE mention.run_id = $run_id | mention.name] AS mentions,
       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) WHERE mention.run_id = $run_id | coalesce(canonical.name, canonical.label)] AS canonical_entities
"""

# Optional citation-relevant fields that should be surfaced as warnings when absent.
_CITATION_OPTIONAL_FIELDS = ("page", "start_char", "end_char")

# Citation token prefix used to verify citation completeness in generated answers.
_CITATION_TOKEN_PREFIX = "[CITATION|"

# Regex matching one or more [CITATION|…] tokens at the very end of a stripped line.
# Built from _CITATION_TOKEN_PREFIX so the two stay in sync.
# Each token starts with _CITATION_TOKEN_PREFIX, contains no unencoded ']', and is
# terminated by ']'. One or more consecutive tokens are allowed (e.g. multi-source claims).
_TRAILING_CITATION_RE = re.compile(rf"({re.escape(_CITATION_TOKEN_PREFIX)}[^\]]*\])+\s*$")


def _check_all_answers_cited(answer: str) -> bool:
    """Return True if every non-empty line in the answer ends with a citation token.

    The Power Atlas prompt instructs the LLM to place a ``[CITATION|...]`` token at the
    end of each sentence or bullet.  This function enforces that contract at the
    line level: every non-empty line must end with at least one complete
    ``[CITATION|…]`` token matched by ``_TRAILING_CITATION_RE``.

    Using a regex anchored at end-of-line (rather than just checking ``endswith("]")``)
    ensures that a ``]`` from unrelated bracketed text (e.g. Markdown links or other
    annotation tokens) does not produce false positives.  One or more consecutive tokens
    are allowed to support multi-source claims.

    This is a heuristic; it errs toward False (under-cited) rather than producing
    false positives.
    """
    lines = answer.strip().splitlines()
    has_any_line = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        has_any_line = True
        # Require at least one complete [CITATION|…] token anchored at end-of-line.
        if not _TRAILING_CITATION_RE.search(line):
            return False
    return has_any_line


def _encode_citation_value(value: object) -> str:
    """Percent-encode characters that would break citation token delimiter parsing.

    The token format uses ``|`` as a field separator and ``]`` as a token terminator.
    Encoding only those two characters (plus ``%`` to prevent double-encoding) keeps
    values like ``file:///path.pdf`` human-readable while ensuring round-trippability
    even when a source_uri contains ``|`` or ``]``.
    """
    s = "" if value is None else str(value)
    return s.replace("%", "%25").replace("|", "%7C").replace("]", "%5D")


def _build_citation_token(
    *,
    chunk_id: str | None,
    run_id: str | None,
    source_uri: str | None,
    chunk_index: int | None,
    page: int | None,
    start_char: int | None,
    end_char: int | None,
) -> str:
    return (
        f"[CITATION"
        f"|chunk_id={_encode_citation_value(chunk_id)}"
        f"|run_id={_encode_citation_value(run_id)}"
        f"|source_uri={_encode_citation_value(source_uri)}"
        f"|chunk_index={_encode_citation_value(chunk_index)}"
        f"|page={_encode_citation_value(page)}"
        f"|start_char={_encode_citation_value(start_char)}"
        f"|end_char={_encode_citation_value(end_char)}"
        f"]"
    )


def _chunk_citation_formatter(record: neo4j.Record) -> RetrieverResultItem:
    """Format a retrieved Chunk record into a RetrieverResultItem with a stable citation token.

    Follows the vendor result_formatter pattern from:
    vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py

    The returned item embeds the citation token in the content string (for prompt context)
    and preserves all citation-relevant fields in metadata (for downstream citation mapping).
    """
    chunk_id = record.get("chunk_id")
    run_id = record.get("run_id")
    source_uri = record.get("source_uri")
    chunk_index = record.get("chunk_index")
    page = record.get("page")
    start_char = record.get("start_char")
    end_char = record.get("end_char")
    chunk_text = record.get("chunk_text") or ""
    score = record.get("similarityScore")

    citation_token = _build_citation_token(
        chunk_id=chunk_id,
        run_id=run_id,
        source_uri=source_uri,
        chunk_index=chunk_index,
        page=page,
        start_char=start_char,
        end_char=end_char,
    )
    citation_object: dict[str, object] = {
        "chunk_id": chunk_id,
        "run_id": run_id,
        "source_uri": source_uri,
        "chunk_index": chunk_index,
        "page": page,
        "start_char": start_char,
        "end_char": end_char,
    }

    # Embed citation token in content so prompt context is self-documenting.
    content = f"{chunk_text}\n{citation_token}"
    metadata: dict[str, object] = {
        "chunk_id": chunk_id,
        "run_id": run_id,
        "source_uri": source_uri,
        "chunk_index": chunk_index,
        "page": page,
        "start_char": start_char,
        "end_char": end_char,
        "score": score,
        "citation_token": citation_token,
        "citation_object": citation_object,
    }
    # Include graph expansion fields when the expanded retrieval query was used.
    for field in ("claims", "mentions", "canonical_entities"):
        value = record.get(field)
        if value is not None:
            metadata[field] = value

    return RetrieverResultItem(content=content, metadata=metadata)


def run_retrieval_and_qa(
    config: object,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    question: str | None = None,
    expand_graph: bool = False,
    message_history: MessageHistory | list[dict[str, str]] | None = None,
    interactive: bool = False,
) -> dict[str, object]:
    """Run retrieval and GraphRAG Q&A for a single question or interactive session.

    Parameters
    ----------
    config:
        Runtime config with Neo4j/OpenAI settings.
    run_id:
        Mandatory for live mode; scopes retrieval to a specific ingest run.
    source_uri:
        Optional source-level filter within the run scope.
    top_k:
        Maximum number of retrieved chunks to pass to the LLM as context.
    index_name:
        Vector index name; defaults to the contract value.
    question:
        The question to answer (single-question mode).  In live mode, when
        *None*, retrieval is skipped and an empty result is returned; in
        dry-run mode, a normal dry-run payload is returned without executing
        retrieval.
    expand_graph:
        When True, adds ExtractedClaim / EntityMention / canonical-entity context
        via graph expansion on top of the base vector retrieval.
    message_history:
        Vendor ``MessageHistory`` object (or a plain list of dicts) for
        conversational/interactive mode.  When provided, prior turns supply
        conversational context while each turn's answer must still be fully
        citation-grounded via retrieved evidence.
    interactive:
        Records whether the call originated from an interactive REPL session.
        Does not change retrieval or generation behaviour on its own.
    """
    resolved_index_name = index_name if index_name is not None else CHUNK_EMBEDDING_INDEX_NAME
    qa_model = getattr(config, "openai_model", None)
    # effective_qa_model is the model that will actually be used for generation; it
    # includes the fallback default so the manifest always reflects the true model.
    effective_qa_model = qa_model or "gpt-4o-mini"
    qa_prompt_version = PROMPT_IDS["qa"]

    # Use provided run_id/source_uri in citation examples so provenance fields align with stage metadata;
    # fall back to placeholder values only when those parameters are absent.
    _fallback_source_uri = (FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf").resolve().as_uri()
    citation_run_id = run_id if run_id is not None else "example_run_id"
    citation_source_uri = source_uri if source_uri is not None else _fallback_source_uri

    citation_token_example = _build_citation_token(
        chunk_id="example_chunk",
        run_id=citation_run_id,
        source_uri=citation_source_uri,
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=999,
    )
    retrieval_query_contract = (
        _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph else _RETRIEVAL_QUERY_BASE
    )
    citation_object_example: dict[str, object] = {
        "chunk_id": "example_chunk",
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 999,
    }

    # Retrieval scope metadata: always recorded so manifests document the scope used.
    # Use the raw run_id (possibly None for dry-run) so the recorded scope reflects the
    # actual input rather than the citation-example fallback value.
    retrieval_scope: dict[str, object] = {
        "run_id": run_id,
        "source_uri": source_uri,
        "scope_widened": False,
    }

    # Build shared base dict; only status/retrievers/qa and live-specific fields differ.
    # Use citation_run_id/citation_source_uri (which include fallbacks) so stage metadata is
    # always consistent with the provenance fields in citation_object_example.
    base: dict[str, object] = {
        "run_id": citation_run_id,
        "source_uri": citation_source_uri,
        "top_k": top_k,
        "retriever_type": "VectorCypherRetriever",
        "retriever_index_name": resolved_index_name,
        "question": question,
        "qa_model": effective_qa_model,
        "qa_prompt_version": qa_prompt_version,
        "answer": "",
        "all_answers_cited": False,
        "expand_graph": expand_graph,
        "retrieval_scope": retrieval_scope,
        "citation_token_example": citation_token_example,
        "citation_object_example": citation_object_example,
        # citation_example is retained for backward compatibility with existing manifest consumers
        "citation_example": citation_object_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
        "interactive_mode": interactive,
        "message_history_enabled": message_history is not None,
    }
    if getattr(config, "dry_run", False):
        dry_run_retrievers = (
            ["VectorCypherRetriever", "graph expansion"] if expand_graph else ["VectorCypherRetriever"]
        )
        return {
            **base,
            "status": "dry_run",
            "retrievers": dry_run_retrievers,
            "qa": "GraphRAG strict citations",
        }

    # Live retrieval: build a run-scoped VectorCypherRetriever with citation formatter.
    # run_id is mandatory for live retrieval — it is the primary run-scope boundary.
    if run_id is None:
        raise ValueError(
            "run_id is required for live retrieval. Set UNSTRUCTURED_RUN_ID or pass run_id explicitly."
        )

    retrieval_query = _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph else _RETRIEVAL_QUERY_BASE

    # Query params for run-scoped filtering. source_uri=None is valid: the null-conditional
    # in the WHERE clause skips source_uri filtering when the parameter is None.
    query_params: dict[str, object] = {
        "run_id": run_id,
        "source_uri": source_uri,
    }

    warnings_list: list[str] = []
    hits: list[dict[str, object]] = []

    if question is None:
        warning_msg = "No question provided; skipping vector retrieval."
        _logger.warning(warning_msg)
        # Retrieval (and optional graph expansion) did not run; report no retrievers.
        return {
            **base,
            "status": "live",
            "retrievers": [],
            "qa": "GraphRAG strict citations",
            "hits": 0,
            "retrieval_results": [],
            "warnings": [warning_msg],
            "retrieval_skipped": True,
        }

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required for live retrieval.")

    neo4j_uri = getattr(config, "neo4j_uri", None)
    neo4j_username = getattr(config, "neo4j_username", None)
    neo4j_password = getattr(config, "neo4j_password", None)
    neo4j_database = getattr(config, "neo4j_database", None)

    missing_cfg = [k for k, v in (("neo4j_uri", neo4j_uri), ("neo4j_username", neo4j_username), ("neo4j_password", neo4j_password)) if not v]
    if missing_cfg:
        raise ValueError(f"Live retrieval requires config attributes: {', '.join(missing_cfg)}")

    with neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password)) as driver:
        embedder = OpenAIEmbeddings(model=EMBEDDER_MODEL_NAME)
        retriever = VectorCypherRetriever(
            driver=driver,
            index_name=resolved_index_name,
            embedder=embedder,
            retrieval_query=retrieval_query,
            result_formatter=_chunk_citation_formatter,
            neo4j_database=neo4j_database,
        )

        # Build GraphRAG with the Power Atlas citation-enforcing prompt template and
        # low-temperature LLM for deterministic, grounded output.
        # Aligned with vendor pattern from vendor-resources/examples/customize/answer/custom_prompt.py
        # and vendor-resources/examples/question_answering/graphrag_with_neo4j_message_history.py.
        llm = OpenAILLM(
            model_name=effective_qa_model,
            model_params={"temperature": 0},
        )
        rag = GraphRAG(
            retriever=retriever,
            llm=llm,
            prompt_template=POWER_ATLAS_RAG_TEMPLATE,
        )

        # Run the GraphRAG search with optional message history for interactive mode.
        # retriever_config passes query_params for run-scoped Cypher filtering.
        rag_result = rag.search(
            query_text=question,
            retriever_config={"top_k": top_k, "query_params": query_params},
            return_context=True,
            message_history=message_history,  # type: ignore[arg-type]
        )

        answer_text: str = rag_result.answer if rag_result else ""

        # Collect retrieval hits from the rag result context for manifest recording.
        if rag_result and rag_result.retriever_result:
            for item in rag_result.retriever_result.items:
                meta = item.metadata or {}
                citation_obj = meta.get("citation_object") or {}
                # Surface warnings for chunks missing optional citation-relevant fields.
                missing_fields = [f for f in _CITATION_OPTIONAL_FIELDS if citation_obj.get(f) is None]
                if missing_fields:
                    _logger.warning(
                        "Chunk %r missing citation fields: %s",
                        citation_obj.get("chunk_id"),
                        ", ".join(missing_fields),
                    )
                    warnings_list.append(
                        f"Chunk {citation_obj.get('chunk_id')!r} missing citation fields: {', '.join(missing_fields)}"
                    )
                hits.append({"content": item.content, "metadata": meta})

    # Check answer citation completeness and record a warning when not fully cited.
    all_cited = _check_all_answers_cited(answer_text) if answer_text else False
    if answer_text and not all_cited:
        citation_warning = "Not all non-empty answer lines end with a citation token."
        _logger.warning(citation_warning)
        warnings_list.append(citation_warning)

    # Use first hit's citation data as example when hits are available so the manifest
    # reflects actual retrieved provenance rather than placeholder values.
    actual_citation_token = citation_token_example
    actual_citation_object = citation_object_example
    if hits:
        first_meta = hits[0].get("metadata") or {}
        if first_meta.get("citation_token"):
            actual_citation_token = first_meta["citation_token"]
        if first_meta.get("citation_object"):
            actual_citation_object = first_meta["citation_object"]

    live_retrievers = (
        ["VectorCypherRetriever", "graph expansion"] if expand_graph else ["VectorCypherRetriever"]
    )
    return {
        **base,
        "status": "live",
        "retrievers": live_retrievers,
        "qa": "GraphRAG strict citations",
        "hits": len(hits),
        "retrieval_results": hits,
        "warnings": warnings_list,
        "citation_token_example": actual_citation_token,
        "citation_object_example": actual_citation_object,
        "citation_example": actual_citation_object,
        "answer": answer_text,
        "all_answers_cited": all_cited,
    }


def run_interactive_qa(
    config: object,
    *,
    run_id: str,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    expand_graph: bool = False,
) -> None:
    """Run a REPL-style interactive Q&A session.

    Reads questions from stdin and prints citation-grounded answers until the user
    types ``exit``, ``quit``, or sends EOF (Ctrl-D).

    Message history is maintained across turns via an in-memory store so the LLM
    has conversational context, but each turn's answer must still be grounded in
    retrieved evidence from the current question's retrieval results.

    The Neo4j driver, retriever, LLM, and GraphRAG objects are constructed once for
    the session to avoid per-turn connection churn and latency.

    Aligned with vendor patterns from:
    - vendor-resources/examples/question_answering/graphrag_with_message_history.py
      (list[dict]-based history)
    - vendor-resources/examples/question_answering/graphrag_with_neo4j_message_history.py
      (MessageHistory-based; this REPL uses InMemoryMessageHistory)
    """
    # Validate and resolve session-level config once before opening any connections.
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required for live retrieval.")

    neo4j_uri = getattr(config, "neo4j_uri", None)
    neo4j_username = getattr(config, "neo4j_username", None)
    neo4j_password = getattr(config, "neo4j_password", None)
    neo4j_database = getattr(config, "neo4j_database", None)

    missing_cfg = [k for k, v in (("neo4j_uri", neo4j_uri), ("neo4j_username", neo4j_username), ("neo4j_password", neo4j_password)) if not v]
    if missing_cfg:
        raise ValueError(f"Live retrieval requires config attributes: {', '.join(missing_cfg)}")

    resolved_index_name = index_name if index_name is not None else CHUNK_EMBEDDING_INDEX_NAME
    effective_qa_model = getattr(config, "openai_model", None) or "gpt-4o-mini"
    retrieval_query = _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph else _RETRIEVAL_QUERY_BASE
    query_params: dict[str, object] = {"run_id": run_id, "source_uri": source_uri}

    history: MessageHistory = InMemoryMessageHistory()
    print("Power Atlas interactive Q&A (type 'exit'/'quit' or Ctrl-D to stop)\n")

    # Build driver, retriever, LLM, and GraphRAG once and reuse across all REPL turns
    # to avoid per-turn connection overhead and Neo4j driver churn.
    with neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password)) as driver:
        embedder = OpenAIEmbeddings(model=EMBEDDER_MODEL_NAME)
        retriever = VectorCypherRetriever(
            driver=driver,
            index_name=resolved_index_name,
            embedder=embedder,
            retrieval_query=retrieval_query,
            result_formatter=_chunk_citation_formatter,
            neo4j_database=neo4j_database,
        )
        llm = OpenAILLM(
            model_name=effective_qa_model,
            model_params={"temperature": 0},
        )
        rag = GraphRAG(
            retriever=retriever,
            llm=llm,
            prompt_template=POWER_ATLAS_RAG_TEMPLATE,
        )
        try:
            while True:
                try:
                    question = input("Question: ").strip()
                except EOFError:
                    print()
                    break
                if not question:
                    continue
                if question.lower() in ("exit", "quit"):
                    break
                rag_result = rag.search(
                    query_text=question,
                    retriever_config={"top_k": top_k, "query_params": query_params},
                    return_context=True,
                    message_history=history,
                )
                answer = rag_result.answer if rag_result else ""
                print(f"\nAnswer:\n{answer}\n")
                if answer and not _check_all_answers_cited(answer):
                    _logger.warning("Not all non-empty answer lines end with a citation token.")
                history.add_messages(
                    [
                        LLMMessage(role="user", content=question),
                        LLMMessage(role="assistant", content=answer),
                    ]
                )
        except KeyboardInterrupt:
            print()


__all__ = [
    "run_retrieval_and_qa",
    "run_interactive_qa",
]

