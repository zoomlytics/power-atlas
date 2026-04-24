from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

import neo4j
from neo4j_graphrag.types import RetrieverResultItem


def format_cluster_context(
    cluster_memberships: list[dict[str, object]],
    cluster_canonical_alignments: list[dict[str, object]],
) -> str:
    """Format provisional cluster membership and alignment information for LLM context."""
    lines: list[str] = []
    seen_memberships: set[tuple[str, str, str]] = set()
    for membership in cluster_memberships:
        cluster_name = membership.get("cluster_name") or membership.get("cluster_id") or ""
        method = membership.get("membership_method") or ""
        raw_status = membership.get("membership_status")
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
    for alignment in cluster_canonical_alignments:
        canonical_name = alignment.get("canonical_name") or ""
        alignment_method = alignment.get("alignment_method") or ""
        alignment_status = alignment.get("alignment_status") or "unknown"
        dedup_key = (canonical_name, alignment_method, alignment_status)
        if dedup_key in seen_alignments:
            continue
        seen_alignments.add(dedup_key)
        if alignment_status == "aligned":
            lines.append(
                f"Cluster aligned to canonical entity: '{canonical_name}' (via {alignment_method})"
            )
        else:
            lines.append(
                f"PROVISIONAL ALIGNMENT to: '{canonical_name}' "
                f"(via {alignment_method}, status: {alignment_status} — not yet confirmed)"
            )

    if not lines:
        return ""
    header = "[Cluster context — provisional inference; not primary evidence]"
    return header + "\n" + "\n".join(lines)


def normalize_claim_roles(detail: dict[str, object]) -> list[dict[str, object]]:
    """Normalize claim role data from one detail record into a canonical list."""
    roles_raw = detail.get("roles")
    if roles_raw is not None:
        roles: list[dict[str, object]] = []
        if isinstance(roles_raw, (list, tuple)):
            for entry in roles_raw:
                if not isinstance(entry, Mapping):
                    continue
                role = entry.get("role")
                if not role:
                    continue
                roles.append(
                    {
                        "role": role,
                        "mention_name": entry.get("mention_name", entry.get("name")),
                        "match_method": entry.get("match_method"),
                    }
                )
    else:
        roles = []
        for role_key, role_name in (("subject_mention", "subject"), ("object_mention", "object")):
            slot = detail.get(role_key)
            if slot is not None and isinstance(slot, Mapping):
                roles.append(
                    {
                        "role": role_name,
                        "mention_name": slot.get("name"),
                        "match_method": slot.get("match_method"),
                    }
                )

    roles.sort(
        key=lambda entry: (
            0 if entry.get("role") == "subject" else 1 if entry.get("role") == "object" else 2,
            str(entry.get("role") or ""),
            str(entry.get("mention_name") or ""),
            str(entry.get("match_method") or ""),
        )
    )
    return roles


def format_claim_details(claim_details: list[dict[str, object]]) -> str:
    """Format structured claim details with explicit role mentions for LLM context."""
    if not claim_details:
        return ""
    lines: list[str] = []
    for detail in claim_details:
        claim_text = (detail.get("claim_text") or "").strip()
        if not claim_text:
            continue
        roles_list = normalize_claim_roles(detail)
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


def build_retrieval_path_diagnostics(
    *,
    claim_details: list[dict[str, object]],
    canonical_entities: list[str],
    cluster_memberships: list[dict[str, object]],
    cluster_canonical_alignments: list[dict[str, object]],
) -> dict[str, object]:
    """Build structured retrieval-path diagnostics from already-available metadata fields."""
    has_participant_edges: list[dict[str, object]] = []
    for detail in claim_details:
        claim_text = (detail.get("claim_text") or "").strip()
        if not claim_text:
            continue
        roles = normalize_claim_roles(detail)
        has_participant_edges.append({"claim_text": claim_text, "roles": roles})
    return {
        "has_participant_edges": has_participant_edges,
        "canonical_via_resolves_to": list(canonical_entities),
        "cluster_memberships": list(cluster_memberships),
        "cluster_canonical_via_aligned_with": list(cluster_canonical_alignments),
    }


def format_chunk_citation_record(
    record: neo4j.Record,
    *,
    build_citation_token: Callable[..., str],
    logger: logging.Logger,
) -> RetrieverResultItem:
    """Format a retrieved Chunk record into a RetrieverResultItem with citation metadata."""
    chunk_id = record.get("chunk_id")
    run_id = record.get("run_id")
    source_uri = record.get("source_uri")
    chunk_index = record.get("chunk_index")
    page = record.get("page")
    start_char = record.get("start_char")
    end_char = record.get("end_char")
    chunk_text = record.get("chunk_text") or ""
    score = record.get("similarityScore")

    empty_chunk_text = not chunk_text.strip()
    if empty_chunk_text:
        logger.warning(
            "Chunk %r has empty or whitespace-only text; it will contribute no evidence to the answer.",
            chunk_id,
        )

    citation_token = build_citation_token(
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

    claim_details_raw = record.get("claim_details")
    claim_details: list[dict[str, object]] = list(claim_details_raw) if claim_details_raw is not None else []
    claim_context = format_claim_details(claim_details)

    cluster_memberships: list[dict[str, object]] = list(record.get("cluster_memberships") or [])
    cluster_canonical_alignments: list[dict[str, object]] = list(record.get("cluster_canonical_alignments") or [])
    cluster_context = format_cluster_context(cluster_memberships, cluster_canonical_alignments)

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
    for field in ("claims", "mentions", "canonical_entities"):
        value = record.get(field)
        if value is not None:
            metadata[field] = value
    if claim_details_raw is not None:
        metadata["claim_details"] = claim_details
    for field in ("cluster_memberships", "cluster_canonical_alignments"):
        value = record.get(field)
        if value is not None:
            metadata[field] = value

    canonical_entities_raw = record.get("canonical_entities")
    canonical_entities_list: list[str] = (
        [str(value) for value in canonical_entities_raw]
        if canonical_entities_raw is not None
        else []
    )
    metadata["retrieval_path_diagnostics"] = build_retrieval_path_diagnostics(
        claim_details=claim_details,
        canonical_entities=canonical_entities_list,
        cluster_memberships=cluster_memberships,
        cluster_canonical_alignments=cluster_canonical_alignments,
    )

    return RetrieverResultItem(content=content, metadata=metadata)


__all__ = [
    "build_retrieval_path_diagnostics",
    "format_chunk_citation_record",
    "format_claim_details",
    "format_cluster_context",
    "normalize_claim_roles",
]