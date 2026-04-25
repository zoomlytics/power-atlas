from __future__ import annotations

import logging
import os
import re
import types
from collections.abc import Mapping
from typing import Literal, TypedDict, cast

import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.message_history import InMemoryMessageHistory, MessageHistory

from power_atlas.bootstrap import require_openai_api_key
from power_atlas.bootstrap.clients import build_embedder, build_llm as build_openai_llm
from power_atlas.context import RequestContext
from power_atlas.contracts import (
    ALIGNMENT_VERSION,
    AmbiguousDatasetError,
    POWER_ATLAS_RAG_TEMPLATE,
    PROMPT_IDS,
    resolve_dataset_root,
)
from power_atlas.contracts.pipeline import (
    PipelineContractSnapshot,
    is_pipeline_contract_snapshot,
)
from power_atlas.retrieval_postprocessing import (
    _AnswerPostprocessResult,
    _CitationQualityBundle,
    _POSTPROCESS_FIELD_MAP,
    _PostprocessPublicFields,
    _RetrievalDebugView,
    apply_citation_repair as _apply_citation_repair_impl,
    build_citation_fallback as _build_citation_fallback_impl,
    build_retrieval_debug_view as _build_retrieval_debug_view_impl,
    check_all_answers_cited as _check_all_answers_cited_impl,
    first_citation_token_from_hits as _first_citation_token_from_hits_impl,
    format_postprocess_debug_summary as _format_postprocess_debug_summary_impl,
    postprocess_answer as _postprocess_answer_impl,
    project_postprocess_to_public as _project_postprocess_to_public_impl,
    repair_uncited_answer as _repair_uncited_answer_impl,
    split_into_segments as _split_into_segments_impl,
)
from power_atlas.retrieval_request_context_adapters import (
    run_interactive_request_context,
    run_retrieval_request_context,
)
from power_atlas.retrieval_chunk_formatter import (
    build_retrieval_path_diagnostics as _build_retrieval_path_diagnostics,
    format_chunk_citation_record,
    format_claim_details as _format_claim_details,
    format_cluster_context as _format_cluster_context,
    normalize_claim_roles as _normalize_claim_roles,
)
from power_atlas.retrieval_path_diagnostics import (
    count_malformed_diagnostics as _count_malformed_diagnostics,
    diagnostics_dict_has_malformed_fields as _diagnostics_dict_has_malformed_fields,
    format_retrieval_path_summary as _format_retrieval_path_summary,
)
from power_atlas.retrieval_query_builders import _build_canonical_names_expr
from power_atlas.retrieval_query_builders import _build_claim_details_with_clause
from power_atlas.retrieval_query_builders import _build_cluster_canonical_alignments_expr
from power_atlas.retrieval_query_builders import _build_cluster_memberships_expr
from power_atlas.retrieval_query_builders import _build_mention_names_expr
from power_atlas.retrieval_query_builders import _build_retrieval_query
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_BASE
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_BASE_ALL_RUNS
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_WITH_CLUSTER
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_WITH_EXPANSION
from power_atlas.retrieval_query_builders import _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS
from power_atlas.retrieval_query_builders import _select_retrieval_query
from power_atlas.retrieval_interactive_session import (
    initialize_interactive_session,
    run_interactive_session_loop,
)
from power_atlas.retrieval_live_preflight import require_live_retrieval_openai_api_key
from power_atlas.retrieval_live_preflight import resolve_live_neo4j_settings
from power_atlas.retrieval_execution_setup import (
    build_live_retrieval_query_params,
    prepare_retrieval_execution_context,
)
from power_atlas.retrieval_result_prelude import prepare_retrieval_result_prelude
from power_atlas.retrieval_request_helpers import build_retrieval_query_params
from power_atlas.retrieval_request_helpers import format_retrieval_scope_label
from power_atlas.retrieval_session_setup import build_retriever_and_rag as build_retriever_and_rag_impl
from power_atlas.retrieval_single_shot_session import run_single_shot_retrieval_session
from power_atlas.retrieval_runtime import (
    InteractiveRetrievalTurnResult,
    build_early_return_retrieval_result,
    build_dry_run_retrieval_result,
    build_retrieval_base_result,
    build_retrieval_skipped_result,
    build_live_retrieval_result,
    execute_retrieval_search,
    finalize_live_retrieval_result,
    run_interactive_retrieval_turn,
    run_live_retrieval_session,
)
from power_atlas.settings import Neo4jSettings
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import LLMMessage, RetrieverResultItem

from demo.stages.pipeline_contract_compat import get_stage_pipeline_contract_value

_DEFAULT_TOP_K = 10
_logger = logging.getLogger(__name__)
_PIPELINE_CONTRACT_EXPORTS = {
    "CHUNK_EMBEDDING_INDEX_NAME": "chunk_embedding_index_name",
    "EMBEDDER_MODEL_NAME": "embedder_model_name",
}


def _pipeline_contract_value(
    name: str,
    pipeline_contract: PipelineContractSnapshot,
) -> str:
    return cast(str, get_stage_pipeline_contract_value(name, _PIPELINE_CONTRACT_EXPORTS, pipeline_contract))


def _resolve_pipeline_contract(
    config: object,
    pipeline_contract: PipelineContractSnapshot | None,
) -> PipelineContractSnapshot:
    if pipeline_contract is not None:
        return pipeline_contract
    config_pipeline_contract = getattr(config, "pipeline_contract", None)
    if is_pipeline_contract_snapshot(config_pipeline_contract):
        return config_pipeline_contract
    raise ValueError(
        "Retrieval stage requires an explicit pipeline contract or "
        "config.pipeline_contract from RequestContext/AppContext-derived config"
    )


def _neo4j_settings_from_config(
    config: object,
    neo4j_settings: Neo4jSettings | None = None,
) -> Neo4jSettings:
    return resolve_live_neo4j_settings(
        config,
        neo4j_settings,
        neo4j_settings_type=Neo4jSettings,
        error_message=(
        "Live retrieval requires config.settings.neo4j or an explicit neo4j_settings "
        "argument from RequestContext/AppContext-derived config"
        ),
    )


def _require_stage_openai_api_key(error_message: str) -> None:
    require_live_retrieval_openai_api_key(
        error_message,
        require_openai_api_key=require_openai_api_key,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    )

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

# Maximum number of characters of the final answer text included in the
# "Answer replaced with citation fallback" diagnostic log message.
_FALLBACK_PREVIEW_MAX_LEN = 200


_format_scope_label = format_retrieval_scope_label


def _first_citation_token_from_hits(hits: list[dict[str, object]]) -> str | None:
    """Return the first non-empty citation token from a list of retrieval hit dicts."""
    return _first_citation_token_from_hits_impl(hits)


def _build_query_params(
    *,
    run_id: str | None,
    source_uri: str | None,
    all_runs: bool,
    cluster_aware: bool,
) -> dict[str, object]:
    """Build Cypher query parameters for retrieval filtering."""
    return build_retrieval_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        alignment_version=ALIGNMENT_VERSION,
    )


def _select_runtime_retrieval_query(
    *,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
) -> str:
    """Return the live-built retrieval query using the stage-bound builder seam."""
    _select_retrieval_query(
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
    )
    return _build_retrieval_query(
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
    )


def _apply_citation_repair(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    raw_answer_all_cited: bool,
) -> tuple[str, bool, bool, str | None, str | None]:
    """Attempt to repair uncited answer segments using retrieved citation tokens."""
    return _apply_citation_repair_impl(
        answer_text,
        hits,
        all_runs=all_runs,
        raw_answer_all_cited=raw_answer_all_cited,
        get_first_citation_token=_first_citation_token_from_hits,
        repair_answer=_repair_uncited_answer,
    )


def _build_citation_fallback(answer: str) -> tuple[str, str, bool]:
    """Compute citation-fallback display and history answers for a single LLM response."""
    return _build_citation_fallback_impl(
        answer,
        check_citations=_check_all_answers_cited,
        fallback_prefix=_CITATION_FALLBACK_PREFIX,
    )


def _project_postprocess_to_public(
    pp: _AnswerPostprocessResult,
) -> _PostprocessPublicFields:
    """Map an :class:`_AnswerPostprocessResult` to the public result surface."""
    return _project_postprocess_to_public_impl(pp)


def _build_retrieval_debug_view(
    pp: _AnswerPostprocessResult,
    *,
    malformed_diagnostics_count: int = 0,
) -> _RetrievalDebugView:
    """Build a :class:`_RetrievalDebugView` from a postprocessing result."""
    return _build_retrieval_debug_view_impl(
        pp,
        malformed_diagnostics_count=malformed_diagnostics_count,
    )


def _postprocess_answer(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    existing_citation_warnings: list[str] | None = None,
) -> _AnswerPostprocessResult:
        """Unified answer postprocessing lifecycle shared by both retrieval entry points."""
        return _postprocess_answer_impl(
                answer_text,
                hits,
                all_runs=all_runs,
                existing_citation_warnings=existing_citation_warnings,
                check_citations=_check_all_answers_cited,
                apply_repair=_apply_citation_repair,
                build_fallback=_build_citation_fallback,
                logger=_logger,
        )


def _split_into_segments(answer: str) -> list[str]:
    """Split answer text into citation-checkable segments (sentences and bullets)."""
    return _split_into_segments_impl(answer)


def _check_all_answers_cited(answer: str) -> bool:
    """Return True if every answer sentence or bullet ends with a citation token."""
    return _check_all_answers_cited_impl(
        answer,
        split_segments=_split_into_segments,
    )


def _repair_uncited_answer(answer: str, first_citation_token: str) -> str:
    """Repair uncited answer segments by appending a citation token from retrieved context."""
    return _repair_uncited_answer_impl(answer, first_citation_token)


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
    return format_chunk_citation_record(
        record,
        build_citation_token=_build_citation_token,
        logger=_logger,
    )


def _build_retriever_and_rag(
    driver: neo4j.Driver,
    *,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    neo4j_database: str | None,
    pipeline_contract: PipelineContractSnapshot,
) -> tuple[VectorCypherRetriever, GraphRAG]:
    """Construct a VectorCypherRetriever and GraphRAG instance for a Neo4j session.

    Shared by both ``run_retrieval_and_qa`` (single-turn) and
    ``run_interactive_qa`` (multi-turn REPL) so that retriever/LLM construction
    is defined in one place.

    Parameters
    ----------
    driver:
        An open Neo4j driver (must already be connected).
    index_name:
        Vector index name to use for similarity search.
    retrieval_query:
        The Cypher retrieval query string (produced by :func:`_select_retrieval_query`).
    qa_model:
        OpenAI model name to use for answer generation.
    neo4j_database:
        Optional Neo4j database name; ``None`` uses the driver's default database.
    """
    retriever, rag = build_retriever_and_rag_impl(
        driver,
        index_name=index_name,
        retrieval_query=retrieval_query,
        qa_model=qa_model,
        neo4j_database=neo4j_database,
        embedder_model_name=_pipeline_contract_value("EMBEDDER_MODEL_NAME", pipeline_contract),
        result_formatter=_chunk_citation_formatter,
        embedder_factory=OpenAIEmbeddings,
        retriever_factory=VectorCypherRetriever,
        rag_factory=GraphRAG,
        build_embedder=build_embedder,
        build_llm=build_openai_llm,
        prompt_template=POWER_ATLAS_RAG_TEMPLATE,
    )
    return retriever, rag


def run_retrieval_and_qa_request_context(
    request_context: RequestContext,
    *,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    question: str | None = None,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    message_history: MessageHistory | list[dict[str, str]] | None = None,
    interactive: bool = False,
) -> dict[str, object]:
    """Run single-turn retrieval using request-scoped context as the primary input."""
    return run_retrieval_request_context(
        request_context,
        top_k=top_k,
        index_name=index_name,
        question=question,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        run_impl=_run_retrieval_and_qa_impl,
    )


def _run_retrieval_and_qa_impl(
    config: object,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    question: str | None = None,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    message_history: MessageHistory | list[dict[str, str]] | None = None,
    interactive: bool = False,
    all_runs: bool = False,
    pipeline_contract: PipelineContractSnapshot | None = None,
    neo4j_settings: Neo4jSettings | None = None,
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
    cluster_aware:
        When True, extends graph expansion with :ResolvedEntityCluster traversal.
        Cluster membership status (``accepted`` / ``provisional``) and any
        :ALIGNED_WITH canonical entity enrichment are included in the LLM
        context so the model can distinguish settled entity identities from
        provisional cluster hypotheses.  Citations always reference the
        underlying Chunk node, not the cluster.  Implies graph expansion
        (``expand_graph`` behaviour is included automatically).
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
    pipeline_contract:
        Optional explicit pipeline contract snapshot. RequestContext-driven calls
        should always provide this rather than relying on config/global fallback.
    neo4j_settings:
        Optional explicit Neo4j settings. RequestContext-driven calls should
        provide this so live retrieval does not depend on config-shape fallback.
    """
    execution_context = prepare_retrieval_execution_context(
        config=config,
        pipeline_contract=pipeline_contract,
        index_name=index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        resolve_pipeline_contract=_resolve_pipeline_contract,
        pipeline_contract_value=_pipeline_contract_value,
        select_runtime_retrieval_query=_select_runtime_retrieval_query,
    )
    resolved_pipeline_contract = execution_context.pipeline_contract
    resolved_index_name = execution_context.resolved_index_name
    effective_qa_model = execution_context.effective_qa_model
    retrieval_query_contract = execution_context.retrieval_query
    qa_prompt_version = PROMPT_IDS["qa"]
    prelude = prepare_retrieval_result_prelude(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        top_k=top_k,
        resolved_index_name=resolved_index_name,
        question=question,
        effective_qa_model=effective_qa_model,
        qa_prompt_version=qa_prompt_version,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        retrieval_query_contract=retrieval_query_contract,
        interactive=interactive,
        message_history_enabled=message_history is not None,
        resolve_dataset_root=resolve_dataset_root,
        ambiguous_dataset_error_type=AmbiguousDatasetError,
        build_citation_token=_build_citation_token,
        build_retrieval_base_result=build_retrieval_base_result,
    )
    base = prelude["base"]
    citation_token_example = prelude["citation_token_example"]
    citation_object_example = prelude["citation_object_example"]
    early_return_result = build_early_return_retrieval_result(
        config=config,
        question=question,
        base=base,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        logger=_logger,
    )
    if early_return_result is not None:
        return early_return_result

    retrieval_query = retrieval_query_contract

    # Query params for filtering. source_uri=None is valid: the null-conditional
    # in the WHERE clause skips source_uri filtering when the parameter is None.
    # run_id is only included for run-scoped queries (not all-runs mode).
    # alignment_version is passed when cluster_aware=True to filter ALIGNED_WITH edges
    # to the current alignment generation only.
    query_params = build_live_retrieval_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        build_query_params=_build_query_params,
        run_id_error_message=(
            "run_id is required for live retrieval. "
            "Pass --run-id, --latest, or use --all-runs to query across all data."
        ),
    )

    # ── Warning surfaces ────────────────────────────────────────────────────────
    # Two parallel accumulators are built during retrieval, then merged after
    # postprocessing:
    #
    #   warnings_list          — top-level, human-facing superset.  Receives ALL
    #                            warnings (operational + citation-quality).
    #   citation_warnings_list — citation-quality subset only.  Passed into
    #                            _postprocess_answer() as existing_citation_warnings
    #                            to seed the helper’s internal accumulator. The
    #                            helper returns a new, extended citation_warnings
    #                            list derived from this seed. Every entry here must
    #                            also appear in warnings_list.
    #
    # After _postprocess_answer() returns, any new citation warnings it produced
    # are propagated up to warnings_list so the two lists remain consistent.
    # See §2.5.2 of the contract document for the full invariant specification.
    warnings_list: list[str] = []
    citation_warnings_list: list[str] = []
    hits: list[dict[str, object]] = []

    def _run_single_shot_session(*, driver: object, retriever: object, rag: GraphRAG) -> tuple[str, list[dict[str, object]], list[str], list[str]]:
        del driver, retriever
        return run_single_shot_retrieval_session(
            rag=rag,
            question=question,
            top_k=top_k,
            query_params=query_params,
            message_history=message_history,
            citation_optional_fields=_CITATION_OPTIONAL_FIELDS,
            logger=_logger,
            execute_search=execute_retrieval_search,
        )

    answer_text, hits, session_warnings, session_citation_warnings = run_live_retrieval_session(
        config=config,
        neo4j_settings=neo4j_settings,
        neo4j_settings_type=Neo4jSettings,
        require_openai_api_key=require_openai_api_key,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_error_message="OPENAI_API_KEY environment variable is required for live retrieval.",
        neo4j_error_message=(
            "Live retrieval requires config.settings.neo4j or an explicit neo4j_settings "
            "argument from RequestContext/AppContext-derived config"
        ),
        index_name=resolved_index_name,
        retrieval_query=retrieval_query,
        qa_model=effective_qa_model,
        pipeline_contract=resolved_pipeline_contract,
        build_retriever_and_rag=_build_retriever_and_rag,
        run_session=_run_single_shot_session,
    )
    return finalize_live_retrieval_result(
        base=base,
        answer_text=answer_text,
        hits=hits,
        session_warnings=session_warnings,
        session_citation_warnings=session_citation_warnings,
        all_runs=all_runs,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        citation_token_example=citation_token_example,
        citation_object_example=citation_object_example,
        fallback_preview_max_len=_FALLBACK_PREVIEW_MAX_LEN,
        logger=_logger,
        postprocess_answer=_postprocess_answer,
        project_postprocess_to_public=_project_postprocess_to_public,
        format_retrieval_path_summary=_format_retrieval_path_summary,
        count_malformed_diagnostics=_count_malformed_diagnostics,
        build_retrieval_debug_view=_build_retrieval_debug_view,
    )


def _format_postprocess_debug_summary(view: _RetrievalDebugView) -> str:
    """Format a compact postprocessing debug summary line from a retrieval debug view."""
    return _format_postprocess_debug_summary_impl(view)


def _run_interactive_qa_impl(
    config: object,
    *,
    run_id: str | None = None,
    source_uri: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
    debug: bool = False,
    pipeline_contract: PipelineContractSnapshot | None = None,
    neo4j_settings: Neo4jSettings | None = None,
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
    cluster_aware:
        When True, extends graph expansion with :ResolvedEntityCluster traversal so
        provisional cluster membership and alignment context are included in the LLM
        context for each turn.  Implies graph expansion behaviour.
    all_runs:
        When True, retrieval queries all Chunk nodes regardless of run_id.
        Citations may span multiple runs/files.
    debug:
        When True, prints a compact postprocessing summary after each answer showing
        citation quality metadata sourced from the shared postprocessing contract
        (raw/final citation state, repair/fallback applied, evidence level, warning
        count).  Default is False so normal interactive output is unaffected.
    pipeline_contract:
        Optional explicit pipeline contract snapshot. RequestContext-driven calls
        should always provide this rather than relying on config/global fallback.
    neo4j_settings:
        Optional explicit Neo4j settings. RequestContext-driven calls should
        provide this so live retrieval does not depend on config-shape fallback.
    """
    execution_context = prepare_retrieval_execution_context(
        config=config,
        pipeline_contract=pipeline_contract,
        index_name=index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        resolve_pipeline_contract=_resolve_pipeline_contract,
        pipeline_contract_value=_pipeline_contract_value,
        select_runtime_retrieval_query=_select_runtime_retrieval_query,
    )
    resolved_pipeline_contract = execution_context.pipeline_contract
    resolved_index_name = execution_context.resolved_index_name
    effective_qa_model = execution_context.effective_qa_model
    retrieval_query = execution_context.retrieval_query
    query_params = build_live_retrieval_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
        build_query_params=_build_query_params,
        run_id_error_message=(
            "run_id is required for interactive retrieval. "
            "Pass run_id, or set all_runs=True to query across all data."
        ),
    )

    history: MessageHistory = initialize_interactive_session(
        run_id=run_id,
        all_runs=all_runs,
        history_factory=InMemoryMessageHistory,
        format_scope_label=_format_scope_label,
    )

    # Build driver, retriever, LLM, and GraphRAG once and reuse across all REPL turns
    # to avoid per-turn connection overhead and Neo4j driver churn.
    def _run_interactive_session(*, driver: object, retriever: object, rag: GraphRAG) -> None:
        del driver, retriever
        run_interactive_session_loop(
            rag=rag,
            history=history,
            top_k=top_k,
            query_params=query_params,
            citation_optional_fields=_CITATION_OPTIONAL_FIELDS,
            logger=_logger,
            all_runs=all_runs,
            debug=debug,
            run_interactive_turn=run_interactive_retrieval_turn,
            postprocess_answer=_postprocess_answer,
            build_retrieval_debug_view=_build_retrieval_debug_view,
            format_postprocess_debug_summary=_format_postprocess_debug_summary,
            count_malformed_diagnostics=_count_malformed_diagnostics,
            llm_message_factory=LLMMessage,
        )

    run_live_retrieval_session(
        config=config,
        neo4j_settings=neo4j_settings,
        neo4j_settings_type=Neo4jSettings,
        require_openai_api_key=require_openai_api_key,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_error_message="OPENAI_API_KEY environment variable is required for live retrieval.",
        neo4j_error_message=(
            "Live retrieval requires config.settings.neo4j or an explicit neo4j_settings "
            "argument from RequestContext/AppContext-derived config"
        ),
        index_name=resolved_index_name,
        retrieval_query=retrieval_query,
        qa_model=effective_qa_model,
        pipeline_contract=resolved_pipeline_contract,
        build_retriever_and_rag=_build_retriever_and_rag,
        run_session=_run_interactive_session,
    )


def run_interactive_qa_request_context(
    request_context: RequestContext,
    *,
    top_k: int = _DEFAULT_TOP_K,
    index_name: str | None = None,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool | None = None,
    debug: bool = False,
) -> None:
    """Run interactive retrieval using request-scoped context as the primary input."""
    return run_interactive_request_context(
        request_context,
        top_k=top_k,
        index_name=index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
        debug=debug,
        run_impl=_run_interactive_qa_impl,
    )


__all__ = [
    "run_retrieval_and_qa_request_context",
    "run_interactive_qa_request_context",
    "_CITATION_FALLBACK_PREFIX",
    "_format_scope_label",
    "_format_retrieval_path_summary",
    "_count_malformed_diagnostics",
    "_diagnostics_dict_has_malformed_fields",
    "_format_postprocess_debug_summary",
    "_postprocess_answer",
    "_POSTPROCESS_FIELD_MAP",
    "_PostprocessPublicFields",
    "_project_postprocess_to_public",
    "_RetrievalDebugView",
    "_build_retrieval_debug_view",
]

