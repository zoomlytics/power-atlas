from __future__ import annotations


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
    claim_filter = " WHERE claim.run_id = $run_id" if run_scoped else ""
    return (
        "WITH c, score,\n"
        "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim)" + claim_filter + " |\n"
        "         {claim_text: claim.claim_text,\n"
        "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
        "     ] AS claim_details"
    )


def _build_mention_names_expr(run_scoped: bool) -> str:
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)" + run_filter
        + " | mention.name] AS mentions"
    )


def _build_canonical_names_expr(run_scoped: bool) -> str:
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical)"
        + run_filter + " | canonical.name] AS canonical_entities"
    )


def _build_cluster_memberships_expr(run_scoped: bool) -> str:
    run_filter = " WHERE mention.run_id = $run_id" if run_scoped else ""
    return (
        "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster)"
        + run_filter
        + " | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name, membership_status: r.status, membership_method: r.method}] AS cluster_memberships"
    )


def _build_cluster_canonical_alignments_expr(run_scoped: bool) -> str:
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
    run_scoped = not all_runs
    expand_graph = expand_graph or cluster_aware

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


_RETRIEVAL_QUERY_BASE = _build_retrieval_query()
_RETRIEVAL_QUERY_WITH_EXPANSION = _build_retrieval_query(expand_graph=True)
_RETRIEVAL_QUERY_BASE_ALL_RUNS = _build_retrieval_query(all_runs=True)
_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS = _build_retrieval_query(expand_graph=True, all_runs=True)
_RETRIEVAL_QUERY_WITH_CLUSTER = _build_retrieval_query(cluster_aware=True)
_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS = _build_retrieval_query(cluster_aware=True, all_runs=True)


def _select_retrieval_query(
    *,
    expand_graph: bool = False,
    cluster_aware: bool = False,
    all_runs: bool = False,
) -> str:
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


__all__ = [
    "_build_canonical_names_expr",
    "_build_claim_details_with_clause",
    "_build_cluster_canonical_alignments_expr",
    "_build_cluster_memberships_expr",
    "_build_mention_names_expr",
    "_build_retrieval_query",
    "_RETRIEVAL_QUERY_BASE",
    "_RETRIEVAL_QUERY_BASE_ALL_RUNS",
    "_RETRIEVAL_QUERY_WITH_CLUSTER",
    "_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS",
    "_RETRIEVAL_QUERY_WITH_EXPANSION",
    "_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS",
    "_select_retrieval_query",
    "_select_runtime_retrieval_query",
]