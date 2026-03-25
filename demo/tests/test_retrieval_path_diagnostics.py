"""Unit tests for retrieval-path diagnostics helpers.

These tests verify:

1. ``_build_retrieval_path_diagnostics`` correctly maps raw metadata fields to the
   structured diagnostics dict.
2. ``_format_retrieval_path_summary`` produces human-readable output for a variety
   of hit configurations (empty, base-query, full cluster-aware, mixed).
3. The ``retrieval_path_diagnostics`` key is present in chunk metadata produced by
   ``_chunk_citation_formatter`` and contains the expected structure.
4. ``run_retrieval_and_qa`` result dicts always contain the ``retrieval_path_summary``
   key (including dry-run and no-question code paths).
"""
from __future__ import annotations

import pytest

from demo.stages.retrieval_and_qa import (
    _build_retrieval_path_diagnostics,
    _format_claim_details,
    _format_retrieval_path_summary,
    _normalize_claim_roles,
)


# ---------------------------------------------------------------------------
# Helpers — sample data fixtures shared across test classes
# ---------------------------------------------------------------------------

_CLAIM_DETAILS_FULL = [
    {
        "claim_text": "Marcos Galperin founded MercadoLibre.",
        "subject_mention": {"name": "Marcos Galperin", "match_method": "raw_exact"},
        "object_mention": {"name": "MercadoLibre", "match_method": "casefold_exact"},
    },
    {
        "claim_text": "MercadoLibre operates in Latin America.",
        "subject_mention": {"name": "MercadoLibre", "match_method": "raw_exact"},
        "object_mention": None,
    },
]

_CLAIM_DETAILS_NO_ROLES = [
    {
        "claim_text": "Some claim with no resolved participants.",
        "subject_mention": None,
        "object_mention": None,
    },
]

_CANONICAL_ENTITIES = ["Marcos Galperin", "MercadoLibre Inc."]

_CLUSTER_MEMBERSHIPS = [
    {
        "cluster_id": "cluster_001",
        "cluster_name": "MercadoLibre",
        "membership_status": "accepted",
        "membership_method": "exact",
    },
    {
        "cluster_id": "cluster_002",
        "cluster_name": "Marcos Galperin",
        "membership_status": "provisional",
        "membership_method": "fuzzy",
    },
]

_CLUSTER_CANONICAL_ALIGNMENTS = [
    {
        "canonical_name": "MercadoLibre Inc.",
        "alignment_method": "embedding_similarity",
        "alignment_status": "aligned",
    },
]


# ---------------------------------------------------------------------------
# _build_retrieval_path_diagnostics tests
# ---------------------------------------------------------------------------


class TestBuildRetrievalPathDiagnostics:
    """_build_retrieval_path_diagnostics assembles structured provenance correctly."""

    def test_empty_inputs_returns_empty_lists(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        assert result["has_participant_edges"] == []
        assert result["canonical_via_resolves_to"] == []
        assert result["cluster_memberships"] == []
        assert result["cluster_canonical_via_aligned_with"] == []

    def test_result_has_expected_top_level_keys(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        assert set(result.keys()) == {
            "has_participant_edges",
            "canonical_via_resolves_to",
            "cluster_memberships",
            "cluster_canonical_via_aligned_with",
        }

    def test_has_participant_edges_extracts_subject_and_object(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=_CLAIM_DETAILS_FULL,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 2

        first = edges[0]
        assert first["claim_text"] == "Marcos Galperin founded MercadoLibre."
        roles = first["roles"]
        assert len(roles) == 2
        subject_role = next(r for r in roles if r["role"] == "subject")
        assert subject_role["mention_name"] == "Marcos Galperin"
        assert subject_role["match_method"] == "raw_exact"
        object_role = next(r for r in roles if r["role"] == "object")
        assert object_role["mention_name"] == "MercadoLibre"
        assert object_role["match_method"] == "casefold_exact"

    def test_has_participant_edges_omits_none_slots(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=_CLAIM_DETAILS_FULL,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        second = edges[1]
        assert second["claim_text"] == "MercadoLibre operates in Latin America."
        # Only subject slot is filled; object_mention is None
        roles = second["roles"]
        assert len(roles) == 1
        assert roles[0]["role"] == "subject"

    def test_has_participant_edges_empty_roles_for_unresolved_claims(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=_CLAIM_DETAILS_NO_ROLES,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 1
        assert edges[0]["roles"] == []

    def test_claim_without_text_is_skipped(self) -> None:
        claim_details_with_empty = [
            {"claim_text": "", "subject_mention": None, "object_mention": None},
            {"claim_text": "  ", "subject_mention": None, "object_mention": None},
            {"claim_text": "Real claim.", "subject_mention": None, "object_mention": None},
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details_with_empty,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        assert len(result["has_participant_edges"]) == 1
        assert result["has_participant_edges"][0]["claim_text"] == "Real claim."

    def test_canonical_via_resolves_to_preserved(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=_CANONICAL_ENTITIES,
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        assert result["canonical_via_resolves_to"] == list(_CANONICAL_ENTITIES)

    def test_canonical_via_resolves_to_is_copy(self) -> None:
        original = ["Entity A"]
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=original,
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        result["canonical_via_resolves_to"].append("Entity B")
        assert original == ["Entity A"]  # original not mutated

    def test_cluster_memberships_preserved(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=[],
            cluster_memberships=_CLUSTER_MEMBERSHIPS,
            cluster_canonical_alignments=[],
        )
        memberships = result["cluster_memberships"]
        assert len(memberships) == 2
        assert memberships[0]["cluster_name"] == "MercadoLibre"
        assert memberships[0]["membership_status"] == "accepted"
        assert memberships[1]["cluster_name"] == "Marcos Galperin"
        assert memberships[1]["membership_status"] == "provisional"

    def test_cluster_canonical_via_aligned_with_preserved(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=[],
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=_CLUSTER_CANONICAL_ALIGNMENTS,
        )
        alignments = result["cluster_canonical_via_aligned_with"]
        assert len(alignments) == 1
        assert alignments[0]["canonical_name"] == "MercadoLibre Inc."
        assert alignments[0]["alignment_method"] == "embedding_similarity"
        assert alignments[0]["alignment_status"] == "aligned"

    def test_full_inputs_returns_all_populated(self) -> None:
        result = _build_retrieval_path_diagnostics(
            claim_details=_CLAIM_DETAILS_FULL,
            canonical_entities=_CANONICAL_ENTITIES,
            cluster_memberships=_CLUSTER_MEMBERSHIPS,
            cluster_canonical_alignments=_CLUSTER_CANONICAL_ALIGNMENTS,
        )
        assert len(result["has_participant_edges"]) == 2
        assert len(result["canonical_via_resolves_to"]) == 2
        assert len(result["cluster_memberships"]) == 2
        assert len(result["cluster_canonical_via_aligned_with"]) == 1

    # ------------------------------------------------------------------
    # New-format (roles list) and arbitrary-role tests
    # ------------------------------------------------------------------

    def test_new_format_roles_list_subject_and_object(self) -> None:
        """New ``roles`` list format must be mapped to has_participant_edges correctly."""
        claim_details = [
            {
                "claim_text": "A acquired B.",
                "roles": [
                    {"role": "subject", "mention_name": "A", "match_method": "raw_exact"},
                    {"role": "object", "mention_name": "B", "match_method": "casefold_exact"},
                ],
            }
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 1
        assert edges[0]["claim_text"] == "A acquired B."
        roles = edges[0]["roles"]
        assert len(roles) == 2
        assert any(r["role"] == "subject" and r["mention_name"] == "A" for r in roles)
        assert any(r["role"] == "object" and r["mention_name"] == "B" for r in roles)

    def test_new_format_arbitrary_roles(self) -> None:
        """Arbitrary roles (e.g. agent, target) in the new ``roles`` list must be
        passed through to has_participant_edges without being filtered or renamed."""
        claim_details = [
            {
                "claim_text": "The board approved the merger.",
                "roles": [
                    {"role": "agent", "mention_name": "The board", "match_method": "casefold_exact"},
                    {"role": "target", "mention_name": "the merger", "match_method": "normalized_exact"},
                ],
            }
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 1
        roles = edges[0]["roles"]
        assert any(r["role"] == "agent" and r["mention_name"] == "The board" for r in roles)
        assert any(r["role"] == "target" and r["mention_name"] == "the merger" for r in roles)

    def test_new_format_empty_roles_list(self) -> None:
        """New format with an empty ``roles`` list must produce an entry with empty roles."""
        claim_details = [
            {"claim_text": "Unresolved claim.", "roles": []}
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 1
        assert edges[0]["roles"] == []

    def test_new_format_mixed_subject_object_and_extra_role(self) -> None:
        """New format with subject, object, and an extra role must preserve all three."""
        claim_details = [
            {
                "claim_text": "Smith transferred assets to Corp.",
                "roles": [
                    {"role": "subject", "mention_name": "assets", "match_method": "raw_exact"},
                    {"role": "object", "mention_name": "Corp", "match_method": "raw_exact"},
                    {"role": "agent", "mention_name": "Smith", "match_method": "casefold_exact"},
                ],
            }
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        roles = result["has_participant_edges"][0]["roles"]
        assert len(roles) == 3
        role_names = {r["role"] for r in roles}
        assert role_names == {"subject", "object", "agent"}




def _make_hit(
    chunk_id: str,
    score: float = 0.9,
    *,
    include_diagnostics: bool = True,
    claim_details: list | None = None,
    canonical_entities: list | None = None,
    cluster_memberships: list | None = None,
    cluster_canonical_alignments: list | None = None,
) -> dict:
    """Build a minimal hit dict as produced by run_retrieval_and_qa."""
    diag = None
    if include_diagnostics:
        diag = _build_retrieval_path_diagnostics(
            claim_details=claim_details or [],
            canonical_entities=canonical_entities or [],
            cluster_memberships=cluster_memberships or [],
            cluster_canonical_alignments=cluster_canonical_alignments or [],
        )
    return {
        "content": "chunk text",
        "metadata": {
            "chunk_id": chunk_id,
            "score": score,
            "retrieval_path_diagnostics": diag,
        },
    }


class TestFormatRetrievalPathSummary:
    """_format_retrieval_path_summary produces correct human-readable output."""

    def test_empty_hits_returns_empty_string(self) -> None:
        assert _format_retrieval_path_summary([]) == ""

    def test_output_starts_with_header(self) -> None:
        hit = _make_hit("chunk_001")
        result = _format_retrieval_path_summary([hit])
        assert result.startswith("=== Retrieval Path Summary ===")

    def test_single_hit_chunk_id_appears(self) -> None:
        hit = _make_hit("chunk_42")
        result = _format_retrieval_path_summary([hit])
        assert "chunk_id='chunk_42'" in result

    def test_single_hit_score_appears(self) -> None:
        hit = _make_hit("chunk_42", score=0.8765)
        result = _format_retrieval_path_summary([hit])
        assert "0.8765" in result

    def test_score_formatted_to_4dp_for_int_like_values(self) -> None:
        """Integer-like scores (e.g., from Neo4j or numpy) should still render as 4dp."""
        hit = _make_hit("chunk_42", score=1)
        result = _format_retrieval_path_summary([hit])
        assert "1.0000" in result

    def test_score_falls_back_to_str_for_non_numeric(self) -> None:
        """Non-numeric score values must not raise; fallback to str() representation."""
        hit = _make_hit("chunk_42")
        hit["metadata"]["score"] = None
        result = _format_retrieval_path_summary([hit])
        assert "score=None" in result

    def test_hit_without_diagnostics_shows_note(self) -> None:
        hit = _make_hit("chunk_x", include_diagnostics=False)
        result = _format_retrieval_path_summary([hit])
        assert "no retrieval-path diagnostics" in result

    def test_hit_number_increments(self) -> None:
        hits = [_make_hit("c1"), _make_hit("c2"), _make_hit("c3")]
        result = _format_retrieval_path_summary(hits)
        assert "Hit 1:" in result
        assert "Hit 2:" in result
        assert "Hit 3:" in result

    def test_has_participant_edges_section_present(self) -> None:
        hit = _make_hit("c1", claim_details=_CLAIM_DETAILS_FULL)
        result = _format_retrieval_path_summary([hit])
        assert "HAS_PARTICIPANT edges" in result

    def test_has_participant_edges_shows_claim_text_preview(self) -> None:
        hit = _make_hit("c1", claim_details=_CLAIM_DETAILS_FULL)
        result = _format_retrieval_path_summary([hit])
        assert "Marcos Galperin founded MercadoLibre" in result

    def test_has_participant_edges_shows_role_and_method(self) -> None:
        hit = _make_hit("c1", claim_details=_CLAIM_DETAILS_FULL)
        result = _format_retrieval_path_summary([hit])
        assert "subject=" in result
        assert "raw_exact" in result

    def test_no_resolved_roles_label_for_empty_roles(self) -> None:
        hit = _make_hit("c1", claim_details=_CLAIM_DETAILS_NO_ROLES)
        result = _format_retrieval_path_summary([hit])
        assert "no resolved roles" in result

    def test_no_participant_edges_when_empty(self) -> None:
        hit = _make_hit("c1")
        result = _format_retrieval_path_summary([hit])
        assert "HAS_PARTICIPANT edges: (none)" in result

    def test_resolves_to_section_shows_canonical_names(self) -> None:
        hit = _make_hit("c1", canonical_entities=_CANONICAL_ENTITIES)
        result = _format_retrieval_path_summary([hit])
        assert "RESOLVES_TO" in result
        assert "Marcos Galperin" in result

    def test_resolves_to_none_when_empty(self) -> None:
        hit = _make_hit("c1")
        result = _format_retrieval_path_summary([hit])
        assert "RESOLVES_TO canonical entities: (none)" in result

    def test_cluster_memberships_section_shows_cluster_name(self) -> None:
        hit = _make_hit("c1", cluster_memberships=_CLUSTER_MEMBERSHIPS)
        result = _format_retrieval_path_summary([hit])
        assert "Cluster memberships" in result
        assert "MercadoLibre" in result

    def test_cluster_memberships_shows_status_and_method(self) -> None:
        hit = _make_hit("c1", cluster_memberships=_CLUSTER_MEMBERSHIPS)
        result = _format_retrieval_path_summary([hit])
        assert "accepted" in result
        assert "exact" in result

    def test_cluster_memberships_none_when_empty(self) -> None:
        hit = _make_hit("c1")
        result = _format_retrieval_path_summary([hit])
        assert "Cluster memberships (MEMBER_OF): (none)" in result

    def test_aligned_with_section_shows_canonical_name(self) -> None:
        hit = _make_hit("c1", cluster_canonical_alignments=_CLUSTER_CANONICAL_ALIGNMENTS)
        result = _format_retrieval_path_summary([hit])
        assert "ALIGNED_WITH" in result
        assert "MercadoLibre Inc." in result

    def test_aligned_with_none_when_empty(self) -> None:
        hit = _make_hit("c1")
        result = _format_retrieval_path_summary([hit])
        assert "Canonical via ALIGNED_WITH: (none)" in result

    def test_fully_populated_hit(self) -> None:
        hit = _make_hit(
            "c1",
            score=0.95,
            claim_details=_CLAIM_DETAILS_FULL,
            canonical_entities=_CANONICAL_ENTITIES,
            cluster_memberships=_CLUSTER_MEMBERSHIPS,
            cluster_canonical_alignments=_CLUSTER_CANONICAL_ALIGNMENTS,
        )
        result = _format_retrieval_path_summary([hit])
        assert "=== Retrieval Path Summary ===" in result
        assert "chunk_id='c1'" in result
        assert "0.9500" in result
        assert "HAS_PARTICIPANT edges" in result
        assert "Marcos Galperin founded MercadoLibre" in result
        assert "RESOLVES_TO" in result
        assert "Cluster memberships" in result
        assert "ALIGNED_WITH" in result

    def test_long_claim_text_is_truncated(self) -> None:
        long_text = "A" * 100
        claim_details = [
            {"claim_text": long_text, "subject_mention": None, "object_mention": None}
        ]
        hit = _make_hit("c1", claim_details=claim_details)
        result = _format_retrieval_path_summary([hit])
        # Preview limited to 80 chars + "..."
        assert "..." in result
        assert "A" * 81 not in result

    def test_multiple_hits_all_appear(self) -> None:
        hits = [
            _make_hit("chunk_A", canonical_entities=["Entity X"]),
            _make_hit("chunk_B", cluster_memberships=_CLUSTER_MEMBERSHIPS),
        ]
        result = _format_retrieval_path_summary(hits)
        assert "chunk_A" in result
        assert "chunk_B" in result
        assert "Entity X" in result
        assert "MercadoLibre" in result

    # ------------------------------------------------------------------
    # Malformed / partial roles payload safety
    # ------------------------------------------------------------------

    def test_malformed_roles_payload_does_not_crash(self) -> None:
        """Non-dict entries in a diagnostics roles list must not raise."""
        hit = _make_hit("c_malformed")
        # Inject a pre-built diagnostics dict with non-dict role entries directly,
        # bypassing _build_retrieval_path_diagnostics which already normalizes.
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [
                {
                    "claim_text": "Claim with bad roles.",
                    "roles": [None, "bad-entry", 42],
                }
            ],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "Claim with bad roles." in result
        assert "malformed" in result

    def test_partial_role_entry_renders_gracefully(self) -> None:
        """Dict role entries missing role/mention_name/match_method must not raise."""
        hit = _make_hit("c_partial")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [
                {
                    "claim_text": "Claim with partial role.",
                    "roles": [
                        {"role": "subject"},  # mention_name and match_method missing
                        {"mention_name": "Bob"},  # role and match_method missing
                    ],
                }
            ],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "Claim with partial role." in result
        assert "(unknown)" in result

    # ------------------------------------------------------------------
    # Malformed non-role diagnostics payload safety
    # ------------------------------------------------------------------

    def test_malformed_diagnostics_root_not_dict_does_not_crash(self) -> None:
        """A non-dict diagnostics root must not raise; emits a degraded note."""
        for bad_root in ["a string", 42, ["a", "list"], True]:
            hit = _make_hit("c_bad_root")
            hit["metadata"]["retrieval_path_diagnostics"] = bad_root
            result = _format_retrieval_path_summary([hit])
            assert "malformed" in result, f"expected 'malformed' in output for root={bad_root!r}"

    def test_malformed_diagnostics_root_not_dict_still_shows_chunk_id(self) -> None:
        """chunk_id must still appear even when the diagnostics root is malformed."""
        hit = _make_hit("c_bad_root_id")
        hit["metadata"]["retrieval_path_diagnostics"] = "not a dict"
        result = _format_retrieval_path_summary([hit])
        assert "c_bad_root_id" in result

    def test_malformed_has_participant_edges_not_list_does_not_crash(self) -> None:
        """A non-list has_participant_edges field must not raise; emits degraded note."""
        hit = _make_hit("c_hp_notlist")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": {"claim_text": "oops", "roles": []},
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_malformed_hp_edge_entry_not_dict_does_not_crash(self) -> None:
        """Non-dict entries in has_participant_edges list must not raise."""
        hit = _make_hit("c_hp_entry_bad")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": ["not a dict", 99, None],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_malformed_cluster_memberships_not_list_does_not_crash(self) -> None:
        """A non-list cluster_memberships field must not raise; emits degraded note."""
        hit = _make_hit("c_mem_notlist")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": "should-be-a-list",
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_malformed_membership_entry_not_dict_does_not_crash(self) -> None:
        """Non-dict entries in cluster_memberships list must not raise."""
        hit = _make_hit("c_mem_entry_bad")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": ["bad-entry", 42],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_partial_membership_entry_renders_gracefully(self) -> None:
        """Membership dict entries missing expected keys must not raise."""
        hit = _make_hit("c_mem_partial")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [
                {"cluster_name": "SomeCluster"},  # status and method missing
                {"membership_status": "provisional"},  # name/id and method missing
            ],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "Cluster memberships" in result
        assert "SomeCluster" in result

    def test_malformed_alignments_not_list_does_not_crash(self) -> None:
        """A non-list cluster_canonical_via_aligned_with field must not raise."""
        hit = _make_hit("c_al_notlist")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": {"canonical_name": "oops"},
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_malformed_alignment_entry_not_dict_does_not_crash(self) -> None:
        """Non-dict entries in cluster_canonical_via_aligned_with list must not raise."""
        hit = _make_hit("c_al_entry_bad")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": ["bad-entry", 99],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_partial_alignment_entry_renders_gracefully(self) -> None:
        """Alignment dict entries missing expected keys must not raise."""
        hit = _make_hit("c_al_partial")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": [],
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [
                {"canonical_name": "PartialCanon"},  # method and status missing
                {"alignment_method": "embedding"},   # name and status missing
            ],
        }
        result = _format_retrieval_path_summary([hit])
        assert "ALIGNED_WITH" in result
        assert "PartialCanon" in result

    def test_malformed_resolves_to_not_list_does_not_crash(self) -> None:
        """A non-list canonical_via_resolves_to field must not raise."""
        hit = _make_hit("c_rt_notlist")
        hit["metadata"]["retrieval_path_diagnostics"] = {
            "has_participant_edges": [],
            "canonical_via_resolves_to": "not-a-list",
            "cluster_memberships": [],
            "cluster_canonical_via_aligned_with": [],
        }
        result = _format_retrieval_path_summary([hit])
        assert "malformed" in result

    def test_well_formed_payload_unaffected_by_hardening(self) -> None:
        """Hardening must not change output for fully well-formed payloads."""
        hit = _make_hit(
            "c_wellformed",
            score=0.95,
            claim_details=_CLAIM_DETAILS_FULL,
            canonical_entities=_CANONICAL_ENTITIES,
            cluster_memberships=_CLUSTER_MEMBERSHIPS,
            cluster_canonical_alignments=_CLUSTER_CANONICAL_ALIGNMENTS,
        )
        result = _format_retrieval_path_summary([hit])
        assert "=== Retrieval Path Summary ===" in result
        assert "chunk_id='c_wellformed'" in result
        assert "HAS_PARTICIPANT edges" in result
        assert "RESOLVES_TO" in result
        assert "Cluster memberships" in result
        assert "ALIGNED_WITH" in result
        assert "malformed" not in result


# ---------------------------------------------------------------------------
# Integration: _chunk_citation_formatter injects retrieval_path_diagnostics
# ---------------------------------------------------------------------------


class TestChunkCitationFormatterInjectsDiagnostics:
    """_chunk_citation_formatter must include retrieval_path_diagnostics in metadata."""

    def _make_record(self, **overrides: object) -> dict:
        """Return a minimal fake record dict that _chunk_citation_formatter can process."""
        base = {
            "chunk_id": "test_chunk",
            "run_id": "run_001",
            "source_uri": "file:///test.pdf",
            "chunk_index": 0,
            "page": 1,
            "start_char": 0,
            "end_char": 100,
            "chunk_text": "Some chunk text.",
            "similarityScore": 0.85,
            "claim_details": None,
            "cluster_memberships": None,
            "cluster_canonical_alignments": None,
            "canonical_entities": None,
            "claims": None,
            "mentions": None,
        }
        base.update(overrides)
        return base

    def _call_formatter(self, record_dict: dict):
        """Call _chunk_citation_formatter with a dict-backed fake neo4j.Record."""
        from demo.stages.retrieval_and_qa import _chunk_citation_formatter

        class FakeRecord:
            def __init__(self, data: dict) -> None:
                self._data = data

            def get(self, key: str, default=None):
                return self._data.get(key, default)

        return _chunk_citation_formatter(FakeRecord(record_dict))

    def test_metadata_contains_retrieval_path_diagnostics_key(self) -> None:
        record = self._make_record()
        item = self._call_formatter(record)
        assert "retrieval_path_diagnostics" in item.metadata

    def test_base_query_diagnostics_has_empty_has_participant_edges(self) -> None:
        record = self._make_record()
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        assert diag["has_participant_edges"] == []

    def test_base_query_diagnostics_has_empty_canonical_via_resolves_to(self) -> None:
        record = self._make_record()
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        assert diag["canonical_via_resolves_to"] == []

    def test_with_claim_details_populates_has_participant_edges(self) -> None:
        record = self._make_record(
            claim_details=[
                {
                    "claim_text": "A founded B.",
                    "subject_mention": {"name": "A", "match_method": "raw_exact"},
                    "object_mention": {"name": "B", "match_method": "casefold_exact"},
                }
            ]
        )
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        edges = diag["has_participant_edges"]
        assert len(edges) == 1
        assert edges[0]["claim_text"] == "A founded B."
        roles = edges[0]["roles"]
        assert any(r["role"] == "subject" and r["mention_name"] == "A" for r in roles)
        assert any(r["role"] == "object" and r["mention_name"] == "B" for r in roles)

    def test_with_canonical_entities_populates_canonical_via_resolves_to(self) -> None:
        record = self._make_record(canonical_entities=["CanonA", "CanonB"])
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        assert diag["canonical_via_resolves_to"] == ["CanonA", "CanonB"]

    def test_with_cluster_memberships_populates_cluster_memberships(self) -> None:
        record = self._make_record(
            cluster_memberships=[
                {
                    "cluster_id": "c1",
                    "cluster_name": "TestCluster",
                    "membership_status": "accepted",
                    "membership_method": "exact",
                }
            ]
        )
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        assert len(diag["cluster_memberships"]) == 1
        assert diag["cluster_memberships"][0]["cluster_name"] == "TestCluster"

    def test_with_cluster_canonical_alignments_populates_aligned_with(self) -> None:
        record = self._make_record(
            cluster_canonical_alignments=[
                {
                    "canonical_name": "Canon Entity",
                    "alignment_method": "embedding",
                    "alignment_status": "aligned",
                }
            ]
        )
        item = self._call_formatter(record)
        diag = item.metadata["retrieval_path_diagnostics"]
        assert len(diag["cluster_canonical_via_aligned_with"]) == 1
        assert diag["cluster_canonical_via_aligned_with"][0]["canonical_name"] == "Canon Entity"

    def test_diagnostics_do_not_alter_citation_token(self) -> None:
        record = self._make_record(
            claim_details=[
                {
                    "claim_text": "Some claim.",
                    "subject_mention": {"name": "X", "match_method": "raw_exact"},
                    "object_mention": None,
                }
            ]
        )
        item = self._call_formatter(record)
        # citation token must still be present and unmodified
        assert item.metadata.get("citation_token")
        token = str(item.metadata["citation_token"])
        assert token.startswith("[CITATION|")
        assert token.endswith("]")

    def test_diagnostics_do_not_alter_content(self) -> None:
        chunk_text = "The chunk content."
        record = self._make_record(chunk_text=chunk_text)
        item_without = self._call_formatter(record)

        record_with = self._make_record(
            chunk_text=chunk_text,
            claim_details=[
                {
                    "claim_text": "A founded B.",
                    "subject_mention": {"name": "A", "match_method": "raw_exact"},
                    "object_mention": None,
                }
            ],
        )
        item_with = self._call_formatter(record_with)

        # diagnostics field is new; citation token and core content must be the same
        assert item_without.metadata["citation_token"] == item_with.metadata["citation_token"]
        assert chunk_text in item_without.content
        assert chunk_text in item_with.content


# ---------------------------------------------------------------------------
# Integration: run_retrieval_and_qa base dict always has retrieval_path_summary
# ---------------------------------------------------------------------------


class TestRunRetrievalAndQaIncludesRetrievalPathSummary:
    """run_retrieval_and_qa result dicts must always contain retrieval_path_summary."""

    def _make_dry_run_config(self):
        class DryRunConfig:
            dry_run = True
            openai_model = "gpt-4o"

        return DryRunConfig()

    def test_dry_run_result_has_retrieval_path_summary(self) -> None:
        from demo.stages.retrieval_and_qa import run_retrieval_and_qa

        result = run_retrieval_and_qa(
            self._make_dry_run_config(),
            run_id="test_run",
            question="Who founded MercadoLibre?",
        )
        assert "retrieval_path_summary" in result
        assert result["retrieval_path_summary"] == ""

    def test_dry_run_with_expand_graph_has_retrieval_path_summary(self) -> None:
        from demo.stages.retrieval_and_qa import run_retrieval_and_qa

        result = run_retrieval_and_qa(
            self._make_dry_run_config(),
            run_id="test_run",
            question="Who founded MercadoLibre?",
            expand_graph=True,
        )
        assert "retrieval_path_summary" in result
        assert result["retrieval_path_summary"] == ""

    def test_dry_run_with_cluster_aware_has_retrieval_path_summary(self) -> None:
        from demo.stages.retrieval_and_qa import run_retrieval_and_qa

        result = run_retrieval_and_qa(
            self._make_dry_run_config(),
            run_id="test_run",
            question="Who founded MercadoLibre?",
            cluster_aware=True,
        )
        assert "retrieval_path_summary" in result
        assert result["retrieval_path_summary"] == ""


# ---------------------------------------------------------------------------
# _normalize_claim_roles: canonical normalization and malformed-payload safety
# ---------------------------------------------------------------------------


class TestNormalizeClaimRoles:
    """_normalize_claim_roles produces a canonical sorted list and handles bad input."""

    # --- new ``roles`` format -----------------------------------------------

    def test_new_format_returns_canonical_entries(self) -> None:
        detail = {
            "roles": [
                {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                {"role": "object", "mention_name": "Bob", "match_method": "casefold_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 2
        assert result[0] == {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"}
        assert result[1] == {"role": "object", "mention_name": "Bob", "match_method": "casefold_exact"}

    def test_new_format_sorts_subject_first(self) -> None:
        detail = {
            "roles": [
                {"role": "object", "mention_name": "Corp", "match_method": "raw_exact"},
                {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert result[0]["role"] == "subject"
        assert result[1]["role"] == "object"

    def test_new_format_empty_list_returns_empty(self) -> None:
        assert _normalize_claim_roles({"roles": []}) == []

    # --- legacy format ------------------------------------------------------

    def test_legacy_format_subject_and_object(self) -> None:
        detail = {
            "subject_mention": {"name": "Galperin", "match_method": "raw_exact"},
            "object_mention": {"name": "MercadoLibre", "match_method": "casefold_exact"},
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 2
        assert result[0]["role"] == "subject"
        assert result[0]["mention_name"] == "Galperin"
        assert result[1]["role"] == "object"
        assert result[1]["mention_name"] == "MercadoLibre"

    def test_legacy_format_only_subject(self) -> None:
        detail = {
            "subject_mention": {"name": "Galperin", "match_method": "raw_exact"},
            "object_mention": None,
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 1
        assert result[0]["role"] == "subject"

    def test_no_roles_key_and_no_legacy_keys_returns_empty(self) -> None:
        assert _normalize_claim_roles({"claim_text": "Some claim."}) == []

    # --- malformed / partial payload safety ---------------------------------

    def test_none_entry_in_roles_list_is_filtered(self) -> None:
        """None entries inside the ``roles`` list must be silently dropped."""
        detail = {
            "roles": [
                None,
                {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 1
        assert result[0]["role"] == "subject"

    def test_non_dict_entry_in_roles_list_is_filtered(self) -> None:
        """Non-dict entries (e.g. strings) inside ``roles`` must be silently dropped."""
        detail = {
            "roles": [
                "bad-entry",
                {"role": "object", "mention_name": "Corp", "match_method": "raw_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 1
        assert result[0]["role"] == "object"

    def test_non_list_roles_value_returns_empty(self) -> None:
        """If ``roles`` is present but not a list (e.g. a plain string), return empty."""
        assert _normalize_claim_roles({"roles": "not-a-list"}) == []
        assert _normalize_claim_roles({"roles": 42}) == []
        assert _normalize_claim_roles({"roles": {"role": "subject"}}) == []

    def test_entry_missing_role_key_is_filtered(self) -> None:
        """Entries without a ``role`` key (or with a falsy role) must be dropped."""
        detail = {
            "roles": [
                {"mention_name": "Unknown", "match_method": "raw_exact"},  # no role key
                {"role": "", "mention_name": "Empty", "match_method": "raw_exact"},  # empty role
                {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 1
        assert result[0]["role"] == "subject"

    def test_partially_populated_entry_preserved(self) -> None:
        """An entry with a valid role but missing mention_name/match_method should survive."""
        detail = {
            "roles": [
                {"role": "subject"},  # mention_name and match_method absent
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 1
        assert result[0]["role"] == "subject"
        assert result[0]["mention_name"] is None
        assert result[0]["match_method"] is None

    def test_mixed_valid_and_malformed_entries(self) -> None:
        """A mix of valid entries and malformed ones returns only the valid entries."""
        detail = {
            "roles": [
                None,
                "garbage",
                {"mention_name": "no-role"},
                {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                {"role": "object", "mention_name": "Corp", "match_method": "casefold_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 2
        assert result[0]["role"] == "subject"
        assert result[1]["role"] == "object"

    def test_legacy_name_key_used_as_mention_name_fallback(self) -> None:
        """Entries using the old ``name`` key (instead of ``mention_name``) must be
        normalised: ``mention_name`` in the returned entry must be the value of ``name``."""
        detail = {
            "roles": [
                {"role": "subject", "name": "Alice", "match_method": "raw_exact"},
                {"role": "object", "name": "Corp", "match_method": "casefold_exact"},
            ]
        }
        result = _normalize_claim_roles(detail)
        assert len(result) == 2
        assert result[0]["mention_name"] == "Alice"
        assert result[1]["mention_name"] == "Corp"

    def test_mention_name_takes_precedence_over_name(self) -> None:
        """When both ``mention_name`` and ``name`` are present, ``mention_name`` wins."""
        detail = {
            "roles": [
                {
                    "role": "subject",
                    "mention_name": "Alice",
                    "name": "AliceLegacy",
                    "match_method": "raw_exact",
                },
            ]
        }
        result = _normalize_claim_roles(detail)
        assert result[0]["mention_name"] == "Alice"

    def test_build_retrieval_path_diagnostics_tolerates_malformed_roles(self) -> None:
        """_build_retrieval_path_diagnostics must not crash when roles contains
        None/non-dict entries — it should produce a clean roles list via the helper."""
        claim_details = [
            {
                "claim_text": "Claim with bad roles.",
                "roles": [
                    None,
                    "garbage",
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                ],
            }
        ]
        result = _build_retrieval_path_diagnostics(
            claim_details=claim_details,
            canonical_entities=[],
            cluster_memberships=[],
            cluster_canonical_alignments=[],
        )
        edges = result["has_participant_edges"]
        assert len(edges) == 1
        assert edges[0]["claim_text"] == "Claim with bad roles."
        roles = edges[0]["roles"]
        assert len(roles) == 1
        assert roles[0]["role"] == "subject"
        assert roles[0]["mention_name"] == "Alice"


# ---------------------------------------------------------------------------
# _format_claim_details: malformed and partial payload safety
# ---------------------------------------------------------------------------


class TestFormatClaimDetails:
    """_format_claim_details must not crash on malformed/partial role payloads
    and must render sensible output across all supported input shapes."""

    def test_empty_claim_details_returns_empty_string(self) -> None:
        assert _format_claim_details([]) == ""

    def test_claim_with_no_roles_key_renders_claim_text(self) -> None:
        """When the ``roles`` key is absent, the claim text is shown without role annotations."""
        result = _format_claim_details([{"claim_text": "Some claim."}])
        assert "Some claim." in result
        assert "subject=" not in result  # no role annotation

    def test_non_list_roles_value_does_not_crash(self) -> None:
        """A non-list ``roles`` value must be silently ignored; claim text still appears."""
        details = [{"claim_text": "Claim here.", "roles": "bad-roles-value"}]
        result = _format_claim_details(details)
        assert "Claim here." in result

    def test_non_list_roles_integer_does_not_crash(self) -> None:
        """An integer ``roles`` value must be silently ignored."""
        details = [{"claim_text": "Claim here.", "roles": 99}]
        result = _format_claim_details(details)
        assert "Claim here." in result

    def test_roles_with_none_entries_does_not_crash(self) -> None:
        """None entries inside ``roles`` list must be filtered; valid roles still rendered."""
        details = [
            {
                "claim_text": "Alice joined Corp.",
                "roles": [
                    None,
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "Alice joined Corp." in result
        assert "subject='Alice'" in result

    def test_roles_with_non_dict_entries_does_not_crash(self) -> None:
        """Non-dict entries (e.g. strings) inside ``roles`` must be filtered."""
        details = [
            {
                "claim_text": "Bob left Corp.",
                "roles": [
                    "garbage",
                    {"role": "object", "mention_name": "Corp", "match_method": "casefold_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "Bob left Corp." in result
        assert "object='Corp'" in result

    def test_entry_missing_role_key_is_filtered_in_output(self) -> None:
        """Role entries missing the ``role`` key must be skipped; claim still rendered."""
        details = [
            {
                "claim_text": "Claim with no-role entry.",
                "roles": [
                    {"mention_name": "Ghost", "match_method": "raw_exact"},  # no role key
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "Claim with no-role entry." in result
        assert "subject='Alice'" in result
        assert "Ghost" not in result

    def test_mention_name_shown_in_output(self) -> None:
        """The canonical ``mention_name`` field must appear in the formatted output."""
        details = [
            {
                "claim_text": "Alice founded Corp.",
                "roles": [
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                    {"role": "object", "mention_name": "Corp", "match_method": "casefold_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "subject='Alice'" in result
        assert "object='Corp'" in result

    def test_legacy_name_key_rendered_as_mention_name(self) -> None:
        """Entries using the old ``name`` key (instead of ``mention_name``) must still
        appear correctly labelled in the output."""
        details = [
            {
                "claim_text": "Alice founded Corp.",
                "roles": [
                    {"role": "subject", "name": "Alice", "match_method": "raw_exact"},
                    {"role": "object", "name": "Corp", "match_method": "casefold_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "subject='Alice'" in result
        assert "object='Corp'" in result

    def test_mixed_valid_and_malformed_roles_shows_only_valid(self) -> None:
        """Mixed valid/malformed roles list: only the valid entries appear in output."""
        details = [
            {
                "claim_text": "Mixed claim.",
                "roles": [
                    None,
                    "bad-entry",
                    {"mention_name": "no-role"},
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                ],
            }
        ]
        result = _format_claim_details(details)
        assert "Mixed claim." in result
        assert "subject='Alice'" in result
        assert "no-role" not in result

    def test_partially_populated_role_with_no_mention_name_rendered_without_role_annotation(
        self,
    ) -> None:
        """An entry with a valid ``role`` but no ``mention_name`` must not produce a
        role annotation (role_name and mention_name are both required for annotation)."""
        details = [
            {
                "claim_text": "Claim with sparse role.",
                "roles": [{"role": "subject"}],  # mention_name absent
            }
        ]
        result = _format_claim_details(details)
        assert "Claim with sparse role." in result
        # No role annotation because mention_name is absent
        assert "subject=" not in result

    def test_legacy_subject_and_object_mention_rendered(self) -> None:
        """Legacy ``subject_mention``/``object_mention`` top-level keys produce role annotations."""
        details = [
            {
                "claim_text": "Galperin founded MercadoLibre.",
                "subject_mention": {"name": "Galperin", "match_method": "raw_exact"},
                "object_mention": {"name": "MercadoLibre", "match_method": "casefold_exact"},
            }
        ]
        result = _format_claim_details(details)
        assert "Galperin founded MercadoLibre." in result
        assert "subject='Galperin'" in result
        assert "object='MercadoLibre'" in result

    def test_multiple_claims_all_rendered(self) -> None:
        """Multiple claims are all included in the formatted output."""
        details = [
            {
                "claim_text": "Alice founded Corp.",
                "roles": [
                    {"role": "subject", "mention_name": "Alice", "match_method": "raw_exact"},
                ],
            },
            {
                "claim_text": "Corp operates globally.",
                "roles": [],
            },
        ]
        result = _format_claim_details(details)
        assert "Alice founded Corp." in result
        assert "Corp operates globally." in result

    def test_claim_with_empty_claim_text_skipped(self) -> None:
        """Claims whose ``claim_text`` is empty or whitespace-only must be skipped."""
        details = [
            {"claim_text": "   ", "roles": []},
            {"claim_text": "Valid claim.", "roles": []},
        ]
        result = _format_claim_details(details)
        assert "Valid claim." in result
        assert result.count("•") == 1
