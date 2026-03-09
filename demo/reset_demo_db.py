"""Reset the demo graph database to a clean state.

This script deletes only demo-owned graph content and drops only demo-owned
indexes.  It is safe to run against a dedicated demo database and is
idempotent: repeated runs succeed even when the graph is already empty or the
indexes no longer exist.

Demo-owned labels (nodes + all their relationships are removed):
  - Document, Chunk  (lexical layer written by ingest-pdf)
  - Claim            (structured layer written by ingest-structured)
  - CanonicalEntity  (resolution layer written by resolve-entities)
  - EntityMention    (extraction layer written by extract-claims)

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
from neo4j_graphrag.indexes import drop_index_if_exists

from demo.contracts import ARTIFACTS_DIR, CHUNK_EMBEDDING_INDEX_NAME

logger = logging.getLogger(__name__)

# Demo-owned node labels.  Nodes with these labels (and all their
# relationships) are removed on reset.  Keep in sync with:
#   - demo/config/pdf_simple_kg_pipeline.yaml
#   - demo/stages/*.py (structured ingest, pdf ingest, claim extraction, etc.)
DEMO_NODE_LABELS: tuple[str, ...] = (
    "Document",
    "Chunk",
    "Claim",
    "CanonicalEntity",
    "EntityMention",
)

# Demo-owned index names dropped on reset.  Keep in sync with:
#   - demo/contracts/pipeline.py  (CHUNK_EMBEDDING_INDEX_NAME)
#   - demo/config/pdf_simple_kg_pipeline.yaml  (contract.chunk_embedding.index_name)
DEMO_OWNED_INDEXES: tuple[str, ...] = (CHUNK_EMBEDDING_INDEX_NAME,)


def _index_exists(driver: neo4j.Driver, index_name: str, database: str) -> bool:
    """Return True if an index named *index_name* exists in *database*."""
    result = driver.execute_query(
        "SHOW INDEXES YIELD name WHERE name = $name RETURN count(*) AS cnt",
        {"name": index_name},
        database_=database,
    )
    record = result.records[0] if result.records else None
    return bool(record and record["cnt"] > 0)


def run_reset(
    *,
    driver: neo4j.Driver,
    database: str,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Reset demo-owned graph content and indexes in *database*.

    Deletes all nodes with demo-owned labels (and their relationships) using
    ``DETACH DELETE``.  Drops each demo-owned index using the vendor
    ``drop_index_if_exists`` helper (idempotent: safe if the index is absent).

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

    # ── Drop demo-owned indexes ───────────────────────────────────────────────
    # Keep this reset contract aligned with demo/config/pdf_simple_kg_pipeline.yaml
    # and demo.contracts.pipeline (CHUNK_EMBEDDING_INDEX_NAME).
    for index_name in DEMO_OWNED_INDEXES:
        if _index_exists(driver, index_name, database):
            # Use vendor helper: issues DROP INDEX $name IF EXISTS safely.
            # drop_index_if_exists uses the database_ keyword argument.
            drop_index_if_exists(driver, index_name, database_=database)
            indexes_dropped.append(index_name)
            logger.info("Dropped demo index: %s", index_name)
        else:
            indexes_not_found.append(index_name)
            warnings_list.append(
                f"Index '{index_name}' not found; skipped (idempotent no-op)."
            )
            logger.info("Demo index not found (already absent): %s", index_name)

    idempotent = deleted_nodes == 0 and not indexes_dropped

    report: dict[str, Any] = {
        "created_at": created_at,
        "target_database": database,
        "reset_mode": "demo_full_graph_wipe",
        "demo_labels_deleted": list(DEMO_NODE_LABELS),
        "deleted_nodes": deleted_nodes,
        "deleted_relationships": deleted_relationships,
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
