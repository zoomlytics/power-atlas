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

import pytest

from demo.stages.retrieval_and_qa import (
    _RETRIEVAL_QUERY_BASE,
    _RETRIEVAL_QUERY_BASE_ALL_RUNS,
    _RETRIEVAL_QUERY_WITH_CLUSTER,
    _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS,
    _RETRIEVAL_QUERY_WITH_EXPANSION,
    _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS,
    _build_canonical_names_expr,
    _build_claim_details_with_clause,
    _build_cluster_canonical_alignments_expr,
    _build_cluster_memberships_expr,
    _build_mention_names_expr,
    _build_retrieval_query,
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

    def test_both_modes_include_has_participant_subject(self) -> None:
        for run_scoped in (True, False):
            result = _build_claim_details_with_clause(run_scoped=run_scoped)
            assert "HAS_PARTICIPANT" in result
            assert "r.role" in result

    def test_both_modes_include_has_participant_object(self) -> None:
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
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, name: m.name, match_method: r.match_method}]}\n"
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
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, name: m.name, match_method: r.match_method}]}\n"
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
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, name: m.name, match_method: r.match_method}]}\n"
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
    "          roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, name: m.name, match_method: r.match_method}]}\n"
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
