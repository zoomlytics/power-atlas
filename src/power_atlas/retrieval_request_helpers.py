from __future__ import annotations


def format_retrieval_scope_label(run_id: str | None, all_runs: bool) -> str:
    """Return a human-readable retrieval scope label for CLI output."""
    if all_runs:
        return "all runs in database"
    if run_id is not None:
        return f"run={run_id}"
    return "run=(none — dry-run placeholder)"


def build_retrieval_query_params(
    *,
    run_id: str | None,
    source_uri: str | None,
    all_runs: bool,
    cluster_aware: bool,
    alignment_version: str,
) -> dict[str, object]:
    """Build Cypher query parameters for retrieval filtering."""
    params: dict[str, object] = {"source_uri": source_uri}
    if not all_runs:
        params["run_id"] = run_id
    if cluster_aware:
        params["alignment_version"] = alignment_version
    return params


__all__ = [
    "build_retrieval_query_params",
    "format_retrieval_scope_label",
]