from __future__ import annotations

import logging
import re
import types
from collections.abc import Callable, Mapping
from typing import Literal, TypedDict, cast

_CITATION_TOKEN_PREFIX = "[CITATION|"
_TRAILING_CITATION_RE = re.compile(rf"({re.escape(_CITATION_TOKEN_PREFIX)}[^\]]*\])+\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'\u201c\u2018\u2019\u201d(]*(?:[A-Z]|\[(?!CITATION\|)))")
_BULLET_PREFIX_RE = re.compile(r"^([-*•]\s+|\d+\.\s+)")
CITATION_FALLBACK_PREFIX = "Insufficient citations detected"


class _CitationQualityBundle(TypedDict):
    """Structured citation-quality summary nested inside :class:`_AnswerPostprocessResult`."""

    all_cited: bool
    raw_answer_all_cited: bool
    evidence_level: Literal["no_answer", "full", "degraded"]
    warning_count: int
    citation_warnings: list[str]


class _AnswerPostprocessResult(TypedDict):
    """Structured result returned by :func:`postprocess_answer`."""

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
    """Public API fields produced by projecting an :class:`_AnswerPostprocessResult`."""

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


class _RetrievalDebugView(TypedDict):
    """Typed inspection model shared across retrieval/QA surfaces."""

    raw_answer_all_cited: bool
    all_cited: bool
    citation_repair_attempted: bool
    citation_repair_applied: bool
    citation_fallback_applied: bool
    evidence_level: Literal["no_answer", "full", "degraded"]
    warning_count: int
    citation_warnings: list[str]
    malformed_diagnostics_count: int


def first_citation_token_from_hits(hits: list[dict[str, object]]) -> str | None:
    """Return the first non-empty citation token from a list of retrieval hit dicts."""
    for hit in hits:
        token = (hit.get("metadata") or {}).get("citation_token")  # type: ignore[union-attr]
        if token:
            return str(token)
    return None


def split_into_segments(answer: str) -> list[str]:
    """Split answer text into citation-checkable segments (sentences and bullets)."""
    segments = []
    for line in answer.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if _BULLET_PREFIX_RE.match(line):
            segments.append(line)
        else:
            parts = _SENTENCE_SPLIT_RE.split(line)
            segments.extend(p.strip() for p in parts if p.strip())
    return segments


def check_all_answers_cited(
    answer: str,
    *,
    split_segments: Callable[[str], list[str]] = split_into_segments,
) -> bool:
    """Return True if every answer sentence or bullet ends with a citation token."""
    segments = split_segments(answer)
    if not segments:
        return False
    for segment in segments:
        if not _TRAILING_CITATION_RE.search(segment):
            return False
    return True


def repair_uncited_answer(answer: str, first_citation_token: str) -> str:
    """Repair uncited answer segments by appending a citation token from retrieved context."""
    if not answer or not first_citation_token:
        return answer
    result_lines: list[str] = []
    for line in answer.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue
        if _BULLET_PREFIX_RE.match(stripped):
            if _TRAILING_CITATION_RE.search(stripped):
                result_lines.append(line)
            else:
                result_lines.append(f"{line} {first_citation_token}")
        else:
            parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(stripped) if p.strip()]
            if all(_TRAILING_CITATION_RE.search(p) for p in parts):
                result_lines.append(line)
            else:
                repaired: list[str] = [
                    p if _TRAILING_CITATION_RE.search(p) else f"{p} {first_citation_token}"
                    for p in parts
                ]
                result_lines.append(" ".join(repaired))
    return "\n".join(result_lines)


def apply_citation_repair(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    raw_answer_all_cited: bool,
    get_first_citation_token: Callable[[list[dict[str, object]]], str | None] = first_citation_token_from_hits,
    repair_answer: Callable[[str, str], str] = repair_uncited_answer,
) -> tuple[str, bool, bool, str | None, str | None]:
    """Attempt to repair uncited answer segments using retrieved citation tokens."""
    if not (all_runs and hits and answer_text.strip() and not raw_answer_all_cited):
        return answer_text, False, False, None, None
    first_token = get_first_citation_token(hits)
    if not first_token:
        return answer_text, True, False, None, None
    source_chunk_id: str | None = None
    for hit in hits:
        metadata = hit.get("metadata") or {}
        token = metadata.get("citation_token")
        if token and str(token) == first_token:
            chunk_id_raw = metadata.get("chunk_id")
            source_chunk_id = str(chunk_id_raw) if chunk_id_raw else None
            break
    repaired = repair_answer(answer_text, first_token)
    if repaired == answer_text:
        return answer_text, True, False, None, None
    return repaired, True, True, "append_first_retrieved_token", source_chunk_id


def build_citation_fallback(
    answer: str,
    *,
    check_citations: Callable[[str], bool] = check_all_answers_cited,
    fallback_prefix: str = CITATION_FALLBACK_PREFIX,
) -> tuple[str, str, bool]:
    """Compute citation-fallback display and history answers for a single LLM response."""
    is_uncited = bool(answer and not check_citations(answer))
    display_answer = f"{fallback_prefix}: {answer}" if is_uncited else answer
    history_answer = fallback_prefix if is_uncited else answer
    return display_answer, history_answer, is_uncited


def project_postprocess_to_public(
    pp: _AnswerPostprocessResult,
) -> _PostprocessPublicFields:
    """Map an :class:`_AnswerPostprocessResult` to the public result surface."""
    return cast(
        _PostprocessPublicFields,
        {
            public_key: pp[internal_key]  # type: ignore[literal-required]
            for internal_key, public_key in _POSTPROCESS_FIELD_MAP.items()
        },
    )


def build_retrieval_debug_view(
    pp: _AnswerPostprocessResult,
    *,
    malformed_diagnostics_count: int = 0,
) -> _RetrievalDebugView:
    """Build a :class:`_RetrievalDebugView` from a postprocessing result."""
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


def postprocess_answer(
    answer_text: str,
    hits: list[dict[str, object]],
    *,
    all_runs: bool,
    existing_citation_warnings: list[str] | None = None,
    check_citations: Callable[[str], bool] = check_all_answers_cited,
    apply_repair: Callable[..., tuple[str, bool, bool, str | None, str | None]] = apply_citation_repair,
    build_fallback: Callable[[str], tuple[str, str, bool]] = build_citation_fallback,
    logger: logging.Logger | None = None,
) -> _AnswerPostprocessResult:
    """Unified answer postprocessing lifecycle shared by both retrieval entry points."""
    raw_answer = answer_text
    raw_answer_all_cited = check_citations(raw_answer) if raw_answer.strip() else False

    repaired, citation_repair_attempted, citation_repair_applied, citation_repair_strategy, citation_repair_source_chunk_id = (
        apply_repair(
            answer_text,
            hits,
            all_runs=all_runs,
            raw_answer_all_cited=raw_answer_all_cited,
        )
    )

    repaired_stripped = repaired.strip()
    display_answer, history_answer, citation_fallback_applied = build_fallback(repaired_stripped)
    all_cited = bool(repaired_stripped) and check_citations(repaired_stripped)

    citation_warnings: list[str] = list(existing_citation_warnings or [])
    if repaired_stripped and not all_cited:
        uncited_warning = "Not all answer sentences or bullets end with a citation token."
        if logger is not None:
            logger.warning(uncited_warning)
        citation_warnings.append(uncited_warning)

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


def format_postprocess_debug_summary(view: _RetrievalDebugView) -> str:
    """Format a compact postprocessing debug summary line from a retrieval debug view."""
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


__all__ = [
    "CITATION_FALLBACK_PREFIX",
    "_AnswerPostprocessResult",
    "_CitationQualityBundle",
    "_POSTPROCESS_FIELD_MAP",
    "_PostprocessPublicFields",
    "_RetrievalDebugView",
    "apply_citation_repair",
    "build_citation_fallback",
    "build_retrieval_debug_view",
    "check_all_answers_cited",
    "first_citation_token_from_hits",
    "format_postprocess_debug_summary",
    "postprocess_answer",
    "project_postprocess_to_public",
    "repair_uncited_answer",
    "split_into_segments",
]
