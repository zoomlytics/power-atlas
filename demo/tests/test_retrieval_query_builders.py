"""Unit tests for retrieval Cypher query builders.

These tests verify:

1. The output of individual sub-expression builder functions.
2. That ``_build_retrieval_query`` assembles the exact same Cypher text that was
   previously defined as hand-written module-level query constants.
3. That ``_select_retrieval_query`` returns the correct pre-built query for every
   combination of ``(expand_graph, cluster_aware, all_runs)`` flags.

The contract snapshot strings embedded here are the authoritative record of what
each query variant must produce.  If a query needs to change, update both the
snapshot and the module together, so the test continues to serve as a guard.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from demo.stages.retrieval_and_qa import (
    _CITATION_FALLBACK_PREFIX,
    _RETRIEVAL_QUERY_BASE,
    _RETRIEVAL_QUERY_BASE_ALL_RUNS,
    _RETRIEVAL_QUERY_WITH_CLUSTER,
    _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS,
    _RETRIEVAL_QUERY_WITH_EXPANSION,
    _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS,
    _apply_citation_repair,
    _build_canonical_names_expr,
    _build_claim_details_with_clause,
    _build_cluster_canonical_alignments_expr,
    _build_cluster_memberships_expr,
    _build_mention_names_expr,
    _build_query_params,
    _build_retrieval_query,
    _postprocess_answer,
    _select_retrieval_query,
)


# ---------------------------------------------------------------------------
# Sub-expression builder tests
# ---------------------------------------------------------------------------


class TestBuildClaimDetailsWithClause:
    """_build_claim_details_with_clause returns the WITH clause for claim_details."""

    def test_run_scoped_includes_run_id_filter(self) -> None:
        result = _build_claim_details_with_clause(run_scoped=True)
        assert "WHERE claim.run_id = $run_id" in result

    def test_all_runs_omits_run_id_filter(self) -> None:
        result = _build_claim_details_with_clause(run_scoped=False)
        assert "WHERE claim.run_id = $run_id" not in result

    def test_both_modes_include_supported_by(self) -> None:
        for run_scoped in (True, False):
            result = _build_claim_details_with_clause(run_scoped=run_scoped)
            assert "SUPPORTED_BY" in result

    def test_both_modes_include_has_participant_with_generic_role_projection(self) -> None:
        for run_scoped in (True, False):
            result = _build_claim_details_with_clause(run_scoped=run_scoped)
            assert "HAS_PARTICIPANT" in result
            assert "r.role" in result

    def test_result_ends_with_claim_details_alias(self) -> None:
        for run_scoped in (True, False):
            result = _build_claim_details_with_clause(run_scoped=run_scoped)
            assert result.endswith("] AS claim_details")

    def test_run_scoped_exact_fragment(self) -> None:
        result = _build_claim_details_with_clause(run_scoped=True)
        assert (
            "[(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) WHERE claim.run_id = $run_id |"
            in result
        )

    def test_all_runs_exact_fragment(self) -> None:
        result = _build_claim_details_with_clause(run_scoped=False)
        assert "[(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) |" in result
        assert "WHERE" not in result


class TestBuildMentionNamesExpr:
    """_build_mention_names_expr returns the mention names pattern comprehension."""

    def test_run_scoped_includes_run_id_filter(self) -> None:
        result = _build_mention_names_expr(run_scoped=True)
        assert "WHERE mention.run_id = $run_id" in result

    def test_all_runs_omits_run_id_filter(self) -> None:
        result = _build_mention_names_expr(run_scoped=False)
        assert "WHERE" not in result

    def test_both_modes_include_mentioned_in(self) -> None:
        for run_scoped in (True, False):
            result = _build_mention_names_expr(run_scoped=run_scoped)
            assert "MENTIONED_IN" in result

    def test_result_aliases_as_mentions(self) -> None:
        for run_scoped in (True, False):
            result = _build_mention_names_expr(run_scoped=run_scoped)
            assert result.endswith("] AS mentions")

    def test_run_scoped_exact_fragment(self) -> None:
        result = _build_mention_names_expr(run_scoped=True)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)"
            " WHERE mention.run_id = $run_id | mention.name] AS mentions"
        )

    def test_all_runs_exact_fragment(self) -> None:
        result = _build_mention_names_expr(run_scoped=False)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention) | mention.name] AS mentions"
        )


class TestBuildCanonicalNamesExpr:
    """_build_canonical_names_expr returns the canonical entity names comprehension."""

    def test_run_scoped_includes_run_id_filter(self) -> None:
        result = _build_canonical_names_expr(run_scoped=True)
        assert "WHERE mention.run_id = $run_id" in result

    def test_all_runs_omits_run_id_filter(self) -> None:
        result = _build_canonical_names_expr(run_scoped=False)
        assert "WHERE" not in result

    def test_both_modes_include_resolves_to(self) -> None:
        for run_scoped in (True, False):
            result = _build_canonical_names_expr(run_scoped=run_scoped)
            assert "RESOLVES_TO" in result

    def test_result_aliases_as_canonical_entities(self) -> None:
        for run_scoped in (True, False):
            result = _build_canonical_names_expr(run_scoped=run_scoped)
            assert result.endswith("] AS canonical_entities")

    def test_run_scoped_exact_fragment(self) -> None:
        result = _build_canonical_names_expr(run_scoped=True)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical)"
            " WHERE mention.run_id = $run_id | canonical.name] AS canonical_entities"
        )

    def test_all_runs_exact_fragment(self) -> None:
        result = _build_canonical_names_expr(run_scoped=False)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical)"
            " | canonical.name] AS canonical_entities"
        )


class TestBuildClusterMembershipsExpr:
    """_build_cluster_memberships_expr returns the cluster memberships comprehension."""

    def test_run_scoped_includes_run_id_filter(self) -> None:
        result = _build_cluster_memberships_expr(run_scoped=True)
        assert "WHERE mention.run_id = $run_id" in result

    def test_all_runs_omits_run_id_filter(self) -> None:
        result = _build_cluster_memberships_expr(run_scoped=False)
        assert "WHERE" not in result

    def test_both_modes_include_member_of(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_memberships_expr(run_scoped=run_scoped)
            assert "MEMBER_OF" in result

    def test_result_includes_cluster_provenance_fields(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_memberships_expr(run_scoped=run_scoped)
            assert "cluster_id" in result
            assert "cluster_name" in result
            assert "membership_status" in result
            assert "membership_method" in result

    def test_result_aliases_as_cluster_memberships(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_memberships_expr(run_scoped=run_scoped)
            assert result.endswith("] AS cluster_memberships")

    def test_run_scoped_exact_fragment(self) -> None:
        result = _build_cluster_memberships_expr(run_scoped=True)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster)"
            " WHERE mention.run_id = $run_id"
            " | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name,"
            " membership_status: r.status, membership_method: r.method}] AS cluster_memberships"
        )

    def test_all_runs_exact_fragment(self) -> None:
        result = _build_cluster_memberships_expr(run_scoped=False)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster)"
            " | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name,"
            " membership_status: r.status, membership_method: r.method}] AS cluster_memberships"
        )


class TestBuildClusterCanonicalAlignmentsExpr:
    """_build_cluster_canonical_alignments_expr returns the ALIGNED_WITH comprehension."""

    def test_run_scoped_includes_mention_run_id_filter(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=True)
        assert "mention.run_id = $run_id" in result

    def test_run_scoped_includes_alignment_run_id_filter(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=True)
        assert "a.run_id = $run_id" in result

    def test_all_runs_uses_self_scoping_run_id(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=False)
        assert "a.run_id = mention.run_id" in result

    def test_all_runs_omits_param_run_id_filter(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=False)
        # Only self-scoping reference, not the $run_id parameter
        assert "$run_id" not in result

    def test_both_modes_include_alignment_version_filter(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_canonical_alignments_expr(run_scoped=run_scoped)
            assert "alignment_version = $alignment_version" in result

    def test_both_modes_include_aligned_with(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_canonical_alignments_expr(run_scoped=run_scoped)
            assert "ALIGNED_WITH" in result

    def test_result_includes_alignment_provenance_fields(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_canonical_alignments_expr(run_scoped=run_scoped)
            assert "canonical_name" in result
            assert "alignment_method" in result
            assert "alignment_status" in result

    def test_result_aliases_as_cluster_canonical_alignments(self) -> None:
        for run_scoped in (True, False):
            result = _build_cluster_canonical_alignments_expr(run_scoped=run_scoped)
            assert result.endswith("] AS cluster_canonical_alignments")

    def test_run_scoped_exact_fragment(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=True)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:MEMBER_OF]"
            "->(cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(aligned_canonical)"
            " WHERE mention.run_id = $run_id AND a.run_id = $run_id"
            " AND a.alignment_version = $alignment_version"
            " | {canonical_name: aligned_canonical.name, alignment_method: a.alignment_method,"
            " alignment_status: a.alignment_status}] AS cluster_canonical_alignments"
        )

    def test_all_runs_exact_fragment(self) -> None:
        result = _build_cluster_canonical_alignments_expr(run_scoped=False)
        assert result == (
            "[(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:MEMBER_OF]"
            "->(cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(aligned_canonical)"
            " WHERE a.run_id = mention.run_id AND a.alignment_version = $alignment_version"
            " | {canonical_name: aligned_canonical.name, alignment_method: a.alignment_method,"
            " alignment_status: a.alignment_status}] AS cluster_canonical_alignments"
        )


# ---------------------------------------------------------------------------
# _build_retrieval_query assembler tests — contract snapshots
# ---------------------------------------------------------------------------

#: Expected text for the base run-scoped query (no expansion, no cluster).
_SNAPSHOT_BASE = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE c.run_id = $run_id\n"
    "  AND ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore\n"
)

#: Expected text for the all-runs base query.
_SNAPSHOT_BASE_ALL_RUNS = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore\n"
)

#: Expected text for the run-scoped graph-expanded query.
_SNAPSHOT_WITH_EXPANSION = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE c.run_id = $run_id\n"
    "  AND ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "WITH c, score,\n"
    "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) WHERE claim.run_id = $run_id |\n"
    "         {claim_text: claim.claim_text,\n"
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
    "     ] AS claim_details\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore,\n"
    "       [cd IN claim_details | cd.claim_text] AS claims,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) WHERE mention.run_id = $run_id | mention.name] AS mentions,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) WHERE mention.run_id = $run_id | canonical.name] AS canonical_entities,\n"
    "       claim_details\n"
)

#: Expected text for the all-runs graph-expanded query.
_SNAPSHOT_WITH_EXPANSION_ALL_RUNS = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "WITH c, score,\n"
    "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) |\n"
    "         {claim_text: claim.claim_text,\n"
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
    "     ] AS claim_details\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore,\n"
    "       [cd IN claim_details | cd.claim_text] AS claims,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) | mention.name] AS mentions,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) | canonical.name] AS canonical_entities,\n"
    "       claim_details\n"
)

#: Expected text for the run-scoped cluster-aware query.
_SNAPSHOT_WITH_CLUSTER = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE c.run_id = $run_id\n"
    "  AND ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "WITH c, score,\n"
    "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) WHERE claim.run_id = $run_id |\n"
    "         {claim_text: claim.claim_text,\n"
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
    "     ] AS claim_details\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore,\n"
    "       [cd IN claim_details | cd.claim_text] AS claims,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) WHERE mention.run_id = $run_id | mention.name] AS mentions,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) WHERE mention.run_id = $run_id | canonical.name] AS canonical_entities,\n"
    "       claim_details,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster) WHERE mention.run_id = $run_id | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name, membership_status: r.status, membership_method: r.method}] AS cluster_memberships,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:MEMBER_OF]->(cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(aligned_canonical) WHERE mention.run_id = $run_id AND a.run_id = $run_id AND a.alignment_version = $alignment_version | {canonical_name: aligned_canonical.name, alignment_method: a.alignment_method, alignment_status: a.alignment_status}] AS cluster_canonical_alignments\n"
)

#: Expected text for the all-runs cluster-aware query.
_SNAPSHOT_WITH_CLUSTER_ALL_RUNS = (
    "\n"
    "WITH node AS c, score\n"
    "WHERE ($source_uri IS NULL OR c.source_uri = $source_uri)\n"
    "WITH c, score,\n"
    "     [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) |\n"
    "         {claim_text: claim.claim_text,\n"
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]}\n"
    "     ] AS claim_details\n"
    "RETURN c.text AS chunk_text,\n"
    "       c.chunk_id AS chunk_id,\n"
    "       c.run_id AS run_id,\n"
    "       c.source_uri AS source_uri,\n"
    "       c.chunk_index AS chunk_index,\n"
    "       coalesce(c.page_number, c.page) AS page,\n"
    "       c.start_char AS start_char,\n"
    "       c.end_char AS end_char,\n"
    "       score AS similarityScore,\n"
    "       [cd IN claim_details | cd.claim_text] AS claims,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention) | mention.name] AS mentions,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:RESOLVES_TO]->(canonical) | canonical.name] AS canonical_entities,\n"
    "       claim_details,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[r:MEMBER_OF]->(cluster:ResolvedEntityCluster) | {cluster_id: cluster.cluster_id, cluster_name: cluster.canonical_name, membership_status: r.status, membership_method: r.method}] AS cluster_memberships,\n"
    "       [(c)<-[:MENTIONED_IN]-(mention:EntityMention)-[:MEMBER_OF]->(cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(aligned_canonical) WHERE a.run_id = mention.run_id AND a.alignment_version = $alignment_version | {canonical_name: aligned_canonical.name, alignment_method: a.alignment_method, alignment_status: a.alignment_status}] AS cluster_canonical_alignments\n"
)


class TestBuildRetrievalQueryContractSnapshots:
    """_build_retrieval_query must produce exact Cypher text for each mode combination."""

    def test_base_matches_snapshot(self) -> None:
        assert _build_retrieval_query() == _SNAPSHOT_BASE

    def test_base_all_runs_matches_snapshot(self) -> None:
        assert _build_retrieval_query(all_runs=True) == _SNAPSHOT_BASE_ALL_RUNS

    def test_expansion_matches_snapshot(self) -> None:
        assert _build_retrieval_query(expand_graph=True) == _SNAPSHOT_WITH_EXPANSION

    def test_expansion_all_runs_matches_snapshot(self) -> None:
        assert (
            _build_retrieval_query(expand_graph=True, all_runs=True)
            == _SNAPSHOT_WITH_EXPANSION_ALL_RUNS
        )

    def test_cluster_matches_snapshot(self) -> None:
        assert _build_retrieval_query(cluster_aware=True) == _SNAPSHOT_WITH_CLUSTER

    def test_cluster_all_runs_matches_snapshot(self) -> None:
        assert (
            _build_retrieval_query(cluster_aware=True, all_runs=True)
            == _SNAPSHOT_WITH_CLUSTER_ALL_RUNS
        )

    def test_cluster_aware_implies_expansion(self) -> None:
        """cluster_aware=True with expand_graph=False must still produce the cluster query."""
        without_explicit_expand = _build_retrieval_query(cluster_aware=True)
        with_explicit_expand = _build_retrieval_query(
            expand_graph=True, cluster_aware=True
        )
        assert without_explicit_expand == with_explicit_expand


class TestBuildRetrievalQueryMatchesModuleConstants:
    """_build_retrieval_query output must equal the module-level query constants."""

    def test_base_equals_constant(self) -> None:
        assert _build_retrieval_query() == _RETRIEVAL_QUERY_BASE

    def test_base_all_runs_equals_constant(self) -> None:
        assert _build_retrieval_query(all_runs=True) == _RETRIEVAL_QUERY_BASE_ALL_RUNS

    def test_expansion_equals_constant(self) -> None:
        assert _build_retrieval_query(expand_graph=True) == _RETRIEVAL_QUERY_WITH_EXPANSION

    def test_expansion_all_runs_equals_constant(self) -> None:
        assert (
            _build_retrieval_query(expand_graph=True, all_runs=True)
            == _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS
        )

    def test_cluster_equals_constant(self) -> None:
        assert _build_retrieval_query(cluster_aware=True) == _RETRIEVAL_QUERY_WITH_CLUSTER

    def test_cluster_all_runs_equals_constant(self) -> None:
        assert (
            _build_retrieval_query(cluster_aware=True, all_runs=True)
            == _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS
        )


# ---------------------------------------------------------------------------
# _select_retrieval_query tests
# ---------------------------------------------------------------------------


class TestSelectRetrievalQuery:
    """_select_retrieval_query returns the correct pre-built query constant."""

    def test_no_flags_returns_base(self) -> None:
        assert _select_retrieval_query() is _RETRIEVAL_QUERY_BASE

    def test_all_runs_only_returns_base_all_runs(self) -> None:
        assert _select_retrieval_query(all_runs=True) is _RETRIEVAL_QUERY_BASE_ALL_RUNS

    def test_expand_graph_returns_expansion(self) -> None:
        assert _select_retrieval_query(expand_graph=True) is _RETRIEVAL_QUERY_WITH_EXPANSION

    def test_expand_graph_and_all_runs_returns_expansion_all_runs(self) -> None:
        assert (
            _select_retrieval_query(expand_graph=True, all_runs=True)
            is _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS
        )

    def test_cluster_aware_returns_cluster(self) -> None:
        assert _select_retrieval_query(cluster_aware=True) is _RETRIEVAL_QUERY_WITH_CLUSTER

    def test_cluster_aware_and_all_runs_returns_cluster_all_runs(self) -> None:
        assert (
            _select_retrieval_query(cluster_aware=True, all_runs=True)
            is _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS
        )

    def test_cluster_aware_overrides_expand_graph(self) -> None:
        """cluster_aware takes priority regardless of expand_graph value."""
        result = _select_retrieval_query(expand_graph=True, cluster_aware=True)
        assert result is _RETRIEVAL_QUERY_WITH_CLUSTER

    def test_cluster_aware_overrides_expand_graph_all_runs(self) -> None:
        result = _select_retrieval_query(expand_graph=True, cluster_aware=True, all_runs=True)
        assert result is _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({}, _RETRIEVAL_QUERY_BASE),
            ({"all_runs": True}, _RETRIEVAL_QUERY_BASE_ALL_RUNS),
            ({"expand_graph": True}, _RETRIEVAL_QUERY_WITH_EXPANSION),
            ({"expand_graph": True, "all_runs": True}, _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS),
            ({"cluster_aware": True}, _RETRIEVAL_QUERY_WITH_CLUSTER),
            ({"cluster_aware": True, "all_runs": True}, _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS),
            # cluster_aware overrides expand_graph
            ({"cluster_aware": True, "expand_graph": True}, _RETRIEVAL_QUERY_WITH_CLUSTER),
            (
                {"cluster_aware": True, "expand_graph": True, "all_runs": True},
                _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS,
            ),
        ],
    )
    def test_all_flag_combinations(
        self, kwargs: dict[str, bool], expected: str
    ) -> None:
        assert _select_retrieval_query(**kwargs) is expected


# ---------------------------------------------------------------------------
# _build_query_params tests
# ---------------------------------------------------------------------------


class TestBuildQueryParams:
    """_build_query_params builds the correct Cypher parameter dict."""

    def test_run_scoped_includes_run_id(self) -> None:
        params = _build_query_params(
            run_id="run123", source_uri=None, all_runs=False, cluster_aware=False
        )
        assert params["run_id"] == "run123"

    def test_all_runs_omits_run_id(self) -> None:
        params = _build_query_params(
            run_id="run123", source_uri=None, all_runs=True, cluster_aware=False
        )
        assert "run_id" not in params

    def test_source_uri_always_included(self) -> None:
        for all_runs in (True, False):
            params = _build_query_params(
                run_id="r", source_uri="file:///doc.pdf", all_runs=all_runs, cluster_aware=False
            )
            assert params["source_uri"] == "file:///doc.pdf"

    def test_source_uri_none_is_valid(self) -> None:
        params = _build_query_params(
            run_id="r", source_uri=None, all_runs=False, cluster_aware=False
        )
        assert params["source_uri"] is None

    def test_cluster_aware_adds_alignment_version(self) -> None:
        from demo.contracts import ALIGNMENT_VERSION
        params = _build_query_params(
            run_id="r", source_uri=None, all_runs=False, cluster_aware=True
        )
        assert params["alignment_version"] == ALIGNMENT_VERSION

    def test_not_cluster_aware_omits_alignment_version(self) -> None:
        params = _build_query_params(
            run_id="r", source_uri=None, all_runs=False, cluster_aware=False
        )
        assert "alignment_version" not in params

    def test_all_runs_cluster_aware_has_no_run_id_but_has_alignment_version(self) -> None:
        from demo.contracts import ALIGNMENT_VERSION
        params = _build_query_params(
            run_id="r", source_uri=None, all_runs=True, cluster_aware=True
        )
        assert "run_id" not in params
        assert params["alignment_version"] == ALIGNMENT_VERSION


# ---------------------------------------------------------------------------
# _apply_citation_repair tests
# ---------------------------------------------------------------------------

def _make_hit(token: str, chunk_id: str) -> dict:
    return {"metadata": {"citation_token": token, "chunk_id": chunk_id}}


class TestApplyCitationRepair:
    """_apply_citation_repair returns (repaired, applied, strategy, chunk_id)."""

    _TOKEN = "[CITATION|chunk_id=abc|run_id=r|source_uri=file%3A%2F%2F%2Ff|chunk_index=0|page=1|start_char=0|end_char=99]"

    def test_no_repair_when_not_all_runs(self) -> None:
        answer = "Uncited sentence."
        hits = [_make_hit(self._TOKEN, "abc")]
        result, applied, strategy, chunk_id = _apply_citation_repair(
            answer, hits, all_runs=False, raw_answer_all_cited=False
        )
        assert result == answer
        assert applied is False
        assert strategy is None
        assert chunk_id is None

    def test_no_repair_when_already_cited(self) -> None:
        answer = f"Already cited {self._TOKEN}"
        hits = [_make_hit(self._TOKEN, "abc")]
        result, applied, _, _ = _apply_citation_repair(
            answer, hits, all_runs=True, raw_answer_all_cited=True
        )
        assert result == answer
        assert applied is False

    def test_no_repair_when_empty_answer(self) -> None:
        result, applied, _, _ = _apply_citation_repair(
            "", [_make_hit(self._TOKEN, "abc")], all_runs=True, raw_answer_all_cited=False
        )
        assert result == ""
        assert applied is False

    def test_no_repair_when_no_hits(self) -> None:
        result, applied, _, _ = _apply_citation_repair(
            "Uncited.", [], all_runs=True, raw_answer_all_cited=False
        )
        assert result == "Uncited."
        assert applied is False

    def test_repair_applied_in_all_runs_mode(self) -> None:
        answer = "Uncited sentence."
        hits = [_make_hit(self._TOKEN, "abc")]
        result, applied, strategy, chunk_id = _apply_citation_repair(
            answer, hits, all_runs=True, raw_answer_all_cited=False
        )
        assert applied is True
        assert strategy == "append_first_retrieved_token"
        assert chunk_id == "abc"
        assert self._TOKEN in result

    def test_repair_uses_first_available_token(self) -> None:
        token_a = self._TOKEN
        token_b = self._TOKEN.replace("chunk_id=abc", "chunk_id=xyz")
        hits = [_make_hit(token_a, "abc"), _make_hit(token_b, "xyz")]
        _, _, _, chunk_id = _apply_citation_repair(
            "Uncited.", hits, all_runs=True, raw_answer_all_cited=False
        )
        assert chunk_id == "abc"

    def test_no_repair_when_hits_have_no_token(self) -> None:
        hits = [{"metadata": {"citation_token": None, "chunk_id": "abc"}}]
        result, applied, _, _ = _apply_citation_repair(
            "Uncited.", hits, all_runs=True, raw_answer_all_cited=False
        )
        assert result == "Uncited."
        assert applied is False

    def test_source_chunk_id_is_none_when_chunk_id_missing(self) -> None:
        hits = [{"metadata": {"citation_token": self._TOKEN, "chunk_id": ""}}]
        _, applied, _, chunk_id = _apply_citation_repair(
            "Uncited.", hits, all_runs=True, raw_answer_all_cited=False
        )
        assert applied is True
        assert chunk_id is None

    def test_applied_false_when_repair_produces_no_change(self) -> None:
        """applied is False when _repair_uncited_answer returns text identical to input.

        citation_repair_applied means the answer text was actually modified, not
        merely that repair logic was invoked.  This test uses a mock to simulate
        the edge case where the repair function returns the original text unchanged.
        """
        answer = "Uncited sentence."
        hits = [_make_hit(self._TOKEN, "abc")]
        with patch(
            "demo.stages.retrieval_and_qa._repair_uncited_answer",
            return_value=answer,
        ):
            result, applied, strategy, chunk_id = _apply_citation_repair(
                answer, hits, all_runs=True, raw_answer_all_cited=False
            )
        assert result == answer
        assert applied is False
        assert strategy is None
        assert chunk_id is None


# ---------------------------------------------------------------------------
# _postprocess_answer tests
# ---------------------------------------------------------------------------

_TOKEN = "[CITATION|chunk_id=abc|run_id=r|source_uri=file%3A%2F%2F%2Ff|chunk_index=0|page=1|start_char=0|end_char=99]"
_HIT: dict[str, object] = {"metadata": {"citation_token": _TOKEN, "chunk_id": "abc"}}


class TestPostprocessAnswer:
    """_postprocess_answer returns a fully-structured postprocessing result.

    Tests verify that both the repaired-answer path and the fallback path
    produce the same contract, ensuring run_retrieval_and_qa and
    run_interactive_qa cannot drift silently.
    """

    def test_fully_cited_answer_returns_full_evidence_level(self) -> None:
        answer = f"Fully cited sentence. {_TOKEN}"
        result = _postprocess_answer(answer, [_HIT], all_runs=True)
        assert result["raw_answer"] == answer
        assert result["raw_answer_all_cited"] is True
        assert result["citation_repair_applied"] is False
        assert result["citation_fallback_applied"] is False
        assert result["all_cited"] is True
        assert result["evidence_level"] == "full"
        assert result["citation_warnings"] == []
        assert result["warning_count"] == 0
        assert result["citation_quality"]["evidence_level"] == "full"
        assert result["display_answer"] == answer
        assert result["history_answer"] == answer

    def test_repaired_answer_path_repair_applied_no_fallback(self) -> None:
        """Repair case: all_runs=True with uncited answer and available hits → repair applied."""
        answer = "Uncited sentence."
        result = _postprocess_answer(answer, [_HIT], all_runs=True)
        assert result["raw_answer"] == answer
        assert result["raw_answer_all_cited"] is False
        assert result["citation_repair_applied"] is True
        assert result["citation_repair_strategy"] == "append_first_retrieved_token"
        assert result["citation_repair_source_chunk_id"] == "abc"
        # After repair the answer should include the citation token.
        assert _TOKEN in result["repaired_answer"]
        # Repair produced a fully-cited answer so no fallback should be applied.
        assert result["citation_fallback_applied"] is False
        assert result["all_cited"] is True
        assert result["evidence_level"] == "full"
        assert result["citation_warnings"] == []
        # Both entry points get the same display_answer and history_answer.
        assert _TOKEN in result["display_answer"]
        assert _TOKEN in result["history_answer"]

    def test_fallback_applied_when_no_repair_possible(self) -> None:
        """Fallback case: all_runs=False (repair skipped) with uncited answer → fallback applied."""
        answer = "Uncited sentence without any citation token."
        result = _postprocess_answer(answer, [], all_runs=False)
        assert result["raw_answer"] == answer
        assert result["raw_answer_all_cited"] is False
        assert result["citation_repair_applied"] is False
        assert result["citation_fallback_applied"] is True
        assert result["all_cited"] is False
        assert result["evidence_level"] == "degraded"
        assert len(result["citation_warnings"]) == 1
        assert "Not all answer sentences" in result["citation_warnings"][0]
        assert result["warning_count"] == 1
        assert result["citation_quality"]["evidence_level"] == "degraded"
        # display_answer includes the fallback prefix.
        assert result["display_answer"].startswith(_CITATION_FALLBACK_PREFIX)
        # history_answer is just the bare prefix (no uncited content).
        assert result["history_answer"] == _CITATION_FALLBACK_PREFIX

    def test_fallback_also_applied_when_all_runs_but_no_hits(self) -> None:
        """Repair requires hits; with no hits and uncited answer fallback is applied."""
        answer = "No evidence here."
        result = _postprocess_answer(answer, [], all_runs=True)
        assert result["citation_repair_applied"] is False
        assert result["citation_fallback_applied"] is True
        assert result["evidence_level"] == "degraded"

    def test_empty_answer_returns_no_answer_evidence_level(self) -> None:
        result = _postprocess_answer("", [], all_runs=False)
        assert result["raw_answer"] == ""
        assert result["raw_answer_all_cited"] is False
        assert result["citation_repair_applied"] is False
        assert result["citation_fallback_applied"] is False
        assert result["all_cited"] is False
        assert result["evidence_level"] == "no_answer"
        assert result["citation_warnings"] == []
        assert result["display_answer"] == ""
        assert result["history_answer"] == ""

    def test_existing_citation_warnings_propagated_and_degrade_evidence(self) -> None:
        """Existing citation warnings (e.g. from empty-chunk detection) degrade evidence_level."""
        answer = f"Cited sentence. {_TOKEN}"
        existing = ["Chunk 'abc' has empty or whitespace-only text."]
        result = _postprocess_answer(answer, [_HIT], all_runs=True, existing_citation_warnings=existing)
        assert result["raw_answer_all_cited"] is True
        assert result["citation_fallback_applied"] is False
        assert result["all_cited"] is True
        # Even though the answer is cited, the pre-existing chunk warning degrades evidence.
        assert result["evidence_level"] == "degraded"
        assert existing[0] in result["citation_warnings"]
        assert result["warning_count"] == 1
        assert result["citation_quality"]["evidence_level"] == "degraded"

    def test_existing_citation_warnings_not_mutated(self) -> None:
        """_postprocess_answer must not mutate the caller's existing_citation_warnings list."""
        existing: list[str] = []
        answer = "Uncited."
        _postprocess_answer(answer, [], all_runs=False, existing_citation_warnings=existing)
        assert existing == []

    def test_citation_quality_bundle_keys_present(self) -> None:
        """citation_quality bundle always contains all required keys.

        The key list here is an explicit contract snapshot: if any key is
        removed or renamed the test intentionally fails so the change is
        reviewed.
        """
        result = _postprocess_answer("Some answer.", [], all_runs=False)
        cq = result["citation_quality"]
        assert isinstance(cq, dict)
        for key in ("all_cited", "raw_answer_all_cited", "evidence_level", "warning_count", "citation_warnings"):
            assert key in cq, f"citation_quality missing key: {key!r}"

    def test_repair_and_fallback_paths_share_same_contract_keys(self) -> None:
        """Both repair and fallback results expose identical top-level keys."""
        repair_result = _postprocess_answer("Uncited.", [_HIT], all_runs=True)
        fallback_result = _postprocess_answer("Uncited.", [], all_runs=False)
        assert set(repair_result.keys()) == set(fallback_result.keys())
