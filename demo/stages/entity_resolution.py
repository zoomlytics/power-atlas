"""Entity mention resolution stage.

Reads :EntityMention nodes (scoped to a ``run_id``) from Neo4j and performs
deterministic, non-destructive resolution to :CanonicalEntity nodes.
Mentions that cannot be resolved are grouped by their normalized text into
:ResolvedEntityCluster provisional cluster nodes and linked via :MEMBER_OF
edges instead.

Resolution strategies (applied in priority order):

1. **qid_exact**   — mention ``name`` matches ``^Q\\d+$``; MATCH
   ``CanonicalEntity {entity_id: name}``.
2. **label_exact** — ``normalized(mention.name) == normalized(canonical.name)``.
3. **alias_exact** — ``normalized(mention.name)`` appears in the
   ``canonical.aliases`` string (pipe-separated or comma-separated list).
4. **label_cluster** — no canonical match found; mention is grouped with other
   mentions sharing the same normalized text into a :ResolvedEntityCluster.

All resolution is **non-destructive**: existing nodes are never mutated;
only ``RESOLVES_TO`` and ``MEMBER_OF`` relationship edges are added/updated.

Graph model
-----------
* ``(:EntityMention)-[:RESOLVES_TO]->(:CanonicalEntity)``   — structured match
* ``(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster)`` — provisional cluster
* ``(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity)`` — future alignment

Artifacts written to ``runs/<run_id>/entity_resolution/``:
- ``entity_resolution_summary.json`` — counts, breakdown, resolver metadata.
- ``unresolved_mentions.json``        — list of clustered (unresolved) mentions.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

# Bump this constant whenever the resolution strategies or scoring logic change
# so that RESOLVES_TO edges in the graph can be distinguished by the version that
# created them (e.g. when re-running resolution after a strategy upgrade).
_RESOLVER_VERSION = "v1.0"

# Bump this constant whenever cluster-assignment logic changes so that MEMBER_OF
# edges can be distinguished by the version that created them.
_CLUSTER_VERSION = "v1.0"

_QID_PATTERN = re.compile(r"^Q\d+$")


def _normalize(text: str) -> str:
    return text.strip().lower()


def _split_aliases(raw: Any) -> list[str]:
    """Parse a pipe- or comma-separated alias string into individual tokens."""
    if not raw or not isinstance(raw, str):
        return []
    sep = "|" if "|" in raw else ","
    return [tok.strip().lower() for tok in raw.split(sep) if tok.strip()]


def _build_lookup_tables(
    canonical_nodes: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build three lookup dicts for fast resolution.

    Returns:
        by_qid:   entity_id  → canonical row
        by_label: normalized_name → canonical row (first match wins)
        by_alias: normalized_alias → canonical row (first match wins)
    """
    by_qid: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}

    for row in canonical_nodes:
        eid = (row.get("entity_id") or "").strip()
        name = (row.get("name") or "").strip()
        if eid and eid not in by_qid:
            by_qid[eid] = row
        norm_name = _normalize(name)
        if norm_name and norm_name not in by_label:
            by_label[norm_name] = row
        for alias in _split_aliases(row.get("aliases")):
            if alias and alias not in by_alias:
                by_alias[alias] = row

    return by_qid, by_label, by_alias


def _resolve_mention(
    mention: dict[str, Any],
    by_qid: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Apply resolution strategies and return a resolution record."""
    name = (mention.get("name") or "").strip()
    normalized = _normalize(name)

    # Strategy 1: exact QID match
    if _QID_PATTERN.match(name):
        canonical = by_qid.get(name)
        if canonical:
            return {
                "mention_id": mention["mention_id"],
                "canonical_entity_id": canonical["entity_id"],
                "canonical_run_id": canonical["run_id"],
                "resolution_method": "qid_exact",
                "resolution_confidence": 1.0,
                "candidate_ids": [canonical["entity_id"]],
                "resolved": True,
            }
        # Name looks like a QID but no canonical QID match exists:
        # treat as a provisional cluster rather than falling through to
        # label/alias strategies.
        return {
            "mention_id": mention["mention_id"],
            "normalized_text": normalized,
            "mention_name": name,
            "resolution_method": "label_cluster",
            "resolution_confidence": 0.0,
            "candidate_ids": [],
            "resolved": False,
        }

    # Strategy 2: exact label match
    canonical = by_label.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical["entity_id"],
            "canonical_run_id": canonical["run_id"],
            "resolution_method": "label_exact",
            "resolution_confidence": 0.9,
            "candidate_ids": [canonical["entity_id"]],
            "resolved": True,
        }

    # Strategy 3: alias match
    canonical = by_alias.get(normalized)
    if canonical:
        return {
            "mention_id": mention["mention_id"],
            "canonical_entity_id": canonical["entity_id"],
            "canonical_run_id": canonical["run_id"],
            "resolution_method": "alias_exact",
            "resolution_confidence": 0.8,
            "candidate_ids": [canonical["entity_id"]],
            "resolved": True,
        }

    # Strategy 4: label_cluster — group into a provisional ResolvedEntityCluster
    return {
        "mention_id": mention["mention_id"],
        "normalized_text": normalized,
        "mention_name": name,
        "resolution_method": "label_cluster",
        "resolution_confidence": 0.0,
        "candidate_ids": [],
        "resolved": False,
    }


def _write_resolution_results(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    neo4j_database: str,
) -> None:
    """Persist RESOLVES_TO edges and ResolvedEntityCluster nodes to Neo4j.

    Resolved mentions receive a ``RESOLVES_TO`` edge pointing at the matched
    :CanonicalEntity.

    Unresolved mentions are grouped by their ``normalized_text`` into
    :ResolvedEntityCluster nodes.  Each mention receives a ``MEMBER_OF`` edge
    carrying the required provenance metadata: ``score``, ``method``,
    ``resolver_version``, ``run_id``, and ``status``.
    """
    if resolved_rows:
        driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
            MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
            MERGE (mention)-[r:RESOLVES_TO]->(canonical)
            SET r.run_id = $run_id,
                r.source_uri = $source_uri,
                r.resolution_method = row.resolution_method,
                r.resolution_confidence = row.resolution_confidence,
                r.candidate_ids = row.candidate_ids
            """,
            parameters_={
                "rows": resolved_rows,
                "run_id": run_id,
                "source_uri": source_uri,
            },
            database_=neo4j_database,
        )

    if unresolved_rows:
        created_at = datetime.now(UTC).isoformat()
        # Build per-mention rows for the cluster MERGE + MEMBER_OF edge.
        cluster_rows = [
            {
                "mention_id": row["mention_id"],
                "cluster_id": f"cluster::{row['normalized_text']}",
                "canonical_name": row["mention_name"],
                "normalized_text": row["normalized_text"],
                "score": 1.0,
                "method": "label_cluster",
                "status": "accepted",
            }
            for row in unresolved_rows
        ]
        driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
            ON CREATE SET
                cluster.canonical_name  = row.canonical_name,
                cluster.normalized_text = row.normalized_text,
                cluster.resolver_version = $resolver_version,
                cluster.created_at = $created_at
            WITH row, cluster
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
            MERGE (mention)-[r:MEMBER_OF]->(cluster)
            SET r.score            = row.score,
                r.method           = row.method,
                r.resolver_version = $resolver_version,
                r.run_id           = $run_id,
                r.status           = row.status
            """,
            parameters_={
                "rows": cluster_rows,
                "run_id": run_id,
                "resolver_version": _CLUSTER_VERSION,
                "created_at": created_at,
            },
            database_=neo4j_database,
        )


def run_entity_resolution(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
) -> dict[str, Any]:
    """Resolve :EntityMention nodes (scoped to *run_id*) to canonical entities.

    Args:
        config:     :class:`~demo.contracts.runtime.Config`.
        run_id:     The run_id whose EntityMention nodes are to be resolved.
                    Must match the run_id used during PDF ingest / claim extraction.
        source_uri: Provenance URI for the source document.

    Returns:
        A summary dict with counts, resolution breakdown, and artifact paths.
    """
    resolved_at = datetime.now(UTC).isoformat()
    run_root = config.output_dir / "runs" / run_id
    resolution_dir = run_root / "entity_resolution"
    resolution_dir.mkdir(parents=True, exist_ok=True)
    summary_path = resolution_dir / "entity_resolution_summary.json"
    unresolved_path = resolution_dir / "unresolved_mentions.json"

    if config.dry_run:
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "resolver_method": "exact_match",
            "resolver_version": _RESOLVER_VERSION,
            "cluster_version": _CLUSTER_VERSION,
            "mentions_total": 0,
            "resolved": 0,
            "unresolved": 0,
            "clusters_created": 0,
            "resolution_breakdown": {},
            "warnings": ["entity resolution skipped in dry_run mode"],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        unresolved_path.write_text(json.dumps([], indent=2), encoding="utf-8")
        return summary

    import neo4j

    driver = neo4j.GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_username, config.neo4j_password),
    )
    with driver:
        # 1. Read EntityMention nodes for this run_id.
        mention_result, _, _ = driver.execute_query(
            """
            MATCH (mention:EntityMention {run_id: $run_id})
            RETURN mention.mention_id AS mention_id,
                   mention.name AS name,
                   mention.entity_type AS entity_type
            ORDER BY mention.mention_id
            """,
            parameters_={"run_id": run_id},
            database_=config.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        mentions = [
            {
                "mention_id": record["mention_id"],
                "name": record["name"] or "",
                "entity_type": record["entity_type"],
            }
            for record in mention_result
        ]

        # 2. Read all CanonicalEntity nodes (cross-run; resolution is non-destructive).
        canonical_result, _, _ = driver.execute_query(
            """
            MATCH (canonical:CanonicalEntity)
            RETURN canonical.entity_id AS entity_id,
                   canonical.run_id AS run_id,
                   canonical.name AS name,
                   canonical.aliases AS aliases
            ORDER BY canonical.entity_id
            """,
            parameters_={},
            database_=config.neo4j_database,
            routing_=neo4j.RoutingControl.READ,
        )
        canonical_nodes = [
            {
                "entity_id": record["entity_id"] or "",
                "run_id": record["run_id"] or "",
                "name": record["name"] or "",
                "aliases": record["aliases"],
            }
            for record in canonical_result
        ]

        # 3. Build lookup tables and resolve each mention.
        by_qid, by_label, by_alias = _build_lookup_tables(canonical_nodes)

        resolved_rows: list[dict[str, Any]] = []
        unresolved_rows: list[dict[str, Any]] = []
        resolution_breakdown: dict[str, int] = {}

        for mention in mentions:
            result_rec = _resolve_mention(mention, by_qid, by_label, by_alias)
            method = result_rec["resolution_method"]
            resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1

            if result_rec["resolved"]:
                resolved_rows.append(result_rec)
            else:
                unresolved_rows.append(result_rec)

        # 4. Write RESOLVES_TO edges and ResolvedEntityCluster nodes.
        _write_resolution_results(
            driver,
            run_id=run_id,
            source_uri=source_uri,
            resolved_rows=resolved_rows,
            unresolved_rows=unresolved_rows,
            neo4j_database=config.neo4j_database,
        )

    # 5. Write artifacts.
    unresolved_list = [
        {
            "mention_id": row["mention_id"],
            "mention_name": row["mention_name"],
            "normalized_text": row["normalized_text"],
            "cluster_id": f"cluster::{row['normalized_text']}",
        }
        for row in unresolved_rows
    ]
    unresolved_path.write_text(json.dumps(unresolved_list, indent=2), encoding="utf-8")

    # Count unique clusters (one cluster per unique normalized_text value).
    clusters_created = len({row["normalized_text"] for row in unresolved_rows})

    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "resolver_method": "exact_match",
        "resolver_version": _RESOLVER_VERSION,
        "cluster_version": _CLUSTER_VERSION,
        "resolved_at": resolved_at,
        "mentions_total": len(mentions),
        "resolved": len(resolved_rows),
        "unresolved": len(unresolved_rows),
        "clusters_created": clusters_created,
        "resolution_breakdown": resolution_breakdown,
        "entity_resolution_summary_path": str(summary_path),
        "unresolved_mentions_path": str(unresolved_path),
        "warnings": [],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


__all__ = ["run_entity_resolution", "_CLUSTER_VERSION"]
