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
Callers may pass ``artifact_subdir`` to ``run_entity_resolution`` to
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

* ``status``: ``"ok"`` on success, or ``"dry_run"`` when resolution was skipped.
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
* ``warnings``: List of non-fatal issues encountered during resolution.

In modes that perform text-based clustering
(``resolution_mode`` is ``"unstructured_only"`` or ``"hybrid"``), the summary
also includes:

* ``mentions_clustered``: Number of mentions that were placed into a
  :ResolvedEntityCluster node via a ``MEMBER_OF`` edge.  In current
  unstructured-first behaviour the ``label_cluster`` fallback ensures every
  mention receives a ``MEMBER_OF`` edge, so this always equals
  ``mentions_total`` when the stage succeeds.
* ``mentions_unclustered``: Number of mentions that were processed by the
  clustering logic but ended up with **no** ``MEMBER_OF`` edge to any cluster.
  Under the current ``label_cluster`` fallback this is always ``0``; it is
  included as an explicit health signal (non-zero values indicate a bug or
  unexpected data condition).

In ``"hybrid"`` mode, canonical alignment metrics are also present:

* ``alignment_version``: Version string for the canonical alignment algorithm.
* ``aligned_clusters``: Number of :ResolvedEntityCluster nodes that received an
  ``ALIGNED_WITH`` edge pointing to a :CanonicalEntity node in this run.
* ``alignment_breakdown``: Mapping from alignment strategy name to the number
  of clusters aligned by that strategy.
* ``distinct_canonical_entities_aligned``: Count of unique :CanonicalEntity
  nodes that are the target of at least one ``ALIGNED_WITH`` edge created in
  this run.
* ``mentions_in_aligned_clusters``: Number of :EntityMention nodes (via
  ``MEMBER_OF``) that belong to a :ResolvedEntityCluster which has an
  ``ALIGNED_WITH`` edge to some :CanonicalEntity.
* ``clusters_pending_alignment``: Number of :ResolvedEntityCluster nodes
  produced by the unstructured clustering step that did **not** receive an
  ``ALIGNED_WITH`` edge in this run (i.e. ``clusters_created - aligned_clusters``).

Recommended metrics per mode
------------------------------
* ``"structured_anchor"``: use ``resolved``, ``unresolved``, ``resolution_breakdown``.
* ``"unstructured_only"``: use ``mentions_clustered``, ``mentions_unclustered``,
  ``clusters_created``, ``resolution_breakdown``.  Ignore ``resolved``/``unresolved``
  (always 0 / mentions_total respectively).
* ``"hybrid"``: use ``mentions_clustered``, ``mentions_unclustered``,
  ``clusters_created``, ``aligned_clusters``, ``distinct_canonical_entities_aligned``,
  ``mentions_in_aligned_clusters``, ``clusters_pending_alignment``, and
  ``alignment_breakdown``.  Ignore ``resolved``/``unresolved``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any
from pathlib import Path
from urllib.parse import quote as _pct_encode

from demo.contracts.resolution import ALIGNMENT_VERSION as _ALIGNMENT_VERSION

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

# Typographic/curly apostrophe variants that should normalise to ASCII ' (U+0027).
# Includes: LEFT/RIGHT SINGLE QUOTATION MARK, MODIFIER LETTER APOSTROPHE,
# MODIFIER LETTER PRIME, GRAVE ACCENT, ACUTE ACCENT.
_RE_APOSTROPHE_VARIANTS = re.compile(r"[\u2018\u2019\u02BC\u02B9\u0060\u00B4]")

# Hyphen/dash variants that should normalise to ASCII hyphen-minus (U+002D).
# Includes: HYPHEN, NON-BREAKING HYPHEN, FIGURE DASH, EN DASH, EM DASH,
# HORIZONTAL BAR, MINUS SIGN, SMALL EM DASH, SMALL HYPHEN-MINUS, FULLWIDTH
# HYPHEN-MINUS.
_RE_HYPHEN_VARIANTS = re.compile(
    r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]"
)

# Matches any run of whitespace (including Unicode whitespace such as
# non-breaking space U+00A0, ideographic space U+3000, etc.).
_RE_WHITESPACE = re.compile(r"\s+")

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
    """Normalise *text* for mention clustering and entity resolution.

    Steps applied in order:

    1. Strip leading/trailing whitespace.
    2. NFKD Unicode normalisation — decomposes compatibility variants
       (e.g. full-width characters, ligatures) *and* separates base characters
       from their combining marks ready for step 3.
    3. Diacritic removal — drops Unicode combining marks (category ``Mn``) so
       accented forms cluster with their unaccented equivalents
       (e.g. ``"naïve"`` → ``"naive"``, and with later case-folding
       ``"Müller"`` → ``"muller"``).
    4. Apostrophe normalisation — collapses typographic/curly apostrophe
       variants (U+2018 LEFT SINGLE QUOTATION MARK ``‘``, U+2019 RIGHT SINGLE
       QUOTATION MARK ``’``, U+02BC MODIFIER LETTER APOSTROPHE ``ʼ``, etc.) to
       the plain ASCII apostrophe (``'``).
    5. Hyphen/dash normalisation — collapses en-dash, em-dash, and other Unicode
       dash code points to the plain ASCII hyphen-minus (``-``).
    6. Whitespace collapse — runs of whitespace (including non-breaking spaces,
       ideographic spaces, etc.) are folded to a single ASCII space.
    7. Case-folding — applies Python's ``str.casefold()`` for aggressive
       lowercase normalisation (handles ``ß`` → ``ss``, etc.).
    """
    # 1. Strip
    text = text.strip()
    # 2+3. NFKD decomposition followed by diacritic removal
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if unicodedata.category(ch) != "Mn"
    )
    # 4. Apostrophe variants → ASCII apostrophe
    text = _RE_APOSTROPHE_VARIANTS.sub("'", text)
    # 5. Hyphen/dash variants → ASCII hyphen-minus
    text = _RE_HYPHEN_VARIANTS.sub("-", text)
    # 6. Collapse whitespace
    text = _RE_WHITESPACE.sub(" ", text).strip()
    # 7. Case-fold
    return text.casefold()


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
    """
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    run_id_enc = _pct_encode(run_id, safe="")
    entity_type_enc = _pct_encode(entity_type or "", safe="")
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
        entity_type: str | None = mention.get("entity_type") or None
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
            "entity_type": mention.get("entity_type") or None,
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
        "entity_type": mention.get("entity_type") or None,
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
    if resolved_rows:
        driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
            MATCH (canonical:CanonicalEntity {entity_id: row.canonical_entity_id, run_id: row.canonical_run_id})
            MERGE (mention)-[r:RESOLVES_TO]->(canonical)
            SET r.run_id = $run_id,
                r.source_uri = coalesce(nullif(mention.source_uri, ''), $source_uri),
                r.resolution_method = row.resolution_method,
                r.resolution_confidence = row.resolution_confidence,
                r.candidate_ids = row.candidate_ids
            """,
            parameters_={
                "rows": resolved_rows,
                "run_id": run_id,
                "source_uri": source_uri or None,
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
        driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
            ON CREATE SET
                cluster.canonical_name  = row.canonical_name,
                cluster.normalized_text = row.normalized_text,
                cluster.entity_type     = row.entity_type,
                cluster.run_id          = $run_id,
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
                r.source_uri       = row.source_uri
            """,
            parameters_={
                "rows": cluster_rows,
                "run_id": run_id,
                "resolver_version": _CLUSTER_VERSION,
                "created_at": created_at,
            },
            database_=neo4j_database,
        )
        # Write explicit CANDIDATE_MATCH edges for memberships that require
        # human review before being relied upon ("candidate" = abbreviation,
        # "review_required" = borderline fuzzy).  These edges are written
        # in addition to MEMBER_OF edges so downstream consumers can use them
        # as a review queue without disturbing the cluster membership graph.
        candidate_rows = [r for r in cluster_rows if r["status"] in ("candidate", "review_required")]
        if candidate_rows:
            driver.execute_query(
                """
                UNWIND $rows AS row
                MATCH (mention:EntityMention {mention_id: row.mention_id, run_id: $run_id})
                MATCH (cluster:ResolvedEntityCluster {cluster_id: row.cluster_id})
                MERGE (mention)-[r:CANDIDATE_MATCH]->(cluster)
                SET r.score            = row.score,
                    r.method           = row.method,
                    r.resolver_version = $resolver_version,
                    r.run_id           = $run_id,
                    r.status           = row.status,
                    r.source_uri       = row.source_uri
                """,
                parameters_={
                    "rows": candidate_rows,
                    "run_id": run_id,
                    "resolver_version": _CLUSTER_VERSION,
                },
                database_=neo4j_database,
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
            r.source_uri       = coalesce(row.source_uri, $source_uri)
        """,
        parameters_={
            "rows": alignment_rows,
            "run_id": run_id,
            "source_uri": source_uri or None,
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
                   mention.entity_type AS entity_type,
                   mention.source_uri AS source_uri
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
                "source_uri": record["source_uri"] if record["source_uri"] not in (None, "") else source_uri,
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
                # Build unique cluster dicts keyed by the scoped cluster_id
                # produced by _make_cluster_id (which incorporates run_id,
                # entity_type, and normalized_text). Multiple mention rows
                # can map to the same cluster_id (including mentions from
                # different source documents — source_uri is NOT part of
                # cluster identity). We deduplicate by cluster_id in a single
                # O(n) pass, then sort only the unique entries (O(u log u),
                # u ≤ n).
                cluster_entries_by_id: dict[str, tuple[tuple[str, str], dict[str, Any]]] = {}
                for row in unresolved_rows:
                    cid = _make_cluster_id(run_id, row.get("entity_type"), row["normalized_text"])
                    if cid not in cluster_entries_by_id:
                        sort_key = (row.get("entity_type") or "", row["normalized_text"])
                        cluster_entries_by_id[cid] = (sort_key, {
                            "cluster_id": cid,
                            "normalized_text": row["normalized_text"],
                        })
                unique_clusters: list[dict[str, Any]] = [
                    c for _, c in sorted(cluster_entries_by_id.values(), key=lambda t: t[0])
                ]
                alignment_rows = _align_clusters_to_canonical(
                    unique_clusters, by_label, by_alias
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
    if resolution_mode in (_RESOLUTION_MODE_UNSTRUCTURED_ONLY, _RESOLUTION_MODE_HYBRID):
        # In unstructured-first modes every mention is placed in a cluster
        # (the label_cluster fallback ensures no mention is left without one).
        # These fields make it explicit that clustering succeeded even though
        # resolved=0 — which reflects the absence of canonical entity matches,
        # not a failure of the clustering/alignment stage.
        summary["mentions_clustered"] = len(unresolved_rows)
        summary["mentions_unclustered"] = 0
    if resolution_mode == _RESOLUTION_MODE_HYBRID:
        alignment_breakdown: dict[str, int] = {}
        for row in alignment_rows:
            m = row["alignment_method"]
            alignment_breakdown[m] = alignment_breakdown.get(m, 0) + 1
        aligned_cluster_ids = {row["cluster_id"] for row in alignment_rows}
        mentions_in_aligned = sum(
            1 for row in unresolved_rows
            if _make_cluster_id(run_id, row.get("entity_type"), row["normalized_text"])
            in aligned_cluster_ids
        )
        summary["alignment_version"] = _ALIGNMENT_VERSION
        summary["aligned_clusters"] = len(alignment_rows)
        summary["alignment_breakdown"] = alignment_breakdown
        summary["distinct_canonical_entities_aligned"] = len(
            {row["canonical_entity_id"] for row in alignment_rows}
        )
        summary["mentions_in_aligned_clusters"] = mentions_in_aligned
        summary["clusters_pending_alignment"] = clusters_created - len(alignment_rows)
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
