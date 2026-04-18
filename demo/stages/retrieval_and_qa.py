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
from power_atlas.bootstrap.clients import build_embedder_for_settings, create_neo4j_driver
from power_atlas.context import RequestContext
from power_atlas.contracts import (
    ALIGNMENT_VERSION,
    AmbiguousDatasetError,
    POWER_ATLAS_RAG_TEMPLATE,
    PROMPT_IDS,
    resolve_dataset_root,
    resolve_early_return_rule,
)
from power_atlas.settings import AppSettings, Neo4jSettings
from power_atlas.llm_utils import build_openai_llm
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import LLMMessage, RetrieverResultItem

from power_atlas.contracts.pipeline import get_pipeline_contract_snapshot

_DEFAULT_TOP_K = 10
_logger = logging.getLogger(__name__)
_PIPELINE_CONTRACT_EXPORTS = {
    "CHUNK_EMBEDDING_INDEX_NAME": "chunk_embedding_index_name",
    "EMBEDDER_MODEL_NAME": "embedder_model_name",
}


def _pipeline_contract_value(name: str) -> str:
    if name in globals():
        return cast(str, globals()[name])
    snapshot = get_pipeline_contract_snapshot()
    return cast(str, getattr(snapshot, _PIPELINE_CONTRACT_EXPORTS[name]))


def __getattr__(name: str) -> object:
    if name in _PIPELINE_CONTRACT_EXPORTS:
        return _pipeline_contract_value(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ---------------------------------------------------------------------------
# Private query sub-expression builders.
#
# Each function returns a Cypher fragment that is shared across multiple query
# variants.  The *run_scoped* flag controls whether run_id WHERE filters are
# included (run-scoped mode) or omitted (all-runs mode).
# ---------------------------------------------------------------------------

# Shared RETURN projection for chunk provenance fields — identical in all variants.
_RETURN_BASE_COLUMNS = (
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore"
)


def _build_claim_details_with_clause(run_scoped: bool) -> str:
    """Return the WITH clause that adds claim_details via HAS_PARTICIPANT traversal.

    Traverses ``SUPPORTED_BY`` edges from the Chunk to ``ExtractedClaim`` nodes,
    then collects **all** ``HAS_PARTICIPANT`` participation edges (v0.3 model) as a
    ``roles`` list.  Each entry in the list carries the ``role`` property, the
    mention ``mention_name``, and the ``match_method`` — covering subject, object,
    and any future roles (agent, target, location, …) without requiring schema
    changes.

    When *run_scoped* is ``True``, a ``WHERE`` filter restricts
    ``ExtractedClaim`` nodes to the current ``$run_id``.  In all-runs mode the
    filter is omitted so claims from all runs are included.
    """
    claim_filter = " WHERE claim.run_id = $run_id" if run_scoped else ""
    return (
        "WITH c, score,\n"
        "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim)" + claim_filter + " |\n"
        "         {claim_text: claim.claim_text,\n"
        "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
        "     ] AS claim_details"
    )


def _build_mention_names_expr(run_scoped: bool) -> str:
    """Return the pattern comprehension that projects mention names from a Chunk.

    Traverses ``MENTIONED_IN`` edges to ``EntityMention`` nodes and collects
    their ``name`` properties.  When *run_scoped* is ``True``, a ``WHERE``
    filter restricts ``EntityMention`` nodes to the current ``$run_id``.
    """
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)" + run_filter
        + " | mention.name] AS mentions"
    )


def _build_canonical_names_expr(run_scoped: bool) -> str:
    """Return the pattern comprehension that projects canonical entity names.

    Traverses ``MENTIONED_IN`` → ``RESOLVES_TO`` to reach ``CanonicalEntity``
    nodes and collects their ``name`` properties.  When *run_scoped* is
    ``True``, a ``WHERE`` filter restricts ``EntityMention`` nodes to the
    current ``$run_id``.
    """
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical)"
        + run_filter + " | canonical.name] AS canonical_entities"
    )


def _build_cluster_memberships_expr(run_scoped: bool) -> str:
    """Return the pattern comprehension that projects ResolvedEntityCluster memberships.

    For each ``EntityMention`` reachable from the Chunk, follows ``MEMBER_OF``
    edges to ``ResolvedEntityCluster`` nodes and collects per-membership
    provenance (``cluster_id``, ``cluster_name``, ``membership_status``,
    ``membership_method``).  When *run_scoped* is ``True``, a ``WHERE`` filter
    restricts ``EntityMention`` nodes to the current ``$run_id``.
    """
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster)"
        + run_filter
        + " | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name, membership_status: r.status, membership_method: r.method}] AS cluster_memberships"
    )


def _build_cluster_canonical_alignments_expr(run_scoped: bool) -> str:
    """Return the pattern comprehension that projects ALIGNED_WITH canonical entities.

    Follows ``MEMBER_OF`` → ``ALIGNED_WITH`` from each ``EntityMention`` to
    reach ``CanonicalEntity`` nodes and collects alignment provenance
    (``canonical_name``, ``alignment_method``, ``alignment_status``).

    In run-scoped mode, filters by ``$run_id`` on both the ``EntityMention``
    and the ``ALIGNED_WITH`` edge, and by ``$alignment_version`` to restrict to
    the current alignment generation.  In all-runs mode, the self-scoping
    filter ``a.run_id = mention.run_id`` is used instead so each mention's
    alignment edges stay paired with their own run.
    """
    if run_scoped:
        where_clause = (
            " WHERE mention.run_id = $run_id AND a.run_id = $run_id"
            " AND a.alignment_version = $alignment_version"
        )
    else:
        where_clause = (
            " WHERE a.run_id = mention.run_id AND a.alignment_version = $alignment_version"
        )
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:MEMBER_OF]"
        "->(cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(aligned_canonical)"
        + where_clause
        + " | {canonical_name: aligned_canonical.name, alignment_method: a.alignment_method,"
        " alignment_status: a.alignment_status}] AS cluster_canonical_alignments"
    )


def _build_retrieval_query(
    *,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
) -> str:
    """Assemble a retrieval Cypher query for the specified combination of modes.

    Delegates sub-expression construction to the individual builder functions
    so each expansion fragment is defined once and reused across all query
    variants.

    Parameters
    ----------
    expand_graph:
        When ``True``, adds ``claim_details``, ``mentions``, and
        ``canonical_entities`` expansions to the query.
    cluster_aware:
        When ``True``, extends graph expansion with ``cluster_memberships`` and
        ``cluster_canonical_alignments`` expansions.  Implies *expand_graph*.
    all_runs:
        When ``True``, omits run-scoped ``WHERE`` filters so the query spans
        all runs in the database.
    """
    run_scoped = not all_runs
    # cluster_aware always includes expansion
    expand_graph = expand_graph or cluster_aware

    # Preamble: scope the Chunk node (and optionally the source_uri).
    if run_scoped:
        preamble = (
            "WITH node AS c, score\n"
            "WHERE c.run_id = $run_id\n"
            "  AND ($source_uri IS NULL OR c.source_uri = $source_uri)"
        )
    else:
        preamble = (
            "WITH node AS c, score\n"
            "WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)"
        )

    if not expand_graph:
        return "\n" + preamble + "\n" + _RETURN_BASE_COLUMNS + "\n"

    with_claim = _build_claim_details_with_clause(run_scoped)
    mention_expr = _build_mention_names_expr(run_scoped)
    canonical_expr = _build_canonical_names_expr(run_scoped)
    expansion_return = (
        "       [cd IN claim_details | cd.claim_text] AS claims,\n"
        "       " + mention_expr + ",\n"
        "       " + canonical_expr + ",\n"
        "       claim_details"
    )

    if not cluster_aware:
        return (
            "\n" + preamble + "\n"
            + with_claim + "\n"
            + _RETURN_BASE_COLUMNS + ",\n"
            + expansion_return + "\n"
        )

    cluster_memberships_expr = _build_cluster_memberships_expr(run_scoped)
    cluster_canonical_expr = _build_cluster_canonical_alignments_expr(run_scoped)
    cluster_return = (
        "       " + cluster_memberships_expr + ",\n"
        "       " + cluster_canonical_expr
    )
    return (
        "\n" + preamble + "\n"
        + with_claim + "\n"
        + _RETURN_BASE_COLUMNS + ",\n"
        + expansion_return + ",\n"
        + cluster_return + "\n"
    )


def _select_retrieval_query(
    *,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
) -> str:
    """Return the pre-built retrieval Cypher query for the given mode combination.

    Encapsulates the query-selection priority so callers do not repeat the
    same conditional chain:

    - ``cluster_aware`` takes precedence over ``expand_graph``.
    - ``all_runs`` selects the scope-widened variant of any expansion level.
    - When neither flag is set, the base run-scoped query is returned.

    Parameters
    ----------
    expand_graph:
        When ``True``, selects a graph-expanded query variant.
    cluster_aware:
        When ``True``, selects the cluster-aware variant (implies expansion).
    all_runs:
        When ``True``, selects the all-runs (scope-widened) variant.
    """
    if cluster_aware and all_runs:
        return _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS
    if cluster_aware:
        return _RETRIEVAL_QUERY_WITH_CLUSTER
    if expand_graph and all_runs:
        return _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS
    if all_runs:
        return _RETRIEVAL_QUERY_BASE_ALL_RUNS
    if expand_graph:
        return _RETRIEVAL_QUERY_WITH_EXPANSION
    return _RETRIEVAL_QUERY_BASE
    
def _select_runtime_retrieval_query(
    *,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
) -> str:
    """Return the live-built retrieval query for the given mode combination.

    ``_select_retrieval_query`` preserves the historical pre-built query
    constants for compatibility and contract tests. This helper rebuilds the
    selected variant on demand so the active retrieval path is not coupled to
    import-time frozen query strings.
    """
    return _build_retrieval_query(
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=all_runs,
    )


# ---------------------------------------------------------------------------
# Pre-built query constants (assembled once at module load from the builders).
#
# These constants are the authoritative query strings used for retrieval and
# for the ``retrieval_query_contract`` manifest field.  Building them from the
# sub-expression builders ensures that shared fragments (claim participation,
# mention expansion, etc.) stay consistent across all variants without
# duplication.
# ---------------------------------------------------------------------------

# Retrieval query: run-scoped by default. `node` is the Chunk matched by the vector index;
# `score` is the similarity score from the index search. The null-conditional on $source_uri
# means the filter is skipped when source_uri is passed as None.
# Aligned with vendor pattern from vendor-resources/examples/retrieve/vector_cypher_retriever.py.
_RETRIEVAL_QUERY_BASE = _build_retrieval_query()

# Graph-expanded retrieval: adds related ExtractedClaim, EntityMention, and canonical entity
# context via optional graph traversal from the retrieved Chunk node.
# Pattern comprehensions are used for each expansion target to avoid row multiplication
# (cartesian products) that would result from chained OPTIONAL MATCH clauses.
# claim_details extends the flat claims list by traversing all HAS_PARTICIPANT edges so
# each claim map carries a generic ``roles`` list — one entry per participation edge —
# where each entry is ``{role, mention_name, match_method}``.  All roles (subject, object,
# and any future roles) are collected without [0]-index assumptions; an empty list is
# returned when no participation edges exist for a claim.
_RETRIEVAL_QUERY_WITH_EXPANSION = _build_retrieval_query(expand_graph=True)

# All-runs retrieval query: no run_id filter; queries across the whole database.
# Used when --all-runs flag is set. Citations may span multiple runs/files so provenance
# should be interpreted with care — each citation includes its own run_id field.
_RETRIEVAL_QUERY_BASE_ALL_RUNS = _build_retrieval_query(all_runs=True)

# All-runs graph-expanded retrieval: no run_id filter on chunks or derived nodes.
_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS = _build_retrieval_query(expand_graph=True, all_runs=True)

# Cluster-aware retrieval (run-scoped): extends graph expansion with provisional
# ResolvedEntityCluster membership and optional ALIGNED_WITH canonical enrichment.
# cluster_memberships returns per-membership provenance (status, method) so the
# LLM context can distinguish provisional from accepted cluster assignments.
# cluster_canonical_alignments surfaces canonical entity identities reached via
# the cluster's ALIGNED_WITH edge, including alignment method and status so
# provisional (non-confirmed) alignments are explicitly labelled.
_RETRIEVAL_QUERY_WITH_CLUSTER = _build_retrieval_query(cluster_aware=True)
_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS = _build_retrieval_query(cluster_aware=True, all_runs=True)

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


def _format_scope_label(run_id: str | None, all_runs: bool) -> str:
    """Return a human-readable retrieval scope label for CLI output.

    Used by both ``run_interactive_qa`` and the ``ask`` path in ``run_demo.main``
    to ensure consistent scope messaging across all entry points.
    """
    if all_runs:
        return "all runs in database"
    if run_id is not None:
        return f"run={run_id}"
    return "run=(none — dry-run placeholder)"


def _first_citation_token_from_hits(hits: list[dict[str, object]]) -> str | None:
    """Return the first non-empty citation token from a list of retrieval hit dicts.

    Each *hit* is expected to have a ``"metadata"`` key containing a dict with an
    optional ``"citation_token"`` entry (as produced by :func:`_chunk_citation_formatter`).
    Returns ``None`` when no hit carries a non-empty citation token.
    """
    for hit in hits:
        token = (hit.get("metadata") or {}).get("citation_token")  # type: ignore[union-attr]
        if token:
            return str(token)
    return None


def _build_query_params(
    *,
    run_id: str | None,
    source_uri: str | None,
    all_runs: bool,
    cluster_aware: bool,
) -> dict[str, object]:
    """Build Cypher query parameters for retrieval filtering.

    Shared by both ``run_retrieval_and_qa`` and ``run_interactive_qa`` so that
    parameter-construction logic stays in one place.

    Parameters
    ----------
    run_id:
        Scopes retrieval to a specific ingest run.  Included in the params dict
        only when *all_runs* is False.
    source_uri:
        Optional source-level filter (``None`` is valid; the Cypher WHERE clause
        skips source_uri filtering when the parameter is ``None``).
    all_runs:
        When True, ``run_id`` is omitted from the params so retrieval queries all
        Chunk nodes regardless of run.
    cluster_aware:
        When True, ``alignment_version`` is added to the params to scope
        ``ALIGNED_WITH`` edge traversal to the current alignment generation.
    """
    params: dict[str, object] = {"source_uri": source_uri}
    if not all_runs:
        params["run_id"] = run_id
    if cluster_aware:
        params["alignment_version"] = ALIGNMENT_VERSION
    return params


def _apply_citation_repair(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    raw_answer_all_cited: bool,
) -> tuple[str, bool, bool, str | None, str | None]:
    """Attempt to repair uncited answer segments using retrieved citation tokens.

    Shared by both ``run_retrieval_and_qa`` and ``run_interactive_qa`` so that
    the repair heuristic stays in one place and the two entry points remain aligned.

    Repair is only attempted when *all_runs* is True, hits are available, the
    answer is non-empty, and the raw answer was not already fully cited.  When
    any precondition is not met this function returns *answer_text* unchanged
    with ``attempted=False`` and ``applied=False``.  When preconditions are met
    but no usable citation token can be found in the hits, ``attempted=True``
    and ``applied=False`` are returned.

    Parameters
    ----------
    answer_text:
        Raw LLM answer text before any repair.
    hits:
        Retrieved chunk hit dicts (each with a ``"metadata"`` key) as produced by
        the retrieval loop in both entry points.
    all_runs:
        Repair is only active in all-runs mode because that mode lacks a single
        authoritative run_id citation token; the LLM sometimes omits trailing
        tokens in this context.
    raw_answer_all_cited:
        Whether the raw answer was already fully cited.  Passed in to avoid
        recomputing inside the helper.

    Returns
    -------
    tuple[str, bool, bool, str | None, str | None]
        ``(repaired_answer, attempted, applied, strategy, source_chunk_id)`` where:

        - *repaired_answer*: The answer after repair (or *answer_text* unchanged).
        - *attempted*: ``True`` when the preconditions for repair were met (i.e.
          ``all_runs=True``, hits non-empty, answer non-empty, answer not already
          fully cited) and repair logic was entered.  ``False`` when any
          precondition was not satisfied and repair was never evaluated.
        - *applied*: ``True`` when the repaired answer text differs from the
          original *answer_text* (i.e. the answer was actually modified by repair).
          ``False`` when no repair ran or when repair produced no change.
        - *strategy*: The repair strategy name (currently
          ``"append_first_retrieved_token"``), or ``None`` when *applied* is
          ``False``.
        - *source_chunk_id*: The ``chunk_id`` of the first retrieved chunk whose
          citation token was used for repair, or ``None`` when *applied* is
          ``False`` **or when the winning hit had no ``chunk_id`` to
          propagate** (empty/missing ``chunk_id`` in hit metadata).
    """
    if not (all_runs and hits and answer_text.strip() and not raw_answer_all_cited):
        return answer_text, False, False, None, None
    first_token = _first_citation_token_from_hits(hits)
    if not first_token:
        # Preconditions were met and repair was attempted, but no citation token
        # was available in the retrieved hits to use for repair.
        return answer_text, True, False, None, None
    source_chunk_id: str | None = None
    for hit in hits:
        metadata = hit.get("metadata") or {}
        token = metadata.get("citation_token")
        if token and str(token) == first_token:
            chunk_id_raw = metadata.get("chunk_id")
            # Treat empty string the same as None: no chunk_id provenance to record.
            source_chunk_id = str(chunk_id_raw) if chunk_id_raw else None
            break
    repaired = _repair_uncited_answer(answer_text, first_token)
    # applied is True only when repair actually modified the answer text.
    # This makes citation_repair_applied unambiguous: it means "the final
    # answer text was changed by repair", not merely "repair logic executed".
    if repaired == answer_text:
        return answer_text, True, False, None, None
    return repaired, True, True, "append_first_retrieved_token", source_chunk_id


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


class _CitationQualityBundle(TypedDict):
    """Structured citation-quality summary nested inside :class:`_AnswerPostprocessResult`."""

    all_cited: bool
    raw_answer_all_cited: bool
    evidence_level: Literal["no_answer", "full", "degraded"]
    warning_count: int
    citation_warnings: list[str]


class _AnswerPostprocessResult(TypedDict):
    """Structured result returned by :func:`_postprocess_answer`.

    All keys are always present regardless of which postprocessing path was
    taken.  Callers can index into the dict without ``# type: ignore``
    annotations.
    """

    raw_answer: str
    raw_answer_all_cited: bool
    repaired_answer: str
    citation_repair_attempted: bool
    citation_repair_applied: bool
    citation_repair_strategy: str | None
    citation_repair_source_chunk_id: str | None
    display_answer: str
    history_answer: str
    citation_fallback_applied: bool
    all_cited: bool
    evidence_level: Literal["no_answer", "full", "degraded"]
    citation_warnings: list[str]
    warning_count: int
    citation_quality: _CitationQualityBundle


#: Single authoritative mapping from :class:`_AnswerPostprocessResult` internal field
#: names to their corresponding public ``run_retrieval_and_qa()`` result-dict keys.
#:
#: This constant is the single source of truth for the projection layer.
#: :func:`_project_postprocess_to_public` builds the returned dict from it, and the
#: test suite imports it directly so the same mapping drives both the runtime and the
#: contract assertions — eliminating any possibility of the two drifting apart.
#:
#: Renames:
#:   - ``display_answer``  → ``answer``           (public name is shorter)
#:   - ``all_cited``       → ``all_answers_cited`` (public name is explicit)
#:
#: All other entries are identity mappings (internal key == public key).
#:
#: Wrapped in :func:`types.MappingProxyType` to prevent accidental mutation at
#: runtime (the mapping is a true constant, not a mutable configuration object).
_POSTPROCESS_FIELD_MAP: Mapping[str, str] = types.MappingProxyType({
    "display_answer": "answer",
    "raw_answer": "raw_answer",
    "citation_fallback_applied": "citation_fallback_applied",
    "all_cited": "all_answers_cited",
    "raw_answer_all_cited": "raw_answer_all_cited",
    "citation_repair_attempted": "citation_repair_attempted",
    "citation_repair_applied": "citation_repair_applied",
    "citation_repair_strategy": "citation_repair_strategy",
    "citation_repair_source_chunk_id": "citation_repair_source_chunk_id",
    "citation_quality": "citation_quality",
})
if len(set(_POSTPROCESS_FIELD_MAP.values())) != len(_POSTPROCESS_FIELD_MAP):
    raise ValueError(
        "_POSTPROCESS_FIELD_MAP contains duplicate public-key values; "
        "each internal key must map to a distinct public key"
    )


class _PostprocessPublicFields(TypedDict):
    """Public API fields produced by projecting an :class:`_AnswerPostprocessResult`.

    This TypedDict is the return type of :func:`_project_postprocess_to_public`
    and codifies the exact translation layer between the internal postprocessing
    contract and the ``run_retrieval_and_qa()`` result surface.  Keeping the
    mapping typed means the compiler and tests can both catch renames that only
    update one side.

    The authoritative field mapping is :data:`_POSTPROCESS_FIELD_MAP`.
    """

    answer: str
    raw_answer: str
    citation_fallback_applied: bool
    all_answers_cited: bool
    raw_answer_all_cited: bool
    citation_repair_attempted: bool
    citation_repair_applied: bool
    citation_repair_strategy: str | None
    citation_repair_source_chunk_id: str | None
    citation_quality: _CitationQualityBundle


def _project_postprocess_to_public(
    pp: _AnswerPostprocessResult,
) -> _PostprocessPublicFields:
    """Map an :class:`_AnswerPostprocessResult` to the public result surface.

    This adapter translates every internal postprocessing field to its
    corresponding public ``run_retrieval_and_qa()`` key using
    :data:`_POSTPROCESS_FIELD_MAP` as the single source of truth.  All callers
    that assemble the public result dict should use this function rather than
    spelling out the field mapping inline.

    Parameters
    ----------
    pp:
        Structured result from :func:`_postprocess_answer`.

    Returns
    -------
    _PostprocessPublicFields
        Typed dict with the public-facing postprocessing fields populated from
        *pp* according to :data:`_POSTPROCESS_FIELD_MAP`.
    """
    return cast(
        _PostprocessPublicFields,
        {
            public_key: pp[internal_key]  # type: ignore[literal-required]
            for internal_key, public_key in _POSTPROCESS_FIELD_MAP.items()
        },
    )


class _RetrievalDebugView(TypedDict):
    """Typed inspection model shared across retrieval/QA surfaces.

    This structure centralises all fields required for the supported
    inspection-oriented surface so that both :func:`run_interactive_qa`
    (interactive path, rendered on stdout when *debug=True*) and
    :func:`run_retrieval_and_qa` (single-shot path, returned as the
    ``debug_view`` key) produce views from the same data shape.  Consuming
    :func:`_format_postprocess_debug_summary` exclusively from this type
    prevents the inspection surface from drifting relative to the underlying
    postprocessing contract.

    ``debug_view`` is a **supported inspection-oriented surface**: it is always
    present in all result shapes and its key set is enforced by contract tests.
    For postprocessed ``status="live"`` results, these fields are populated with
    the full postprocessing state; for early-return payloads (e.g. dry-run or
    retrieval-skipped paths) the same keys are present but carry default or
    zero-valued data.  It is suitable for diagnostics, tooling, and evaluation.
    Callers should prefer top-level fields and ``citation_quality`` for ordinary
    application logic; ``debug_view`` consolidates the same state for
    convenience without carrying additional hidden data.

    Fields are populated by :func:`_build_retrieval_debug_view` from an
    :class:`_AnswerPostprocessResult` plus any supplementary runtime data (e.g.
    *malformed_diagnostics_count* derived from the hit list).
    """

    raw_answer_all_cited: bool
    all_cited: bool
    citation_repair_attempted: bool
    citation_repair_applied: bool
    citation_fallback_applied: bool
    evidence_level: Literal["no_answer", "full", "degraded"]
    warning_count: int
    citation_warnings: list[str]
    malformed_diagnostics_count: int


def _build_retrieval_debug_view(
    pp: _AnswerPostprocessResult,
    *,
    malformed_diagnostics_count: int = 0,
) -> _RetrievalDebugView:
    """Build a :class:`_RetrievalDebugView` from a postprocessing result.

    This is the single factory used by both retrieval entry points to construct
    the typed inspection model.  All inspection rendering should consume the
    returned view rather than reading ``_AnswerPostprocessResult`` fields
    directly, so the two cannot drift apart silently.

    Parameters
    ----------
    pp:
        Postprocessing result returned by :func:`_postprocess_answer`.
    malformed_diagnostics_count:
        Number of hits that contain structurally malformed
        ``retrieval_path_diagnostics`` payloads, as returned by
        :func:`_count_malformed_diagnostics`.  Defaults to ``0`` when not
        provided (e.g. when the hit list is empty or diagnostics were not
        collected).

    Returns
    -------
    _RetrievalDebugView
        Typed inspection view populated from *pp* and the supplementary
        runtime data.
    """
    return {
        "raw_answer_all_cited": pp["raw_answer_all_cited"],
        "all_cited": pp["all_cited"],
        "citation_repair_attempted": pp["citation_repair_attempted"],
        "citation_repair_applied": pp["citation_repair_applied"],
        "citation_fallback_applied": pp["citation_fallback_applied"],
        "evidence_level": pp["evidence_level"],
        "warning_count": pp["warning_count"],
        "citation_warnings": pp["citation_warnings"],
        "malformed_diagnostics_count": malformed_diagnostics_count,
    }


def _postprocess_answer(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    existing_citation_warnings: list[str] | None = None,
) -> _AnswerPostprocessResult:
    """Unified answer postprocessing lifecycle shared by both retrieval entry points.

    Centralises the full postprocessing contract so that
    :func:`run_retrieval_and_qa` and :func:`run_interactive_qa` cannot drift
    silently:

    1. Preserve *raw_answer* and compute *raw_answer_all_cited*.
    2. Attempt citation repair via :func:`_apply_citation_repair`.
    3. Apply the citation fallback via :func:`_build_citation_fallback`.
    4. Derive *all_cited* for the final delivered answer.
    5. Collect citation warnings (including the uncited-answer warning when
       applicable) and log the canonical warning message once.
    6. Derive *evidence_level* from *all_cited* and the combined warning list.
    7. Build the structured *citation_quality* bundle.

    Parameters
    ----------
    answer_text:
        Raw LLM answer text to postprocess.
    hits:
        Retrieved chunk hit dicts (each with a ``"metadata"`` key) as produced
        by the retrieval loop in both entry points.
    all_runs:
        When ``True``, citation repair is attempted via the all-runs heuristic.
    existing_citation_warnings:
        Citation-quality warnings already collected before postprocessing (e.g.
        empty-chunk-text warnings from the retrieval loop).  The returned
        ``citation_warnings`` list always begins with all elements of this list
        (in the same order), followed by any new warnings added during
        postprocessing.  The caller's list is never mutated.  May be ``None`` or
        empty.

    Returns
    -------
    _AnswerPostprocessResult
        A structured result with the following keys:

        - ``raw_answer`` — original LLM output before any repair or fallback.
        - ``raw_answer_all_cited`` — whether the raw answer was fully cited.
        - ``repaired_answer`` — answer text after citation repair (equals
          *raw_answer* when no repair was applied).
        - ``citation_repair_attempted`` — ``True`` when the preconditions for
          repair were met and repair logic was entered, regardless of whether
          repair ultimately changed the answer.  ``False`` when repair was not
          evaluated at all (e.g. not in all-runs mode, answer already cited,
          no hits available).
        - ``citation_repair_applied`` — ``True`` when repair actually modified
          the answer text (i.e. the repaired answer differs from the raw answer).
          ``False`` when repair was not attempted, was not needed, or produced no
          change.  This field reflects whether the *answer text changed*, not
          merely whether repair logic was invoked.
        - ``citation_repair_strategy`` — repair algorithm name when
          ``citation_repair_applied`` is ``True``, otherwise ``None``.
        - ``citation_repair_source_chunk_id`` — ``chunk_id`` of the retrieved
          chunk used for repair when ``citation_repair_applied`` is ``True``
          **and** the winning hit exposed a non-empty ``chunk_id``; ``None``
          when ``citation_repair_applied`` is ``False`` or when the winning hit
          had no ``chunk_id`` to propagate.
        - ``display_answer`` — final answer for display/return (includes the
          fallback prefix when not fully cited).
        - ``history_answer`` — sanitised answer for conversation history (bare
          refusal prefix when not fully cited).
        - ``citation_fallback_applied`` — ``True`` when the fallback prefix was
          applied.
        - ``all_cited`` — whether the *final delivered* answer is fully cited.
        - ``evidence_level`` — ``"no_answer"``, ``"full"``, or ``"degraded"``.
        - ``citation_warnings`` — combined list of citation-quality warnings
          (existing + any new ones added here).
        - ``warning_count`` — ``len(citation_warnings)``.
        - ``citation_quality`` — structured citation quality bundle dict.
    """
    raw_answer = answer_text
    raw_answer_all_cited = _check_all_answers_cited(raw_answer) if raw_answer.strip() else False

    repaired, citation_repair_attempted, citation_repair_applied, citation_repair_strategy, citation_repair_source_chunk_id = (
        _apply_citation_repair(
            answer_text,
            hits,
            all_runs=all_runs,
            raw_answer_all_cited=raw_answer_all_cited,
        )
    )

    repaired_stripped = repaired.strip()
    display_answer, history_answer, citation_fallback_applied = _build_citation_fallback(
        repaired_stripped
    )
    # Derive all_cited directly from the repaired answer text so citation
    # completeness semantics are independent of fallback behavior.
    all_cited = bool(repaired_stripped) and _check_all_answers_cited(repaired_stripped)

    citation_warnings: list[str] = list(existing_citation_warnings or [])
    if repaired_stripped and not all_cited:
        uncited_warning = "Not all answer sentences or bullets end with a citation token."
        _logger.warning(uncited_warning)
        citation_warnings.append(uncited_warning)

    # evidence_level encodes the overall quality of the retrieved evidence:
    #   "no_answer"  – no answer was generated (empty answer text)
    #   "full"       – every answer sentence/bullet ends with a citation token AND
    #                  no critical citation-quality warnings exist.
    #   "degraded"   – any answer sentence/bullet is missing a citation token, OR a
    #                  critical citation-quality warning exists (e.g. empty chunk text).
    evidence_level = (
        "no_answer"
        if not repaired_stripped
        else ("degraded" if (not all_cited or citation_warnings) else "full")
    )

    citation_quality: _CitationQualityBundle = {
        "all_cited": all_cited,
        "raw_answer_all_cited": raw_answer_all_cited,
        "evidence_level": evidence_level,
        "warning_count": len(citation_warnings),
        "citation_warnings": citation_warnings,
    }

    return {
        "raw_answer": raw_answer,
        "raw_answer_all_cited": raw_answer_all_cited,
        "repaired_answer": repaired,
        "citation_repair_attempted": citation_repair_attempted,
        "citation_repair_applied": citation_repair_applied,
        "citation_repair_strategy": citation_repair_strategy,
        "citation_repair_source_chunk_id": citation_repair_source_chunk_id,
        "display_answer": display_answer,
        "history_answer": history_answer,
        "citation_fallback_applied": citation_fallback_applied,
        "all_cited": all_cited,
        "evidence_level": evidence_level,
        "citation_warnings": citation_warnings,
        "warning_count": len(citation_warnings),
        "citation_quality": citation_quality,
    }


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


def _repair_uncited_answer(answer: str, first_citation_token: str) -> str:
    """Repair uncited answer segments by appending a citation token from retrieved context.

    Used in widened-scope (all-runs) retrieval to avoid the generic citation fallback
    when the LLM fails to attach a trailing citation token to some segments despite
    valid evidence being retrieved.  Only called when at least one retrieved chunk
    provides a usable citation token.

    Processing mirrors :func:`_check_all_answers_cited`:

    - Bullet lines (starting with ``-``, ``*``, ``•``, or a digit followed by ``.)``
      are treated as atomic units and have *first_citation_token* appended when uncited.
    - Paragraph lines are split into sentences by :data:`_SENTENCE_SPLIT_RE`; each
      uncited sentence receives *first_citation_token*.  Sentences that already carry a
      trailing token are left unchanged.

    The *first_citation_token* is the citation token from the first hit with a non-empty
    token value.  Applying the same token to all uncited segments is a pragmatic
    heuristic: it ensures citation compliance without requiring a per-sentence
    similarity lookup.  The ``raw_answer`` field in the result preserves the original
    LLM output for transparency regardless of any repair applied here.

    Returns:
        The repaired answer string, or *answer* unchanged when *answer* or
        *first_citation_token* is empty.
    """
    if not answer or not first_citation_token:
        return answer
    result_lines: list[str] = []
    for line in answer.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue
        if _BULLET_PREFIX_RE.match(stripped):
            # Bullet: single citation unit — append token when not already cited.
            if _TRAILING_CITATION_RE.search(stripped):
                result_lines.append(line)
            else:
                result_lines.append(f"{line} {first_citation_token}")
        else:
            # Paragraph: process sentence-by-sentence.
            parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(stripped) if p.strip()]
            if all(_TRAILING_CITATION_RE.search(p) for p in parts):
                # All sentences in this line are already cited; keep original.
                result_lines.append(line)
            else:
                repaired: list[str] = [
                    p if _TRAILING_CITATION_RE.search(p) else f"{p} {first_citation_token}"
                    for p in parts
                ]
                result_lines.append(" ".join(repaired))
    return "\n".join(result_lines)


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


def _format_cluster_context(
    cluster_memberships: list[dict[str, object]],
    cluster_canonical_alignments: list[dict[str, object]],
) -> str:
    """Format provisional cluster membership and alignment information for LLM context.

    Produces a human-readable section labelled as provisional inference so the LLM
    can distinguish cluster-derived entity hints from settled canonical identities.
    Membership status values control the rendered label:

    - ``"accepted"`` — deterministic assignment; rendered as ``Entity cluster (accepted)``.
    - ``"provisional"`` — high-confidence fuzzy match; rendered as ``PROVISIONAL CLUSTER``.
    - ``"candidate"`` — abbreviation/initialism match; rendered as ``CANDIDATE CLUSTER``
      to signal that the abbreviated form is ambiguous and requires review.
    - ``"review_required"`` — borderline fuzzy match; rendered as
      ``REVIEW REQUIRED CLUSTER`` to signal that the relationship needs verification.

    Canonical alignments via ``ALIGNED_WITH`` edges include alignment method and status
    so tentative alignments are clearly distinguishable.

    Duplicate membership/alignment entries (e.g. from multiple mentions in the same
    chunk pointing at the same cluster) are deduplicated before rendering so the per-
    chunk LLM context is not bloated with repeated lines.

    Returns an empty string when both input lists are empty or contain no usable entries.
    """
    lines: list[str] = []
    seen_memberships: set[tuple[str, str, str]] = set()
    for cm in cluster_memberships:
        cluster_name = cm.get("cluster_name") or cm.get("cluster_id") or ""
        method = cm.get("membership_method") or ""
        raw_status = cm.get("membership_status")
        status = (raw_status or "unknown").lower()
        dedup_key = (cluster_name, method, status)
        if dedup_key in seen_memberships:
            continue
        seen_memberships.add(dedup_key)
        if status == "accepted":
            lines.append(
                f"Entity cluster (accepted): '{cluster_name}' (membership via {method})"
            )
        elif status == "review_required":
            lines.append(
                f"REVIEW REQUIRED CLUSTER: '{cluster_name}' "
                f"(membership via {method}, status: review_required — "
                f"borderline match; requires human review before treating as confirmed)"
            )
        elif status == "candidate":
            lines.append(
                f"CANDIDATE CLUSTER: '{cluster_name}' "
                f"(membership via {method}, status: candidate — "
                f"abbreviated form match; identity is plausible but unconfirmed)"
            )
        elif status == "provisional":
            lines.append(
                f"PROVISIONAL CLUSTER: '{cluster_name}' "
                f"(membership via {method}, status: provisional — "
                f"identity not confirmed; treat as tentative, not a settled fact)"
            )
        else:
            display_status = raw_status or "unknown"
            lines.append(
                f"PROVISIONAL CLUSTER: '{cluster_name}' "
                f"(membership via {method}, status: {display_status} — "
                f"identity not confirmed; treat as tentative, not a settled fact)"
            )
    seen_alignments: set[tuple[str, str, str]] = set()
    for ca in cluster_canonical_alignments:
        canon_name = ca.get("canonical_name") or ""
        a_method = ca.get("alignment_method") or ""
        a_status = ca.get("alignment_status") or "unknown"
        dedup_key = (canon_name, a_method, a_status)
        if dedup_key in seen_alignments:
            continue
        seen_alignments.add(dedup_key)
        if a_status == "aligned":
            lines.append(
                f"Cluster aligned to canonical entity: '{canon_name}' (via {a_method})"
            )
        else:
            lines.append(
                f"PROVISIONAL ALIGNMENT to: '{canon_name}' "
                f"(via {a_method}, status: {a_status} — not yet confirmed)"
            )
    if not lines:
        return ""
    header = "[Cluster context — provisional inference; not primary evidence]"
    return header + "\n" + "\n".join(lines)


def _normalize_claim_roles(detail: dict[str, object]) -> list[dict[str, object]]:
    """Normalize claim role data from one detail record into a canonical list.

    Accepts the following input shapes for ``roles`` list entries:

    - Current canonical shape: ``{role, mention_name, match_method}``
    - Backward-compat shape: ``{role, name, match_method}`` — ``name`` is read
      when ``mention_name`` is absent, so data produced by older code paths or
      queries that project ``name`` instead of ``mention_name`` is handled
      transparently.
    - Legacy top-level keys: ``subject_mention`` / ``object_mention`` dicts
      (each with their own ``name`` and ``match_method`` fields) — used when no
      ``roles`` key is present at all.

    Malformed entries (``None``, non-dict, or missing ``role``) are silently
    filtered out so that downstream formatting and diagnostic code never crashes
    on partial payloads.

    Each entry in the returned list has the keys ``role``, ``mention_name``,
    and ``match_method``.  The list is sorted for deterministic output:
    ``subject`` first, ``object`` second, all other roles alphabetically, with
    ``mention_name`` and ``match_method`` as secondary tie-breakers.

    Parameters
    ----------
    detail:
        A single claim-detail record as returned by the retrieval Cypher query.

    Returns
    -------
    list[dict[str, object]]
        Canonical, sorted role entries for this claim.
    """
    roles_raw = detail.get("roles")
    if roles_raw is not None:
        roles: list[dict[str, object]] = []
        if isinstance(roles_raw, (list, tuple)):
            for entry in roles_raw:
                if not isinstance(entry, dict):
                    continue
                role = entry.get("role")
                if not role:
                    continue
                roles.append({
                    "role": role,
                    "mention_name": entry.get("mention_name", entry.get("name")),
                    "match_method": entry.get("match_method"),
                })
    else:
        # Backward compat: legacy ``subject_mention`` / ``object_mention`` keys.
        roles = []
        for role_key, role_name in (("subject_mention", "subject"), ("object_mention", "object")):
            slot = detail.get(role_key)
            if slot is not None and isinstance(slot, dict):
                roles.append({
                    "role": role_name,
                    "mention_name": slot.get("name"),
                    "match_method": slot.get("match_method"),
                })
    # Sort for deterministic output: subject first, object second, rest alphabetically,
    # with mention_name and match_method as tie-breakers for stable ordering within the same role.
    roles.sort(
        key=lambda e: (
            0 if e.get("role") == "subject" else 1 if e.get("role") == "object" else 2,
            str(e.get("role") or ""),
            str(e.get("mention_name") or ""),
            str(e.get("match_method") or ""),
        )
    )
    return roles


def _format_claim_details(claim_details: list[dict[str, object]]) -> str:
    """Format structured claim details (with explicit role mentions) for LLM context.

    For each claim, renders the claim text together with all explicitly matched
    participant mentions reached via ``HAS_PARTICIPANT {role}`` participation edges
    (v0.3 model).  Roles are taken from the ``roles`` list in each claim detail;
    the legacy ``subject_mention`` / ``object_mention`` keys are also supported for
    backward compatibility with older stored metadata.  When a claim has no
    participation edges the claim text is still included without role annotations.

    The section is labelled so the LLM can treat the explicit role assignments as
    first-class evidence rather than positional guesses.

    Returns an empty string when *claim_details* is empty or contains no claim text.
    """
    if not claim_details:
        return ""
    lines: list[str] = []
    for detail in claim_details:
        claim_text = (detail.get("claim_text") or "").strip()
        if not claim_text:
            continue
        roles_list = _normalize_claim_roles(detail)
        role_parts: list[str] = []
        for entry in roles_list:
            role_name = str(entry.get("role") or "").strip()
            mention_name = str(entry.get("mention_name") or "").strip()
            method_raw = entry.get("match_method")
            method = str(method_raw).strip() if method_raw is not None else ""
            method_display = method if method else "unknown"
            if role_name and mention_name:
                role_parts.append(f"{role_name}='{mention_name}' (match: {method_display})")
        if role_parts:
            lines.append(f"  • {claim_text} [{', '.join(role_parts)}]")
        else:
            lines.append(f"  • {claim_text}")
    if not lines:
        return ""
    header = "[Claim context — explicit roles via participation edges]"
    return header + "\n" + "\n".join(lines)


def _build_retrieval_path_diagnostics(
    *,
    claim_details: list[dict[str, object]],
    canonical_entities: list[str],
    cluster_memberships: list[dict[str, object]],
    cluster_canonical_alignments: list[dict[str, object]],
) -> dict[str, object]:
    """Build structured retrieval-path diagnostics from already-available metadata fields.

    Consolidates all graph-traversal provenance for a single retrieved Chunk into a
    single, inspectable dict so callers can audit the exact paths that contributed to
    the retrieved context without re-querying the graph.  This function is a pure
    transformation of data already present in the formatter input; it does **not**
    alter semantics, content, or citation tokens.

    Parameters
    ----------
    claim_details:
        Structured claim records from the ``claim_details`` query column.  Each entry
        carries ``claim_text`` and either a ``roles`` list (new generic format, each
        entry is ``{role, mention_name, match_method}``) or legacy ``subject_mention`` /
        ``object_mention`` dicts (backward-compatible fallback).
    canonical_entities:
        List of canonical entity names reached via
        ``EntityMention -[:RESOLVES_TO]-> CanonicalEntity``.
    cluster_memberships:
        Per-membership provenance records from the ``cluster_memberships`` query column.
        Each entry has ``cluster_id``, ``cluster_name``, ``membership_status``, and
        ``membership_method``.
    cluster_canonical_alignments:
        Per-alignment provenance records from the ``cluster_canonical_alignments`` query
        column.  Each entry has ``canonical_name``, ``alignment_method``, and
        ``alignment_status`` (reached via ``cluster -[:ALIGNED_WITH]-> CanonicalEntity``).

    Returns
    -------
    dict
        Keys:

        - ``has_participant_edges``: list of ``{claim_text, roles}`` dicts.  Each
          ``roles`` entry is ``{role, mention_name, match_method}`` for a resolved
          ``HAS_PARTICIPANT`` edge.  Claims with no participation edges have an empty
          ``roles`` list.
        - ``canonical_via_resolves_to``: list of canonical entity name strings reached
          via the ``RESOLVES_TO`` relationship.
        - ``cluster_memberships``: copy of the input membership records.
        - ``cluster_canonical_via_aligned_with``: copy of the alignment records (path
          via ``MEMBER_OF`` → ``ALIGNED_WITH``).
    """
    has_participant_edges: list[dict[str, object]] = []
    for detail in claim_details:
        claim_text = (detail.get("claim_text") or "").strip()
        if not claim_text:
            continue
        roles = _normalize_claim_roles(detail)
        has_participant_edges.append({"claim_text": claim_text, "roles": roles})
    return {
        "has_participant_edges": has_participant_edges,
        "canonical_via_resolves_to": list(canonical_entities),
        "cluster_memberships": list(cluster_memberships),
        "cluster_canonical_via_aligned_with": list(cluster_canonical_alignments),
    }


def _format_retrieval_path_summary(hits: list[dict[str, object]]) -> str:
    """Format a human-readable retrieval-path summary across all retrieved hits.

    Iterates over *hits* (as produced by ``run_retrieval_and_qa``) and renders each
    chunk's ``retrieval_path_diagnostics`` metadata into a structured text block
    suitable for debug output, logging, or evaluation inspection.

    Each hit section shows:

    - Chunk identity (``chunk_id``) and similarity ``score``.
    - **HAS_PARTICIPANT edges**: per-claim role assignments resolved via participation
      edges.  Claims without any resolved participation edges are listed as
      ``[no resolved roles]``.
    - **RESOLVES_TO canonical entities**: entity names reached directly from an
      ``EntityMention`` via ``RESOLVES_TO``.
    - **Cluster memberships (MEMBER_OF)**: cluster identity and membership provenance.
    - **Canonical via ALIGNED_WITH**: canonical entities reached transitively via
      ``cluster -[:ALIGNED_WITH]->``, including alignment method and status.

    In base-retrieval mode (no graph expansion), ``retrieval_path_diagnostics`` is
    still present in the metadata but contains empty lists; in that case a brief note
    is shown in place of detailed graph-expansion diagnostics.

    Parameters
    ----------
    hits:
        List of hit dicts as stored in the ``retrieval_results`` field of the
        ``run_retrieval_and_qa`` return value.  Each dict must have a ``"metadata"``
        key containing the chunk metadata produced by ``_chunk_citation_formatter``.

    Returns
    -------
    str
        Multi-line summary string, or an empty string when *hits* is empty.
    """
    if not hits:
        return ""
    lines: list[str] = ["=== Retrieval Path Summary ==="]
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata") or {}
        chunk_id = meta.get("chunk_id") or "(unknown)"
        score = meta.get("score")
        try:
            score_str = f"{float(score):.4f}"
        except (TypeError, ValueError):
            score_str = str(score)
        lines.append(f"\nHit {i}: chunk_id={chunk_id!r}  score={score_str}")

        diag = meta.get("retrieval_path_diagnostics")
        if "retrieval_path_diagnostics" not in meta or diag is None:
            lines.append("  (no retrieval-path diagnostics available — older result format)")
            continue

        if not isinstance(diag, dict):
            lines.append(f"  (malformed retrieval-path diagnostics: expected dict, got {type(diag).__name__!r})")
            continue

        # HAS_PARTICIPANT edges (from claim_details)
        _raw_hp = diag.get("has_participant_edges")
        if isinstance(_raw_hp, list):
            hp_edges: list[object] = _raw_hp
        else:
            if _raw_hp is not None:
                lines.append(f"  (malformed has_participant_edges: expected list, got {type(_raw_hp).__name__!r} — skipped)")
            hp_edges = []
        if hp_edges:
            lines.append("  HAS_PARTICIPANT edges (claims with participation):")
            for entry in hp_edges:
                if not isinstance(entry, dict):
                    lines.append(f"    • (malformed entry: {entry!r})")
                    continue
                claim_text = str(entry.get("claim_text") or "")
                _raw_roles = entry.get("roles")
                if isinstance(_raw_roles, list):
                    roles: list[object] = _raw_roles
                else:
                    roles = []
                    if _raw_roles is not None:
                        role_parts_list = [f"(malformed roles: {_raw_roles!r})"]
                        preview = claim_text[:80] + ("..." if len(claim_text) > 80 else "")
                        lines.append(f"    • \"{preview}\" [{', '.join(role_parts_list)}]")
                        continue
                role_parts_list: list[str] = []
                for r in roles:
                    if not isinstance(r, dict):
                        role_parts_list.append(f"(malformed: {r!r})")
                        continue
                    r_role = r.get("role") or "(unknown)"
                    r_mention = r.get("mention_name") or "(unknown)"
                    r_method = r.get("match_method") or "(unknown)"
                    role_parts_list.append(f"{r_role}={r_mention!r} (match: {r_method})")
                role_parts = ", ".join(role_parts_list)
                preview = claim_text[:80] + ("..." if len(claim_text) > 80 else "")
                if role_parts:
                    lines.append(f"    • \"{preview}\" [{role_parts}]")
                else:
                    lines.append(f"    • \"{preview}\" [no resolved roles]")
        else:
            lines.append("  HAS_PARTICIPANT edges: (none)")

        # RESOLVES_TO canonical entities
        _raw_rt = diag.get("canonical_via_resolves_to")
        if isinstance(_raw_rt, list):
            resolves_to: list[object] = _raw_rt
        else:
            if _raw_rt is not None:
                lines.append(f"  (malformed canonical_via_resolves_to: expected list, got {type(_raw_rt).__name__!r} — skipped)")
            resolves_to = []
        if resolves_to:
            lines.append(f"  RESOLVES_TO canonical entities: {resolves_to!r}")
        else:
            lines.append("  RESOLVES_TO canonical entities: (none)")

        # Cluster memberships (MEMBER_OF)
        _raw_mem = diag.get("cluster_memberships")
        if isinstance(_raw_mem, list):
            memberships: list[object] = _raw_mem
        else:
            if _raw_mem is not None:
                lines.append(f"  (malformed cluster_memberships: expected list, got {type(_raw_mem).__name__!r} — skipped)")
            memberships = []
        if memberships:
            lines.append("  Cluster memberships (MEMBER_OF):")
            for m in memberships:
                if not isinstance(m, dict):
                    lines.append(f"    • (malformed entry: {m!r})")
                    continue
                c_name = m.get("cluster_name") or m.get("cluster_id") or ""
                c_status = m.get("membership_status") or "unknown"
                c_method = m.get("membership_method") or ""
                lines.append(f"    • cluster={c_name!r}  status={c_status}  method={c_method}")
        else:
            lines.append("  Cluster memberships (MEMBER_OF): (none)")

        # Canonical alignments (ALIGNED_WITH)
        _raw_al = diag.get("cluster_canonical_via_aligned_with")
        if isinstance(_raw_al, list):
            alignments: list[object] = _raw_al
        else:
            if _raw_al is not None:
                lines.append(f"  (malformed cluster_canonical_via_aligned_with: expected list, got {type(_raw_al).__name__!r} — skipped)")
            alignments = []
        if alignments:
            lines.append("  Canonical via ALIGNED_WITH:")
            for a in alignments:
                if not isinstance(a, dict):
                    lines.append(f"    • (malformed entry: {a!r})")
                    continue
                canon_name = a.get("canonical_name") or ""
                a_method = a.get("alignment_method") or ""
                a_status = a.get("alignment_status") or ""
                lines.append(f"    • canonical={canon_name!r}  method={a_method}  status={a_status}")
        else:
            lines.append("  Canonical via ALIGNED_WITH: (none)")
    return "\n".join(lines)


def _count_malformed_diagnostics(hits: list[dict[str, object]]) -> int:
    """Return the number of hits that contain malformed retrieval-path diagnostics payloads.

    A hit is counted (at most once regardless of how many sub-field errors it has)
    when its ``retrieval_path_diagnostics`` value is **present and not ``None``** but
    fails any of the structural checks performed by
    :func:`_format_retrieval_path_summary`:

    - The root value is not a ``dict``.
    - Any known list field (``has_participant_edges``,
      ``canonical_via_resolves_to``, ``cluster_memberships``,
      ``cluster_canonical_via_aligned_with``) is present and not ``None`` but
      not a ``list``.
    - Any entry in ``has_participant_edges`` or ``cluster_memberships`` or
      ``cluster_canonical_via_aligned_with`` is not a ``dict``.
    - Any ``roles`` entry within a ``has_participant_edges`` element is present
      and not ``None`` but not a ``list``, or contains a non-``dict`` item.

    Hits where ``retrieval_path_diagnostics`` is absent or ``None`` are **not**
    counted — they represent an older result format rather than a data error.

    Parameters
    ----------
    hits:
        List of hit dicts as stored in the ``retrieval_results`` field of the
        ``run_retrieval_and_qa`` return value.

    Returns
    -------
    int
        Count of hits with at least one malformed diagnostics condition.
        Zero when all hits have well-formed (or absent/``None``) diagnostics.
    """
    count = 0
    for hit in hits:
        meta = hit.get("metadata") or {}
        if "retrieval_path_diagnostics" not in meta:
            continue
        diag = meta["retrieval_path_diagnostics"]
        if diag is None:
            continue
        if not isinstance(diag, dict):
            count += 1
            continue
        if _diagnostics_dict_has_malformed_fields(diag):
            count += 1
    return count


def _diagnostics_dict_has_malformed_fields(diag: dict[str, object]) -> bool:
    """Return ``True`` if *diag* contains any structurally malformed sub-field.

    Mirrors the type checks performed by :func:`_format_retrieval_path_summary`
    so that :func:`_count_malformed_diagnostics` stays aligned with the formatter
    without duplicating the full rendering logic.
    """
    # Check that known list fields are actually lists when present.
    _list_fields = (
        "has_participant_edges",
        "canonical_via_resolves_to",
        "cluster_memberships",
        "cluster_canonical_via_aligned_with",
    )
    for field in _list_fields:
        val = diag.get(field)
        if val is not None and not isinstance(val, list):
            return True

    # Check that entries in list fields that iterate as dicts are actually dicts.
    _dict_entry_fields = (
        "has_participant_edges",
        "cluster_memberships",
        "cluster_canonical_via_aligned_with",
    )
    for field in _dict_entry_fields:
        val = diag.get(field)
        if not isinstance(val, list):
            continue
        for entry in val:
            if not isinstance(entry, dict):
                return True
            # For HAS_PARTICIPANT edges, also check the nested roles list.
            if field == "has_participant_edges":
                roles = entry.get("roles")
                if roles is not None and not isinstance(roles, list):
                    return True
                if isinstance(roles, list):
                    for role in roles:
                        if not isinstance(role, dict):
                            return True
    return False


def _chunk_citation_formatter(record: neo4j.Record) -> RetrieverResultItem:
    """Format a retrieved Chunk record into a RetrieverResultItem with a stable citation token.

    Follows the vendor result_formatter pattern from:
    vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py

    The returned item embeds the citation token in the content string (for prompt context)
    and preserves all citation-relevant fields in metadata (for downstream citation mapping).

    When the graph-expanded retrieval query was used, structured claim details (including
    explicit participant mention names and match methods via HAS_PARTICIPANT {role}
    participation edges) are appended to the content so the LLM can reason about claim
    roles precisely. The claim context section appears when claim_details include claim
    text; role annotations are shown for every resolved participation edge (subject, object,
    or any future role); no fallback to chunk co-location heuristics is used.

    When the cluster-aware retrieval query was used, provisional cluster membership and
    alignment context is appended to the content string so the LLM can distinguish between
    settled entity identities and provisional cluster hypotheses.  Citations always reference
    the underlying Chunk, not the cluster node.
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

    # Build claim context section when the graph-expanded query returned claim_details.
    # Explicit role mentions (via HAS_PARTICIPANT {role} edges) are surfaced so the LLM
    # can reason about claim roles precisely.  When no participation edges exist for a
    # claim the roles list is empty (roles: []) — no chunk co-location fallback is applied.
    claim_details_raw = record.get("claim_details")
    claim_details: list[dict[str, object]] = list(claim_details_raw) if claim_details_raw is not None else []
    claim_context = _format_claim_details(claim_details)

    # Build cluster context section when the cluster-aware query returned cluster fields.
    # Provisional cluster membership and alignment are appended to the content so the LLM
    # can reason about tentative identity inference without treating it as settled evidence.
    cluster_memberships: list[dict[str, object]] = list(record.get("cluster_memberships") or [])
    cluster_canonical_alignments: list[dict[str, object]] = list(record.get("cluster_canonical_alignments") or [])
    cluster_context = _format_cluster_context(cluster_memberships, cluster_canonical_alignments)

    # Embed citation token (and optional claim/cluster context) in content so prompt context
    # is self-documenting.  The citation token always trails the content block.
    content_parts = [chunk_text]
    if claim_context:
        content_parts.append(claim_context)
    if cluster_context:
        content_parts.append(cluster_context)
    content_parts.append(citation_token)
    content = "\n".join(content_parts)

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
    # Include claim_details when the expanded retrieval query was used (v0.3 participation edges).
    if claim_details_raw is not None:
        metadata["claim_details"] = claim_details
    # Include cluster fields when the cluster-aware retrieval query was used.
    for field in ("cluster_memberships", "cluster_canonical_alignments"):
        value = record.get(field)
        if value is not None:
            metadata[field] = value
    # Build structured retrieval-path diagnostics so callers can audit graph-traversal
    # provenance per chunk without re-querying.  Purely additive — does not alter
    # content, semantics, or citation tokens.
    canonical_entities_raw = record.get("canonical_entities")
    canonical_entities_list: list[str] = (
        [str(v) for v in canonical_entities_raw]
        if canonical_entities_raw is not None
        else []
    )
    metadata["retrieval_path_diagnostics"] = _build_retrieval_path_diagnostics(
        claim_details=claim_details,
        canonical_entities=canonical_entities_list,
        cluster_memberships=cluster_memberships,
        cluster_canonical_alignments=cluster_canonical_alignments,
    )

    return RetrieverResultItem(content=content, metadata=metadata)


def _build_retriever_and_rag(
    driver: neo4j.Driver,
    *,
    index_name: str,
    retrieval_query: str,
    qa_model: str,
    neo4j_database: str | None,
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
    embedder = build_embedder_for_settings(
        AppSettings(
            neo4j=Neo4jSettings(),
            openai_model=qa_model,
            embedder_model=_pipeline_contract_value("EMBEDDER_MODEL_NAME"),
        ),
        embedder_factory=OpenAIEmbeddings,
    )
    retriever = VectorCypherRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        retrieval_query=retrieval_query,
        result_formatter=_chunk_citation_formatter,
        neo4j_database=neo4j_database,
    )
    llm = build_openai_llm(qa_model)
    rag = GraphRAG(
        retriever=retriever,
        llm=llm,
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
    return run_retrieval_and_qa(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        top_k=top_k,
        index_name=index_name or request_context.pipeline_contract.chunk_embedding_index_name,
        question=question if question is not None else getattr(request_context.config, "question", None),
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        message_history=message_history,
        interactive=interactive,
        all_runs=request_context.all_runs,
    )


def run_retrieval_and_qa(
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
    """
    resolved_index_name = index_name if index_name is not None else _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME")
    qa_model = getattr(config, "openai_model", None)
    # effective_qa_model is the model that will actually be used for generation; it
    # includes the fallback default so the manifest always reflects the true model.
    effective_qa_model = qa_model or "gpt-5.4"
    qa_prompt_version = PROMPT_IDS["qa"]

    # Use provided run_id/source_uri in citation examples so provenance fields align with stage metadata;
    # fall back to the active dataset's PDF URI, or a placeholder when dataset resolution is ambiguous.
    citation_run_id = run_id if run_id is not None else "example_run_id"
    if source_uri is not None:
        citation_source_uri = source_uri
    else:
        try:
            citation_source_uri = resolve_dataset_root().pdf_path.resolve().as_uri()
        except AmbiguousDatasetError:
            citation_source_uri = "placeholder://citation-source"

    citation_token_example = _build_citation_token(
        chunk_id="example_chunk",
        run_id=citation_run_id,
        source_uri=citation_source_uri,
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=999,
    )
    # cluster_aware implies expansion (clusters are reached via entity mention traversal).
    # The retrieval query selection priority: cluster_aware > expand_graph > base.
    # effective_expand_graph records whether any form of graph expansion is active so
    # manifests accurately describe the retrieval context used.
    effective_expand_graph = expand_graph or cluster_aware
    retrieval_query_contract = _select_runtime_retrieval_query(
        expand_graph=expand_graph, cluster_aware=cluster_aware, all_runs=all_runs
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
    # raw_answer_all_cited reflects whether the raw LLM output (before any repair or fallback)
    # was fully cited; all_cited reflects the final delivered answer after repair+fallback.
    _default_citation_quality: dict[str, object] = {
        "all_cited": False,
        "raw_answer_all_cited": False,
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
        # all_answers_cited reflects the FINAL delivered answer citation state (after any
        # repair or fallback).  See raw_answer_all_cited for the raw LLM output state.
        "all_answers_cited": False,
        # raw_answer_all_cited reflects whether the original LLM output (raw_answer) was
        # fully cited before any repair or fallback was applied.  False when the LLM
        # omitted citation tokens on some segments; True when all segments were already cited.
        "raw_answer_all_cited": False,
        # citation_repair_attempted is True when the preconditions for repair evaluation
        # were met (all_runs=True, non-empty answer, hits available, answer not already
        # cited) and repair logic was entered.
        "citation_repair_attempted": False,
        # citation_repair_applied is True when the all-runs repair heuristic appended a
        # retrieved citation token to one or more uncited answer segments.
        "citation_repair_applied": False,
        # citation_repair_strategy names the repair algorithm used, or None when no repair
        # was applied.  Currently the only strategy is "append_first_retrieved_token".
        "citation_repair_strategy": None,
        # citation_repair_source_chunk_id is the chunk_id of the retrieved context chunk
        # whose citation token was appended during repair, or None when no repair was applied.
        "citation_repair_source_chunk_id": None,
        "citation_quality": _default_citation_quality,
        "expand_graph": effective_expand_graph,
        "cluster_aware": cluster_aware,
        "retrieval_scope": retrieval_scope,
        "citation_token_example": citation_token_example,
        "citation_object_example": citation_object_example,
        # citation_example is retained for backward compatibility with existing manifest consumers
        "citation_example": citation_object_example,
        "retrieval_query_contract": retrieval_query_contract.strip(),
        "interactive_mode": interactive,
        "message_history_enabled": message_history is not None,
        # retrieval_path_summary is populated with the formatted path diagnostics after
        # retrieval completes; the empty-string default is used for dry-run and
        # no-question paths where no retrieval actually ran.
        "retrieval_path_summary": "",
        # malformed_diagnostics_count counts hits whose retrieval_path_diagnostics
        # payload failed any structural check during formatting.  Zero in base (no
        # retrieval ran yet); overridden with the actual count in the live result.
        "malformed_diagnostics_count": 0,
        # debug_view provides the typed inspection surface populated from the
        # postprocessing result.  Defaults to all-zero values in early-return paths
        # where no retrieval or postprocessing ran; overridden in the live result.
        "debug_view": {
            "raw_answer_all_cited": False,
            "all_cited": False,
            "citation_repair_attempted": False,
            "citation_repair_applied": False,
            "citation_fallback_applied": False,
            "evidence_level": "no_answer",
            "warning_count": 0,
            "citation_warnings": [],
            "malformed_diagnostics_count": 0,
        },
    }
    # Resolve which (if any) early-return rule applies.
    # EARLY_RETURN_PRECEDENCE is the single authoritative ordering source; the
    # resolver evaluates conditions in that order so that mixed inputs
    # (e.g. dry_run=True and question=None simultaneously) always produce the
    # correct winning branch without duplicating precedence in manual if-chains.
    # Precedence contract: src/power_atlas/contracts/retrieval_early_return_policy.py
    # Contract doc: docs/architecture/retrieval-citation-result-contract-v0.1.md §5
    _early_rule = resolve_early_return_rule(
        is_dry_run=getattr(config, "dry_run", False),
        question=question,
    )
    if _early_rule is not None:
        if _early_rule.name == "dry_run":
            # §5.1 — dry_run early return.
            dry_run_retrievers: list[str] = ["VectorCypherRetriever"]
            if cluster_aware:
                dry_run_retrievers += ["graph expansion", "cluster traversal"]
            elif expand_graph:
                dry_run_retrievers.append("graph expansion")
            dry_run_qa_label = "GraphRAG all-runs citations" if all_runs else "GraphRAG run-scoped citations"
            return {
                **base,
                "status": "dry_run",
                "retrievers": dry_run_retrievers,
                "qa": dry_run_qa_label,
            }
        elif _early_rule.name == "retrieval_skipped":
            # §5.2 — retrieval_skipped early return.
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
        else:
            # Guard against future rules added to EARLY_RETURN_PRECEDENCE without
            # a corresponding branch here.  resolve_early_return_rule() already
            # raises if the _conditions dict is missing a rule name, but this
            # else-raise catches the symmetric gap: a rule whose condition fires
            # but whose payload is not yet implemented in this block.
            raise RuntimeError(
                f"run_retrieval_and_qa: matched early-return rule {_early_rule.name!r} "
                "has no corresponding payload branch.  Add a branch for this rule."
            )

    # Live retrieval: build a VectorCypherRetriever with citation formatter.
    # run_id is mandatory unless all_runs=True (which queries across all chunks).
    if not all_runs and run_id is None:
        raise ValueError(
            "run_id is required for live retrieval. "
            "Pass --run-id, --latest, or use --all-runs to query across all data."
        )

    retrieval_query = _select_runtime_retrieval_query(
        expand_graph=expand_graph, cluster_aware=cluster_aware, all_runs=all_runs
    )

    # Query params for filtering. source_uri=None is valid: the null-conditional
    # in the WHERE clause skips source_uri filtering when the parameter is None.
    # run_id is only included for run-scoped queries (not all-runs mode).
    # alignment_version is passed when cluster_aware=True to filter ALIGNED_WITH edges
    # to the current alignment generation only.
    query_params = _build_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
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

    require_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live retrieval."
    )

    neo4j_uri = getattr(config, "neo4j_uri", None)
    neo4j_username = getattr(config, "neo4j_username", None)
    neo4j_password = getattr(config, "neo4j_password", None)
    neo4j_database = getattr(config, "neo4j_database", None)

    missing_cfg = [k for k, v in (("neo4j_uri", neo4j_uri), ("neo4j_username", neo4j_username), ("neo4j_password", neo4j_password)) if not v]
    if missing_cfg:
        raise ValueError(f"Live retrieval requires config attributes: {', '.join(missing_cfg)}")

    with create_neo4j_driver(
        Neo4jSettings(
            uri=neo4j_uri,
            username=neo4j_username,
            password=neo4j_password,
            database=neo4j_database,
        )
    ) as driver:
        # Build GraphRAG with the Power Atlas citation-enforcing prompt template and
        # capability-aware LLM for grounded, citation-enforced output.
        # Aligned with vendor pattern from vendor-resources/examples/customize/answer/custom_prompt.py
        # and vendor-resources/examples/question_answering/graphrag_with_neo4j_message_history.py.
        _, rag = _build_retriever_and_rag(
            driver,
            index_name=resolved_index_name,
            retrieval_query=retrieval_query,
            qa_model=effective_qa_model,
            neo4j_database=neo4j_database,
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
                # ── Stage 1: retrieval-time OPERATIONAL warnings ─────────────────
                # Missing optional fields (page, start_char, end_char) are surfaced
                # to warnings_list only.  They are NOT added to citation_warnings_list
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
                    # Operational warning: top-level only, NOT a citation-quality issue.
                    warnings_list.append(chunk_warning)
                # ── Stage 2: retrieval-time CITATION-QUALITY warnings ────────────
                # Empty/whitespace-only chunk text is a citation-quality issue: the
                # cited chunk carries no usable evidence.  Added to both surfaces so
                # the invariant (citation_warnings ⊆ warnings) is maintained.
                if meta.get("empty_chunk_text"):
                    chunk_id_val = citation_obj.get("chunk_id")
                    empty_text_warning = f"Chunk {chunk_id_val!r} has empty or whitespace-only text."
                    warnings_list.append(empty_text_warning)           # superset
                    citation_warnings_list.append(empty_text_warning)  # citation-quality subset
                hits.append({"content": item.content, "metadata": meta})

    # ── Stage 3: postprocessing — may add MORE citation-quality warnings ─────
    # Pass the retrieval-time citation warnings into _postprocess_answer() so the
    # helper can derive an updated list of citation warnings (e.g. by appending
    # an uncited-answer warning) without mutating the input list.
    # The helper guarantees that the returned citation_warnings list is a new list
    # whose initial elements are exactly existing_citation_warnings, in the same order.
    # evidence quality bundle — computed via the shared helper so single-shot and
    # interactive paths cannot drift silently.
    _n_retrieval_citation_warnings = len(citation_warnings_list)
    pp = _postprocess_answer(
        answer_text,
        hits,
        all_runs=all_runs,
        existing_citation_warnings=citation_warnings_list,
    )

    # ── Stage 4: propagate postprocessing-added citation warnings upward ─────
    # pp["citation_warnings"] starts with all retrieval-time citation warnings,
    # so slicing at _n_retrieval_citation_warnings yields only the warnings that
    # _postprocess_answer() added (e.g. the uncited-answer warning).  Each is
    # appended to warnings_list so the superset invariant is maintained.
    for w in pp["citation_warnings"][_n_retrieval_citation_warnings:]:
        warnings_list.append(w)
    if pp["citation_fallback_applied"]:
        display = pp["display_answer"]
        fallback_preview = (
            display[:_FALLBACK_PREVIEW_MAX_LEN] + "..."
            if len(display) > _FALLBACK_PREVIEW_MAX_LEN
            else display
        )
        _logger.warning(
            "Answer replaced with citation fallback (length=%d, preview=%r)",
            len(display),
            fallback_preview,
        )

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

    live_retrievers: list[str] = ["VectorCypherRetriever"]
    if cluster_aware:
        live_retrievers += ["graph expansion", "cluster traversal"]
    elif expand_graph:
        live_retrievers.append("graph expansion")
    qa_scope_label = "GraphRAG all-runs citations" if all_runs else "GraphRAG run-scoped citations"
    _malformed_count = _count_malformed_diagnostics(hits)
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
        **_project_postprocess_to_public(pp),
        "retrieval_path_summary": _format_retrieval_path_summary(hits),
        "malformed_diagnostics_count": _malformed_count,
        # Build the typed inspection view from the postprocess result and the malformed
        # count so the single-shot path surfaces the same inspection model as the
        # interactive path, preventing silent drift between the two.
        "debug_view": _build_retrieval_debug_view(pp, malformed_diagnostics_count=_malformed_count),
    }


def _format_postprocess_debug_summary(view: _RetrievalDebugView) -> str:
    """Format a compact postprocessing debug summary line from a retrieval debug view.

    Intended for opt-in debug output in :func:`run_interactive_qa` when
    *debug=True*.  All values are read from the shared :class:`_RetrievalDebugView`
    contract so the debug surface cannot drift from the underlying postprocessing
    semantics.  Callers must first build the view via
    :func:`_build_retrieval_debug_view`.

    Parameters
    ----------
    view:
        Typed inspection view built by :func:`_build_retrieval_debug_view`.

    Returns
    -------
    str
        A human-readable single-line summary (plus an optional second line for
        warning details when ``warning_count > 0``).
    """
    parts = [
        f"raw_cited={view['raw_answer_all_cited']}",
        f"final_cited={view['all_cited']}",
        f"repair_applied={view['citation_repair_applied']}",
        f"fallback_applied={view['citation_fallback_applied']}",
        f"evidence={view['evidence_level']}",
        f"warnings={view['warning_count']}",
        f"malformed_diagnostics={view['malformed_diagnostics_count']}",
    ]
    summary = "[debug] " + " | ".join(parts)
    if view["citation_warnings"]:
        warning_details = "; ".join(view["citation_warnings"])
        summary += f"\n[debug] warning_details: {warning_details}"
    return summary


def run_interactive_qa(
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
    """
    # Validate and resolve session-level config once before opening any connections.
    if not all_runs and run_id is None:
        raise ValueError(
            "run_id is required for interactive retrieval. "
            "Pass run_id, or set all_runs=True to query across all data."
        )

    require_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live retrieval."
    )

    neo4j_uri = getattr(config, "neo4j_uri", None)
    neo4j_username = getattr(config, "neo4j_username", None)
    neo4j_password = getattr(config, "neo4j_password", None)
    neo4j_database = getattr(config, "neo4j_database", None)

    missing_cfg = [k for k, v in (("neo4j_uri", neo4j_uri), ("neo4j_username", neo4j_username), ("neo4j_password", neo4j_password)) if not v]
    if missing_cfg:
        raise ValueError(f"Live retrieval requires config attributes: {', '.join(missing_cfg)}")

    resolved_index_name = index_name if index_name is not None else _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME")
    effective_qa_model = getattr(config, "openai_model", None) or "gpt-5.4"
    retrieval_query = _select_runtime_retrieval_query(
        expand_graph=expand_graph, cluster_aware=cluster_aware, all_runs=all_runs
    )
    query_params = _build_query_params(
        run_id=run_id,
        source_uri=source_uri,
        all_runs=all_runs,
        cluster_aware=cluster_aware,
    )

    history: MessageHistory = InMemoryMessageHistory()
    print(f"Using retrieval scope: {_format_scope_label(run_id, all_runs)}")
    print("Power Atlas interactive Q&A (type 'exit'/'quit' or Ctrl-D to stop)\n")

    # Build driver, retriever, LLM, and GraphRAG once and reuse across all REPL turns
    # to avoid per-turn connection overhead and Neo4j driver churn.
    with create_neo4j_driver(
        Neo4jSettings(
            uri=neo4j_uri,
            username=neo4j_username,
            password=neo4j_password,
            database=neo4j_database,
        )
    ) as driver:
        _, rag = _build_retriever_and_rag(
            driver,
            index_name=resolved_index_name,
            retrieval_query=retrieval_query,
            qa_model=effective_qa_model,
            neo4j_database=neo4j_database,
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
                # Build repair hits from retriever result items (empty list when no
                # retriever result is available — _postprocess_answer handles this).
                _repair_hits: list[dict[str, object]] = []
                if rag_result and rag_result.retriever_result:
                    _repair_hits = [
                        {"metadata": item.metadata or {}}
                        for item in rag_result.retriever_result.items
                    ]
                # Unified postprocessing: repair, fallback, warnings, and citation quality
                # via the shared helper so this path stays aligned with run_retrieval_and_qa.
                pp = _postprocess_answer(answer, _repair_hits, all_runs=all_runs)
                print(f"\nAnswer:\n{pp['display_answer']}\n")
                if pp["citation_fallback_applied"]:
                    print(
                        "WARNING: Not all answer sentences or bullets are cited - evidence quality may be degraded."
                    )
                if debug:
                    # Build the typed inspection view from the postprocess result so
                    # that debug rendering consumes the shared model rather than reading
                    # _AnswerPostprocessResult fields directly.
                    debug_view = _build_retrieval_debug_view(
                        pp,
                        malformed_diagnostics_count=_count_malformed_diagnostics(_repair_hits),
                    )
                    print(_format_postprocess_debug_summary(debug_view))
                # Store only the refusal prefix (not the full uncited output) in history
                # so that subsequent turns are not conditioned on under-cited content.
                # The full fallback text is still printed to the user above.
                history.add_messages(
                    [
                        LLMMessage(role="user", content=question),
                        LLMMessage(role="assistant", content=pp["history_answer"]),
                    ]
                )
        except KeyboardInterrupt:
            print()


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
    return run_interactive_qa(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        top_k=top_k,
        index_name=index_name or request_context.pipeline_contract.chunk_embedding_index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=request_context.all_runs if all_runs is None else all_runs,
        debug=debug,
    )


__all__ = [
    "run_retrieval_and_qa",
    "run_retrieval_and_qa_request_context",
    "run_interactive_qa",
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

