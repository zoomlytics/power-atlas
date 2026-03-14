"""Entity mention resolution stage.

Reads :EntityMention nodes (scoped to a ``run_id``) from Neo4j and performs
deterministic, non-destructive resolution to :CanonicalEntity nodes.
Mentions that cannot be resolved are grouped by their normalized text into
:ResolvedEntityCluster provisional cluster nodes and linked via :MEMBER_OF
edges instead.

Resolution strategies applied in priority order (``structured_anchor`` mode):

1. **qid_exact**   — mention ``name`` matches ``^Q\\d+$``; MATCH
   ``CanonicalEntity {entity_id: name}``.
2. **label_exact** — ``normalized(mention.name) == normalized(canonical.name)``.
3. **alias_exact** — ``normalized(mention.name)`` appears in the
   ``canonical.aliases`` string (pipe-separated or comma-separated list).
4. **label_cluster** — no canonical match found; mention is grouped with other
   mentions sharing the same normalized text into a :ResolvedEntityCluster.

Resolution strategies applied in priority order (``unstructured_only`` mode):

1. **normalized_exact** — mentions sharing the same normalized text are
   clustered together.
2. **abbreviation** — a mention that is an initialism of another mention's
   normalized text is placed in that mention's cluster.
3. **fuzzy** — mentions whose normalized texts are sufficiently similar
   (difflib SequenceMatcher ratio ≥ 0.85) are placed in the same cluster.
4. **label_cluster** — fallback; mention is grouped in a singleton cluster
   keyed by its own normalized text.

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
from difflib import SequenceMatcher
from typing import Any

# Bump this constant whenever the resolution strategies or scoring logic change
# so that RESOLVES_TO edges in the graph can be distinguished by the version that
# created them (e.g. when re-running resolution after a strategy upgrade).
_RESOLVER_VERSION = "v1.0"

# Bump this constant whenever cluster-assignment logic changes so that MEMBER_OF
# edges can be distinguished by the version that created them.
_CLUSTER_VERSION = "v1.1"

_QID_PATTERN = re.compile(r"^Q\d+$")

# Supported resolution mode identifiers.
_RESOLUTION_MODE_STRUCTURED_ANCHOR = "structured_anchor"
_RESOLUTION_MODE_UNSTRUCTURED_ONLY = "unstructured_only"
_VALID_RESOLUTION_MODES = frozenset({
    _RESOLUTION_MODE_STRUCTURED_ANCHOR,
    _RESOLUTION_MODE_UNSTRUCTURED_ONLY,
})


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


# ---------------------------------------------------------------------------
# Helpers for unstructured_only resolution
# ---------------------------------------------------------------------------

# Common articles/prepositions that are typically skipped when forming initialisms.
_INITIALISM_STOP_WORDS = frozenset({"of", "the", "and", "for", "in", "on", "at", "to", "a", "an"})


def _is_abbreviation(short: str, long_form: str) -> bool:
    """Return True if *short* looks like an initialism of *long_form*.

    Example: "fbi" is an initialism of "federal bureau of investigation"
    (skipping the stop word "of").  Both inputs must already be normalized
    (lowercased, stripped).
    """
    words = long_form.split()
    if len(words) < 2:
        return False
    # Build initials from significant words only (skip common stop words).
    significant = [w for w in words if w and w not in _INITIALISM_STOP_WORDS]
    if len(significant) < 2:
        return False
    initials = "".join(w[0] for w in significant)
    return bool(short) and short == initials


def _fuzzy_ratio(a: str, b: str) -> float:
    """Return the SequenceMatcher similarity ratio for two strings."""
    return SequenceMatcher(None, a, b).ratio()


def _cluster_mentions_unstructured_only(
    mentions: list[dict[str, Any]],
    *,
    fuzzy_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Cluster *mentions* against each other without relying on canonical entities.

    Strategies applied in priority order:

    1. **normalized_exact** — identical normalized text → same cluster.
    2. **abbreviation** — a mention that is an initialism of another's text is
       placed into that mention's cluster.
    3. **fuzzy** — mentions with SequenceMatcher ratio ≥ *fuzzy_threshold* are
       placed in the same cluster as the first sufficiently similar mention.
    4. **label_cluster** — fallback; singleton cluster keyed by the mention's
       own normalized text.

    Returns a list of dicts with the same shape as the ``unresolved_rows``
    produced by :func:`_resolve_mention` (``mention_id``, ``mention_name``,
    ``normalized_text``, ``resolution_method``, ``resolution_confidence``).
    """
    # Canonical cluster text for each mention: maps mention_id → canonical_text
    # (the normalized text that will be used as the cluster key).
    mention_to_cluster: dict[str, str] = {}
    # All unique normalized texts seen so far (in insertion order), used as
    # cluster representatives for fuzzy / abbreviation look-ups.
    seen_texts: list[str] = []
    # Map from normalized_text → resolution_method that assigned it as a cluster rep
    seen_method: dict[str, str] = {}

    for mention in mentions:
        name = (mention.get("name") or "").strip()
        normalized = _normalize(name)

        # Strategy 1: normalized_exact — if we've already seen this exact text,
        # assign to the existing cluster representative.
        if normalized in seen_method:
            mention_to_cluster[mention["mention_id"]] = normalized
            # The method recorded on this mention's row is "normalized_exact".
            continue

        # Strategy 2: abbreviation — check if this mention is an initialism of
        # any existing cluster representative, or vice versa.
        # To be order-independent, when the current mention is the *long form* of
        # an existing abbreviation cluster key, we re-key prior assignments so the
        # long form becomes the stable cluster key.
        abbrev_target: str | None = None
        abbrev_existing_is_short: bool = False
        for existing in seen_texts:
            if _is_abbreviation(normalized, existing):
                # Current is the abbreviation of an existing long form → use existing.
                abbrev_target = existing
                break
            if _is_abbreviation(existing, normalized):
                # Existing is an abbreviation of the current long form.
                # Prefer the long form as the canonical cluster key.
                abbrev_target = existing
                abbrev_existing_is_short = True
                break
        if abbrev_target is not None:
            if abbrev_existing_is_short:
                # Re-key: swap the abbreviation cluster key to the long form so
                # the cluster key is stable regardless of mention order.
                long_key = normalized
                short_key = abbrev_target
                # Update seen_texts and seen_method.
                seen_texts[seen_texts.index(short_key)] = long_key
                seen_method[long_key] = seen_method.pop(short_key)
                # Remap all prior mentions pointing to the abbreviation cluster key.
                for mid, key in mention_to_cluster.items():
                    if key == short_key:
                        mention_to_cluster[mid] = long_key
                abbrev_target = long_key
            mention_to_cluster[mention["mention_id"]] = abbrev_target
            continue

        # Strategy 3: fuzzy — find the first existing representative that is
        # similar enough.
        # Cheap prefilter: SequenceMatcher ratio ≤ 2*min/(min+max), so if the
        # length ratio is too small the ratio cannot reach fuzzy_threshold.
        # Skipping dissimilar-length pairs avoids expensive SequenceMatcher calls.
        norm_len = len(normalized)
        fuzzy_target: str | None = None
        for existing in seen_texts:
            ex_len = len(existing)
            if ex_len == 0 and norm_len == 0:
                fuzzy_target = existing
                break
            if ex_len == 0 or norm_len == 0:
                continue
            min_len = min(norm_len, ex_len)
            max_len = max(norm_len, ex_len)
            # Maximum possible SequenceMatcher ratio given these lengths.
            max_possible = 2 * min_len / (min_len + max_len)
            if max_possible < fuzzy_threshold:
                continue
            if _fuzzy_ratio(normalized, existing) >= fuzzy_threshold:
                fuzzy_target = existing
                break
        if fuzzy_target is not None:
            mention_to_cluster[mention["mention_id"]] = fuzzy_target
            continue

        # Strategy 4: label_cluster fallback — new cluster keyed by own text.
        seen_texts.append(normalized)
        seen_method[normalized] = "label_cluster"
        mention_to_cluster[mention["mention_id"]] = normalized

    # Build result rows.
    # Determine per-mention resolution_method:
    # - "normalized_exact" if the cluster key was already seen before this mention
    # - "abbreviation" if it matched an existing representative by initialism
    # - "fuzzy" if it matched by fuzzy ratio
    # - "label_cluster" if it became its own cluster representative

    # Re-derive the method per mention by re-walking the assignments.
    # We track which mention introduced each cluster key.
    first_introducer: dict[str, str] = {}  # cluster_key → mention_id of introducer
    result_rows: list[dict[str, Any]] = []

    for mention in mentions:
        name = (mention.get("name") or "").strip()
        normalized = _normalize(name)
        cluster_key = mention_to_cluster[mention["mention_id"]]

        if cluster_key not in first_introducer:
            first_introducer[cluster_key] = mention["mention_id"]
            # This mention introduced the cluster.
            method = "label_cluster"
            confidence = 0.0
        elif cluster_key == normalized:
            # Same normalized text as the cluster key → normalized_exact.
            method = "normalized_exact"
            confidence = 1.0
        elif _is_abbreviation(normalized, cluster_key) or _is_abbreviation(cluster_key, normalized):
            method = "abbreviation"
            confidence = 0.75
        else:
            method = "fuzzy"
            confidence = _fuzzy_ratio(normalized, cluster_key)

        result_rows.append({
            "mention_id": mention["mention_id"],
            "mention_name": name,
            "normalized_text": cluster_key,
            "resolution_method": method,
            "resolution_confidence": confidence,
            "resolved": False,
        })

    return result_rows


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
        # Use the per-row resolution_method and resolution_confidence so that
        # the MEMBER_OF edge carries accurate provenance (abbreviation/fuzzy/etc.)
        # rather than a hardcoded fallback.
        cluster_rows = [
            {
                "mention_id": row["mention_id"],
                "cluster_id": f"cluster::{row['normalized_text']}",
                # Use a deterministic canonical name derived from the normalized text
                "canonical_name": row["normalized_text"].title(),
                "normalized_text": row["normalized_text"],
                "score": row.get("resolution_confidence", 1.0),
                "method": row.get("resolution_method", "label_cluster"),
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
                r.status           = row.status,
                r.source_uri       = $source_uri
            """,
            parameters_={
                "rows": cluster_rows,
                "run_id": run_id,
                "resolver_version": _CLUSTER_VERSION,
                "created_at": created_at,
                "source_uri": source_uri,
            },
            database_=neo4j_database,
        )


def run_entity_resolution(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str | None = None,
) -> dict[str, Any]:
    """Resolve or cluster :EntityMention nodes scoped to *run_id*.

    Behaviour depends on *resolution_mode*:

    * ``"structured_anchor"`` (default) — resolves mentions against
      :CanonicalEntity nodes using QID, label-exact, and alias-exact strategies.
      Mentions that cannot be matched are grouped into provisional
      :ResolvedEntityCluster nodes via ``MEMBER_OF`` edges.

    * ``"unstructured_only"`` — clusters mentions against each other without
      any :CanonicalEntity lookup.  All mentions produce ``MEMBER_OF`` edges to
      :ResolvedEntityCluster nodes; no ``RESOLVES_TO`` edges are created.

    All resolution is **non-destructive**: existing nodes are never mutated;
    only ``RESOLVES_TO`` and ``MEMBER_OF`` relationship edges are added.

    Args:
        config:          :class:`~demo.contracts.runtime.Config`.
        run_id:          The run_id whose EntityMention nodes are to be resolved.
                         Must match the run_id used during PDF ingest / claim extraction.
        source_uri:      Provenance URI for the source document.
        resolution_mode: One of ``"structured_anchor"`` (default) or
                         ``"unstructured_only"``.  When ``None`` the value is
                         read from ``config.resolution_mode`` (if present) and
                         falls back to ``"structured_anchor"``.

    Returns:
        A summary dict with counts, resolution breakdown, ``resolution_mode``,
        and artifact paths.
    """
    # Resolve the effective mode: explicit arg > config attribute > default.
    if resolution_mode is None:
        resolution_mode = getattr(config, "resolution_mode", _RESOLUTION_MODE_STRUCTURED_ANCHOR) or _RESOLUTION_MODE_STRUCTURED_ANCHOR
    if resolution_mode not in _VALID_RESOLUTION_MODES:
        raise ValueError(
            f"Unknown resolution_mode {resolution_mode!r}. "
            f"Valid modes: {sorted(_VALID_RESOLUTION_MODES)}"
        )

    resolved_at = datetime.now(UTC).isoformat()
    run_root = config.output_dir / "runs" / run_id
    resolution_dir = run_root / "entity_resolution"
    resolution_dir.mkdir(parents=True, exist_ok=True)
    summary_path = resolution_dir / "entity_resolution_summary.json"
    unresolved_path = resolution_dir / "unresolved_mentions.json"

    if config.dry_run:
        resolver_method = (
            "unstructured_clustering"
            if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY
            else "canonical_exact_match"
        )
        summary: dict[str, Any] = {
            "status": "dry_run",
            "run_id": run_id,
            "source_uri": source_uri,
            "resolution_mode": resolution_mode,
            "resolver_method": resolver_method,
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

        resolved_rows: list[dict[str, Any]] = []
        unresolved_rows: list[dict[str, Any]] = []
        resolution_breakdown: dict[str, int] = {}

        if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY:
            # 2a. unstructured_only: cluster mentions against each other.
            #     No CanonicalEntity lookup is performed.
            cluster_rows_result = _cluster_mentions_unstructured_only(mentions)
            for row in cluster_rows_result:
                method = row["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1
                unresolved_rows.append(row)
        else:
            # 2b. structured_anchor (default): resolve against CanonicalEntity nodes.
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

            by_qid, by_label, by_alias = _build_lookup_tables(canonical_nodes)

            for mention in mentions:
                result_rec = _resolve_mention(mention, by_qid, by_label, by_alias)
                method = result_rec["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1

                if result_rec["resolved"]:
                    resolved_rows.append(result_rec)
                else:
                    unresolved_rows.append(result_rec)

        # 3. Write RESOLVES_TO edges and ResolvedEntityCluster nodes.
        _write_resolution_results(
            driver,
            run_id=run_id,
            source_uri=source_uri,
            resolved_rows=resolved_rows,
            unresolved_rows=unresolved_rows,
            neo4j_database=config.neo4j_database,
        )

    # 4. Write artifacts.
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

    live_resolver_method = (
        "unstructured_clustering"
        if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY
        else "canonical_exact_match"
    )
    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "resolution_mode": resolution_mode,
        "resolver_method": live_resolver_method,
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


__all__ = [
    "run_entity_resolution",
    "_RESOLUTION_MODE_STRUCTURED_ANCHOR",
    "_RESOLUTION_MODE_UNSTRUCTURED_ONLY",
    "_VALID_RESOLUTION_MODES",
    "_cluster_mentions_unstructured_only",
    "_is_abbreviation",
    "_fuzzy_ratio",
]
