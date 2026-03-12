from __future__ import annotations

import logging
import os
import re

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.message_history import InMemoryMessageHistory, MessageHistory

from demo.llm_utils import build_openai_llm
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

# Graph-expanded retrieval: adds related ExtractedClaim, EntityMention, and canonical entity
# context via optional graph traversal from the retrieved Chunk node.
# Pattern comprehensions are used for each expansion target to avoid row multiplication
# (cartesian products) that would result from chained OPTIONAL MATCH clauses.
_RETRIEVAL_QUERY_WITH_EXPANSION = """
WITH node AS c, score
WHERE c.run_id = $run_id
  AND ($source_uri IS NULL OR c.source_uri = $source_uri)
RETURN c.text AS chunk_text,
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

# All-runs retrieval query: no run_id filter; queries across the whole database.
# Used when --all-runs flag is set. Citations may span multiple runs/files so provenance
# should be interpreted with care — each citation includes its own run_id field.
_RETRIEVAL_QUERY_BASE_ALL_RUNS = """
WITH node AS c, score
WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)
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

# All-runs graph-expanded retrieval: no run_id filter on chunks or derived nodes.
_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS = """
WITH node AS c, score
WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)
RETURN c.text AS chunk_text,
       c.chunk_id AS chunk_id,
       c.run_id AS run_id,
       c.source_uri AS source_uri,
       c.chunk_index AS chunk_index,
       coalesce(c.page_number, c.page) AS page,
       c.start_char AS start_char,
       c.end_char AS end_char,
       score AS similarityScore,
       [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) | claim.claim_text] AS claims,
       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) | mention.name] AS mentions,
       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) | coalesce(canonical.name, canonical.label)] AS canonical_entities
"""

# Optional citation-relevant fields that should be surfaced as warnings when absent.
_CITATION_OPTIONAL_FIELDS = ("page", "start_char", "end_char")

# Citation token prefix used to verify citation completeness in generated answers.
_CITATION_TOKEN_PREFIX = "[CITATION|"

# Regex matching one or more [CITATION|…] tokens at the very end of a stripped segment.
# Built from _CITATION_TOKEN_PREFIX so the two stay in sync.
# Each token starts with _CITATION_TOKEN_PREFIX, contains no unencoded ']', and is
# terminated by ']'. One or more consecutive tokens are allowed (e.g. multi-source claims).
_TRAILING_CITATION_RE = re.compile(rf"({re.escape(_CITATION_TOKEN_PREFIX)}[^\]]*\])+\s*$")

# Regex to split a paragraph line into individual sentences at natural boundaries.
# Splits at [.!?] followed by whitespace and (optionally) opening punctuation (quotes
# or parens), then either an uppercase letter or a '[' that is NOT immediately followed
# by 'CITATION|'. The latter allows sentence splits before non-citation bracketed text
# (e.g. "[Note]", "[1]") so that uncited sentences cannot slip through by being
# followed by such a bracket. '[CITATION|…]' tokens are never split-points: the
# negative lookahead '(?!CITATION\|)' blocks the split, keeping the citation token
# attached to the sentence it supports.
# Known limitation: title abbreviations before proper nouns (e.g. "Dr. Smith",
# "Mr. Jones") will be incorrectly split; this is an acceptable trade-off given the
# controlled, low-temperature LLM output environment where such patterns are rare.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'\u201c\u2018\u2019\u201d(]*(?:[A-Z]|\[(?!CITATION\|)))")

# Bullet line prefix: a line starting with -, *, •, or a number followed by a period,
# where the bullet marker is followed by at least one whitespace character.
# Grouping both alternatives inside the outer group ensures the '^' start anchor
# applies to both, making the pattern unambiguous regardless of match mode.
_BULLET_PREFIX_RE = re.compile(r"^([-*•]\s+|\d+\.\s+)")

# Prefix used when replacing an uncited answer with a structured fallback message.
# This is intended for user-visible messaging only; consumers (UI, manifests,
# downstream stages) should detect fallback answers via explicit metadata
# (for example, a `citation_fallback_applied` flag or citation-quality fields),
# not by matching this prefix against the answer text.
_CITATION_FALLBACK_PREFIX = "Insufficient citations detected"


def _build_citation_fallback(answer: str) -> tuple[str, str, bool]:
    """Compute citation-fallback display and history answers for a single LLM response.

    Both ``run_retrieval_and_qa`` and ``run_interactive_qa`` share this helper so
    that fallback-format changes (prefix text, separator, etc.) are applied in one place.

    Args:
        answer: Raw LLM answer text (may or may not contain citation tokens).

    Returns:
        A three-tuple ``(display_answer, history_answer, is_uncited)`` where:
        - *display_answer*: Message to show the user.  When uncited, this is the
          fallback prefix followed by the original answer text so the content is
          visible but clearly labeled; otherwise it equals *answer* unchanged.
        - *history_answer*: Sanitized message for conversation history.  When
          uncited, only the bare refusal prefix is stored so subsequent turns are
          not conditioned on under-cited content; otherwise it equals *answer*.
        - *is_uncited*: ``True`` when the answer lacks required citation tokens.
    """
    is_uncited = bool(answer and not _check_all_answers_cited(answer))
    display_answer = f"{_CITATION_FALLBACK_PREFIX}: {answer}" if is_uncited else answer
    history_answer = _CITATION_FALLBACK_PREFIX if is_uncited else answer
    return display_answer, history_answer, is_uncited


def _split_into_segments(answer: str) -> list[str]:
    """Split answer text into citation-checkable segments (sentences and bullets).

    Performs a two-level split:

    1. **Newline split**: each line is treated separately.
    2. **Sentence split within paragraphs**: non-bullet lines are further split at
       sentence boundaries (``[.!?]`` followed by whitespace and optional opening
       punctuation, then an uppercase letter) so that multi-sentence paragraphs are
       validated sentence-by-sentence rather than only checking whether the paragraph
       line ends with a citation.

    Bullet lines (starting with ``-``, ``*``, ``•``, or a digit followed by ``.`` and
    whitespace) are treated as atomic units: the whole bullet, including any sentence
    structure within it, is checked as a single citation segment.

    Citation tokens (``[CITATION|…]``) are intentionally kept attached to the sentence
    they support.  The negative lookahead ``(?!CITATION\\|)`` in ``_SENTENCE_SPLIT_RE``
    prevents a split directly before ``[CITATION|``, so ``"sentence. [CITATION|…]"``
    is never severed.  The lookbehind ``(?<=[.!?])`` also prevents splits between a
    citation token's closing ``]`` and the text that follows it.

    However, non-citation brackets (e.g. ``[Note]``, ``[1]``) DO trigger a split when
    they appear after sentence-ending punctuation, because ``\\[(?!CITATION\\|)`` in the
    lookahead matches any ``[`` not followed by ``CITATION|``.  This ensures that a
    line like ``"Claim A. [Note] Claim B. [CITATION|…]"`` is split into
    ``"Claim A."`` (no trailing citation → rejected) and
    ``"[Note] Claim B. [CITATION|…]"`` (has trailing citation → accepted).

    **Known limitation**: title abbreviations before proper nouns (e.g. ``"Dr. Smith"``,
    ``"Mr. Jones"``) will be split at the period.  This is an accepted heuristic
    trade-off in a controlled, low-temperature LLM output environment.

    Returns a list of non-empty stripped segments.
    """
    segments = []
    for line in answer.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if _BULLET_PREFIX_RE.match(line):
            # Bullet lines are treated as a single citation unit.
            segments.append(line)
        else:
            # Split paragraph lines on sentence boundaries.
            parts = _SENTENCE_SPLIT_RE.split(line)
            segments.extend(p.strip() for p in parts if p.strip())
    return segments


def _check_all_answers_cited(answer: str) -> bool:
    """Return True if every answer sentence or bullet ends with a citation token.

    The Power Atlas prompt instructs the LLM to place a ``[CITATION|...]`` token at the
    end of each sentence or bullet.  This function enforces that contract at the
    **sentence and bullet level** using ``_split_into_segments``:

    - The answer is split on newlines first.
    - Bullet lines (starting with ``-``, ``*``, ``•``, or a digit followed by ``.``)
      are treated as atomic units; one citation at the end of the bullet is sufficient.
    - Non-bullet paragraph lines are further split into individual sentences at
      ``[.!?]`` boundaries followed by an uppercase letter.  Each sentence must
      independently end with at least one citation token, catching uncited sentences
      embedded mid-line (e.g. ``"A. B. [CITATION]"`` → ``"A."`` fails because it
      does not itself end with a citation token).

    Using a regex anchored at end-of-segment (rather than just checking
    ``endswith("]")``) ensures that a ``]`` from unrelated bracketed text (e.g.
    Markdown links or other annotation tokens) does not produce false positives.
    One or more consecutive tokens are allowed to support multi-source claims.

    This is a heuristic; it errs toward False (under-cited) rather than producing
    false positives.
    """
    segments = _split_into_segments(answer)
    if not segments:
        return False
    for segment in segments:
        if not _TRAILING_CITATION_RE.search(segment):
            return False
    return True


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

    # Warn immediately when the retrieved chunk has no usable text content.
    # Empty or whitespace-only chunk text means the LLM will receive no evidence
    # for this chunk, which can silently degrade answer quality.
    empty_chunk_text = not chunk_text.strip()
    if empty_chunk_text:
        _logger.warning(
            "Chunk %r has empty or whitespace-only text; it will contribute no evidence to the answer.",
            chunk_id,
        )

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
        "empty_chunk_text": empty_chunk_text,
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
    all_runs: bool = False,
) -> dict[str, object]:
    """Run retrieval and GraphRAG Q&A for a single question or interactive session.

    Parameters
    ----------
    config:
        Runtime config with Neo4j/OpenAI settings.
    run_id:
        Scopes retrieval to a specific ingest run.  Mandatory for live mode
        unless *all_runs* is True.
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
        conversational context ONLY — they are never a source of answer
        evidence.  Each turn's answer must still be fully citation-grounded
        via retrieved chunks from the current question's retrieval results.
        No evidence may be sourced from assistant history turns.
    interactive:
        Records whether the call originated from an interactive REPL session.
        Does not change retrieval or generation behaviour on its own.
    all_runs:
        When True, retrieval queries all Chunk nodes regardless of run_id.
        Citations may span multiple runs/files; *run_id* is ignored.  In this
        mode each citation still carries its own ``run_id`` provenance field.
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
        _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS if (expand_graph and all_runs)
        else _RETRIEVAL_QUERY_BASE_ALL_RUNS if all_runs
        else _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph
        else _RETRIEVAL_QUERY_BASE
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
    # Use the raw run_id (possibly None for dry-run or all-runs mode) so the recorded
    # scope reflects the actual input rather than the citation-example fallback value.
    retrieval_scope: dict[str, object] = {
        "run_id": run_id,
        "source_uri": source_uri,
        "scope_widened": all_runs,
        "all_runs": all_runs,
    }

    # Build shared base dict; only status/retrievers/qa and live-specific fields differ.
    # Use citation_run_id/citation_source_uri (which include fallbacks) so stage metadata is
    # always consistent with the provenance fields in citation_object_example.
    # citation_quality provides a structured per-answer QA signal bundle that manifests and
    # downstream consumers can query without inspecting individual warning strings.
    _default_citation_quality: dict[str, object] = {
        "all_cited": False,
        "evidence_level": "no_answer",
        "warning_count": 0,
        "citation_warnings": [],
    }
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
        "raw_answer": "",
        "citation_fallback_applied": False,
        "all_answers_cited": False,
        "citation_quality": _default_citation_quality,
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
            "qa": "GraphRAG run-scoped citations",
        }

    # Live retrieval: build a VectorCypherRetriever with citation formatter.
    # run_id is mandatory unless all_runs=True (which queries across all chunks).
    if not all_runs and run_id is None:
        raise ValueError(
            "run_id is required for live retrieval. "
            "Pass --run-id, --latest, or use --all-runs to query across all data."
        )

    retrieval_query = (
        _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS if (expand_graph and all_runs)
        else _RETRIEVAL_QUERY_BASE_ALL_RUNS if all_runs
        else _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph
        else _RETRIEVAL_QUERY_BASE
    )

    # Query params for filtering. source_uri=None is valid: the null-conditional
    # in the WHERE clause skips source_uri filtering when the parameter is None.
    # run_id is only included for run-scoped queries (not all-runs mode).
    query_params: dict[str, object] = {"source_uri": source_uri}
    if not all_runs:
        query_params["run_id"] = run_id

    warnings_list: list[str] = []
    citation_warnings_list: list[str] = []
    hits: list[dict[str, object]] = []

    if question is None:
        warning_msg = "No question provided; skipping vector retrieval."
        _logger.warning(warning_msg)
        # Retrieval (and optional graph expansion) did not run; report no retrievers.
        return {
            **base,
            "status": "live",
            "retrievers": [],
            "qa": "GraphRAG run-scoped citations",
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
        # capability-aware LLM for grounded, citation-enforced output.
        # Aligned with vendor pattern from vendor-resources/examples/customize/answer/custom_prompt.py
        # and vendor-resources/examples/question_answering/graphrag_with_neo4j_message_history.py.
        llm = build_openai_llm(effective_qa_model)
        rag = GraphRAG(
            retriever=retriever,
            llm=llm,
            prompt_template=POWER_ATLAS_RAG_TEMPLATE,
        )

        # Run the GraphRAG search with optional message history for interactive mode.
        # message_history provides conversational context ONLY — it is never a
        # source of answer evidence.  All evidence must come from the retrieved
        # chunks returned by the VectorCypherRetriever for this turn.
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
                # Surface informational warnings for chunks missing optional citation
                # fields (page, start_char, end_char).  These are logged for
                # observability but are intentionally not added to citation_warnings_list
                # because missing optional fields do not degrade citation enforcement.
                # evidence_level is only degraded by critical issues (empty chunk text
                # or uncited answer segments); see RFC #159 citation contract.
                missing_fields = [f for f in _CITATION_OPTIONAL_FIELDS if citation_obj.get(f) is None]
                if missing_fields:
                    _logger.info(
                        "Chunk %r missing optional citation fields: %s",
                        citation_obj.get("chunk_id"),
                        ", ".join(missing_fields),
                    )
                    chunk_warning = f"Chunk {citation_obj.get('chunk_id')!r} missing optional citation fields: {', '.join(missing_fields)}"
                    warnings_list.append(chunk_warning)
                    # Intentionally NOT added to citation_warnings_list: optional
                    # fields do not affect evidence_level per citation contract #159.
                # Surface warnings for chunks with empty or whitespace-only text.
                # These chunks contribute no evidence to the answer and degrade retrieval quality.
                if meta.get("empty_chunk_text"):
                    chunk_id_val = citation_obj.get("chunk_id")
                    empty_text_warning = f"Chunk {chunk_id_val!r} has empty or whitespace-only text."
                    warnings_list.append(empty_text_warning)
                    citation_warnings_list.append(empty_text_warning)
                hits.append({"content": item.content, "metadata": meta})

    # Check answer citation completeness; apply controlled fallback when not fully cited.
    # raw_answer preserves the original LLM output for transparency/debugging regardless
    # of whether a fallback replacement is applied.
    raw_answer = answer_text
    answer_text, _, uncited = _build_citation_fallback(answer_text)
    # all_cited is False both when the answer is empty (nothing to cite) and when
    # the helper finds uncited sentences; True only when the answer is non-empty
    # and every segment carries a trailing citation token.
    all_cited = bool(raw_answer) and not uncited
    if answer_text and not all_cited:
        citation_warning = "Not all answer sentences or bullets end with a citation token."
        _logger.warning(citation_warning)
        warnings_list.append(citation_warning)
        citation_warnings_list.append(citation_warning)
        # Wrap the under-cited answer in a structured, clearly labeled fallback so that
        # all consumers (UI, manifests, downstream stages) see an explicit citation
        # warning instead of silently treating an under-cited response as fully reliable.
        fallback_preview = (
            answer_text[:200] + "..." if len(answer_text) > 200 else answer_text
        )
        _logger.warning(
            "Answer replaced with citation fallback (length=%d, preview=%r)",
            len(answer_text),
            fallback_preview,
        )

    # Build the structured per-answer citation quality signal bundle.
    # evidence_level encodes the overall quality of the retrieved evidence:
    #   "no_answer"  – no answer was generated (empty answer text)
    #   "full"       – every answer sentence and bullet ends with a citation token AND
    #                  no critical citation-quality warnings exist (e.g. no empty chunks)
    #   "degraded"   – any answer sentence or bullet is missing a citation token, OR a
    #                  critical citation-quality warning exists (e.g. empty chunk text).
    #                  Missing OPTIONAL citation fields (page, start_char, end_char) do
    #                  NOT degrade evidence_level per citation contract #159.
    evidence_level = (
        "no_answer" if not answer_text
        else ("degraded" if (not all_cited or citation_warnings_list) else "full")
    )
    live_citation_quality: dict[str, object] = {
        "all_cited": all_cited,
        "evidence_level": evidence_level,
        "warning_count": len(citation_warnings_list),
        "citation_warnings": citation_warnings_list,
    }

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
    qa_scope_label = "GraphRAG all-runs citations" if all_runs else "GraphRAG run-scoped citations"
    return {
        **base,
        "status": "live",
        "retrievers": live_retrievers,
        "qa": qa_scope_label,
        "hits": len(hits),
        "retrieval_results": hits,
        "warnings": warnings_list,
        "citation_token_example": actual_citation_token,
        "citation_object_example": actual_citation_object,
        "citation_example": actual_citation_object,
        "answer": answer_text,
        "raw_answer": raw_answer or "",
        "citation_fallback_applied": uncited,
        "all_answers_cited": all_cited,
        "citation_quality": live_citation_quality,
    }


def run_interactive_qa(
    config: object,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    expand_graph: bool = False,
    all_runs: bool = False,
) -> None:
    """Run a REPL-style interactive Q&A session.

    Reads questions from stdin and prints citation-grounded answers until the user
    types ``exit``, ``quit``, or sends EOF (Ctrl-D).

    Message history is maintained across turns via an in-memory store so the LLM
    has conversational context, but message history provides conversational context
    ONLY — it is never a source of answer evidence.  Each turn's answer must still
    be fully citation-grounded via retrieved chunks from the current question's
    retrieval results.  No evidence may be sourced from assistant history turns.

    The Neo4j driver, retriever, LLM, and GraphRAG objects are constructed once for
    the session to avoid per-turn connection churn and latency.

    Aligned with vendor patterns from:
    - vendor-resources/examples/question_answering/graphrag_with_message_history.py
      (list[dict]-based history)
    - vendor-resources/examples/question_answering/graphrag_with_neo4j_message_history.py
      (MessageHistory-based; this REPL uses InMemoryMessageHistory)

    Parameters
    ----------
    config:
        Runtime config with Neo4j/OpenAI settings.
    run_id:
        Scopes retrieval to a specific ingest run.  Mandatory unless *all_runs* is True.
    source_uri:
        Optional source-level filter within the run scope.
    top_k:
        Maximum number of retrieved chunks to pass to the LLM as context.
    index_name:
        Vector index name; defaults to the contract value.
    expand_graph:
        When True, adds graph-expansion context via ExtractedClaim / EntityMention.
    all_runs:
        When True, retrieval queries all Chunk nodes regardless of run_id.
        Citations may span multiple runs/files.
    """
    # Validate and resolve session-level config once before opening any connections.
    if not all_runs and run_id is None:
        raise ValueError(
            "run_id is required for interactive retrieval. "
            "Pass run_id, or set all_runs=True to query across all data."
        )

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
    retrieval_query = (
        _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS if (expand_graph and all_runs)
        else _RETRIEVAL_QUERY_BASE_ALL_RUNS if all_runs
        else _RETRIEVAL_QUERY_WITH_EXPANSION if expand_graph
        else _RETRIEVAL_QUERY_BASE
    )
    query_params: dict[str, object] = {"source_uri": source_uri}
    if not all_runs:
        query_params["run_id"] = run_id

    history: MessageHistory = InMemoryMessageHistory()
    if all_runs:
        print("Using retrieval scope: all runs in database")
    else:
        print(f"Using retrieval scope: run={run_id}")
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
        llm = build_openai_llm(effective_qa_model)
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
                    # history provides conversational context only — never answer evidence.
                    # All evidence for this turn comes exclusively from the retriever above.
                    message_history=history,
                )
                answer = rag_result.answer if rag_result else ""
                display_answer, history_answer, uncited = _build_citation_fallback(answer)
                print(f"\nAnswer:\n{display_answer}\n")
                if uncited:
                    _logger.warning("Not all answer sentences or bullets end with a citation token.")
                    print(
                        "⚠ WARNING: Not all answer sentences or bullets are cited — evidence quality may be degraded."
                    )
                # Store only the refusal prefix (not the full uncited output) in history
                # so that subsequent turns are not conditioned on under-cited content.
                # The full fallback text is still printed to the user above.
                history.add_messages(
                    [
                        LLMMessage(role="user", content=question),
                        LLMMessage(role="assistant", content=history_answer),
                    ]
                )
        except KeyboardInterrupt:
            print()


__all__ = [
    "run_retrieval_and_qa",
    "run_interactive_qa",
    "_CITATION_FALLBACK_PREFIX",
]

