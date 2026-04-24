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
    resolve_early_return_rule,
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
from power_atlas.retrieval_query_builders import _select_runtime_retrieval_query
from power_atlas.retrieval_interactive_session import run_interactive_session_loop
from power_atlas.retrieval_request_helpers import build_retrieval_query_params
from power_atlas.retrieval_request_helpers import format_retrieval_scope_label
from power_atlas.retrieval_session_setup import build_retriever_and_rag as build_retriever_and_rag_impl
from power_atlas.retrieval_single_shot_session import run_single_shot_retrieval_session
from power_atlas.retrieval_runtime import (
    InteractiveRetrievalTurnResult,
    build_dry_run_retrieval_result,
    build_retrieval_base_result,
    build_retrieval_skipped_result,
    build_live_retrieval_result,
    execute_retrieval_search,
    run_interactive_retrieval_turn,
    run_with_retrieval_session,
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
    if neo4j_settings is not None:
        return neo4j_settings
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Live retrieval requires config.settings.neo4j or an explicit neo4j_settings "
        "argument from RequestContext/AppContext-derived config"
    )


def _require_stage_openai_api_key(error_message: str) -> None:
    require_openai_api_key(
        error_message,
        environ={"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")},
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
    return _run_retrieval_and_qa_impl(
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
        pipeline_contract=request_context.pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
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
    resolved_pipeline_contract = _resolve_pipeline_contract(config, pipeline_contract)
    resolved_index_name = (
        index_name
        if index_name is not None
        else _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME", resolved_pipeline_contract)
    )
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
    base: dict[str, object] = build_retrieval_base_result(
        citation_run_id=citation_run_id,
        citation_source_uri=citation_source_uri,
        top_k=top_k,
        resolved_index_name=resolved_index_name,
        question=question,
        effective_qa_model=effective_qa_model,
        qa_prompt_version=qa_prompt_version,
        effective_expand_graph=effective_expand_graph,
        cluster_aware=cluster_aware,
        retrieval_scope=retrieval_scope,
        citation_token_example=citation_token_example,
        citation_object_example=citation_object_example,
        retrieval_query_contract=retrieval_query_contract,
        interactive=interactive,
        message_history_enabled=message_history is not None,
    )
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
            return build_dry_run_retrieval_result(
                base=base,
                expand_graph=expand_graph,
                cluster_aware=cluster_aware,
                all_runs=all_runs,
            )
        elif _early_rule.name == "retrieval_skipped":
            # §5.2 — retrieval_skipped early return.
            warning_msg = "No question provided; skipping vector retrieval."
            _logger.warning(warning_msg)
            return build_retrieval_skipped_result(base=base, warning_msg=warning_msg)
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

    _require_stage_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live retrieval."
    )

    resolved_neo4j_settings = _neo4j_settings_from_config(config, neo4j_settings)
    neo4j_database = resolved_neo4j_settings.database

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

    answer_text, hits, session_warnings, session_citation_warnings = run_with_retrieval_session(
        resolved_neo4j_settings,
        index_name=resolved_index_name,
        retrieval_query=retrieval_query,
        qa_model=effective_qa_model,
        neo4j_database=neo4j_database,
        pipeline_contract=resolved_pipeline_contract,
        build_retriever_and_rag=_build_retriever_and_rag,
        run_session=_run_single_shot_session,
    )
    warnings_list.extend(session_warnings)
    citation_warnings_list.extend(session_citation_warnings)

    return build_live_retrieval_result(
        base=base,
        answer_text=answer_text,
        hits=hits,
        warnings=warnings_list,
        citation_warnings=citation_warnings_list,
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
    resolved_pipeline_contract = _resolve_pipeline_contract(config, pipeline_contract)
    # Validate and resolve session-level config once before opening any connections.
    if not all_runs and run_id is None:
        raise ValueError(
            "run_id is required for interactive retrieval. "
            "Pass run_id, or set all_runs=True to query across all data."
        )

    _require_stage_openai_api_key(
        "OPENAI_API_KEY environment variable is required for live retrieval."
    )

    resolved_index_name = (
        index_name
        if index_name is not None
        else _pipeline_contract_value("CHUNK_EMBEDDING_INDEX_NAME", resolved_pipeline_contract)
    )
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

    resolved_neo4j_settings = _neo4j_settings_from_config(config, neo4j_settings)

    run_with_retrieval_session(
        resolved_neo4j_settings,
        index_name=resolved_index_name,
        retrieval_query=retrieval_query,
        qa_model=effective_qa_model,
        neo4j_database=resolved_neo4j_settings.database,
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
    return _run_interactive_qa_impl(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        top_k=top_k,
        index_name=index_name or request_context.pipeline_contract.chunk_embedding_index_name,
        expand_graph=expand_graph,
        cluster_aware=cluster_aware,
        all_runs=request_context.all_runs if all_runs is None else all_runs,
        debug=debug,
        pipeline_contract=request_context.pipeline_contract,
        neo4j_settings=request_context.settings.neo4j,
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

