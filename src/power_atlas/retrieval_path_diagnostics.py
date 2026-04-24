from __future__ import annotations

from power_atlas.retrieval_chunk_formatter import build_retrieval_path_diagnostics


def format_retrieval_path_summary(hits: list[dict[str, object]]) -> str:
    """Format a human-readable retrieval-path summary across all retrieved hits."""
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

        raw_has_participant_edges = diag.get("has_participant_edges")
        if isinstance(raw_has_participant_edges, list):
            has_participant_edges: list[object] = raw_has_participant_edges
        else:
            if raw_has_participant_edges is not None:
                lines.append(
                    "  (malformed has_participant_edges: expected list, got "
                    f"{type(raw_has_participant_edges).__name__!r} — skipped)"
                )
            has_participant_edges = []
        if has_participant_edges:
            lines.append("  HAS_PARTICIPANT edges (claims with participation):")
            for entry in has_participant_edges:
                if not isinstance(entry, dict):
                    lines.append(f"    • (malformed entry: {entry!r})")
                    continue
                claim_text = str(entry.get("claim_text") or "")
                raw_roles = entry.get("roles")
                if isinstance(raw_roles, list):
                    roles: list[object] = raw_roles
                else:
                    roles = []
                    if raw_roles is not None:
                        role_parts_list = [f"(malformed roles: {raw_roles!r})"]
                        preview = claim_text[:80] + ("..." if len(claim_text) > 80 else "")
                        lines.append(f"    • \"{preview}\" [{', '.join(role_parts_list)}]")
                        continue
                role_parts_list: list[str] = []
                for role_entry in roles:
                    if not isinstance(role_entry, dict):
                        role_parts_list.append(f"(malformed: {role_entry!r})")
                        continue
                    role_name = role_entry.get("role") or "(unknown)"
                    mention_name = role_entry.get("mention_name") or "(unknown)"
                    match_method = role_entry.get("match_method") or "(unknown)"
                    role_parts_list.append(f"{role_name}={mention_name!r} (match: {match_method})")
                role_parts = ", ".join(role_parts_list)
                preview = claim_text[:80] + ("..." if len(claim_text) > 80 else "")
                if role_parts:
                    lines.append(f"    • \"{preview}\" [{role_parts}]")
                else:
                    lines.append(f"    • \"{preview}\" [no resolved roles]")
        else:
            lines.append("  HAS_PARTICIPANT edges: (none)")

        raw_resolves_to = diag.get("canonical_via_resolves_to")
        if isinstance(raw_resolves_to, list):
            resolves_to: list[object] = raw_resolves_to
        else:
            if raw_resolves_to is not None:
                lines.append(
                    "  (malformed canonical_via_resolves_to: expected list, got "
                    f"{type(raw_resolves_to).__name__!r} — skipped)"
                )
            resolves_to = []
        if resolves_to:
            lines.append(f"  RESOLVES_TO canonical entities: {resolves_to!r}")
        else:
            lines.append("  RESOLVES_TO canonical entities: (none)")

        raw_cluster_memberships = diag.get("cluster_memberships")
        if isinstance(raw_cluster_memberships, list):
            memberships: list[object] = raw_cluster_memberships
        else:
            if raw_cluster_memberships is not None:
                lines.append(
                    "  (malformed cluster_memberships: expected list, got "
                    f"{type(raw_cluster_memberships).__name__!r} — skipped)"
                )
            memberships = []
        if memberships:
            lines.append("  Cluster memberships (MEMBER_OF):")
            for membership in memberships:
                if not isinstance(membership, dict):
                    lines.append(f"    • (malformed entry: {membership!r})")
                    continue
                cluster_name = membership.get("cluster_name") or membership.get("cluster_id") or ""
                membership_status = membership.get("membership_status") or "unknown"
                membership_method = membership.get("membership_method") or ""
                lines.append(
                    f"    • cluster={cluster_name!r}  status={membership_status}  method={membership_method}"
                )
        else:
            lines.append("  Cluster memberships (MEMBER_OF): (none)")

        raw_alignments = diag.get("cluster_canonical_via_aligned_with")
        if isinstance(raw_alignments, list):
            alignments: list[object] = raw_alignments
        else:
            if raw_alignments is not None:
                lines.append(
                    "  (malformed cluster_canonical_via_aligned_with: expected list, got "
                    f"{type(raw_alignments).__name__!r} — skipped)"
                )
            alignments = []
        if alignments:
            lines.append("  Canonical via ALIGNED_WITH:")
            for alignment in alignments:
                if not isinstance(alignment, dict):
                    lines.append(f"    • (malformed entry: {alignment!r})")
                    continue
                canonical_name = alignment.get("canonical_name") or ""
                alignment_method = alignment.get("alignment_method") or ""
                alignment_status = alignment.get("alignment_status") or ""
                lines.append(
                    f"    • canonical={canonical_name!r}  method={alignment_method}  status={alignment_status}"
                )
        else:
            lines.append("  Canonical via ALIGNED_WITH: (none)")
    return "\n".join(lines)


def count_malformed_diagnostics(hits: list[dict[str, object]]) -> int:
    """Return the number of hits that contain malformed retrieval-path diagnostics payloads."""
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
        if diagnostics_dict_has_malformed_fields(diag):
            count += 1
    return count


def diagnostics_dict_has_malformed_fields(diag: dict[str, object]) -> bool:
    """Return True if diag contains any structurally malformed sub-field."""
    list_fields = (
        "has_participant_edges",
        "canonical_via_resolves_to",
        "cluster_memberships",
        "cluster_canonical_via_aligned_with",
    )
    for field in list_fields:
        value = diag.get(field)
        if value is not None and not isinstance(value, list):
            return True

    dict_entry_fields = (
        "has_participant_edges",
        "cluster_memberships",
        "cluster_canonical_via_aligned_with",
    )
    for field in dict_entry_fields:
        value = diag.get(field)
        if not isinstance(value, list):
            continue
        for entry in value:
            if not isinstance(entry, dict):
                return True
            if field == "has_participant_edges":
                roles = entry.get("roles")
                if roles is not None and not isinstance(roles, list):
                    return True
                if isinstance(roles, list):
                    for role in roles:
                        if not isinstance(role, dict):
                            return True
    return False


__all__ = [
    "build_retrieval_path_diagnostics",
    "count_malformed_diagnostics",
    "diagnostics_dict_has_malformed_fields",
    "format_retrieval_path_summary",
]
