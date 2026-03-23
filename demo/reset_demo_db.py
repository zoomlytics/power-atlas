"""Reset the demo graph database to a clean state.

This script deletes only demo-owned graph content and drops only demo-owned
indexes.  It is safe to run against a dedicated demo database and is
idempotent: repeated runs succeed even when the graph is already empty or the
indexes no longer exist.

Demo-owned labels (nodes + all their relationships are removed):
  - Document, Chunk         (lexical layer written by ingest-pdf)
  - CanonicalEntity         (structured layer written by ingest-structured)
  - Claim                   (structured layer written by ingest-structured; claims.csv)
  - Fact                    (structured layer written by ingest-structured; facts.csv)
  - Relationship            (structured layer written by ingest-structured; relationships.csv)
  - Source                  (structured layer written by ingest-structured; dataset source nodes)
  - ExtractedClaim          (extraction layer written by extract-claims)
  - EntityMention           (extraction layer written by extract-claims)
  - UnresolvedEntity        (resolution layer written by resolve-entities; fallback for unresolved mentions)
  - ResolvedEntityCluster   (resolution layer written by resolve-entities; resolved entity clusters)

Stale participation edges (pre-v0.3 graphs only, non-migratable):
  Because the DETACH DELETE above removes all ExtractedClaim and EntityMention
  nodes, any v0.3 :HAS_PARTICIPANT edges attached to those nodes are
  automatically removed.

  Old demo graphs produced before v0.2 may contain :HAS_SUBJECT and :HAS_OBJECT
  edges (v0.1 types).  Old graphs produced before v0.3 may contain
  :HAS_SUBJECT_MENTION and :HAS_OBJECT_MENTION edges (v0.2 types).
  All of these relationship types are retired and replaced by :HAS_PARTICIPANT
  (v0.3).  The DETACH DELETE of ExtractedClaim/EntityMention nodes removes
  these stale edges as a side-effect.  However, if any such edges somehow
  survive between non-deleted endpoints, this script issues explicit DELETE
  statements scoped to demo-owned endpoints to remove them and records the
  count in the reset report under ``stale_participation_edges_deleted``.

  **Old demo graphs (pre-v0.3) are not migratable.**  A full reset followed by
  a fresh pipeline run (ingest-pdf → extract-claims → resolve-entities) is the
  only supported path to a clean v0.3 graph.

Demo-owned indexes (dropped by name):
  - demo_chunk_embedding_index  (vector index on Chunk.embedding, created by
    ingest-pdf or run_demo.py setup; name pinned in
    demo/config/pdf_simple_kg_pipeline.yaml and demo.contracts.pipeline)

Preserved (not touched by this script):
  - Any nodes with labels not in the list above
  - Relationships whose endpoints are not among the deleted demo nodes (regardless
    of relationship type); relationships attached to deleted nodes are removed via
    DETACH DELETE as a consequence of node deletion
  - Any indexes not in the list above
  - Any other Neo4j databases on the same server

Reset actions are written to a JSON report file in the output directory for
inspection/debugging.  See ``run_reset()`` for the report schema.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neo4j

from demo.contracts import ARTIFACTS_DIR, CHUNK_EMBEDDING_INDEX_NAME
from demo.cypher_utils import validate_cypher_identifier as _validate_cypher_identifier

logger = logging.getLogger(__name__)

# Demo-owned node labels.  Nodes with these labels (and all their
# relationships) are removed on reset.  Keep in sync with:
#   - demo/config/pdf_simple_kg_pipeline.yaml
#   - demo/stages/*.py (structured ingest, pdf ingest, claim extraction, etc.)
DEMO_NODE_LABELS: tuple[str, ...] = (
    # Lexical layer — pdf ingest
    "Document",
    "Chunk",
    # Structured layer — structured ingest (CSV fixtures)
    "CanonicalEntity",
    "Claim",
    "Fact",
    "Relationship",
    "Source",
    # Extraction layer — claim/mention extraction
    "ExtractedClaim",
    "EntityMention",
    # Resolution layer — entity resolution
    "UnresolvedEntity",
    "ResolvedEntityCluster",
)

# Demo-owned index names dropped on reset.  Keep in sync with:
#   - demo/contracts/pipeline.py  (CHUNK_EMBEDDING_INDEX_NAME)
#   - demo/config/pdf_simple_kg_pipeline.yaml  (contract.chunk_embedding.index_name)
DEMO_OWNED_INDEXES: tuple[str, ...] = (CHUNK_EMBEDDING_INDEX_NAME,)


def _index_exists(driver: neo4j.Driver, index_name: str, database: str) -> bool:
    """Return True if an index named *index_name* exists in *database*."""
    records, _, _ = driver.execute_query(
        "SHOW INDEXES YIELD name WHERE name = $name RETURN count(*) AS cnt",
        parameters_={"name": index_name},
        database_=database,
    )
    record = records[0] if records else None
    return bool(record and record["cnt"] > 0)


def run_reset(
    *,
    driver: neo4j.Driver,
    database: str,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Reset demo-owned graph content and indexes in *database*.

    Deletes all nodes with demo-owned labels (and their relationships) using
    ``DETACH DELETE``.  Also explicitly removes any surviving stale
    pre-v0.3 participation edges left by old demo runs:

    - :HAS_SUBJECT / :HAS_OBJECT (v0.1, retired in v0.2)
    - :HAS_SUBJECT_MENTION / :HAS_OBJECT_MENTION (v0.2, retired in v0.3)

    These relationship types are all replaced by :HAS_PARTICIPANT (v0.3).
    Old graphs are **non-migratable** — a full reset + fresh pipeline run is
    required.  Drops each demo-owned index by issuing a direct Cypher
    ``DROP INDEX <name> IF EXISTS`` statement scoped to *database*
    (idempotent: safe if the index is absent).

    Does **not** touch any other nodes, relationships, indexes, constraints, or
    databases.

    Args:
        driver: Connected Neo4j driver pointing at the demo database host.
        database: Name of the Neo4j database to reset (must be the demo DB).
        output_dir: Directory where the reset report JSON is written.  If
            ``None``, no report file is created on disk (the report dict is
            still returned).

    Returns:
        Report dict with the following keys:

        - ``created_at``: ISO-8601 timestamp of the reset run.
        - ``target_database``: Name of the database that was reset.
        - ``reset_mode``: Always ``"demo_full_graph_wipe"`` for this function.
        - ``demo_labels_deleted``: List of node labels targeted by the delete.
        - ``deleted_nodes``: Number of nodes actually removed.
        - ``deleted_relationships``: Number of relationships actually removed.
        - ``stale_participation_edges_deleted``: Number of surviving pre-v0.3
          stale participation edges removed (normally 0; non-zero only when a
          pre-v0.3 graph was not fully cleaned up by the DETACH DELETE).
        - ``indexes_dropped``: Names of indexes that existed and were dropped.
        - ``indexes_not_found``: Names of indexes that were absent (no-op).
        - ``warnings``: Human-readable strings for idempotent no-ops or other
          non-fatal conditions.
        - ``idempotent``: ``True`` when nothing was changed (graph already
          empty, all indexes already absent).
        - ``report_path``: Path to the written JSON file (only present when
          *output_dir* is provided).
    """
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    # Derive a filesystem-safe timestamp for the report filename, consistent with
    # other demo artifacts (e.g., run IDs/manifests).
    _ts_for_filename = now.strftime("%Y%m%dT%H%M%S%fZ")
    warnings_list: list[str] = []
    indexes_dropped: list[str] = []
    indexes_not_found: list[str] = []

    # ── Delete demo-owned nodes and their relationships ──────────────────────
    # Generate the WHERE clause from DEMO_NODE_LABELS so the Cypher and the
    # reported contract cannot drift independently.  Each label is a compile-time
    # constant (simple identifier string) so the OR-join is safe to construct.
    _label_conditions = " OR ".join(f"n:{label}" for label in DEMO_NODE_LABELS)
    _delete_query = f"MATCH (n) WHERE {_label_conditions} DETACH DELETE n"
    with driver.session(database=database) as session:
        result = session.run(_delete_query)
        counters = result.consume().counters
        deleted_nodes: int = counters.nodes_deleted
        deleted_relationships: int = counters.relationships_deleted

    if deleted_nodes == 0:
        _label_list = ", ".join(DEMO_NODE_LABELS)
        warnings_list.append(
            f"No demo-owned nodes found for labels ({_label_list}); nothing deleted (idempotent no-op)."
        )
    logger.info(
        "Demo node deletion: database=%s nodes_deleted=%d relationships_deleted=%d",
        database,
        deleted_nodes,
        deleted_relationships,
    )

    # ── Stale pre-v0.3 participation edge cleanup ─────────────────────────────
    # Old demo graphs may contain stale participation edges that were not
    # removed by the DETACH DELETE above (e.g. when their endpoints were not
    # among the deleted labels).  Two generations of stale types are covered:
    #
    #   v0.1 types: :HAS_SUBJECT / :HAS_OBJECT
    #     Retired in v0.2 and replaced by :HAS_SUBJECT_MENTION/:HAS_OBJECT_MENTION.
    #   v0.2 types: :HAS_SUBJECT_MENTION / :HAS_OBJECT_MENTION
    #     Retired in v0.3 and replaced by :HAS_PARTICIPANT {role}.
    #
    # Both are cleaned up here.  Old graphs are non-migratable; a full reset
    # plus a fresh pipeline run is the only supported upgrade path.
    _stale_query = (
        "MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT|HAS_OBJECT|HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention) DELETE r"
    )
    with driver.session(database=database) as _stale_session:
        _stale_result = _stale_session.run(_stale_query)
        _stale_counters = _stale_result.consume().counters
        stale_participation_edges_deleted: int = _stale_counters.relationships_deleted

    if stale_participation_edges_deleted > 0:
        warnings_list.append(
            f"Removed {stale_participation_edges_deleted} stale pre-v0.3 participation "
            "edge(s) (:HAS_SUBJECT, :HAS_OBJECT, :HAS_SUBJECT_MENTION, or "
            ":HAS_OBJECT_MENTION).  These relationship types were retired prior to v0.3 and "
            "replaced by :HAS_PARTICIPANT {role}.  Old demo graphs are non-migratable — "
            "a full reset followed by a fresh pipeline run is required."
        )

    logger.info(
        "Stale pre-v0.3 participation edge cleanup: stale_deleted=%d",
        stale_participation_edges_deleted,
    )

    # ── Drop demo-owned indexes ───────────────────────────────────────────────
    # Keep this reset contract aligned with demo/config/pdf_simple_kg_pipeline.yaml
    # and demo.contracts.pipeline (CHUNK_EMBEDDING_INDEX_NAME).
    for index_name in DEMO_OWNED_INDEXES:
        if _index_exists(driver, index_name, database):
            # Issue a direct DROP INDEX statement in a session scoped to the
            # demo database.  The index name is a compile-time constant from
            # demo.contracts, but we validate it as a safe bare identifier
            # before interpolating it into the Cypher string.
            _validate_cypher_identifier(index_name, "index name")
            with driver.session(database=database) as _drop_session:
                _drop_session.run(f"DROP INDEX {index_name} IF EXISTS")
            indexes_dropped.append(index_name)
            logger.info("Dropped demo index: %s", index_name)
        else:
            indexes_not_found.append(index_name)
            warnings_list.append(
                f"Index '{index_name}' not found; skipped (idempotent no-op)."
            )
            logger.info("Demo index not found (already absent): %s", index_name)

    idempotent = deleted_nodes == 0 and not indexes_dropped and stale_participation_edges_deleted == 0

    report: dict[str, Any] = {
        "created_at": created_at,
        "target_database": database,
        "reset_mode": "demo_full_graph_wipe",
        "demo_labels_deleted": list(DEMO_NODE_LABELS),
        "deleted_nodes": deleted_nodes,
        "deleted_relationships": deleted_relationships,
        "stale_participation_edges_deleted": stale_participation_edges_deleted,
        "indexes_dropped": indexes_dropped,
        "indexes_not_found": indexes_not_found,
        "warnings": warnings_list,
        "idempotent": idempotent,
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"reset_report_{_ts_for_filename}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        logger.info("Reset report written to: %s", report_path)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset demo nodes and indexes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Deletes all nodes with demo-owned labels ({', '.join(DEMO_NODE_LABELS)})\n"
            f"and drops the following indexes: {', '.join(DEMO_OWNED_INDEXES)}.\n"
            "Run only against a dedicated demo database to avoid data loss."
        ),
    )
    parser.add_argument("--confirm", action="store_true", help="required safety flag")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--neo4j-database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACTS_DIR,
        help="Directory for the reset report JSON (default: demo/artifacts)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to run without --confirm")
    if not args.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD environment variable or --neo4j-password must be set")

    driver = neo4j.GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_username, args.neo4j_password)
    )
    with driver:
        report = run_reset(
            driver=driver,
            database=args.neo4j_database,
            output_dir=args.output_dir,
        )

    print(
        f"Demo graph reset complete: "
        f"database={report['target_database']} "
        f"nodes_deleted={report['deleted_nodes']} "
        f"relationships_deleted={report['deleted_relationships']} "
        f"indexes_dropped={report['indexes_dropped']}"
    )
    if report.get("warnings"):
        for w in report["warnings"]:
            print(f"  warning: {w}")
    if report.get("report_path"):
        print(f"Reset report written to: {report['report_path']}")


if __name__ == "__main__":
    main()
