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

from typing import Any

import neo4j

from power_atlas.context import RequestContext
from power_atlas.contracts import (
    EntityTypeNormalizationPolicy,
    POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY,
    build_entity_type_cypher_case as build_entity_type_cypher_case_from_policy,
    normalize_entity_type as normalize_entity_type_from_policy,
)
from power_atlas.contracts.resolution import ALIGNMENT_VERSION as _ALIGNMENT_VERSION
from power_atlas.entity_resolution_entrypoint import (
    RESOLUTION_MODE_HYBRID as _ENTRYPOINT_RESOLUTION_MODE_HYBRID,
    RESOLUTION_MODE_STRUCTURED_ANCHOR as _ENTRYPOINT_RESOLUTION_MODE_STRUCTURED_ANCHOR,
    RESOLUTION_MODE_UNSTRUCTURED_ONLY as _ENTRYPOINT_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
    VALID_RESOLUTION_MODES as _ENTRYPOINT_VALID_RESOLUTION_MODES,
    neo4j_settings_from_config as _neo4j_settings_from_config_impl,
    resolve_effective_dataset_id as _resolve_effective_dataset_id_impl,
    run_entity_resolution as _run_entity_resolution_impl_entrypoint,
    run_entity_resolution_request_context as _run_entity_resolution_request_context_impl,
)
from power_atlas.entity_resolution_queries import (
    fetch_alignment_coverage,
    fetch_canonical_entities,
    fetch_entity_mentions,
    fetch_member_of_coverage,
)
from power_atlas.entity_resolution_clustering import _FUZZY_REVIEW_THRESHOLD
from power_atlas.entity_resolution_clustering import _cluster_mentions_unstructured_only
from power_atlas.entity_resolution_clustering import _compute_initials
from power_atlas.entity_resolution_clustering import _fuzzy_ratio
from power_atlas.entity_resolution_clustering import _is_abbreviation
from power_atlas.entity_resolution_clustering import _make_cluster_id
from power_atlas.entity_resolution_clustering import _membership_score
from power_atlas.entity_resolution_clustering import _membership_status
from power_atlas.entity_resolution_resolver import _build_lookup_tables
from power_atlas.entity_resolution_resolver import _resolve_mention
from power_atlas.entity_resolution_resolver import _split_aliases
from power_atlas.entity_resolution_runner import run_entity_resolution_runtime as _run_entity_resolution_runtime_impl
from power_atlas.entity_resolution_runner import write_alignment_results as _write_alignment_results_impl
from power_atlas.entity_resolution_runner import write_cluster_memberships as _write_cluster_memberships_impl
from power_atlas.entity_resolution_runner import write_resolution_results as _write_resolution_results_impl
from power_atlas.entity_resolution_runner import write_resolved_mentions as _write_resolved_mentions_impl
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

# Normalisation function used throughout this module. Kept as a compatibility
# alias because tests and neighboring helpers import it from the stage.
_normalize = normalize_mention_text

# Supported resolution mode identifiers.
_RESOLUTION_MODE_STRUCTURED_ANCHOR = _ENTRYPOINT_RESOLUTION_MODE_STRUCTURED_ANCHOR
_RESOLUTION_MODE_UNSTRUCTURED_ONLY = _ENTRYPOINT_RESOLUTION_MODE_UNSTRUCTURED_ONLY
_RESOLUTION_MODE_HYBRID = _ENTRYPOINT_RESOLUTION_MODE_HYBRID
_VALID_RESOLUTION_MODES = _ENTRYPOINT_VALID_RESOLUTION_MODES

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
_ENTITY_TYPE_SYNONYMS: dict[str, str] = POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY.synonyms

# Reserved sentinel key used in entity_type_report dicts to represent absent or
# empty entity_type values (None / "").  The decorated name is chosen to make
# it unlikely (but not impossible) for a real NLP extractor to emit this label
# accidentally; if it does, collisions are detected and reported via
# sentinel_label_warnings.  Do NOT change this value without also updating any
# consumers of entity_type_report summaries/artifacts that rely on this sentinel.
_ENTITY_TYPE_NULL_SENTINEL = POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY.null_sentinel


def _neo4j_settings_from_config(
    config: object,
    neo4j_settings: Neo4jSettings | None = None,
) -> Neo4jSettings:
    return _neo4j_settings_from_config_impl(config, neo4j_settings)


def _resolve_effective_dataset_id(
    config: Any,
    dataset_id: str | None,
    *,
    dataset_name: str | None = None,
) -> str:
    return _resolve_effective_dataset_id_impl(
        config,
        dataset_id,
        dataset_name=dataset_name,
    )


def _normalize_entity_type(
    entity_type: str | None,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str | None:
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
    return ``None``.
    """
    return normalize_entity_type_from_policy(entity_type, entity_type_policy)


def build_entity_type_cypher_case(
    var: str,
    unknown_label: str = "UNKNOWN",
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str:
    """Compatibility wrapper over the package-owned Cypher normalization helper."""
    return build_entity_type_cypher_case_from_policy(
        var,
        unknown_label,
        entity_type_policy=entity_type_policy,
    )


def _build_entity_type_report(
    mentions: list[dict[str, Any]],
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
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
            normalized = _normalize_entity_type(raw, entity_type_policy)
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


# ---------------------------------------------------------------------------
# Helpers for unstructured_only resolution
# ---------------------------------------------------------------------------

def _write_resolution_results(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    source_uri: str | None,
    resolved_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    neo4j_database: str,
) -> None:
    _write_resolution_results_impl(
        driver,
        run_id=run_id,
        source_uri=source_uri,
        resolved_rows=resolved_rows,
        unresolved_rows=unresolved_rows,
        neo4j_database=neo4j_database,
        make_cluster_id=lambda current_run_id, current_entity_type, normalized_text: _make_cluster_id(
            current_run_id,
            current_entity_type,
            normalized_text,
        ),
        membership_score=_membership_score,
        membership_status=_membership_status,
        cluster_version=_CLUSTER_VERSION,
    )


def _write_cluster_memberships(
    driver: "neo4j.Driver",  # type: ignore[name-defined]  # noqa: F821
    *,
    run_id: str,
    cluster_rows: list[dict[str, Any]],
    neo4j_database: str,
    created_at: str,
) -> None:
    _write_cluster_memberships_impl(
        driver,
        run_id=run_id,
        cluster_rows=cluster_rows,
        neo4j_database=neo4j_database,
        cluster_version=_CLUSTER_VERSION,
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
    _write_resolved_mentions_impl(
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
    _write_alignment_results_impl(
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
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> dict[str, Any]:
    return _run_entity_resolution_impl_entrypoint(
        config,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        neo4j_settings=neo4j_settings,
        dataset_name=dataset_name,
        entity_type_policy=entity_type_policy,
        runtime_runner=_run_entity_resolution_runtime,
        default_resolution_mode=_RESOLUTION_MODE_STRUCTURED_ANCHOR,
        valid_resolution_modes=_VALID_RESOLUTION_MODES,
    )


def _run_entity_resolution_runtime(
    *,
    config: Any,
    run_id: str,
    source_uri: str | None,
    resolution_mode: str,
    artifact_subdir: str,
    effective_dataset_id: str,
    neo4j_settings: Neo4jSettings,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> dict[str, Any]:
    return _run_entity_resolution_runtime_impl(
        config=config,
        run_id=run_id,
        source_uri=source_uri,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        effective_dataset_id=effective_dataset_id,
        neo4j_settings=neo4j_settings,
        entity_type_policy=entity_type_policy,
        resolver_version=_RESOLVER_VERSION,
        cluster_version=_CLUSTER_VERSION,
        alignment_version=_ALIGNMENT_VERSION,
        build_entity_type_report=_build_entity_type_report,
        cluster_mentions=lambda mentions: _cluster_mentions_unstructured_only(
            mentions,
            entity_type_policy=entity_type_policy,
        ),
        fetch_mentions=fetch_entity_mentions,
        fetch_canonicals=fetch_canonical_entities,
        build_lookup_tables=_build_lookup_tables,
        make_cluster_id=lambda current_run_id, current_entity_type, normalized_text: _make_cluster_id(
            current_run_id,
            current_entity_type,
            normalized_text,
            entity_type_policy,
        ),
        align_clusters_to_canonical=_align_clusters_to_canonical,
        resolve_mention=lambda mention, by_qid, by_label, by_alias: _resolve_mention(
            mention,
            by_qid,
            by_label,
            by_alias,
            entity_type_policy,
        ),
        write_resolution_results=_write_resolution_results,
        write_alignment_results=_write_alignment_results,
        fetch_member_of_coverage=fetch_member_of_coverage,
        fetch_alignment_coverage=fetch_alignment_coverage,
        resolution_mode_structured_anchor=_RESOLUTION_MODE_STRUCTURED_ANCHOR,
        resolution_mode_unstructured_only=_RESOLUTION_MODE_UNSTRUCTURED_ONLY,
        resolution_mode_hybrid=_RESOLUTION_MODE_HYBRID,
    )


def run_entity_resolution_request_context(
    request_context: RequestContext,
    *,
    resolution_mode: str | None = None,
    artifact_subdir: str = "entity_resolution",
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """Run entity resolution using request-scoped context as the primary input."""
    return _run_entity_resolution_request_context_impl(
        request_context,
        resolution_mode=resolution_mode,
        artifact_subdir=artifact_subdir,
        dataset_id=dataset_id,
        config_runner=_run_entity_resolution_impl,
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
