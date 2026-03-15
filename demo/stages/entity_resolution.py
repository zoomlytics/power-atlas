"""Entity mention resolution and clustering stage.

Reads :EntityMention nodes (scoped to a ``run_id``) from Neo4j and, depending
on the configured mode, either performs deterministic resolution to
:CanonicalEntity nodes (``structured_anchor`` mode), performs
normalization- and similarity-based clustering of mentions without requiring
a canonical entity anchor (``unstructured_only`` mode), or performs a
two-stage process that first clusters mentions against each other and then
optionally enriches resulting clusters with alignment links to
:CanonicalEntity nodes (``hybrid`` mode).

In ``structured_anchor`` mode, mentions that cannot be resolved are grouped by
their normalized text into :ResolvedEntityCluster provisional cluster nodes
and linked via :MEMBER_OF edges instead.

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

``hybrid`` mode runs the full ``unstructured_only`` clustering pass first, then
performs a best-effort alignment of each resulting :ResolvedEntityCluster to a
matching :CanonicalEntity node (if any exist).  Alignment uses label-exact and
alias-exact strategies; matched clusters receive an ``ALIGNED_WITH`` edge
pointing at the :CanonicalEntity.  Structured ingest is entirely optional:
when no :CanonicalEntity nodes are present the mode degrades gracefully to
pure unstructured clustering.

Alignment strategies applied in priority order (``hybrid`` mode):

1. **label_exact** — the cluster's ``normalized_text`` key (or the normalized
   suffix of its ``cluster_id``) matches a :CanonicalEntity by its normalized
   label.
2. **alias_exact** — the same normalized cluster value appears in the
   ``canonical.aliases`` string (pipe-separated or comma-separated list) of a :CanonicalEntity.

All resolution and clustering is **non-destructive**: existing nodes are
never mutated; only ``RESOLVES_TO``, ``MEMBER_OF``, and ``ALIGNED_WITH``
relationship edges are added/updated.

Graph model
-----------
* ``(:EntityMention)-[:RESOLVES_TO]->(:CanonicalEntity)``     — structured match
* ``(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster)`` — provisional cluster
* ``(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity)`` — enrichment link

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
from pathlib import Path

# Bump this constant whenever the resolution strategies or scoring logic change
# so that RESOLVES_TO edges in the graph can be distinguished by the version that
# created them (e.g. when re-running resolution after a strategy upgrade).
_RESOLVER_VERSION = "v1.0"

# Bump this constant whenever cluster-assignment logic changes so that MEMBER_OF
# edges can be distinguished by the version that created them.
_CLUSTER_VERSION = "v1.1"

# Bump this constant whenever the cluster-to-canonical alignment logic changes so
# that ALIGNED_WITH edges can be distinguished by the version that created them.
_ALIGNMENT_VERSION = "v1.0"

_QID_PATTERN = re.compile(r"^Q\d+$")

# Strips everything that is not a lowercase ASCII letter. Intended to be used
# on already-normalized (lowercased) text to normalize abbreviated forms like
# "f.b.i." → "fbi" and "fbi," → "fbi" so that _is_abbreviation() works on
# typical extracted text.
_RE_NON_ALPHA = re.compile(r"[^a-z]")

# Supported resolution mode identifiers.
_RESOLUTION_MODE_STRUCTURED_ANCHOR = "structured_anchor"
_RESOLUTION_MODE_UNSTRUCTURED_ONLY = "unstructured_only"
_RESOLUTION_MODE_HYBRID = "hybrid"
_VALID_RESOLUTION_MODES = frozenset({
    _RESOLUTION_MODE_STRUCTURED_ANCHOR,
    _RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    _RESOLUTION_MODE_HYBRID,
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


def _compute_initials(text: str) -> str | None:
    """Return the initialism formed by the significant words in *text*.

    The input is lowercased, and each word token is stripped of non-alphabetic
    characters before stop-word filtering and initial extraction, so tokens like
    ``"Of,"``/``"of,"`` or ``"The."``/``"the."`` are treated identically to their
    clean equivalents.

    Returns ``None`` when *text* has fewer than two significant words (i.e.
    it would not produce a meaningful abbreviation).
    """
    significant: list[str] = []
    for w in text.split():
        w_lower = w.lower()
        alpha = _RE_NON_ALPHA.sub("", w_lower)
        if alpha and alpha not in _INITIALISM_STOP_WORDS:
            significant.append(alpha)
    if len(significant) < 2:
        return None
    return "".join(w[0] for w in significant)


def _is_abbreviation(short: str, long_form: str) -> bool:
    """Return True if *short* looks like an initialism of *long_form*.

    Example: ``"fbi"`` is an initialism of ``"federal bureau of investigation"``
    (skipping the stop word ``"of"``).  Inputs are case-normalized internally.
    The *short* token is further stripped of non-alphabetic characters so forms
    like ``"F.B.I."`` and ``"fbi,"`` still match the same initialism as
    ``"fbi"``.  Each word in *long_form* is likewise stripped of punctuation
    before stop-word filtering and initial extraction, so tokens like
    ``"Investigation,"``/``"investigation,"`` are handled correctly.
    """
    short_alpha = _RE_NON_ALPHA.sub("", short.lower())
    if not short_alpha:
        return False
    initials = _compute_initials(long_form.lower())
    if initials is None:
        return False
    return short_alpha == initials


def _fuzzy_ratio(a: str, b: str) -> float:
    """Return the SequenceMatcher similarity ratio for two strings."""
    return SequenceMatcher(None, a, b).ratio()


def _membership_score(method: str, resolution_confidence: float) -> float:
    """Return the MEMBER_OF edge score for a given cluster assignment method.

    ``resolution_confidence`` from :func:`_resolve_mention` is a match-quality
    score, not a membership certainty score.  Deterministic cluster assignments
    (``label_cluster``, ``normalized_exact``) have certainty 1.0 even though
    their match confidence may be stored as 0.0 on the unresolved-row.  Fuzzy
    matches use the actual SequenceMatcher ratio as the membership score.
    """
    if method in ("label_cluster", "normalized_exact"):
        return 1.0
    if method == "abbreviation":
        return 0.75
    # fuzzy: use the actual similarity ratio stored in resolution_confidence.
    return resolution_confidence


def _cluster_mentions_unstructured_only(
    mentions: list[dict[str, Any]],
    *,
    fuzzy_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Cluster *mentions* against each other without relying on canonical entities.

    Strategies applied in priority order:

    1. **normalized_exact** — identical normalized text → same cluster (type-agnostic).
    2. **abbreviation** — a mention that is an initialism of another mention's
       normalized text (within the same ``entity_type``) is placed into that
       mention's cluster.  O(1) per mention via per-type initialism indices.
    3. **fuzzy** — mentions with SequenceMatcher ratio ≥ *fuzzy_threshold*
       (within the same ``entity_type``) are placed in the same cluster as the
       first sufficiently similar mention.
    4. **label_cluster** — fallback; singleton cluster keyed by the mention's
       own normalized text.

    Abbreviation and fuzzy comparisons are scoped to mentions sharing the same
    ``entity_type`` value (including ``None``).  This acts as a blocking step
    that avoids cross-type spurious matches and bounds each per-mention scan
    to same-type cluster representatives.

    Returns a list of dicts with keys: ``mention_id``, ``mention_name``,
    ``normalized_text``, ``resolution_method``, ``resolution_confidence``,
    and ``resolved`` (always ``False``).
    """
    # mention_id → cluster key
    mention_to_cluster: dict[str, str] = {}
    # mention_id → (resolution_method, resolution_confidence)
    mention_to_method: dict[str, tuple[str, float]] = {}
    # mention_id → entity_type  (required to scope re-key operations correctly)
    mention_to_type: dict[str, str | None] = {}

    # All registered cluster keys, type-agnostic (for O(1) normalized_exact check).
    seen_keys: set[str] = set()

    # cluster_key → [mention_ids]  Reverse index enabling O(cluster_size) remap
    # during re-keying instead of scanning all mentions seen so far.
    cluster_to_mentions: dict[str, list[str]] = {}

    # Per-type abbreviation indices (both O(1)):
    #   initials_to_long_by_type:  initials_str → long_form_cluster_key
    #     Forward check: is the current text's alpha form an initialism of some
    #     already-registered long-form cluster?
    initials_to_long_by_type: dict[str | None, dict[str, str]] = {}
    #   abbrev_alpha_by_type:  alpha_of_cluster_key → list[cluster_key]
    #     Reverse check: which existing cluster keys look like abbreviations of
    #     the current text (i.e. their alpha-stripped form equals the current
    #     text's initials)?  A list is used so that multiple abbreviation variants
    #     sharing the same alpha (e.g. "fbi" and "f.b.i.") are *all* promoted when
    #     a long form is encountered, rather than only the last-registered one.
    abbrev_alpha_by_type: dict[str | None, dict[str, list[str]]] = {}

    # Per-type ordered list of cluster representatives (for fuzzy scan).
    seen_texts_by_type: dict[str | None, list[str]] = {}

    def _register_new_cluster(cluster_key: str, etype: str | None) -> None:
        """Add a brand-new cluster key to every per-type index."""
        seen_keys.add(cluster_key)
        seen_texts_by_type.setdefault(etype, []).append(cluster_key)
        abbrev_alpha_by_type.setdefault(etype, {}).setdefault(
            _RE_NON_ALPHA.sub("", cluster_key), []
        ).append(cluster_key)
        initials = _compute_initials(cluster_key)
        if initials is not None:
            initials_to_long_by_type.setdefault(etype, {})[initials] = cluster_key

    def _register_cluster_for_type(cluster_key: str, etype: str | None) -> None:
        """Ensure cluster_key is visible in the per-type indices for etype.

        Called when a normalized_exact match joins a cluster that was first
        introduced by a different entity_type.  This ensures later same-type
        fuzzy/abbreviation matching can still find the cluster without
        disturbing existing assignments.  Uses setdefault so that existing
        entries for this type are never overwritten.
        """
        type_texts = seen_texts_by_type.setdefault(etype, [])
        if cluster_key not in type_texts:
            type_texts.append(cluster_key)
        alpha = _RE_NON_ALPHA.sub("", cluster_key)
        bucket = abbrev_alpha_by_type.setdefault(etype, {}).setdefault(alpha, [])
        if cluster_key not in bucket:
            bucket.append(cluster_key)
        initials = _compute_initials(cluster_key)
        if initials is not None:
            initials_to_long_by_type.setdefault(etype, {}).setdefault(initials, cluster_key)

    def _promote_long_form(short_key: str, long_key: str, etype: str | None) -> None:
        """Re-key same-*etype* mentions from short_key to long_key.

        Mentions of a *different* entity_type that share ``short_key`` via
        ``normalized_exact`` are intentionally left in place so that cross-type
        clustering is never disturbed by an abbreviation relationship found in
        another type.
        """
        # Always register long_key in the global key set.
        seen_keys.add(long_key)

        # Update per-type text list (swap short → long for this type).
        type_texts = seen_texts_by_type.get(etype, [])
        if short_key in type_texts:
            # Replace the short form with the long form for this type.
            type_texts[type_texts.index(short_key)] = long_key
            # De-duplicate representatives for this type (preserve order).
            seen_for_type: set[str] = set()
            deduped_type_texts: list[str] = []
            for t in type_texts:
                if t not in seen_for_type:
                    seen_for_type.add(t)
                    deduped_type_texts.append(t)
            if len(deduped_type_texts) != len(type_texts):
                seen_texts_by_type[etype] = deduped_type_texts

        # Update abbreviation indices for this type.
        old_alpha = _RE_NON_ALPHA.sub("", short_key)
        type_abbrev = abbrev_alpha_by_type.get(etype, {})
        bucket = type_abbrev.get(old_alpha, [])
        if short_key in bucket:
            bucket.remove(short_key)
        if not bucket:
            type_abbrev.pop(old_alpha, None)
        # Add long_key to its own alpha bucket.
        long_alpha = _RE_NON_ALPHA.sub("", long_key)
        long_bucket = abbrev_alpha_by_type.setdefault(etype, {}).setdefault(long_alpha, [])
        if long_key not in long_bucket:
            long_bucket.append(long_key)
        # Remove any longform-initials entry that pointed to short_key.
        initials_map = initials_to_long_by_type.get(etype, {})
        for k in [k for k, v in initials_map.items() if v == short_key]:
            del initials_map[k]
        # Register long_key's own initials (it may in turn be a long form).
        long_initials = _compute_initials(long_key)
        if long_initials is not None:
            initials_to_long_by_type.setdefault(etype, {})[long_initials] = long_key

        # Remap only same-type members using the reverse index (O(cluster_size)).
        new_members: list[str] = []
        remaining: list[str] = []
        for prior_mid in cluster_to_mentions.get(short_key, []):
            if mention_to_type.get(prior_mid) == etype:
                mention_to_cluster[prior_mid] = long_key
                mention_to_method[prior_mid] = ("abbreviation", 0.75)
                new_members.append(prior_mid)
            else:
                remaining.append(prior_mid)
        cluster_to_mentions.setdefault(long_key, []).extend(new_members)
        if remaining:
            cluster_to_mentions[short_key] = remaining
        elif short_key in cluster_to_mentions:
            del cluster_to_mentions[short_key]

        # Only remove short_key from seen_keys when no cross-type mentions
        # remain on it; otherwise Strategy 1 (normalized_exact) must still be
        # able to match future mentions of those other types.
        if not remaining:
            seen_keys.discard(short_key)

    for mention in mentions:
        name = (mention.get("name") or "").strip()
        normalized = _normalize(name)
        mid = mention["mention_id"]
        entity_type: str | None = mention.get("entity_type")
        short_alpha = _RE_NON_ALPHA.sub("", normalized)

        # Strategy 1: normalized_exact (type-agnostic).
        if normalized in seen_keys:
            # IMPORTANT: If this normalized key is a known short-form whose
            # initials have been promoted to a different long-form cluster for
            # this entity_type, prefer the long-form cluster instead of
            # re-attaching to the short-form key. This preserves the invariant
            # that abbreviation promotion yields a stable long-form cluster key
            # per entity_type, even though short-form keys remain in seen_keys
            # for cross-type mentions.
            mapped_long = initials_to_long_by_type.get(entity_type, {}).get(short_alpha)
            if mapped_long is not None and mapped_long != normalized:
                mention_to_cluster[mid] = mapped_long
                mention_to_method[mid] = ("abbreviation", 0.75)
                mention_to_type[mid] = entity_type
                cluster_to_mentions.setdefault(mapped_long, []).append(mid)
                continue

            mention_to_cluster[mid] = normalized
            mention_to_method[mid] = ("normalized_exact", 1.0)
            mention_to_type[mid] = entity_type
            cluster_to_mentions.setdefault(normalized, []).append(mid)
            # Ensure the cluster is visible in the per-type indices so later
            # same-type mentions can still fuzzy/abbreviation-match against it
            # even if the cluster was first introduced by a different entity_type.
            _register_cluster_for_type(normalized, entity_type)
            continue

        # Strategy 2: abbreviation (type-scoped, O(1) via index).

        # Forward: is current text an abbreviation of an existing long-form cluster?
        existing_long = initials_to_long_by_type.get(entity_type, {}).get(short_alpha)
        if existing_long is not None:
            mention_to_cluster[mid] = existing_long
            mention_to_method[mid] = ("abbreviation", 0.75)
            mention_to_type[mid] = entity_type
            cluster_to_mentions.setdefault(existing_long, []).append(mid)
            continue

        # Reverse: is current text a long form whose initials match existing
        # cluster keys (which would then be abbreviations)?  Multiple variants
        # sharing the same alpha (e.g. "fbi" and "f.b.i.") must ALL be promoted
        # to avoid orphaned abbreviation clusters.
        current_initials = _compute_initials(normalized)
        abbrev_cluster_keys: list[str] = []
        if current_initials is not None:
            abbrev_cluster_keys = list(
                abbrev_alpha_by_type.get(entity_type, {}).get(current_initials, [])
            )
        if abbrev_cluster_keys:
            for abbrev_key in abbrev_cluster_keys:
                _promote_long_form(abbrev_key, normalized, entity_type)
            mention_to_cluster[mid] = normalized
            mention_to_method[mid] = ("label_cluster", 1.0)
            mention_to_type[mid] = entity_type
            cluster_to_mentions.setdefault(normalized, []).append(mid)
            continue

        # Strategy 3: fuzzy (type-scoped, with length-ratio prefilter).
        norm_len = len(normalized)
        fuzzy_target: str | None = None
        fuzzy_score: float = 0.0
        for existing in seen_texts_by_type.get(entity_type, []):
            ex_len = len(existing)
            if ex_len == 0 and norm_len == 0:
                fuzzy_target = existing
                fuzzy_score = 1.0
                break
            if ex_len == 0 or norm_len == 0:
                continue
            min_len = min(norm_len, ex_len)
            max_len = max(norm_len, ex_len)
            # Upper bound on SequenceMatcher ratio; skip if it can't reach threshold.
            if 2 * min_len / (min_len + max_len) < fuzzy_threshold:
                continue
            ratio = _fuzzy_ratio(normalized, existing)
            if ratio >= fuzzy_threshold:
                fuzzy_target = existing
                fuzzy_score = ratio
                break
        if fuzzy_target is not None:
            mention_to_cluster[mid] = fuzzy_target
            mention_to_method[mid] = ("fuzzy", fuzzy_score)
            mention_to_type[mid] = entity_type
            cluster_to_mentions.setdefault(fuzzy_target, []).append(mid)
            continue

        # Strategy 4: label_cluster fallback — new singleton cluster.
        _register_new_cluster(normalized, entity_type)
        mention_to_cluster[mid] = normalized
        mention_to_method[mid] = ("label_cluster", 1.0)
        mention_to_type[mid] = entity_type
        cluster_to_mentions.setdefault(normalized, []).append(mid)

    return [
        {
            "mention_id": mention["mention_id"],
            "mention_name": (mention.get("name") or "").strip(),
            "normalized_text": mention_to_cluster[mention["mention_id"]],
            "resolution_method": mention_to_method[mention["mention_id"]][0],
            "resolution_confidence": mention_to_method[mention["mention_id"]][1],
            "resolved": False,
        }
        for mention in mentions
    ]


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
        # Use per-row resolution_method for accurate provenance and compute the
        # MEMBER_OF score via _membership_score so deterministic cluster
        # assignments (label_cluster, normalized_exact) always get score=1.0,
        # regardless of any match-quality confidence on the unresolved row.
        cluster_rows = []
        for row in unresolved_rows:
            method = row.get("resolution_method", "label_cluster")
            cluster_rows.append({
                "mention_id": row["mention_id"],
                "cluster_id": f"cluster::{row['normalized_text']}",
                # Use a deterministic canonical name derived from the normalized text
                "canonical_name": row["normalized_text"].title(),
                "normalized_text": row["normalized_text"],
                "score": _membership_score(method, row.get("resolution_confidence", 1.0)),
                "method": method,
                # "accepted" only for deterministic cluster assignments;
                # probabilistic methods (abbreviation, fuzzy) are "provisional"
                # so downstream consumers can distinguish high-confidence from
                # review-required memberships.
                "status": "accepted" if method in ("label_cluster", "normalized_exact") else "provisional",
            })
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


def _align_clusters_to_canonical(
    cluster_normalized_texts: list[str],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Align :ResolvedEntityCluster nodes to :CanonicalEntity nodes.

    For each unique cluster (identified by its *normalized_text* key) applies
    label-exact then alias-exact lookup against the pre-built lookup tables.
    Returns one alignment row per cluster that matched a canonical entity.

    Alignment strategies applied in priority order:

    1. **label_exact** — cluster's normalized text matches a CanonicalEntity
       by its normalized label.
    2. **alias_exact** — cluster's normalized text appears in a CanonicalEntity's
       alias list.

    Args:
        cluster_normalized_texts: Unique normalized-text keys of clusters to align.
        by_label: Mapping of normalized canonical label → canonical row.
        by_alias:  Mapping of normalized alias → canonical row.

    Returns:
        A list of alignment row dicts with keys: ``cluster_id``,
        ``canonical_entity_id``, ``canonical_run_id``, ``alignment_method``,
        ``alignment_score``, and ``alignment_status``.
    """
    rows: list[dict[str, Any]] = []
    for normalized_text in cluster_normalized_texts:
        cluster_id = f"cluster::{normalized_text}"

        canonical = by_label.get(normalized_text)
        if canonical:
            rows.append({
                "cluster_id": cluster_id,
                "canonical_entity_id": canonical["entity_id"],
                "canonical_run_id": canonical["run_id"],
                "alignment_method": "label_exact",
                "alignment_score": 0.9,
                "alignment_status": "aligned",
            })
            continue

        canonical = by_alias.get(normalized_text)
        if canonical:
            rows.append({
                "cluster_id": cluster_id,
                "canonical_entity_id": canonical["entity_id"],
                "canonical_run_id": canonical["run_id"],
                "alignment_method": "alias_exact",
                "alignment_score": 0.8,
                "alignment_status": "aligned",
            })

    return rows


def _write_alignment_results(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    alignment_rows: list[dict[str, Any]],
    neo4j_database: str,
) -> None:
    """Persist ALIGNED_WITH edges from :ResolvedEntityCluster to :CanonicalEntity.

    Each matched cluster receives a non-destructive ``ALIGNED_WITH`` edge
    carrying alignment provenance metadata: ``alignment_method``,
    ``alignment_score``, ``alignment_status``, ``alignment_version``,
    ``run_id``, and ``source_uri``.  Existing cluster nodes and ``MEMBER_OF``
    edges are never modified.
    """
    if not alignment_rows:
        return
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
        MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
        MERGE (cluster)-[r:ALIGNED_WITH {
            run_id:            $run_id,
            alignment_version: $alignment_version
        }]->(canonical)
        SET r.alignment_method = row.alignment_method,
            r.alignment_score  = row.alignment_score,
            r.alignment_status = row.alignment_status,
            r.source_uri       = $source_uri
        """,
        parameters_={
            "rows": alignment_rows,
            "run_id": run_id,
            "source_uri": source_uri,
            "alignment_version": _ALIGNMENT_VERSION,
        },
        database_=neo4j_database,
    )


def run_entity_resolution(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
) -> dict[str, Any]:
    """Resolve or cluster :EntityMention nodes scoped to *run_id*.

    Behaviour depends on *resolution_mode*:

    * ``"structured_anchor"`` — resolves mentions against
      :CanonicalEntity nodes using QID, label-exact, and alias-exact strategies.
      Mentions that cannot be matched are grouped into provisional
      :ResolvedEntityCluster nodes via ``MEMBER_OF`` edges.

    * ``"unstructured_only"`` — clusters mentions against each other without
      any :CanonicalEntity lookup.  All mentions produce ``MEMBER_OF`` edges to
      :ResolvedEntityCluster nodes; no ``RESOLVES_TO`` edges are created.

    * ``"hybrid"`` — runs the full unstructured clustering pass first (identical
      to ``unstructured_only``), then optionally enriches resulting
      :ResolvedEntityCluster nodes with ``ALIGNED_WITH`` edges to any matching
      :CanonicalEntity nodes.  Structured ingest is not required; when no
      :CanonicalEntity nodes are present the mode degrades gracefully to pure
      unstructured clustering.

    All resolution is **non-destructive**: existing nodes are never mutated;
    only ``RESOLVES_TO``, ``MEMBER_OF``, and ``ALIGNED_WITH`` relationship edges
    are added.

    Args:
        config:          :class:`~demo.contracts.runtime.Config`.
        run_id:          The run_id whose EntityMention nodes are to be resolved.
                         Must match the run_id used during PDF ingest / claim extraction.
        source_uri:      Provenance URI for the source document.
        resolution_mode: One of ``"structured_anchor"``, ``"unstructured_only"``, or
                         ``"hybrid"``. When ``None``, the effective mode is resolved as:
                         explicit argument (if provided) > ``config.resolution_mode``
                         (if present and truthy, typically defaulting to ``"unstructured_only"``)
                         > ``"structured_anchor"`` as a final fallback.
        artifact_subdir: Subdirectory under ``runs/<run_id>/`` where artifacts are
                         written.  Defaults to ``"entity_resolution"``.  Pass a
                         mode-specific name (e.g. ``"entity_resolution_unstructured_only"``
                         or ``"entity_resolution_hybrid"``) when calling the function
                         multiple times for the same *run_id* to avoid overwriting
                         artifacts from an earlier pass.

    Returns:
        A summary dict with counts, resolution breakdown, ``resolution_mode``,
        and artifact paths.  In ``"hybrid"`` mode the summary additionally
        includes ``aligned_clusters``, ``alignment_breakdown``, and
        ``alignment_version``.
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
    run_root = (config.output_dir / "runs" / run_id).resolve()

    artifact_subdir_path = Path(artifact_subdir)
    # Prevent path traversal and absolute paths in artifact_subdir to keep writes
    # confined under the run_root directory.
    if artifact_subdir_path.is_absolute() or ".." in artifact_subdir_path.parts:
        raise ValueError(f"Invalid artifact_subdir {artifact_subdir!r}: must be a relative path without '..'.")
    if any(part in ("", ".") for part in artifact_subdir_path.parts):
        raise ValueError(f"Invalid artifact_subdir {artifact_subdir!r}: contains empty or '.' path components.")

    resolution_dir = (run_root / artifact_subdir_path).resolve()
    if run_root != resolution_dir and run_root not in resolution_dir.parents:
        raise ValueError(f"Invalid artifact_subdir {artifact_subdir!r}: resolved path escapes run directory.")

    resolution_dir.mkdir(parents=True, exist_ok=True)
    summary_path = resolution_dir / "entity_resolution_summary.json"
    unresolved_path = resolution_dir / "unresolved_mentions.json"

    if config.dry_run:
        if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY:
            resolver_method = "unstructured_clustering"
        elif resolution_mode == _RESOLUTION_MODE_HYBRID:
            resolver_method = "unstructured_clustering_with_canonical_alignment"
        else:
            resolver_method = "canonical_exact_match"
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
        if resolution_mode == _RESOLUTION_MODE_HYBRID:
            summary["alignment_version"] = _ALIGNMENT_VERSION
            summary["aligned_clusters"] = 0
            summary["alignment_breakdown"] = {}
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
        alignment_rows: list[dict[str, Any]] = []

        if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY:
            # 2a. unstructured_only: cluster mentions against each other.
            #     No CanonicalEntity lookup is performed.
            cluster_rows_result = _cluster_mentions_unstructured_only(mentions)
            for row in cluster_rows_result:
                method = row["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1
                unresolved_rows.append(row)
        elif resolution_mode == _RESOLUTION_MODE_HYBRID:
            # 2c. hybrid: cluster mentions first (identical to unstructured_only),
            #     then optionally align resulting clusters to CanonicalEntity nodes.
            cluster_rows_result = _cluster_mentions_unstructured_only(mentions)
            for row in cluster_rows_result:
                method = row["resolution_method"]
                resolution_breakdown[method] = resolution_breakdown.get(method, 0) + 1
                unresolved_rows.append(row)

            # Enrichment step: align clusters to canonical entities where possible.
            # This is additive — clusters with no canonical match remain unchanged.
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
                    "entity_id": record["entity_id"],
                    "run_id": record["run_id"],
                    "name": record["name"] or "",
                    "aliases": record["aliases"],
                }
                for record in canonical_result
                if record["entity_id"] and record["run_id"]
            ]
            if canonical_nodes:
                _, by_label, by_alias = _build_lookup_tables(canonical_nodes)
                unique_cluster_texts = sorted(
                    {row["normalized_text"] for row in unresolved_rows}
                )
                alignment_rows = _align_clusters_to_canonical(
                    unique_cluster_texts, by_label, by_alias
                )
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
                    "entity_id": record["entity_id"],
                    "run_id": record["run_id"],
                    "name": record["name"] or "",
                    "aliases": record["aliases"],
                }
                for record in canonical_result
                if record["entity_id"] and record["run_id"]
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

        # 3b. In hybrid mode, write ALIGNED_WITH enrichment edges.
        if resolution_mode == _RESOLUTION_MODE_HYBRID:
            _write_alignment_results(
                driver,
                run_id=run_id,
                source_uri=source_uri,
                alignment_rows=alignment_rows,
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

    if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY:
        live_resolver_method = "unstructured_clustering"
    elif resolution_mode == _RESOLUTION_MODE_HYBRID:
        live_resolver_method = "unstructured_clustering_with_canonical_alignment"
    else:
        live_resolver_method = "canonical_exact_match"

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
    if resolution_mode == _RESOLUTION_MODE_HYBRID:
        alignment_breakdown: dict[str, int] = {}
        for row in alignment_rows:
            m = row["alignment_method"]
            alignment_breakdown[m] = alignment_breakdown.get(m, 0) + 1
        summary["alignment_version"] = _ALIGNMENT_VERSION
        summary["aligned_clusters"] = len(alignment_rows)
        summary["alignment_breakdown"] = alignment_breakdown
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


__all__ = [
    "run_entity_resolution",
    "_RESOLUTION_MODE_STRUCTURED_ANCHOR",
    "_RESOLUTION_MODE_UNSTRUCTURED_ONLY",
    "_RESOLUTION_MODE_HYBRID",
    "_VALID_RESOLUTION_MODES",
    "_ALIGNMENT_VERSION",
]
