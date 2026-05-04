"""Runtime helpers for resetting the demo graph database."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neo4j

from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.neo4j_io import validate_cypher_identifier

logger = logging.getLogger(__name__)


# Demo-owned node labels. Nodes with these labels (and all their
# relationships) are removed on reset. Keep in sync with:
#   - demo/config/pdf_simple_kg_pipeline.yaml
#   - demo/stages/*.py (structured ingest, pdf ingest, claim extraction, etc.)
DEMO_NODE_LABELS: tuple[str, ...] = (
    "Document",
    "Chunk",
    "CanonicalEntity",
    "Claim",
    "Fact",
    "Relationship",
    "Source",
    "ExtractedClaim",
    "EntityMention",
    "UnresolvedEntity",
    "ResolvedEntityCluster",
)


def demo_owned_indexes(
    pipeline_contract: PipelineContractSnapshot,
) -> tuple[str, ...]:
    """Return the current demo-owned index names from the provided pipeline contract."""
    return (pipeline_contract.chunk_embedding_index_name,)


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
    pipeline_contract: PipelineContractSnapshot,
) -> dict[str, Any]:
    """Reset demo-owned graph content and indexes in *database*."""
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    ts_for_filename = now.strftime("%Y%m%dT%H%M%S%fZ")
    warnings_list: list[str] = []
    indexes_dropped: list[str] = []
    indexes_not_found: list[str] = []

    label_conditions = " OR ".join(f"n:{label}" for label in DEMO_NODE_LABELS)
    delete_query = f"MATCH (n) WHERE {label_conditions} DETACH DELETE n"
    with driver.session(database=database) as session:
        result = session.run(delete_query)
        counters = result.consume().counters
        deleted_nodes: int = counters.nodes_deleted
        deleted_relationships: int = counters.relationships_deleted

    if deleted_nodes == 0:
        label_list = ", ".join(DEMO_NODE_LABELS)
        warnings_list.append(
            f"No demo-owned nodes found for labels ({label_list}); nothing deleted (idempotent no-op)."
        )
    logger.info(
        "Demo node deletion: database=%s nodes_deleted=%d relationships_deleted=%d",
        database,
        deleted_nodes,
        deleted_relationships,
    )

    stale_query = (
        "MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT|HAS_OBJECT|HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention) DELETE r"
    )
    with driver.session(database=database) as stale_session:
        stale_result = stale_session.run(stale_query)
        stale_counters = stale_result.consume().counters
        stale_participation_edges_deleted: int = stale_counters.relationships_deleted

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

    for index_name in demo_owned_indexes(pipeline_contract):
        if _index_exists(driver, index_name, database):
            validate_cypher_identifier(index_name, "index name")
            with driver.session(database=database) as drop_session:
                drop_session.run(f"DROP INDEX {index_name} IF EXISTS")
            indexes_dropped.append(index_name)
            logger.info("Dropped demo index: %s", index_name)
        else:
            indexes_not_found.append(index_name)
            warnings_list.append(
                f"Index '{index_name}' not found; skipped (idempotent no-op)."
            )
            logger.info("Demo index not found (already absent): %s", index_name)

    idempotent = (
        deleted_nodes == 0
        and not indexes_dropped
        and stale_participation_edges_deleted == 0
    )

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
        report_path = output_dir / f"reset_report_{ts_for_filename}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        logger.info("Reset report written to: %s", report_path)

    return report


__all__ = ["DEMO_NODE_LABELS", "demo_owned_indexes", "run_reset"]