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
their ``(run_id, entity_type, normalized_text)`` identity into
:ResolvedEntityCluster provisional cluster nodes and linked via :MEMBER_OF
edges instead.

Resolution strategies applied in priority order (``structured_anchor`` mode):

1. **qid_exact**   — mention ``name`` matches ``^Q\\d+$``; MATCH
   ``CanonicalEntity {entity_id: name}``.
2. **label_exact** — ``normalized(mention.name) == normalized(canonical.name)``.
3. **alias_exact** — ``normalized(mention.name)`` appears in the
   ``canonical.aliases`` string (pipe-separated or comma-separated list).
4. **label_cluster** — no canonical match found; mention is grouped with other
   mentions sharing the same ``(run_id, entity_type, normalized_text)``
   into a :ResolvedEntityCluster.

Resolution strategies applied in priority order (``unstructured_only`` mode):

1. **normalized_exact** — mentions sharing the same ``normalized_text`` are
   attached to the same internal cluster key regardless of entity type.
   Entity-type isolation is **not** enforced here; it is enforced later when
   ``_make_cluster_id`` generates the final ``cluster_id`` (which encodes
   ``entity_type`` as a separate component).  This means two mentions with the
   same normalized text but different entity types share one internal key but
   end up in two separate :ResolvedEntityCluster nodes in Neo4j.
2. **abbreviation** — a mention that is an initialism of another mention's
   normalized text is placed in that mention's cluster (within the same
   ``entity_type`` bucket).
3. **fuzzy** — mentions whose normalized texts are sufficiently similar
   (difflib SequenceMatcher ratio ≥ 0.85) are placed in the same cluster
   (within the same ``entity_type`` bucket).
4. **label_cluster** — fallback; mention is grouped in a singleton cluster
   keyed by its ``(run_id, entity_type, normalized_text)`` identity.

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

Mention normalisation
---------------------
All mention and entity-name comparisons are performed on the output of
:func:`_normalize`, which applies the following transformations in order:

1. Strip leading/trailing whitespace.
2. NFKD Unicode decomposition — folds compatibility variants (full-width
   characters, ligatures, etc.) and separates base characters from
   combining marks.
3. Diacritic removal — drops combining marks so accented forms cluster with
   their unaccented equivalents (e.g. ``"naïve"`` → ``"naive"``).
4. Apostrophe normalisation — curly/typographic apostrophe variants → ``'``.
5. Hyphen/dash normalisation — en-dash, em-dash, etc. → ``-``.
6. Whitespace collapse — runs of whitespace → single ASCII space.
7. Case-folding (``str.casefold()``) — aggressive lowercasing including
   ``ß`` → ``ss``.

Graph model
-----------
* ``(:EntityMention)-[:RESOLVES_TO]->(:CanonicalEntity)``     — structured match
* ``(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster)`` — provisional cluster
* ``(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity)`` — enrichment link

Artifacts written to ``runs/<run_id>/entity_resolution/`` by default.
Callers may pass ``artifact_subdir`` to ``run_entity_resolution_request_context()`` to
redirect artifacts to a different subdirectory under ``runs/<run_id>/``
(e.g. ``"entity_resolution_unstructured_only"``), which is useful when
running multiple passes for the same *run_id*:

- ``entity_resolution_summary.json`` — counts, breakdown, resolver metadata.
- ``unresolved_mentions.json``        — list of clustered (unresolved) mentions, each
  containing: ``mention_id``, ``mention_name``, ``normalized_text``, ``entity_type``,
  ``cluster_id``, and ``source_uri``.  ``source_uri`` is the per-mention origin URI
  read from the :EntityMention node in Neo4j; it is included here as provenance
  metadata only and does **not** affect which cluster a mention belongs to.

Summary JSON metrics
---------------------
The main resolution routine writes ``entity_resolution_summary.json`` which is
also returned to callers as a plain ``dict``. It always contains the following
keys (regardless of resolution mode):

* ``status``: ``"live"`` on success, or ``"dry_run"`` when resolution was skipped.
* ``run_id``: The run identifier used to scope :EntityMention nodes.
* ``source_uri``: URI of the ingested source whose mentions were resolved.
* ``resolution_mode``: One of ``"structured_anchor"``, ``"unstructured_only"``,
  or ``"hybrid"``.
* ``resolver_method``: Human-readable label for the resolver strategy used.
* ``resolver_version``: Version string for the resolver implementation.
* ``cluster_version``: Version string for the clustering strategy.
* ``mentions_total``: Total number of :EntityMention nodes considered.
* ``resolved``: Count of mentions that matched a canonical entity and received a
  ``RESOLVES_TO`` edge to a :CanonicalEntity node (``"structured_anchor"`` mode
  only; always ``0`` in ``"unstructured_only"`` and ``"hybrid"`` modes, because
  those modes do not attempt canonical matching per mention).
* ``unresolved``: Count of mentions that were **not** matched to any canonical
  entity and therefore received no ``RESOLVES_TO`` edge.  In
  ``"unstructured_only"`` and ``"hybrid"`` modes this equals ``mentions_total``
  (all mentions go through clustering rather than canonical resolution); it does
  not indicate clustering failure.  Consumers of those modes should use
  ``mentions_clustered`` and the alignment metrics below instead.
* ``clusters_created``: Number of unique :ResolvedEntityCluster nodes created or
  reused in this run.
* ``resolution_breakdown``: Mapping from resolution strategy name to the
  number of mentions whose cluster assignment was decided by that strategy.
* ``entity_type_report``: Per-run diagnostic summary of observed raw
  ``entity_type`` values.  Always present (empty report in ``dry_run`` mode).
  Contains the following sub-keys:

  - ``raw_counts``: ``{raw_label: count}`` for every distinct raw value seen,
    ordered by descending count.  The reserved sentinel key ``"__null__"``
    aggregates all mentions whose ``entity_type`` was ``None`` or ``""`` **and**
    any mentions where an upstream extractor emitted the literal string
    ``"__null__"``.  When this collision occurs, the merged/ambiguous nature of
    the bucket is indicated via ``sentinel_label_warnings`` (see below).
  - ``normalized_counts``: ``{canonical_label: count}`` after applying
    ``_normalize_entity_type()``, ordered by descending count.  The reserved
    sentinel key ``"__null__"`` aggregates mentions whose normalized type is
    absent/empty, as well as any whose normalized label is the literal
    ``"__null__"``.  As with ``raw_counts``, such collisions are flagged via
    ``sentinel_label_warnings``.  Use this to understand post-normalization type
    distribution.
  - ``mapped_variants``: ``{raw_label: canonical_label}`` for synonym mappings
    from ``_ENTITY_TYPE_SYNONYMS`` that were actually observed this run.
    A non-empty entry here means at least one upstream extractor emitted a
    non-canonical label that was silently unified.
  - ``passthrough_labels``: Sorted list of non-empty labels that are **not** in
    the synonym table and are therefore returned unchanged (i.e. passed through
    as-is).  New or unexpected labels appear here and should be reviewed to
    determine whether they require a synonym mapping or remain distinct.
  - ``null_or_empty_count``: Number of mentions with absent/empty
    ``entity_type``.  A non-zero value indicates extractor output that carries
    no type signal.
  - ``sentinel_label_warnings``: List of human-readable warnings (normally
    empty).  A non-empty list means an upstream extractor emitted the reserved
    sentinel string ``"__null__"`` alongside absent/empty mentions; the counts
    are merged and cannot be distinguished retroactively.
* ``warnings``: List of non-fatal issues encountered during resolution.

In modes that perform text-based clustering
(``resolution_mode`` is ``"unstructured_only"`` or ``"hybrid"``), the summary
also includes:

* ``mentions_clustered``: Number of :EntityMention nodes for this run_id that
  have a persisted ``MEMBER_OF`` edge to a :ResolvedEntityCluster node (verified
  by a post-write graph query).  In current unstructured-first behaviour the
  ``label_cluster`` fallback ensures every mention receives a ``MEMBER_OF`` edge,
  so this always equals ``mentions_total`` when the stage succeeds.
* ``mentions_unclustered``: Number of :EntityMention nodes for this run_id that
  have **no** ``MEMBER_OF`` edge after the write step, as reported by the same
  post-write graph query.  Under the current ``label_cluster`` fallback this is
  always ``0``; a non-zero value indicates a write failure or unexpected data
  condition and is also surfaced as a warning in the summary.
  Invariant: ``mentions_clustered + mentions_unclustered == mentions_total``.

In ``"hybrid"`` mode, canonical alignment metrics are also present:

* ``alignment_version``: Version string for the canonical alignment algorithm.
* ``aligned_clusters``: Number of :ResolvedEntityCluster nodes that received an
  ``ALIGNED_WITH`` edge whose ``(run_id, alignment_version)`` properties match
  this stage, pointing to some :CanonicalEntity node.
* ``alignment_breakdown``: Mapping from alignment strategy name to the number
  of ``ALIGNED_WITH`` edges written by that strategy, derived from persisted
  graph state (scoped to ``run_id`` and ``alignment_version``).
* ``distinct_canonical_entities_aligned``: Count of unique :CanonicalEntity
  nodes that are the target of at least one ``ALIGNED_WITH`` edge whose
  ``(run_id, alignment_version)`` properties match this stage.
* ``mentions_in_aligned_clusters``: Number of :EntityMention nodes (via
  ``MEMBER_OF``) that belong to a :ResolvedEntityCluster which has at least one
  ``ALIGNED_WITH`` edge whose ``(run_id, alignment_version)`` properties match
  this stage, to some :CanonicalEntity.
* ``clusters_pending_alignment``: Number of run-scoped :ResolvedEntityCluster
  nodes that did **not** receive any ``ALIGNED_WITH`` edge whose
  ``(run_id, alignment_version)`` properties match this stage.

All alignment counts are scoped to ``(run_id, alignment_version)`` so they are
consistent with the write path (which MERGEs ``ALIGNED_WITH`` by that composite
key) and with cluster-aware retrieval queries that filter by ``alignment_version``.

Recommended metrics per mode
------------------------------
* ``"structured_anchor"``: use ``resolved``, ``unresolved``, ``resolution_breakdown``.
* ``"unstructured_only"``: use ``mentions_clustered``, ``mentions_unclustered``,
  ``clusters_created``, ``resolution_breakdown``.  Ignore ``resolved``/``unresolved``
  (always 0 / mentions_total respectively).
* ``"hybrid"``: use ``mentions_clustered``, ``mentions_unclustered``,
  ``clusters_created``, ``aligned_clusters``, ``distinct_canonical_entities_aligned``,
  ``mentions_in_aligned_clusters``, ``clusters_pending_alignment``, and
  ``alignment_breakdown``.  All alignment-related counts are verified against
  persisted ``ALIGNED_WITH`` edges via post-write graph queries, so they reflect
  actual graph state rather than in-memory assumptions.  Ignore ``resolved``/``unresolved``.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote as _pct_encode

import neo4j

from power_atlas.context import RequestContext
from power_atlas.contracts import resolve_dataset_root
from power_atlas.contracts.resolution import ALIGNMENT_VERSION as _ALIGNMENT_VERSION
from power_atlas.entity_resolution_queries import (
    fetch_alignment_coverage,
    fetch_canonical_entities,
    fetch_entity_mentions,
    fetch_member_of_coverage,
)
from power_atlas.entity_resolution_runtime import run_entity_resolution_live
from power_atlas.entity_resolution_writes import (
    write_alignment_results as _write_alignment_results_live,
    write_cluster_memberships as _write_cluster_memberships_live,
    write_resolved_mentions as _write_resolved_mentions_live,
)
from power_atlas.settings import Neo4jSettings
from power_atlas.text_utils import normalize_mention_text

# Bump this constant whenever the resolution strategies or scoring logic change
# so that RESOLVES_TO edges in the graph can be distinguished by the version that
# created them (e.g. when re-running resolution after a strategy upgrade).
_RESOLVER_VERSION = "v1.2"

# Bump this constant whenever cluster-assignment logic changes so that MEMBER_OF
# edges can be distinguished by the version that created them.
_CLUSTER_VERSION = "v1.3"

# Fuzzy SequenceMatcher ratio at-or-above which a fuzzy cluster match is classified
# as "provisional" (high-confidence minor surface variant) rather than
# "review_required" (borderline ambiguous match that warrants human review).
_FUZZY_REVIEW_THRESHOLD = 0.92

_QID_PATTERN = re.compile(r"^Q\d+$")

# Strips everything that is not a lowercase ASCII letter. Intended to be used
# on already-normalized (lowercased) text to normalize abbreviated forms like
# "f.b.i." → "fbi" and "fbi," → "fbi" so that _is_abbreviation() works on
# typical extracted text.
_RE_NON_ALPHA = re.compile(r"[^a-z]")

# Normalisation function used throughout this module.  Defined in
# :mod:`demo.text_utils` and imported here as a module-private alias so that
# call-sites within this file do not need to change.
_normalize = normalize_mention_text

# Supported resolution mode identifiers.
_RESOLUTION_MODE_STRUCTURED_ANCHOR = "structured_anchor"
_RESOLUTION_MODE_UNSTRUCTURED_ONLY = "unstructured_only"
_RESOLUTION_MODE_HYBRID = "hybrid"
_VALID_RESOLUTION_MODES = frozenset({
    _RESOLUTION_MODE_STRUCTURED_ANCHOR,
    _RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    _RESOLUTION_MODE_HYBRID,
})

# Mapping of synonymous/variant entity-type labels to their canonical forms.
# This table is the single authoritative source of truth for entity-type
# normalization within this module.
#
# Design rationale:
#   - ``'ORG'`` and ``'Organization'`` are both common outputs from upstream
#     LLM extraction; they are unified to ``'Organization'``.
#   - ``'Company'`` is treated as a synonym for ``'Organization'`` because
#     companies are organizations.  Any mention extracted as ``'Company'``
#     will share a cluster with ``'Organization'`` / ``'ORG'`` mentions of
#     the same normalized text.
#   - ``'PERSON'`` and ``'Person'`` are both produced by upstream extractors;
#     they are unified to ``'Person'``.
#   - ``'organization'`` (all-lowercase) is mapped to ``'Organization'``.
#     Real-run benchmark evidence (run unstructured_ingest-20260401T184420771950Z)
#     showed that lowercase ``'organization'`` and title-case ``'Organization'``
#     were producing separate cluster identities for the same entity family,
#     causing benchmark-visible canonical-empty / cluster-populated fragmentation.
#   - ``'person'`` (all-lowercase) is mapped to ``'Person'`` for the same reason:
#     consistent treatment of the all-lowercase casing variant that LLM extractors
#     sometimes emit.
#   - Note: ``'org'`` is still NOT mapped here — it is an abbreviation, not a
#     casing variant, and its correct canonical form cannot be assumed without
#     additional context.
#   - All other labels are left unchanged, including ``None`` (handled
#     separately as an empty/unknown type).
#   - Leading/trailing whitespace is stripped before this lookup is applied
#     (see ``_normalize_entity_type``), so ``' Organization '`` resolves
#     correctly even though no explicit entry exists for the padded form.
_ENTITY_TYPE_SYNONYMS: dict[str, str] = {
    "ORG": "Organization",
    "Company": "Organization",
    "organization": "Organization",
    "PERSON": "Person",
    "person": "Person",
}

# Reserved sentinel key used in entity_type_report dicts to represent absent or
# empty entity_type values (None / "").  The decorated name is chosen to make
# it unlikely (but not impossible) for a real NLP extractor to emit this label
# accidentally; if it does, collisions are detected and reported via
# sentinel_label_warnings.  Do NOT change this value without also updating any
# consumers of entity_type_report summaries/artifacts that rely on this sentinel.
_ENTITY_TYPE_NULL_SENTINEL = "__null__"


def _neo4j_settings_from_config(
    config: object,
    neo4j_settings: Neo4jSettings | None = None,
) -> Neo4jSettings:
    if neo4j_settings is not None:
        return neo4j_settings
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, Neo4jSettings):
        return settings_neo4j
    raise ValueError(
        "Live entity resolution requires config.settings.neo4j or an explicit "
        "neo4j_settings argument from RequestContext/AppContext-backed config"
    )


def _resolve_effective_dataset_id(
    config: Any,
    dataset_id: str | None,
    *,
    dataset_name: str | None = None,
) -> str:
    if isinstance(dataset_id, str) and dataset_id:
        return dataset_id

    configured_dataset_name = dataset_name or getattr(config, "dataset_name", None)
    if isinstance(configured_dataset_name, str) and configured_dataset_name:
        return resolve_dataset_root(configured_dataset_name).dataset_id
    raise ValueError(
        "Entity resolution requires an explicit dataset_id or config.dataset_name from "
        "RequestContext/AppContext-backed config"
    )


def _normalize_entity_type(entity_type: str | None) -> str | None:
    """Return the canonical form of *entity_type*, or ``None`` if absent.

    Synonymous and variant labels produced by upstream LLM extractors are
    mapped to a single canonical string so that :func:`_make_cluster_id` and
    the type-scoped clustering indices always see a consistent value:

    * ``'ORG'`` → ``'Organization'``
    * ``'Company'`` → ``'Organization'``  (companies are organizations)
    * ``'organization'`` → ``'Organization'``  (all-lowercase casing variant)
    * ``'PERSON'`` → ``'Person'``
    * ``'person'`` → ``'Person'``  (all-lowercase casing variant)

    Leading and trailing whitespace is stripped before the synonym lookup, so
    ``' Organization '`` resolves to ``'Organization'`` even though no padded
    form is listed in the table.

    All other non-empty labels are returned with whitespace stripped but
    otherwise unchanged.  ``None``, ``''``, and whitespace-only strings all
    return ``None`` (the caller of :func:`_make_cluster_id` maps ``None``
    to an empty string, preserving the existing ``None``/``''`` equivalence).
    """
    entity_type = (entity_type or "").strip()
    if not entity_type:
        return None
    return _ENTITY_TYPE_SYNONYMS.get(entity_type, entity_type)


# Allowlist for the `var` parameter of build_entity_type_cypher_case.
# A safe Cypher variable reference consists of alphanumeric characters,
# underscores, and dots (for property access, e.g. "m.entity_type").
_SAFE_CYPHER_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _escape_cypher_string(value: str) -> str:
    """Escape a string value for embedding in a single-quoted Cypher literal.

    Replaces each ``'`` with ``''`` (the Cypher escaping convention) so that
    the caller can safely wrap the result in single quotes without producing
    invalid Cypher or enabling injection.
    """
    return value.replace("'", "''")


def build_entity_type_cypher_case(var: str, unknown_label: str = "UNKNOWN") -> str:
    """Return a Cypher CASE expression that mirrors :func:`_normalize_entity_type`.

    The generated expression is derived directly from :data:`_ENTITY_TYPE_SYNONYMS`
    and therefore reflects the same normalization policy that determines cluster
    identity during entity resolution.  Use this whenever a Cypher query needs
    to apply entity-type normalization (e.g. graph-health type-fragmentation
    diagnostics) so that the Cypher semantics stay automatically in sync with
    the Python policy.

    Matching is **case-sensitive** and applies ``trim()`` to strip leading/trailing
    whitespace before comparison, mirroring the ``.strip()`` applied by
    :func:`_normalize_entity_type`.  ``NULL``, whitespace-only strings, and
    empty strings all resolve to *unknown_label*.

    Parameters
    ----------
    var:
        The Cypher variable or property expression whose value is the raw
        ``entity_type`` string, e.g. ``"m.entity_type"``.  Must be a
        dot-separated sequence of valid identifiers
        (``[A-Za-z_][A-Za-z0-9_]*``); trailing dots and empty segments are
        rejected to prevent Cypher injection.
    unknown_label:
        The literal string to emit when *var* is ``NULL``, the empty string,
        or a whitespace-only string (i.e. when :func:`_normalize_entity_type`
        would return ``None``).
        Defaults to ``"UNKNOWN"``.  Single-quotes are escaped automatically.

    Returns
    -------
    A Cypher expression string (without a trailing newline) suitable for use
    in a ``WITH`` or ``RETURN`` clause.

    Raises
    ------
    ValueError
        If *var* does not match the safe allowlist pattern
        ``[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*``
        (dot-separated identifier segments; trailing dots and empty segments
        are rejected).

    Example
    -------
    With the default synonym table the expression produced for
    ``var="m.entity_type"`` is equivalent to::

        CASE
          WHEN m.entity_type IS NULL OR trim(m.entity_type) = '' THEN 'UNKNOWN'
          WHEN trim(m.entity_type) = 'ORG' THEN 'Organization'
          WHEN trim(m.entity_type) = 'Company' THEN 'Organization'
          WHEN trim(m.entity_type) = 'organization' THEN 'Organization'
          WHEN trim(m.entity_type) = 'PERSON' THEN 'Person'
          WHEN trim(m.entity_type) = 'person' THEN 'Person'
          ELSE trim(m.entity_type)
        END
    """
    if not _SAFE_CYPHER_VAR_RE.fullmatch(var):
        raise ValueError(
            f"Unsafe Cypher variable reference {var!r}: must match "
            f"[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)* "
            f"(dot-separated identifier segments; only alphanumerics and underscores)."
        )
    escaped_unknown = _escape_cypher_string(unknown_label)
    when_lines = "\n".join(
        f"  WHEN trim({var}) = '{_escape_cypher_string(raw)}' THEN '{_escape_cypher_string(canonical)}'"
        for raw, canonical in _ENTITY_TYPE_SYNONYMS.items()
    )
    return (
        f"CASE\n"
        f"  WHEN {var} IS NULL OR trim({var}) = '' THEN '{escaped_unknown}'\n"
        f"{when_lines}\n"
        f"  ELSE trim({var})\n"
        f"END"
    )


def _build_entity_type_report(
    mentions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a per-run summary of observed raw ``entity_type`` values.

    Iterates over *mentions* (each a ``dict`` with an optional ``"entity_type"``
    key) and produces a structured diagnostic report that surfaces:

    * **raw_counts** — ``{raw_label: count}`` for every distinct raw value seen,
      including the reserved sentinel key ``"__null__"`` for absent/empty labels.
    * **normalized_counts** — ``{canonical_label: count}`` after applying
      :func:`_normalize_entity_type`; absent/empty values are represented as
      the reserved sentinel key ``"__null__"`` so the mapping is JSON-serializable.
    * **mapped_variants** — ``{raw_label: canonical_label}`` for synonym mappings
      (i.e. ``_ENTITY_TYPE_SYNONYMS`` entries) that were actually observed this run.
    * **passthrough_labels** — sorted list of non-empty labels that are *not* in
      the synonym table and are therefore returned unchanged by normalization.
    * **null_or_empty_count** — number of mentions with ``None``, ``""``, or
      whitespace-only ``entity_type`` (they produce ``None`` after normalization).
    * **sentinel_label_warnings** — list of human-readable warning strings (normally
      empty).  A non-empty entry means an upstream extractor emitted the literal
      string ``"__null__"``, which is the reserved sentinel; its counts are merged
      with the null/empty bucket in both ``raw_counts`` and ``normalized_counts``
      and cannot be distinguished retroactively.

    This report is embedded in the entity-resolution summary so that each run
    produces a repeatable, reviewable record of the raw type-label distribution.
    Unexpected new labels (potential upstream drift) appear in
    ``passthrough_labels`` and can be compared across runs to detect whether a
    new extractor variant would reintroduce cluster fragmentation.

    The report is **diagnostic only**; it does not alter any mention, cluster, or
    graph state.
    """
    raw_counts: dict[str | None, int] = {}
    normalized_counts: dict[str, int] = {}
    mapped_variants: dict[str, str] = {}
    passthrough_labels: set[str] = set()
    null_or_empty_count = 0
    raw_null_sentinel_seen = False  # tracks whether extractor emitted literal "__null__"

    for mention in mentions:
        raw = mention.get("entity_type")
        if isinstance(raw, str) and raw.strip() == _ENTITY_TYPE_NULL_SENTINEL:
            raw_null_sentinel_seen = True
        # Normalise empty and whitespace-only strings to None so counts are
        # consistent with how _normalize_entity_type treats them: both are
        # stripped to "" and return None.
        if isinstance(raw, str) and not raw.strip():
            raw = None

        raw_counts[raw] = raw_counts.get(raw, 0) + 1

        if raw is None:
            null_or_empty_count += 1
            norm_key = _ENTITY_TYPE_NULL_SENTINEL
        else:
            normalized = _normalize_entity_type(raw)
            if normalized is None:
                null_or_empty_count += 1
                norm_key = _ENTITY_TYPE_NULL_SENTINEL
            else:
                norm_key = normalized
                if normalized != raw:
                    mapped_variants[raw] = normalized
                elif raw != _ENTITY_TYPE_NULL_SENTINEL:
                    passthrough_labels.add(raw)
        normalized_counts[norm_key] = normalized_counts.get(norm_key, 0) + 1

    # Serialise raw_counts so None keys become the reserved sentinel "__null__"
    # for JSON safety.  Counts are summed in the unlikely event that an upstream
    # extractor also emits the literal string "__null__"; that collision is
    # surfaced in sentinel_label_warnings below.
    serialized_raw_counts: dict[str, int] = {}
    for k, v in raw_counts.items():
        # Collapse None, exact sentinel, and padded-sentinel (e.g. " __null__ ")
        # into a single "__null__" bucket so raw_counts is collision-free.
        if k is None or (isinstance(k, str) and k.strip() == _ENTITY_TYPE_NULL_SENTINEL):
            key = _ENTITY_TYPE_NULL_SENTINEL
        else:
            key = k
        serialized_raw_counts[key] = serialized_raw_counts.get(key, 0) + v

    sentinel_label_warnings: list[str] = []
    if raw_null_sentinel_seen and null_or_empty_count > 0:
        sentinel_label_warnings.append(
            f"Upstream extractor emitted the reserved sentinel label "
            f"{_ENTITY_TYPE_NULL_SENTINEL!r}; "
            "its counts are merged with the absent/empty bucket in raw_counts "
            "and normalized_counts and cannot be distinguished retroactively."
        )

    return {
        "raw_counts": dict(
            sorted(serialized_raw_counts.items(), key=lambda t: (-t[1], t[0]))
        ),
        "normalized_counts": dict(
            sorted(normalized_counts.items(), key=lambda t: (-t[1], t[0]))
        ),
        "mapped_variants": dict(sorted(mapped_variants.items())),
        "passthrough_labels": sorted(passthrough_labels),
        "null_or_empty_count": null_or_empty_count,
        "sentinel_label_warnings": sentinel_label_warnings,
    }


def _make_cluster_id(
    run_id: str,
    entity_type: str | None,
    normalized_text: str,
) -> str:
    """Compute a scoped cluster_id for a :ResolvedEntityCluster node.

    The cluster_id encodes three identity dimensions so that clusters are never
    unintentionally merged across runs, entity types, or normalized texts:

    * **run_id** — prevents cross-run collision when the same text appears in
      multiple independent processing runs.
    * **entity_type** — prevents merging semantically distinct clusters that
      share a normalized text but belong to different entity types (e.g. "IBM"
      as an ORG vs "IBM" as a PRODUCT).
    * **normalized_text** — the canonical text of the cluster representative.

    ``source_uri`` is intentionally **not** part of cluster identity.  Mentions
    from different source documents within the same run that refer to the same
    entity type and normalized text are considered the same cluster; this allows
    cross-document clustering within a run.  ``source_uri`` is still propagated
    as provenance on ``MEMBER_OF``, ``RESOLVES_TO``, and ``ALIGNED_WITH`` edges
    so that per-mention origin tracking is preserved without forcing
    source-partitioned cluster identity.

    Format: ``cluster::<run_id_enc>::<entity_type_enc>::<normalized_text_enc>``

    Each component is percent-encoded (RFC 3986, ``safe=''``) before joining
    so that a component containing the ``::`` delimiter cannot produce a
    cluster_id that collides with a legitimately different tuple.

    ``entity_type=None`` is treated as an empty string before encoding, so
    ``None`` and ``""`` produce the same cluster_id for that dimension.  An
    empty *normalized_text* is accepted and yields a deterministic ID.  A
    non-empty *run_id* is required; passing an empty string raises
    :exc:`ValueError` because it would produce IDs indistinguishable across
    runs.

    *entity_type* is normalized via :func:`_normalize_entity_type` before
    encoding so that synonymous labels (``'ORG'``/``'Organization'``,
    ``'PERSON'``/``'Person'``, ``'Company'``/``'Organization'``) produce the
    same cluster_id and are never split into unintended separate clusters.
    """
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    run_id_enc = _pct_encode(run_id, safe="")
    entity_type_enc = _pct_encode(_normalize_entity_type(entity_type) or "", safe="")
    normalized_text_enc = _pct_encode(normalized_text, safe="")
    return f"cluster::{run_id_enc}::{entity_type_enc}::{normalized_text_enc}"


def _split_aliases(raw: Any) -> list[str]:
    """Parse a pipe- or comma-separated alias string into normalised tokens.

    Each token is processed through :func:`_normalize` so that alias lookup
    keys are consistent with the normalisation applied to mention text.  This
    ensures that aliases containing diacritics, Unicode dashes, curly
    apostrophes, or non-ASCII casing (e.g. ``"Müller"``, ``"naïve"``,
    ``"state\u2013of"``) resolve correctly against normalised mention names.
    """
    if not raw or not isinstance(raw, str):
        return []
    sep = "|" if "|" in raw else ","
    return [n for tok in raw.split(sep) if (n := _normalize(tok))]


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


def _membership_status(method: str, score: float) -> str:
    """Return the MEMBER_OF edge status for a given cluster assignment method and score.

    Status values reflect the confidence and ambiguity of the membership:

    - ``"accepted"`` — deterministic assignment (``label_cluster``,
      ``normalized_exact``); high-confidence, no review needed.
    - ``"provisional"`` — high-confidence probabilistic fuzzy match
      (SequenceMatcher ratio ≥ :data:`_FUZZY_REVIEW_THRESHOLD`); minor
      surface-form variant, review is optional.
    - ``"candidate"`` — abbreviation/initialism match; identity is plausible
      but the abbreviated form is inherently ambiguous, so human review adds
      value.  Explicit :data:`CANDIDATE_MATCH` edges are also written for
      these memberships.
    - ``"review_required"`` — borderline fuzzy match (ratio below
      :data:`_FUZZY_REVIEW_THRESHOLD`); the relationship is tentative and
      should be verified before being relied upon.  Explicit
      :data:`CANDIDATE_MATCH` edges are also written for these memberships.
    """
    if method in ("label_cluster", "normalized_exact"):
        return "accepted"
    if method == "abbreviation":
        return "candidate"
    if method == "fuzzy":
        return "provisional" if score >= _FUZZY_REVIEW_THRESHOLD else "review_required"
    # Fallback for any future methods not yet mapped.
    return "provisional"


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
    ``normalized_text``, ``entity_type``, ``resolution_method``,
    ``resolution_confidence``, ``resolved`` (always ``False``), and
    ``source_uri``. ``entity_type`` is normalized so that ``None`` and
    ``""`` both appear as ``None`` on output rows (matching the identity
    scope of :func:`_make_cluster_id`).
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
        entity_type: str | None = _normalize_entity_type(mention.get("entity_type") or None)
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
            "entity_type": mention_to_type[mention["mention_id"]],
            "source_uri": mention.get("source_uri") or None,
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
            "entity_type": _normalize_entity_type(mention.get("entity_type") or None),
            "source_uri": mention.get("source_uri") or None,
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
        "entity_type": _normalize_entity_type(mention.get("entity_type") or None),
        "source_uri": mention.get("source_uri") or None,
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

    Unresolved mentions are grouped into :ResolvedEntityCluster nodes keyed by
    ``(run_id, entity_type, normalized_text)``.  ``source_uri`` is **not** part
    of cluster identity — mentions from different source documents within the
    same run that share the same entity type and normalized text map to the same
    cluster, enabling cross-document clustering.  Each mention receives a
    ``MEMBER_OF`` edge carrying per-mention provenance metadata: ``score``,
    ``method``, ``resolver_version``, ``run_id``, ``source_uri``, and
    ``status``.  The ``source_uri`` on the edge is taken from the per-mention
    value propagated from the EntityMention node in the DB.
    """
    _write_resolved_mentions(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        resolved_rows=resolved_rows,
        neo4j_database=neo4j_database,
    )

    if unresolved_rows:
        created_at = datetime.now(UTC).isoformat()
        # Build per-mention rows for the cluster MERGE + MEMBER_OF edge.
        # Use per-row resolution_method for accurate provenance and compute the
        # MEMBER_OF score via _membership_score so deterministic cluster
        # assignments (label_cluster, normalized_exact) always get score=1.0,
        # regardless of any match-quality confidence on the unresolved row.
        # The cluster_id is scoped by (run_id, entity_type, normalized_text) to
        # prevent unintentional merging across runs or entity types.
        # source_uri is NOT part of cluster identity; it is carried per-mention
        # as provenance on the MEMBER_OF edge so cross-document clustering
        # within the same run is supported.
        #
        # NOTE — cluster_id scheme compatibility: if the cluster_id format
        # changes (e.g. due to a future schema upgrade) any previously-written
        # ResolvedEntityCluster nodes for the same run_id will become orphaned
        # (old MEMBER_OF edges won't be touched and old cluster nodes will
        # remain). The demo DB is assumed to be cleanly reset before each run,
        # so this is not a concern for the demo workflow. For production use
        # cases that retain DB state across upgrades, callers should delete
        # all MEMBER_OF and ResolvedEntityCluster nodes for the affected run_id
        # before re-running entity resolution with the new scheme.
        cluster_rows = []
        for row in unresolved_rows:
            method = row.get("resolution_method", "label_cluster")
            entity_type = row.get("entity_type")
            row_source_uri = row.get("source_uri")
            score = _membership_score(method, row.get("resolution_confidence", 1.0))
            cluster_rows.append({
                "mention_id": row["mention_id"],
                "cluster_id": _make_cluster_id(run_id, entity_type, row["normalized_text"]),
                # Use a deterministic canonical name derived from the normalized text
                "canonical_name": row["normalized_text"].title(),
                "normalized_text": row["normalized_text"],
                "entity_type": entity_type,
                "source_uri": row_source_uri,
                "score": score,
                "method": method,
                # Status encodes ambiguity level for downstream consumers and reviewers:
                # "accepted"        — deterministic assignments (label_cluster, normalized_exact)
                # "provisional"     — high-confidence fuzzy match (ratio ≥ _FUZZY_REVIEW_THRESHOLD)
                # "candidate"       — abbreviation/initialism match (plausible but ambiguous)
                # "review_required" — borderline fuzzy match (ratio < _FUZZY_REVIEW_THRESHOLD)
                "status": _membership_status(method, score),
            })
        _write_cluster_memberships(
            driver,
            run_id=run_id,
            cluster_rows=cluster_rows,
            neo4j_database=neo4j_database,
            created_at=created_at,
        )


def _write_cluster_memberships(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    cluster_rows: list[dict[str, Any]],
    neo4j_database: str,
    created_at: str,
) -> None:
    _write_cluster_memberships_live(
        driver,
        run_id=run_id,
        cluster_rows=cluster_rows,
        neo4j_database=neo4j_database,
        resolver_version=_CLUSTER_VERSION,
        created_at=created_at,
    )


def _write_resolved_mentions(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    neo4j_database: str,
) -> None:
    _write_resolved_mentions_live(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        resolved_rows=resolved_rows,
        neo4j_database=neo4j_database,
    )



def _align_clusters_to_canonical(
    clusters: list[dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_alias: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Align :ResolvedEntityCluster nodes to :CanonicalEntity nodes.

    For each unique cluster applies label-exact then alias-exact lookup against
    the pre-built lookup tables.  Returns one alignment row per cluster that
    matched a canonical entity.

    Alignment strategies applied in priority order:

    1. **label_exact** — cluster's normalized text matches a CanonicalEntity
       by its normalized label.
    2. **alias_exact** — cluster's normalized text appears in a CanonicalEntity's
       alias list.

    Args:
        clusters: Unique clusters to align.  Each element must be a dict with
            at least ``cluster_id`` (the scoped identity key produced by
            :func:`_make_cluster_id`) and ``normalized_text`` (used for
            label/alias lookup).
        by_label: Mapping of normalized canonical label → canonical row.
        by_alias:  Mapping of normalized alias → canonical row.

    Returns:
        A list of alignment row dicts with keys: ``cluster_id``,
        ``canonical_entity_id``, ``canonical_run_id``, ``alignment_method``,
        ``alignment_score``, ``alignment_status``, and ``source_uri``
        (carried forward from the cluster dict for per-cluster edge provenance).
    """
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        normalized_text = cluster["normalized_text"]
        cluster_source_uri = cluster.get("source_uri")

        canonical = by_label.get(normalized_text)
        if canonical:
            rows.append({
                "cluster_id": cluster_id,
                "canonical_entity_id": canonical["entity_id"],
                "canonical_run_id": canonical["run_id"],
                "alignment_method": "label_exact",
                "alignment_score": 0.9,
                "alignment_status": "aligned",
                "source_uri": cluster_source_uri,
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
                "source_uri": cluster_source_uri,
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
    ``run_id``, and ``source_uri``.  The function-level ``source_uri``
    argument is used as a fallback; it is normalized to ``None`` for empty
    strings so that blank values are not persisted as a distinct provenance.
    Existing cluster nodes and ``MEMBER_OF`` edges are never modified.
    """
    _write_alignment_results_live(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        alignment_rows=alignment_rows,
        neo4j_database=neo4j_database,
        alignment_version=_ALIGNMENT_VERSION,
    )


def _run_entity_resolution_impl(
    config: Any,
    *,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
    neo4j_settings: Neo4jSettings | None = None,
    dataset_name: str | None = None,
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
        config:          :class:`~power_atlas.contracts.runtime.Config`.
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
        dataset_id:      Dataset identifier used to scope :CanonicalEntity lookups to
                 the active dataset. When ``None``, the stage resolves scope
                 from ``config.dataset_name`` and then falls back to the demo's
                 historical default dataset for compatibility with direct callers.
                 Pass this explicitly when calling from an orchestrated pipeline
                 stage to avoid relying on implicit defaults.

    Returns:
        A summary dict with counts, resolution breakdown, ``resolution_mode``,
        and artifact paths.  See the module-level "Summary JSON metrics" section
        for a full description of every field and which modes emit each one.
        In brief: ``"unstructured_only"`` and ``"hybrid"`` modes add
        ``mentions_clustered`` / ``mentions_unclustered``; ``"hybrid"`` mode
        further adds ``aligned_clusters``, ``alignment_breakdown``,
        ``alignment_version``, ``distinct_canonical_entities_aligned``,
        ``mentions_in_aligned_clusters``, and ``clusters_pending_alignment``.
    """
    # Resolve the effective mode: explicit arg > config attribute > default.
    if resolution_mode is None:
        resolution_mode = getattr(config, "resolution_mode", _RESOLUTION_MODE_STRUCTURED_ANCHOR) or _RESOLUTION_MODE_STRUCTURED_ANCHOR
    if resolution_mode not in _VALID_RESOLUTION_MODES:
        raise ValueError(
            f"Unknown resolution_mode {resolution_mode!r}. "
            f"Valid modes: {sorted(_VALID_RESOLUTION_MODES)}"
        )

    # Resolve the effective dataset_id for scoping CanonicalEntity lookups.
    # Explicit parameter takes precedence; otherwise use config.dataset_name when
    # available and finally the historical demo default dataset for compatibility.
    effective_dataset_id: str = _resolve_effective_dataset_id(
        config,
        dataset_id,
        dataset_name=dataset_name,
    )

    resolved_at = datetime.now(UTC).isoformat()

    # Ensure the run directory is always a descendant of <output_dir>/runs and that
    # run_id cannot be used for path traversal or absolute path escape.
    runs_root = (config.output_dir / "runs").resolve()
    run_id_path = Path(run_id)
    if run_id_path.is_absolute() or ".." in run_id_path.parts or run_id_path.name != run_id:
        raise ValueError(
            f"Invalid run_id {run_id!r}: must be a simple relative name without path separators or '..'."
        )
    run_root = (runs_root / run_id_path).resolve()
    # Reject run_ids that resolve to the runs_root itself (e.g. "" or ".") or that
    # escape it (e.g. via symlinks after the parts-level '..' check above).
    if run_root == runs_root or runs_root not in run_root.parents:
        raise ValueError(
            f"Invalid run_id {run_id!r}: must resolve to a subdirectory of the runs directory."
        )

    artifact_subdir_path = Path(artifact_subdir)
    # Prevent path traversal and absolute paths in artifact_subdir to keep writes
    # confined under the run_root directory.
    if artifact_subdir_path.is_absolute() or ".." in artifact_subdir_path.parts:
        raise ValueError(f"Invalid artifact_subdir {artifact_subdir!r}: must be a relative path without '..'.")

    resolution_dir = (run_root / artifact_subdir_path).resolve()
    # Reject subdirs that resolve to run_root itself (e.g. "" or ".") or that escape it
    # (e.g. via symlinks after the parts-level ".." check above).
    if resolution_dir == run_root or run_root not in resolution_dir.parents:
        raise ValueError(f"Invalid artifact_subdir {artifact_subdir!r}: must resolve to a subdirectory of the run directory.")

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
            "dataset_id": effective_dataset_id,
            "resolver_method": resolver_method,
            "resolver_version": _RESOLVER_VERSION,
            "cluster_version": _CLUSTER_VERSION,
            "mentions_total": 0,
            "resolved": 0,
            "unresolved": 0,
            "clusters_created": 0,
            "resolution_breakdown": {},
            "entity_type_report": _build_entity_type_report([]),
            "warnings": ["entity resolution skipped in dry_run mode"],
        }
        if resolution_mode in (_RESOLUTION_MODE_UNSTRUCTURED_ONLY, _RESOLUTION_MODE_HYBRID):
            summary["mentions_clustered"] = 0
            summary["mentions_unclustered"] = 0
        if resolution_mode == _RESOLUTION_MODE_HYBRID:
            summary["alignment_version"] = _ALIGNMENT_VERSION
            summary["aligned_clusters"] = 0
            summary["alignment_breakdown"] = {}
            summary["distinct_canonical_entities_aligned"] = 0
            summary["mentions_in_aligned_clusters"] = 0
            summary["clusters_pending_alignment"] = 0
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        unresolved_path.write_text(json.dumps([], indent=2), encoding="utf-8")
        return summary

    resolved_neo4j_settings = _neo4j_settings_from_config(config, neo4j_settings)

    live_result = run_entity_resolution_live(
        resolved_neo4j_settings,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        effective_dataset_id=effective_dataset_id,
        alignment_version=_ALIGNMENT_VERSION,
        neo4j_database=resolved_neo4j_settings.database,
        fetch_mentions=fetch_entity_mentions,
        cluster_mentions=_cluster_mentions_unstructured_only,
        fetch_canonicals=fetch_canonical_entities,
        build_lookup_tables=_build_lookup_tables,
        make_cluster_id=_make_cluster_id,
        align_clusters_to_canonical=_align_clusters_to_canonical,
        resolve_mention=_resolve_mention,
        write_resolution_results=_write_resolution_results,
        write_alignment_results=_write_alignment_results,
        fetch_member_of_coverage=fetch_member_of_coverage,
        fetch_alignment_coverage=fetch_alignment_coverage,
    )

    mentions = live_result.mentions
    resolved_rows = live_result.resolved_rows
    unresolved_rows = live_result.unresolved_rows
    resolution_breakdown = live_result.resolution_breakdown
    _graph_mentions_clustered = live_result.graph_mentions_clustered
    _graph_mentions_unclustered = live_result.graph_mentions_unclustered
    _graph_total_clusters = live_result.graph_total_clusters
    _graph_aligned_clusters = live_result.graph_aligned_clusters
    _graph_distinct_canonical_entities = live_result.graph_distinct_canonical_entities
    _graph_mentions_in_aligned = live_result.graph_mentions_in_aligned
    _graph_alignment_breakdown = live_result.graph_alignment_breakdown
    _stage_warnings = live_result.warnings

    # 4. Write artifacts.
    unresolved_list = [
        {
            "mention_id": row["mention_id"],
            "mention_name": row["mention_name"],
            "normalized_text": row["normalized_text"],
            "entity_type": row.get("entity_type") or None,
            "cluster_id": _make_cluster_id(run_id, row.get("entity_type"), row["normalized_text"]),
        }
        for row in unresolved_rows
    ]
    unresolved_path.write_text(json.dumps(unresolved_list, indent=2), encoding="utf-8")

    # Count unique clusters — one cluster per unique (entity_type, normalized_text)
    # pair, matching the scoped identity enforced by _make_cluster_id.
    # Normalize entity_type with `or ""` to match _make_cluster_id's
    # treatment of None and empty string as equivalent (both produce an empty segment).
    clusters_created = len({
        (row.get("entity_type") or "", row["normalized_text"]) for row in unresolved_rows
    })

    if resolution_mode == _RESOLUTION_MODE_UNSTRUCTURED_ONLY:
        live_resolver_method = "unstructured_clustering"
    elif resolution_mode == _RESOLUTION_MODE_HYBRID:
        live_resolver_method = "unstructured_clustering_with_canonical_alignment"
    else:
        live_resolver_method = "canonical_exact_match"

    # Build entity_type_report and propagate any sentinel_label_warnings into the
    # stage warnings list so they surface at orchestration boundaries.
    _entity_type_report = _build_entity_type_report(mentions)
    _stage_warnings.extend(_entity_type_report.get("sentinel_label_warnings") or [])

    summary = {
        "status": "live",
        "run_id": run_id,
        "source_uri": source_uri,
        "resolution_mode": resolution_mode,
        "dataset_id": effective_dataset_id,
        "resolver_method": live_resolver_method,
        "resolver_version": _RESOLVER_VERSION,
        "cluster_version": _CLUSTER_VERSION,
        "resolved_at": resolved_at,
        "mentions_total": len(mentions),
        "resolved": len(resolved_rows),
        "unresolved": len(unresolved_rows),
        "clusters_created": clusters_created,
        "resolution_breakdown": resolution_breakdown,
        "entity_type_report": _entity_type_report,
        "entity_resolution_summary_path": str(summary_path),
        "unresolved_mentions_path": str(unresolved_path),
        "warnings": list(_stage_warnings),
    }
    if resolution_mode in (_RESOLUTION_MODE_UNSTRUCTURED_ONLY, _RESOLUTION_MODE_HYBRID):
        # Use graph-queried counts (set above) so the metrics reflect actual
        # MEMBER_OF edges that were persisted, not just in-memory row counts.
        summary["mentions_clustered"] = _graph_mentions_clustered
        summary["mentions_unclustered"] = _graph_mentions_unclustered
        if _graph_mentions_unclustered:
            summary["warnings"].append(
                f"{_graph_mentions_unclustered} mentions were not assigned to any cluster"
            )
    if resolution_mode == _RESOLUTION_MODE_HYBRID:
        summary["alignment_version"] = _ALIGNMENT_VERSION
        summary["aligned_clusters"] = _graph_aligned_clusters
        summary["alignment_breakdown"] = _graph_alignment_breakdown
        summary["distinct_canonical_entities_aligned"] = _graph_distinct_canonical_entities
        summary["mentions_in_aligned_clusters"] = _graph_mentions_in_aligned
        # Derive pending count from graph totals so the subtraction is consistent.
        # Clamp at 0 to guard against stale edges on a reused run_id.
        summary["clusters_pending_alignment"] = max(
            0, _graph_total_clusters - _graph_aligned_clusters
        )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_entity_resolution_request_context(
    request_context: RequestContext,
    *,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """Run entity resolution using request-scoped context as the primary input."""
    effective_resolution_mode = resolution_mode
    if effective_resolution_mode is None:
        effective_resolution_mode = getattr(request_context.config, "resolution_mode", None)

    return _run_entity_resolution_impl(
        request_context.config,
        run_id=request_context.run_id,
        source_uri=request_context.source_uri,
        resolution_mode=effective_resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        neo4j_settings=request_context.settings.neo4j,
        dataset_name=request_context.settings.dataset_name,
    )


__all__ = [
    "build_entity_type_cypher_case",
    "run_entity_resolution_request_context",
    "_build_entity_type_report",
    "_RESOLUTION_MODE_STRUCTURED_ANCHOR",
    "_RESOLUTION_MODE_UNSTRUCTURED_ONLY",
    "_RESOLUTION_MODE_HYBRID",
    "_VALID_RESOLUTION_MODES",
    "_ALIGNMENT_VERSION",
]
