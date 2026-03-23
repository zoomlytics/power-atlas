# Power Atlas — Retrieval Semantics: Chunk-First, Participation-Aware, Cluster-Enriched (v0.1)

**Status:** Accepted  
**Audience:** Contributors, architects, reviewers  
**Scope:** Retrieval design semantics — chunk anchoring, graph expansion, evidence boundaries

---

## 1) Summary

Power Atlas retrieval is **chunk-first**: the primary retrieval unit is always a `Chunk` node
returned by vector similarity search.  Graph expansion — participation edges, cluster
membership, canonical alignment — is a **layered enrichment** applied to each chunk after it
is retrieved.  These layers supply richer context to the language model but never replace or
override the chunk as the citation anchor.

---

## 2) The Four Invariants

### 2.1 Retrieval is chunk-first; graph expansion is layered enrichment

Vector similarity search identifies the `Chunk` nodes most relevant to the query.  The Cypher
retrieval query then optionally expands each chunk using one or more graph layers:

| Layer | Enabled by | Graph edges consulted |
|---|---|---|
| Base | *(default)* | None — chunk text and metadata only |
| Graph-expanded | `--expand-graph` | `SUPPORTED_BY` (claim→chunk), `HAS_PARTICIPANT` (claim→mention), `RESOLVES_TO` (mention→canonical) |
| Cluster-aware | `--cluster-aware` | All of the above + `MEMBER_OF` (mention→cluster), `ALIGNED_WITH` (cluster→canonical) |

Graph expansion enriches the LLM context window but does **not** re-rank or replace chunks.
The chunk returned by vector search is always the primary retrieval result.

### 2.2 Explicit participation edges outrank chunk co-location

`HAS_PARTICIPANT {role}` edges (written by the `claim-participation` stage) are the
authoritative record of which entity mentions fill which argument slots of a claim.  They
are preferred over chunk co-location for all claim-focused retrieval and graph traversal
because:

- **Precision**: co-location (`MENTIONED_IN`) reports every mention that appears anywhere in the
  same chunk, including mentions unrelated to the claim.  A participation edge records exactly
  which mention was resolved as the `"subject"` or `"object"` of that specific claim.
- **Match-method provenance**: each `HAS_PARTICIPANT` edge carries a `match_method` property
  (`raw_exact`, `casefold_exact`, `normalized_exact`) that documents how the slot text was
  resolved to the mention.  Co-location carries no equivalent signal.
- **No fallback**: the retrieval stage does **not** fall back to co-located mentions for claims
  that lack participation edges.  Absence of a participation edge is recorded faithfully as a
  `null` slot in `claim_details`; it is not silently backfilled.

Chunk co-location (`MENTIONED_IN`) is preserved in the graph for architecture-level inspection
but must not be used as a proxy for claim-argument semantics.

### 2.3 Cluster and canonical enrichments are provisional / secondary evidence

`ResolvedEntityCluster` membership (`MEMBER_OF`) and canonical entity alignment (`ALIGNED_WITH`
in hybrid mode, `RESOLVES_TO` in structured-anchor mode) are derived, provisional views
built on top of the extraction layer.  They are treated as secondary evidence in retrieval:

- Cluster membership is **provisional**: it reflects the best available clustering at the
  time `resolve-entities` ran and may be revised in a future run without altering the
  underlying `EntityMention` or `ExtractedClaim` nodes.
- Canonical alignment via `ALIGNED_WITH` is an **optional enrichment pass**: it is only
  present after `resolve-entities --resolution-mode hybrid` and may cover only a subset of
  clusters (those with a label-exact or alias-exact match to a `CanonicalEntity`).
- Cluster and canonical context is surfaced to the LLM as supplementary framing, not as
  authoritative claim evidence.  The retrieval path diagnostics field
  (`retrieval_path_diagnostics`) explicitly labels these as `cluster_memberships` and
  `cluster_canonical_via_aligned_with` to distinguish them from the primary participation
  edge evidence.
- Plain vector retrieval (without `--cluster-aware`) does **not** traverse `ALIGNED_WITH`
  or `MEMBER_OF` edges, ensuring that unenriched runs remain coherent.

### 2.4 Citation anchoring remains at the chunk level

Every citation token emitted by the system identifies a `Chunk` node:

```
[CITATION|chunk_id=...|run_id=...|source_uri=...|chunk_index=...|page=...|start_char=...|end_char=...]
```

This invariant holds regardless of how much graph expansion was applied:

- Claims, entity mentions, cluster labels, and canonical entity names enriched in the LLM
  context do **not** produce independent citation tokens.
- The underlying `Chunk` — with its `source_uri`, `page`, and character offsets — remains
  the verifiable evidence anchor for every statement in the answer.
- The citation-validation pass (`_check_all_answers_cited`) enforces that every sentence or
  bullet in the generated answer ends with a `[CITATION|...]` token referencing a retrieved
  chunk.

This design means that a contributor inspecting a citation can always trace it to a specific
passage in a source document, independent of how the graph enrichment layers are configured.

---

## 3) Retrieval Query Variants

The implementation exposes six pre-built Cypher retrieval queries selected by the combination
of `expand_graph`, `cluster_aware`, and `all_runs` flags:

| Query variant | `expand_graph` | `cluster_aware` | `all_runs` |
|---|:---:|:---:|:---:|
| Base run-scoped | — | — | — |
| Graph-expanded run-scoped | ✓ | — | — |
| Cluster-aware run-scoped | ✓ (implied) | ✓ | — |
| Base all-runs | — | — | ✓ |
| Graph-expanded all-runs | ✓ | — | ✓ |
| Cluster-aware all-runs | ✓ (implied) | ✓ | ✓ |

`cluster_aware` implies `expand_graph`: cluster-aware retrieval always includes the full
participation-edge and canonical-entity expansion as well.

---

## 4) Retrieval-Path Diagnostics

Each retrieved chunk carries a `retrieval_path_diagnostics` metadata dict that audits which
graph layers contributed context for that chunk:

| Field | Source graph layer | Provenance type |
|---|---|---|
| `has_participant_edges` | `HAS_PARTICIPANT {role}` | Primary — explicit participation |
| `canonical_via_resolves_to` | `RESOLVES_TO` | Primary — structured-anchor canonical identity |
| `cluster_memberships` | `MEMBER_OF` | Provisional — cluster identity |
| `cluster_canonical_via_aligned_with` | `ALIGNED_WITH` | Provisional — hybrid canonical alignment |

The top-level `retrieval_path_summary` field in the `run_retrieval_and_qa` result consolidates
these per-chunk diagnostics into a human-readable text summary for debugging.

---

## 5) Design Rationale

These invariants reflect several architectural commitments:

- **Evidence-first**: answers must be traceable to a specific passage in a source document.
  Chunk-anchored citations enforce this without ambiguity.
- **Provenance over convenience**: graph expansion layers are additive and explicitly labeled;
  they do not silently change what counts as evidence.
- **Provisional resolution**: entity clusters and canonical alignments are working hypotheses
  that improve over time.  The retrieval model is designed so that changes to the resolution
  layer cannot corrupt the citation anchor.
- **Semantic Core independence**: the role semantics of `"subject"` and `"object"` live in
  the `HAS_PARTICIPANT {role}` property, not in retrieval heuristics or co-location
  assumptions.  Future role types (agent, location, value, etc.) extend the participation
  model without changing the retrieval invariants.

---

## 6) Related Architecture Documents

- [Claim argument model v0.3](claim-argument-model-v0.3.md) — decision record for the
  `HAS_PARTICIPANT {role}` edge model that underpins participation-aware retrieval
- [Unstructured-first entity resolution v0.1](unstructured-first-entity-resolution-v0.1.md) —
  layered identity model that defines how cluster and canonical enrichments are built
- [Architecture overview v0.1](v0.1.md) — Semantic Core independence principle and
  conceptual layering model

---

## Closing Note

This document is the canonical reference for retrieval design semantics in Power Atlas.
Contributors adding new retrieval modes, citation formats, or graph expansion layers should
verify that all four invariants (§2.1–2.4) are preserved.  Any deviation requires an explicit
update to this document.
