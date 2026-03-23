"""Integration tests for claim participation edge scoping and idempotency invariants.

These tests exercise ``build_participation_edges`` and ``write_participation_edges``
together against an in-memory graph simulation that faithfully implements Neo4j MERGE
semantics.  Unlike the unit tests in ``test_claim_participation.py``, they verify
invariants at the *graph/transaction level*:

- Edges are only created when both source claim and target mention nodes exist in the
  graph (MATCH pre-condition enforced by the Cypher writer).
- Only claims and mentions that share the same (run_id, chunk_id) can be linked —
  duplicate text in other chunks or runs does **not** produce edges.
- Repeated calls to ``write_participation_edges`` with the same rows are idempotent:
  MERGE ensures no duplicate relationships are created in the graph.
- Properties like ``match_method`` and ``source_uri`` remain consistent after a rerun.
- Reset-and-rerun cycles leave no stale or duplicate edges.
- Any cross-run contamination via shared ``chunk_id`` strings is impossible at the
  graph level (run_id is part of the node identity used in MATCH clauses).
"""
from __future__ import annotations

import re
import unittest
from typing import Any

from demo.stages.claim_participation import (
    EDGE_TYPE_HAS_OBJECT,
    EDGE_TYPE_HAS_SUBJECT,
    MATCH_METHOD_CASEFOLD_EXACT,
    MATCH_METHOD_NORMALIZED_EXACT,
    MATCH_METHOD_RAW_EXACT,
    build_participation_edges,
    write_participation_edges,
)


# ---------------------------------------------------------------------------
# In-memory graph database simulation
# ---------------------------------------------------------------------------


class InMemoryGraphDb:
    """Minimal in-memory simulation of a Neo4j graph database.

    Implements just enough of the ``neo4j.Driver`` interface to support the
    MERGE-based Cypher queries issued by ``write_participation_edges``.  The
    simulation faithfully reproduces two key behaviours:

    1. **MATCH pre-condition** — an edge is only created if *both* the claim
       and the mention node exist in the graph (mirroring the ``MATCH`` clauses
       in the Cypher query).
    2. **MERGE idempotency** — writing the same edge twice results in exactly
       one relationship in the graph (not two), just like a real ``MERGE``.

    Edge properties follow the same ``coalesce`` rule as the real Cypher:
    ``source_uri`` keeps its existing value when the new value is ``None``.
    """

    def __init__(self) -> None:
        # Claim nodes: key = (claim_id, run_id)
        self._claims: dict[tuple[str, str], dict[str, Any]] = {}
        # Mention nodes: key = (mention_id, run_id)
        self._mentions: dict[tuple[str, str], dict[str, Any]] = {}
        # Edges: key = (claim_id, run_id, rel_type, mention_id)
        # Value = {run_id, source_uri, match_method}
        self._edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    # ── node helpers ──────────────────────────────────────────────────────────

    def add_claim(self, claim_id: str, run_id: str, **extra_props: Any) -> None:
        """Pre-populate a :ExtractedClaim node so MATCH clauses can find it."""
        self._claims[(claim_id, run_id)] = {"claim_id": claim_id, "run_id": run_id, **extra_props}

    def add_mention(self, mention_id: str, run_id: str, **extra_props: Any) -> None:
        """Pre-populate an :EntityMention node so MATCH clauses can find it."""
        self._mentions[(mention_id, run_id)] = {"mention_id": mention_id, "run_id": run_id, **extra_props}

    def clear_all(self) -> None:
        """Simulate a graph reset: remove all nodes and edges."""
        self._claims.clear()
        self._mentions.clear()
        self._edges.clear()

    # ── neo4j.Driver interface ────────────────────────────────────────────────

    def execute_query(
        self,
        query: str,
        *,
        parameters_: dict[str, Any] | None = None,
        database_: str = "neo4j",
        routing_: Any = None,
    ) -> Any:
        """Execute a MERGE query and update the in-memory graph state.

        Only the two query patterns emitted by ``write_participation_edges``
        are recognised; all other queries are ignored (no-op).  The method
        signature matches ``neo4j.Driver.execute_query`` so no patches are
        needed in the calling code.

        As a regression guard the method also asserts that every participation
        MERGE query scopes both the claim MATCH and the mention MATCH by
        ``run_id``.  This catches the class of regression where the ``run_id``
        predicate is accidentally removed from one of the MATCH clauses — a
        bug that would allow cross-run edge creation in real Neo4j but would
        otherwise pass these tests silently (because the in-memory sim enforces
        run-scoping independently of the query text).
        """
        rows: list[dict[str, Any]] = (parameters_ or {}).get("rows", [])

        if "HAS_SUBJECT_MENTION" in query and "MERGE" in query:
            self._assert_query_has_run_id_predicates(query)
            self._apply_merge(rows, EDGE_TYPE_HAS_SUBJECT)
        elif "HAS_OBJECT_MENTION" in query and "MERGE" in query:
            self._assert_query_has_run_id_predicates(query)
            self._apply_merge(rows, EDGE_TYPE_HAS_OBJECT)

        # Return a no-op result tuple that matches the neo4j driver's API.
        return ([], None, None)

    @staticmethod
    def _assert_query_has_run_id_predicates(query: str) -> None:
        """Assert that both MATCH clauses in a participation MERGE query scope by run_id.

        The real ``write_participation_edges`` queries use patterns like::

            MATCH (claim:ExtractedClaim {claim_id: row.claim_id, run_id: row.run_id})
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: row.run_id})

        If a future refactor accidentally removes a ``run_id`` predicate from
        either MATCH clause, cross-run edges could be written in Neo4j.  This
        check makes the integration tests fail immediately in that case, even
        though the in-memory graph always enforces run-scoping via node keys.

        The check normalises whitespace before matching, so harmless query
        reformatting (extra spaces, newlines, indentation) does not cause
        false failures.
        """
        # Normalise whitespace so the check is insensitive to formatting.
        normalised = re.sub(r"\s+", " ", query)

        # Verify the ExtractedClaim MATCH scopes by run_id.
        _claim_re = re.compile(
            r"MATCH\s*\([^)]*:\s*ExtractedClaim\s*\{[^}]*\brun_id\b[^}]*\}",
            re.IGNORECASE,
        )
        if not _claim_re.search(normalised):
            raise AssertionError(
                "Participation MERGE query is missing 'run_id' in the "
                "ExtractedClaim MATCH clause — cross-run edges could be "
                "created in real Neo4j.\n\nQuery:\n" + query
            )

        # Verify the EntityMention MATCH scopes by run_id.
        _mention_re = re.compile(
            r"MATCH\s*\([^)]*:\s*EntityMention\s*\{[^}]*\brun_id\b[^}]*\}",
            re.IGNORECASE,
        )
        if not _mention_re.search(normalised):
            raise AssertionError(
                "Participation MERGE query is missing 'run_id' in the "
                "EntityMention MATCH clause — cross-run edges could be "
                "created in real Neo4j.\n\nQuery:\n" + query
            )

    def _apply_merge(self, rows: list[dict[str, Any]], rel_type: str) -> None:
        """Apply MERGE + SET semantics for one batch of edge rows."""
        for row in rows:
            claim_id: str = row["claim_id"]
            mention_id: str = row["mention_id"]
            run_id: str = row["run_id"]

            # MATCH pre-condition: both nodes must exist in the graph.
            if (claim_id, run_id) not in self._claims:
                continue
            if (mention_id, run_id) not in self._mentions:
                continue

            edge_key = (claim_id, run_id, rel_type, mention_id)

            # MERGE: create edge entry only if it does not already exist.
            if edge_key not in self._edges:
                self._edges[edge_key] = {}

            props = self._edges[edge_key]
            props["run_id"] = run_id
            props["match_method"] = row["match_method"]
            # coalesce(row.source_uri, r.source_uri): keep existing value when new is None.
            new_uri = row.get("source_uri")
            existing_uri = props.get("source_uri")
            props["source_uri"] = new_uri if new_uri is not None else existing_uri

    # ── query helpers ─────────────────────────────────────────────────────────

    def count_edges(self, rel_type: str | None = None) -> int:
        """Return the total number of edges, optionally filtered by *rel_type*."""
        if rel_type is None:
            return len(self._edges)
        return sum(1 for (_, _, rt, _) in self._edges if rt == rel_type)

    def has_edge(self, claim_id: str, rel_type: str, mention_id: str, run_id: str) -> bool:
        """Return True if the specified edge exists in the graph."""
        return (claim_id, run_id, rel_type, mention_id) in self._edges

    def get_edge_properties(
        self, claim_id: str, rel_type: str, mention_id: str, run_id: str
    ) -> dict[str, Any] | None:
        """Return the property dict for an edge, or None if it does not exist."""
        return self._edges.get((claim_id, run_id, rel_type, mention_id))


# ---------------------------------------------------------------------------
# Helpers for building test data rows
# ---------------------------------------------------------------------------


def _mention_row(
    name: str,
    mention_id: str = "m1",
    chunk_ids: list[str] | None = None,
    run_id: str = "run-1",
    source_uri: str | None = "uri://test",
) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "chunk_ids": chunk_ids if chunk_ids is not None else ["chunk-1"],
        "run_id": run_id,
        "source_uri": source_uri,
        "properties": {"name": name, "entity_type": "ORG"},
    }


def _claim_row(
    claim_id: str = "c1",
    subject: str | None = None,
    obj: str | None = None,
    chunk_ids: list[str] | None = None,
    run_id: str = "run-1",
    source_uri: str | None = "uri://test",
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "run_id": run_id,
        "source_uri": source_uri,
        "claim_text": "some claim",
    }
    if subject is not None:
        props["subject"] = subject
    if obj is not None:
        props["object"] = obj
    return {
        "claim_id": claim_id,
        "chunk_ids": chunk_ids if chunk_ids is not None else ["chunk-1"],
        "run_id": run_id,
        "source_uri": source_uri,
        "properties": props,
    }


def _run_full(
    db: InMemoryGraphDb,
    claims: list[dict[str, Any]],
    mentions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build participation edges and write them to *db*. Returns the edge rows."""
    edge_rows = build_participation_edges(claims, mentions)
    write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
    return edge_rows


# ---------------------------------------------------------------------------
# Integration tests: same-chunk / same-run scoping
# ---------------------------------------------------------------------------


class TestEdgeScopingIntegration(unittest.TestCase):
    """Verify that edges are only created for claims and mentions in the
    same (run_id, chunk_id) scope — both at the build layer and at the
    graph-write layer."""

    def _db_with_nodes(
        self,
        claim_id: str,
        mention_id: str,
        run_id: str = "run-1",
    ) -> InMemoryGraphDb:
        db = InMemoryGraphDb()
        db.add_claim(claim_id, run_id)
        db.add_mention(mention_id, run_id)
        return db

    def test_edge_created_when_claim_and_mention_share_chunk_and_run(self):
        """Happy path: subject slot matches mention in the same chunk/run → one edge."""
        db = self._db_with_nodes("c1", "m-google")
        claims = [_claim_row("c1", subject="Google", chunk_ids=["chunk-1"])]
        mentions = [_mention_row("Google", "m-google", chunk_ids=["chunk-1"])]
        _run_full(db, claims, mentions)

        self.assertEqual(db.count_edges(), 1)
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-google", "run-1"))

    def test_no_edge_when_mention_is_in_different_chunk(self):
        """Negative: mention exists in chunk-2 but claim is in chunk-1 → no edge."""
        db = self._db_with_nodes("c1", "m-google")
        claims = [_claim_row("c1", subject="Google", chunk_ids=["chunk-1"])]
        mentions = [_mention_row("Google", "m-google", chunk_ids=["chunk-2"])]
        _run_full(db, claims, mentions)

        self.assertEqual(db.count_edges(), 0)

    def test_no_edge_when_mention_belongs_to_different_run(self):
        """Negative: mention has run-B but claim has run-A → no edge."""
        db = InMemoryGraphDb()
        db.add_claim("c-a", "run-A")
        db.add_mention("m-b", "run-B")

        claims = [_claim_row("c-a", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-A")]
        mentions = [_mention_row("Tesla", "m-b", chunk_ids=["chunk-1"], run_id="run-B")]
        _run_full(db, claims, mentions)

        self.assertEqual(db.count_edges(), 0)

    def test_edge_created_when_mention_spans_multiple_chunks_and_overlaps(self):
        """Mention spans chunk-1 and chunk-2; claim is in chunk-1 → edge created."""
        db = self._db_with_nodes("c1", "m-ibm")
        claims = [_claim_row("c1", subject="IBM", chunk_ids=["chunk-1"])]
        mentions = [_mention_row("IBM", "m-ibm", chunk_ids=["chunk-1", "chunk-2"])]
        _run_full(db, claims, mentions)

        self.assertEqual(db.count_edges(), 1)
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-ibm", "run-1"))

    def test_subject_and_object_edges_for_same_chunk(self):
        """Both subject and object slots match mentions in the same chunk → 2 edges."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m-google", "run-1")
        db.add_mention("m-revenue", "run-1")

        claims = [_claim_row("c1", subject="Google", obj="revenue")]
        mentions = [
            _mention_row("Google", "m-google"),
            _mention_row("revenue", "m-revenue"),
        ]
        _run_full(db, claims, mentions)

        self.assertEqual(db.count_edges(EDGE_TYPE_HAS_SUBJECT), 1)
        self.assertEqual(db.count_edges(EDGE_TYPE_HAS_OBJECT), 1)
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-google", "run-1"))
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_OBJECT, "m-revenue", "run-1"))

    def test_duplicate_text_in_other_chunk_does_not_create_edge(self):
        """Same mention name in a different chunk must not link to a claim in chunk-1."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m-chunk1", "run-1")
        db.add_mention("m-chunk2", "run-1")

        claims = [_claim_row("c1", subject="Apple", chunk_ids=["chunk-1"])]
        mentions = [
            _mention_row("Apple", "m-chunk1", chunk_ids=["chunk-1"]),
            _mention_row("Apple", "m-chunk2", chunk_ids=["chunk-2"]),
        ]
        # Both mentions have the name "Apple" but only m-chunk1 shares chunk-1.
        # The matching algorithm sees only m-chunk1 as a candidate for c1, so it
        # finds exactly one match → one edge to m-chunk1, none to m-chunk2.
        edge_rows = _run_full(db, claims, mentions)

        self.assertEqual(len(edge_rows), 1)
        self.assertEqual(edge_rows[0]["mention_id"], "m-chunk1")
        self.assertFalse(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-chunk2", "run-1"))


# ---------------------------------------------------------------------------
# Integration tests: graph-level MERGE idempotency
# ---------------------------------------------------------------------------


class TestMergeIdempotencyIntegration(unittest.TestCase):
    """Verify that writing the same edges multiple times does not create
    duplicate relationships in the graph (MERGE semantics)."""

    def _setup(self) -> tuple[InMemoryGraphDb, list[dict], list[dict]]:
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m-google", "run-1")
        db.add_mention("m-revenue", "run-1")
        claims = [_claim_row("c1", subject="Google", obj="revenue")]
        mentions = [
            _mention_row("Google", "m-google"),
            _mention_row("revenue", "m-revenue"),
        ]
        return db, claims, mentions

    def test_writing_same_edges_twice_yields_same_count(self):
        """Second write must not increase edge count (MERGE deduplication)."""
        db, claims, mentions = self._setup()
        edge_rows = build_participation_edges(claims, mentions)
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        count_after_first = db.count_edges()
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        count_after_second = db.count_edges()

        self.assertEqual(count_after_first, count_after_second)
        self.assertEqual(count_after_second, 2)

    def test_writing_same_subject_edge_ten_times_yields_exactly_one_edge(self):
        """Stress test: repeated MERGE calls for the same edge must stay at 1."""
        db, claims, mentions = self._setup()
        edge_rows = [r for r in build_participation_edges(claims, mentions) if r["slot"] == "subject"]
        for _ in range(10):
            write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)

        self.assertEqual(db.count_edges(EDGE_TYPE_HAS_SUBJECT), 1)

    def test_writing_empty_edge_rows_does_not_add_edges(self):
        """write_participation_edges with no rows must leave the graph unchanged."""
        db, _, _ = self._setup()
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=[])
        self.assertEqual(db.count_edges(), 0)

    def test_full_pipeline_rerun_does_not_duplicate_edges(self):
        """Simulate a full rerun: build + write called twice → still 2 edges total."""
        db, claims, mentions = self._setup()
        _run_full(db, claims, mentions)
        _run_full(db, claims, mentions)  # rerun

        self.assertEqual(db.count_edges(), 2)


# ---------------------------------------------------------------------------
# Integration tests: property stability across reruns
# ---------------------------------------------------------------------------


class TestPropertyStabilityIntegration(unittest.TestCase):
    """Verify that edge properties (match_method, source_uri) remain stable
    and consistent when the same edge is written more than once."""

    def test_match_method_preserved_after_rerun(self):
        """match_method written on first run must equal match_method after rerun."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m1", "run-1")

        claims = [_claim_row("c1", subject="Google")]
        mentions = [_mention_row("Google", "m1")]

        edge_rows = build_participation_edges(claims, mentions)
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        props_first = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m1", "run-1")
        self.assertIsNotNone(props_first)

        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        props_second = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m1", "run-1")
        self.assertIsNotNone(props_second)

        self.assertEqual(props_first["match_method"], props_second["match_method"])
        self.assertEqual(props_first["match_method"], MATCH_METHOD_RAW_EXACT)

    def test_source_uri_coalesce_preserves_existing_when_new_is_none(self):
        """If a subsequent write supplies source_uri=None, the existing value is kept."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m1", "run-1")

        first_row = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": "uri://original",
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        second_row = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": None,  # no new URI supplied on rerun
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]

        write_participation_edges(db, neo4j_database="neo4j", edge_rows=first_row)
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=second_row)

        props = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m1", "run-1")
        self.assertIsNotNone(props)
        self.assertEqual(props["source_uri"], "uri://original")

    def test_match_method_stable_for_casefold_across_reruns(self):
        """casefold_exact match_method must be stable across multiple writes."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m-un", "run-1")

        claims = [_claim_row("c1", subject="united nations")]
        mentions = [_mention_row("United Nations", "m-un")]

        edge_rows = build_participation_edges(claims, mentions)
        for _ in range(3):
            write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)

        props = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m-un", "run-1")
        self.assertIsNotNone(props)
        self.assertEqual(props["match_method"], MATCH_METHOD_CASEFOLD_EXACT)

    def test_match_method_stable_for_normalized_across_reruns(self):
        """normalized_exact match_method must be stable across multiple writes."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")
        db.add_mention("m1", "run-1")

        claims = [_claim_row("c1", subject="Muller")]
        mentions = [_mention_row("Müller", "m1")]

        edge_rows = build_participation_edges(claims, mentions)
        for _ in range(3):
            write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)

        props = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m1", "run-1")
        self.assertIsNotNone(props)
        self.assertEqual(props["match_method"], MATCH_METHOD_NORMALIZED_EXACT)

    def test_run_id_on_edge_matches_input_run_id(self):
        """The run_id property on the edge must match the run_id in the claim rows."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-demo")
        db.add_mention("m1", "run-demo")

        claims = [_claim_row("c1", subject="IBM", run_id="run-demo")]
        mentions = [_mention_row("IBM", "m1", run_id="run-demo")]
        edge_rows = build_participation_edges(claims, mentions)
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)

        props = db.get_edge_properties("c1", EDGE_TYPE_HAS_SUBJECT, "m1", "run-demo")
        self.assertIsNotNone(props)
        self.assertEqual(props["run_id"], "run-demo")


# ---------------------------------------------------------------------------
# Integration tests: reset + rerun cycles
# ---------------------------------------------------------------------------


class TestResetRerunCycleIntegration(unittest.TestCase):
    """Verify that a simulated graph-reset followed by a re-extraction run
    produces a clean, healthy edge structure with no stale or duplicate edges."""

    def _build_graph(
        self,
        db: InMemoryGraphDb,
        run_id: str = "run-1",
    ) -> tuple[list[dict], list[dict]]:
        """Populate *db* with one claim and two mentions, then return the row dicts."""
        db.add_claim("c1", run_id)
        db.add_mention("m-google", run_id)
        db.add_mention("m-revenue", run_id)
        claims = [_claim_row("c1", subject="Google", obj="revenue", run_id=run_id)]
        mentions = [
            _mention_row("Google", "m-google", run_id=run_id),
            _mention_row("revenue", "m-revenue", run_id=run_id),
        ]
        return claims, mentions

    def test_reset_and_rerun_produces_same_edge_count(self):
        """After a reset (clear_all) + rerun, the graph has the same number of edges."""
        db = InMemoryGraphDb()
        claims, mentions = self._build_graph(db)
        _run_full(db, claims, mentions)
        self.assertEqual(db.count_edges(), 2)

        # Simulate reset: clear all graph state.
        db.clear_all()
        self.assertEqual(db.count_edges(), 0)

        # Rerun: re-populate nodes and re-execute the stage.
        self._build_graph(db)
        _run_full(db, claims, mentions)
        self.assertEqual(db.count_edges(), 2)

    def test_reset_removes_all_edges_before_rerun(self):
        """clear_all must remove every edge; the graph starts fresh on rerun."""
        db = InMemoryGraphDb()
        claims, mentions = self._build_graph(db)
        _run_full(db, claims, mentions)
        self.assertGreater(db.count_edges(), 0)

        db.clear_all()
        self.assertEqual(db.count_edges(), 0)
        self.assertFalse(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-google", "run-1"))
        self.assertFalse(db.has_edge("c1", EDGE_TYPE_HAS_OBJECT, "m-revenue", "run-1"))

    def test_rerun_after_reset_creates_correct_edges(self):
        """After reset + rerun, exactly the expected edges exist — no extras."""
        db = InMemoryGraphDb()
        claims, mentions = self._build_graph(db)
        _run_full(db, claims, mentions)
        db.clear_all()
        self._build_graph(db)
        _run_full(db, claims, mentions)

        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-google", "run-1"))
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_OBJECT, "m-revenue", "run-1"))
        self.assertEqual(db.count_edges(), 2)

    def test_second_rerun_without_reset_does_not_add_edges(self):
        """Running the stage twice without a reset must leave edge count unchanged."""
        db = InMemoryGraphDb()
        claims, mentions = self._build_graph(db)
        _run_full(db, claims, mentions)
        count_first = db.count_edges()
        _run_full(db, claims, mentions)
        self.assertEqual(db.count_edges(), count_first)

    def test_new_run_id_produces_isolated_edge_set(self):
        """A second run with a new run_id must produce independent edges."""
        db = InMemoryGraphDb()

        # First run
        db.add_claim("c1", "run-v1")
        db.add_mention("m-v1", "run-v1")
        claims_v1 = [_claim_row("c1", subject="Tesla", run_id="run-v1")]
        mentions_v1 = [_mention_row("Tesla", "m-v1", run_id="run-v1")]
        _run_full(db, claims_v1, mentions_v1)

        # Second run with new run_id (simulates a fresh extraction run)
        db.add_claim("c1", "run-v2")
        db.add_mention("m-v2", "run-v2")
        claims_v2 = [_claim_row("c1", subject="Tesla", run_id="run-v2")]
        mentions_v2 = [_mention_row("Tesla", "m-v2", run_id="run-v2")]
        _run_full(db, claims_v2, mentions_v2)

        # Each run produces its own isolated edge.
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-v1", "run-v1"))
        self.assertTrue(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-v2", "run-v2"))
        # No cross-run contamination: run-v1 claim must not link run-v2 mention.
        self.assertFalse(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-v2", "run-v1"))
        self.assertFalse(db.has_edge("c1", EDGE_TYPE_HAS_SUBJECT, "m-v1", "run-v2"))


# ---------------------------------------------------------------------------
# Integration tests: graph-level orphan edge prevention
# ---------------------------------------------------------------------------


class TestOrphanEdgePreventionIntegration(unittest.TestCase):
    """Verify that write_participation_edges never creates edges whose claim
    or mention node is absent from the graph (enforced by MATCH clauses)."""

    def test_no_edge_when_claim_node_absent(self):
        """Edge rows referencing a non-existent claim node must produce no graph edge."""
        db = InMemoryGraphDb()
        db.add_mention("m1", "run-1")  # mention exists, claim does NOT

        edge_rows = [
            {
                "claim_id": "c-missing",
                "mention_id": "m1",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(db.count_edges(), 0)

    def test_no_edge_when_mention_node_absent(self):
        """Edge rows referencing a non-existent mention node must produce no graph edge."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-1")  # claim exists, mention does NOT

        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m-missing",
                "run_id": "run-1",
                "source_uri": "uri://test",
                "slot": "object",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_OBJECT,
            }
        ]
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(db.count_edges(), 0)

    def test_no_edge_when_claim_belongs_to_different_run_in_graph(self):
        """A claim with run-A in the graph must not be linked by a row with run-B."""
        db = InMemoryGraphDb()
        db.add_claim("c1", "run-A")  # claim stored as run-A
        db.add_mention("m1", "run-B")  # mention stored as run-B

        # Row claims both are run-B, but the claim node is run-A → MATCH fails.
        edge_rows = [
            {
                "claim_id": "c1",
                "mention_id": "m1",
                "run_id": "run-B",
                "source_uri": None,
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(db.count_edges(), 0)


# ---------------------------------------------------------------------------
# Integration tests: cross-run contamination via shared chunk_id strings
# ---------------------------------------------------------------------------


class TestCrossRunContaminationIntegration(unittest.TestCase):
    """Regression guard: shared chunk_id strings across runs must never cause
    edges to bleed across run boundaries, either at the build layer or the
    write layer."""

    def test_shared_chunk_id_string_does_not_cross_run_boundary_at_build(self):
        """build_participation_edges must not match mentions from a different run
        even when the chunk_id string is the same (chunk ids are only unique within
        a run_id — see extraction_utils.py)."""
        claims = [_claim_row("c-A", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-A")]
        mentions = [_mention_row("Tesla", "m-B", chunk_ids=["chunk-1"], run_id="run-B")]

        edge_rows = build_participation_edges(claims, mentions)
        self.assertEqual(edge_rows, [])

    def test_shared_chunk_id_string_does_not_cross_run_boundary_at_write(self):
        """write_participation_edges must not write an edge when the claim node
        in the graph has a different run_id than the edge row specifies."""
        db = InMemoryGraphDb()
        db.add_claim("c-A", "run-A")
        db.add_mention("m-B", "run-B")

        # Hypothetical edge row asking to link c-A to m-B under run-A.
        # mention node m-B is stored under run-B, so the MATCH on run_id fails.
        edge_rows = [
            {
                "claim_id": "c-A",
                "mention_id": "m-B",
                "run_id": "run-A",
                "source_uri": None,
                "slot": "subject",
                "match_method": MATCH_METHOD_RAW_EXACT,
                "edge_type": EDGE_TYPE_HAS_SUBJECT,
            }
        ]
        write_participation_edges(db, neo4j_database="neo4j", edge_rows=edge_rows)
        self.assertEqual(db.count_edges(), 0)

    def test_two_runs_with_shared_chunk_id_each_get_own_edge(self):
        """Two runs that happen to use the same chunk_id string must each receive
        their own independent participation edge at both the build and write layers."""
        db = InMemoryGraphDb()
        db.add_claim("c-A", "run-A")
        db.add_mention("m-A", "run-A")
        db.add_claim("c-B", "run-B")
        db.add_mention("m-B", "run-B")

        claims = [
            _claim_row("c-A", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-A"),
            _claim_row("c-B", subject="Tesla", chunk_ids=["chunk-1"], run_id="run-B"),
        ]
        mentions = [
            _mention_row("Tesla", "m-A", chunk_ids=["chunk-1"], run_id="run-A"),
            _mention_row("Tesla", "m-B", chunk_ids=["chunk-1"], run_id="run-B"),
        ]
        _run_full(db, claims, mentions)

        # Each run must have exactly one edge pointing to its own mention.
        self.assertTrue(db.has_edge("c-A", EDGE_TYPE_HAS_SUBJECT, "m-A", "run-A"))
        self.assertTrue(db.has_edge("c-B", EDGE_TYPE_HAS_SUBJECT, "m-B", "run-B"))
        # No cross-run edges.
        self.assertFalse(db.has_edge("c-A", EDGE_TYPE_HAS_SUBJECT, "m-B", "run-A"))
        self.assertFalse(db.has_edge("c-B", EDGE_TYPE_HAS_SUBJECT, "m-A", "run-B"))
        self.assertEqual(db.count_edges(), 2)


if __name__ == "__main__":
    unittest.main()
