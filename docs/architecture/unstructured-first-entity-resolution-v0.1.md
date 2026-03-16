# Power Atlas — Unstructured-First Entity Resolution (v0.1, Draft)

**Status:** Accepted — Phase 1 + Phase 3 implemented  
**Audience:** Contributors, architects, reviewers  
**Scope:** Entity resolution, ingestion architecture, demo posture, retrieval implications

## 1) Summary

Power Atlas should support a **first-class unstructured-first entity resolution mode** in which extracted entities from unstructured datasets can be meaningfully resolved **without requiring prior structured ingest**.

Structured datasets remain valuable, but primarily as an **optional verification and enrichment layer**, not the only canonical anchor for identity resolution.

This document proposes a **non-destructive, provenance-preserving layered identity model**:

- **Lexical/source layer** — documents, chunks, structured rows, and provenance artifacts
- **Extracted assertion layer** — `EntityMention` and `ExtractedClaim`
- **Provisional resolution layer** — `ResolvedEntityCluster` (or equivalent derived node)
- **Optional curated/enrichment layer** — `CanonicalEntity` and structured/external reference records

The goal is to support additive multi-dataset workflows in which:

- each dataset can stand on its own
- extracted mentions can be clustered/resolved against each other first
- ambiguity remains explicit when confidence is limited
- provenance is preserved
- structured data can later verify, enrich, or extend the graph without being a hidden prerequisite

---

## 2) Context

### 2.1 Current demo posture

The current demo sequence is roughly:

1. ingest PDF
2. extract claims and mentions
3. resolve entities
4. ingest structured data
5. ask questions

Observed recent walkthrough behavior suggests:

- unstructured ingest works
- claim extraction works
- structured ingest works
- entity resolution currently appears exact-match based
- relatively few mentions resolve compared to total mentions
- Q&A and citation validation work operationally

This suggests the demo is operationally sound, but the current resolution story appears to lean on structured ingest as a canonical identity anchor.

### 2.2 Current strengths to preserve

Power Atlas already appears to favor several good design properties:

- preserving lexical/source assertions
- preserving extracted mentions and claims
- non-destructive resolution patterns
- run scoping and provenance retention
- explicit auditability

These are strengths and should be preserved.

### 2.3 Product intent

The intended broader model is:

- unstructured datasets should be useful on their own
- multiple datasets should behave additively
- extracted mentions/entities from unstructured data should be resolvable against each other
- structured ingest should be optional
- structured data should act as:
  - verification when available
  - enrichment when useful
  - an additive source of new nodes, edges, and relationships
  - not the sole privileged identity substrate

---

## 3) Problem statement

Power Atlas currently lacks a clearly defined **first-class unstructured-only resolution layer** between raw extracted mentions and structured canonical entities.

As a result, the demo can imply that:

- meaningful entity resolution depends on structured ingest
- structured rows are the primary identity anchor
- extracted mentions are mainly useful as pre-resolution artifacts rather than as inputs to a full standalone resolution workflow

This is narrower than the intended product model and narrower than common graph + RAG research patterns, where systems often:

1. ingest unstructured documents
2. extract mentions/entities/relations/claims
3. preserve a raw extracted graph
4. resolve extracted entities against each other
5. optionally derive a provisional canonical layer
6. optionally verify/enrich later with structured or external sources

---

## 4) Decision

Power Atlas will adopt an **unstructured-first, non-destructive entity resolution model**.

### 4.1 Core decision

Entity resolution will support a mode in which:

- `EntityMention` nodes are resolved against other extracted mentions/entities
- this process does **not** require structured ingest
- the result is a derived, provisional identity layer
- raw mentions and source assertions remain preserved

### 4.2 Structured ingest posture

Structured ingest will be treated as:

- **optional**
- **additive**
- useful for **verification**
- useful for **enrichment**
- useful for introducing additional entities/relationships
- **not required** for meaningful unstructured resolution

### 4.3 Non-destructive posture

Power Atlas will prefer **non-destructive resolution** by default:

- extracted mentions remain explicit
- source assertions remain explicit
- derived resolved entities/clusters are created without collapsing provenance
- ambiguity may remain explicit when confidence is insufficient

### 4.4 Preferred identity layers

The preferred conceptual model is:

- `EntityMention` = what a source chunk mentions
- `ExtractedClaim` = what the extractor asserted from a source chunk
- `ResolvedEntityCluster` = a system-derived grouping of mentions believed to refer to the same underlying entity
- `CanonicalEntity` = a curated or externally sourced identity record used for optional alignment, verification, and enrichment

---

## 5) Decision details

## 5.1 Layered model

### Layer 1 — Lexical / source layer

Represents source artifacts as ingested.

Examples:
- document
- chunk
- structured source row
- source manifests
- provenance metadata

Purpose:
- preserve source truth
- support citation and traceability
- maintain auditability

### Layer 2 — Extracted assertion layer

Represents direct extraction outputs from source material.

Examples:
- `EntityMention`
- `ExtractedClaim`

Purpose:
- capture extractor outputs without premature normalization
- preserve source-scoped assertions
- support downstream resolution and retrieval

### Layer 3 — Provisional resolution layer

Represents system-derived groupings across extracted mentions.

Recommended node:
- `ResolvedEntityCluster`

Alternative names may be considered, such as:
- `ProvisionalEntity`

Current recommendation:
- prefer `ResolvedEntityCluster` because it communicates that this layer is derived and may remain provisional

Purpose:
- cluster mentions across documents and datasets
- support unstructured-first resolution
- maintain non-destructive provenance-preserving semantics

### Layer 4 — Curated / enrichment layer

Represents structured or externally curated identity records.

Examples:
- `CanonicalEntity`
- external identifier-backed entities
- structured fact/relationship rows and derived graph objects

Purpose:
- verify cluster identity when possible
- enrich graph structure
- add nodes/edges/relationships not present in original unstructured sources

---

## 5.2 Recommended relationship semantics

The exact labels may evolve, but the intended semantics are:

- `(:EntityMention)-[:MENTIONED_IN]->(:Chunk)`
- `(:ExtractedClaim)-[:SUPPORTED_BY]->(:Chunk)`
- `(:ExtractedClaim)-[:MENTIONS]->(:EntityMention)`

For provisional resolution:

- `(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster)`

This relationship should be capable of carrying:

- `score`
- `method`
- `resolver_version`
- `run_id`
- optional `status` such as `accepted`, `tentative`, or `review_required`

For structured alignment:

- `(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity)`

This relationship should also be capable of carrying:

- `score`
- `method`
- `alignment_status`
- provenance to the alignment process or input rows

Optional future candidate relationships may include:

- `POSSIBLE_MATCH`
- `SAME_AS_CANDIDATE`
- `REVIEW_REQUIRED`

Current preference is to center the model on **cluster membership** rather than immediate hard merge semantics.

---

## 5.3 Resolution modes

Power Atlas should support multiple explicit resolution modes.

### Mode A — `unstructured_only`

Use only extracted mentions/entities from unstructured datasets.

Behavior:
- cluster extracted mentions against each other
- create provisional clusters
- do not require structured entities

Use case:
- research, exploratory, or investigative workflows
- document-first graph construction
- cases where no curated reference dataset exists yet

### Mode B — `structured_anchor`

Resolve extracted mentions primarily against structured/canonical entities.

Behavior:
- keep the current deterministic structured-anchored path available where useful

Use case:
- demos or workflows where a high-quality structured registry already exists
- tightly scoped curated environments

### Mode C — `hybrid`

Resolve unstructured mentions into clusters first, then optionally align clusters to structured/canonical entities.

Behavior:
- runs the full `unstructured_only` clustering pass first (normalized-exact, abbreviation, fuzzy, label_cluster)
- for each resulting :ResolvedEntityCluster, checks whether its normalized text matches a :CanonicalEntity by label or alias
- creates `ALIGNED_WITH` edges from matched clusters to their canonical counterparts
- structured ingest is entirely optional; when no :CanonicalEntity nodes are present the mode degrades gracefully to pure unstructured clustering
- all existing `MEMBER_OF` edges and cluster nodes remain unchanged (non-destructive)

Summary fields added in `hybrid` mode (beyond the standard set):
- `aligned_clusters` — number of clusters that received an `ALIGNED_WITH` edge
- `alignment_breakdown` — per-method count of alignment edges written (`label_exact`, `alias_exact`)
- `alignment_version` — value of `_ALIGNMENT_VERSION` constant

Use case:
- the intended long-term default product posture
- workflows where structured data should enrich but not gate resolution

---

## 5.4 Resolution methods

The initial unstructured-first resolver should be incremental and practical.

Recommended resolution stages:

1. normalized exact match
2. alias / abbreviation heuristics
3. fuzzy lexical match
4. optional semantic similarity
5. optional contextual / neighborhood similarity
6. optional review workflow for uncertain cases

### Guidance

- prefer simple, high-signal methods first
- persist confidence and method metadata
- avoid overstating certainty
- do not destructively merge extracted mentions by default

---

## 6) Consequences

## 6.1 Positive consequences

### Meaningful unstructured workflows
Users can ingest a document set, extract mentions/claims, resolve them into provisional identity clusters, and retrieve useful answers **without structured ingest**.

### Better alignment with research patterns
The architecture becomes more aligned with common graph + RAG patterns used in document intelligence, investigative research, and evidence-sensitive settings.

### Preserved provenance and auditability
Because raw mentions remain intact, the system can continue to support:

- traceable citation
- explanation of derivation
- explicit ambiguity
- later review or correction

### Additive multi-dataset behavior
Overlapping datasets can enrich the graph without requiring a single privileged source to define identity.

### Better product messaging
The demo can more accurately communicate the intended product behavior:
- structured data enhances the graph
- it does not grant the graph permission to become meaningful

## 6.2 Costs / tradeoffs

### More graph complexity
Introducing a provisional cluster layer adds another conceptual layer to the model.

### More retrieval design work
Retrieval and answer generation will need to reason over:
- mentions
- clusters
- optional canonical alignments

### More resolver bookkeeping
The system will need to track:
- scores
- methods
- thresholds
- alignment status
- possible review states

### Potential user confusion if poorly documented
Without clear docs, users may confuse:
- a mention
- a cluster
- a canonical entity
- an inferred alignment

This increases the importance of documentation and demo clarity.

---

## 7) Non-goals

This decision does **not** currently require:

- destructive merge-based entity resolution
- a full human review UI in the first implementation
- a finalized long-term ontology vocabulary for all future versions
- replacing the current structured-anchored demo path entirely
- solving all semantic/entity-resolution edge cases in v0.1

This is a directional architecture decision, not a claim that all downstream implementation choices are settled.

---

## 8) Retrieval and Q&A implications

A provisional resolution layer should improve recall and graph connectivity, but retrieval must remain evidence-grounded.

### Required posture

When answering questions:

- source chunks, extracted claims, and structured source rows remain the primary evidence basis
- provisional clusters may help connect evidence across mentions/datasets
- the system should avoid presenting provisional identity inference as settled source fact when confidence is limited

### Implication

Cluster nodes are useful retrieval intermediaries, but they are **not themselves the original evidence**.

---

## 9) Demo implications

The demo should evolve to show the intended product behavior more clearly.

### Recommended demo sequence

1. ingest PDF
2. extract claims and mentions
3. resolve entities in `unstructured_only` mode
4. ask questions
5. ingest structured data
6. align or re-resolve in `hybrid` mode
7. ask questions again

### Why

This demonstrates that:

- unstructured data stands on its own
- entity resolution is meaningful before structured ingest
- structured data enriches and verifies rather than silently serving as the only identity anchor

---

## 10) Implementation guidance

Recommended phased implementation:

### Phase 1
Define the graph model and terminology:
- `EntityMention`
- `ResolvedEntityCluster`
- `CanonicalEntity`
- relationship semantics and confidence fields

### Phase 2
Implement `unstructured_only` resolution:
- cluster extracted mentions
- create provisional clusters
- persist score/method metadata
- emit summary metrics

### Phase 3
Implement `hybrid` alignment (implemented):
- align clusters to canonical entities after unstructured clustering
- create ALIGNED_WITH edges with alignment provenance metadata
- preserve additive enrichment semantics; structured ingest remains optional
- degrade gracefully when no CanonicalEntity nodes are present

### Phase 4
Update retrieval and Q&A behavior (implemented):
- `cluster_aware=True` flag on `run_retrieval_and_qa` and `run_interactive_qa` enables
  cluster-aware retrieval using `_RETRIEVAL_QUERY_WITH_CLUSTER` (run-scoped) and
  `_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS` (all-runs)
- Cluster membership (`MEMBER_OF`) and canonical alignment (`ALIGNED_WITH`) context is
  appended to each retrieved chunk's LLM context via `_format_cluster_context`
- Membership status is rendered with graduated labels:
  - `"accepted"` → `Entity cluster (accepted)` — deterministic; no review needed
  - `"provisional"` → `PROVISIONAL CLUSTER` — high-confidence fuzzy; review optional
  - `"candidate"` → `CANDIDATE CLUSTER` — abbreviation match; plausible but ambiguous
  - `"review_required"` → `REVIEW REQUIRED CLUSTER` — borderline fuzzy; needs verification
- Provisional canonical alignments are labelled `PROVISIONAL ALIGNMENT`; confirmed
  alignments use `Cluster aligned to canonical entity`
- The QA prompt template (`qa_v3`) instructs the model to use qualified language
  ("possibly", "may be") for provisional inferences and never present them as settled
  identity claims
- Citations always reference the underlying `Chunk` node, never the cluster node

### Phase 5
Review-oriented features (implemented):
- `CANDIDATE_MATCH` edges written alongside `MEMBER_OF` for all `"candidate"` and
  `"review_required"` status memberships; provide a dedicated review queue
- `_FUZZY_REVIEW_THRESHOLD = 0.92` separates high-confidence fuzzy (`"provisional"`)
  from borderline fuzzy (`"review_required"`)
- `"candidate"` status on `abbreviation` matches makes ambiguity explicit for HITL review
- Audit trail: all edges carry `method`, `score`, `resolver_version`, `run_id`, `source_uri`

---

## 11) Open questions

The following questions remain intentionally open for implementation design:

1. Should the provisional node be named `ResolvedEntityCluster` or `ProvisionalEntity`?
2. Should uncertain pairwise links be persisted explicitly as relationships between mentions, or only as cluster membership decisions?
3. How much contextual similarity should be included in the first resolver iteration?
4. What thresholds should separate:
   - accepted cluster membership
   - tentative membership
   - review-required cases
5. How should retrieval rank evidence that is connected through provisional clusters but not yet aligned to canonical entities?
   - **Phase 4 partial answer**: cluster membership and alignment context is surfaced to the LLM
     but is labelled explicitly as provisional inference; ranking is currently identical to base
     vector retrieval — cluster context enriches the prompt without reordering results.

---

## 12) Decision outcome

**Adopt unstructured-first, non-destructive entity resolution with a provisional cluster layer and optional structured alignment/enrichment.**

This decision is intended to keep Power Atlas aligned with:

- provenance-first architecture
- additive multi-dataset workflows
- research-grade graph + RAG patterns
- explicit ambiguity handling
- the product intent that structured ingest is beneficial, but not required, for meaningful resolution

---

## 13) Suggested follow-on work

1. ~~Add a second issue for `hybrid_additive` structured alignment~~ (implemented as `hybrid` mode)
2. Update demo documentation to show unstructured-only usefulness before structured ingest
3. Add a follow-on retrieval design note if cluster-aware retrieval introduces material answer-policy changes

---

## 14) Phase 1 implementation notes

Phase 1 has been implemented in the following modules:

### `demo/stages/entity_resolution.py`

- The `_resolve_mention()` helper now returns `resolution_method = "label_cluster"` (replacing the
  former `"unresolved"` placeholder) for every mention that does not match a `CanonicalEntity`.
- `_write_resolution_results()` creates a `:ResolvedEntityCluster` node for each unique
  `normalized_text` value in the unresolved set, using `MERGE` so that clusters are
  **additive across runs** (the same normalized text always maps to the same cluster node).
- Each `:EntityMention` in the unresolved set receives a `MEMBER_OF` edge to its cluster carrying
  the required metadata:
  - `score` — membership confidence (1.0 for deterministic label matching)
  - `method` — `"label_cluster"`
  - `resolver_version` — value of `_CLUSTER_VERSION` constant
  - `run_id` — the run that created the membership link
  - `status` — `"accepted"` for high-confidence label-cluster assignments
- The run summary dict now includes `clusters_created` (count of unique clusters created or
  merged in this run) and `cluster_version`.
- A `_CLUSTER_VERSION` module constant (currently `"v1.1"`) is bumped independently of
  `_RESOLVER_VERSION` so that cluster-membership edges can be distinguished by the version that
  created them.

### `demo/contracts/claim_schema.py`

- Added a new `resolution_layer_schema()` function (intentionally separate from
  `claim_extraction_schema()`) that defines the `ResolvedEntityCluster` `NodeType` with documented
  properties: `cluster_id`, `canonical_name`, `normalized_text`, `resolver_version`, `created_at`.
- Added `MEMBER_OF`, `CANDIDATE_MATCH`, and `ALIGNED_WITH` `RelationshipType` entries to `resolution_layer_schema()`.
  Keeping these out of `claim_extraction_schema()` ensures the LLM extractor never attempts to
  produce resolution-layer nodes or edges directly.

### Graph model (Phase 1 + Phase 3 + Phase 5)

```
(:EntityMention)-[:MENTIONED_IN]->(:Chunk)
(:ExtractedClaim)-[:SUPPORTED_BY]->(:Chunk)
(:ExtractedClaim)-[:MENTIONS]->(:EntityMention)
(:EntityMention)-[:RESOLVES_TO]->(:CanonicalEntity)      ← structured match (structured_anchor)
(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster)  ← provisional cluster
(:EntityMention)-[:CANDIDATE_MATCH]->(:ResolvedEntityCluster) ← ambiguous candidate (review queue)
(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity) ← enrichment alignment (hybrid)
```

### What is implemented (Phase 1 + `unstructured_only` + `hybrid`)

- `unstructured_only` resolution mode flag on `run_entity_resolution()` and `Config`.
- `--resolution-mode` CLI argument on the `resolve-entities` command.
- Matching pipeline in `unstructured_only` mode: normalized exact, abbreviation/initialism, basic fuzzy (difflib).
- `ResolvedEntityCluster` nodes and `MEMBER_OF` edges persist provisional clusters; summary metrics emitted.
- `MEMBER_OF` edge metadata in `unstructured_only` mode:
  - `method` — the actual strategy used: `"normalized_exact"`, `"abbreviation"`, `"fuzzy"`, or `"label_cluster"` (singleton fallback).
  - `score` — `1.0` for deterministic assignments (`label_cluster`, `normalized_exact`), `0.75` for `abbreviation`, actual SequenceMatcher ratio for `fuzzy`.
  - `status` — encodes ambiguity level for downstream consumers and reviewers:
    - `"accepted"` — deterministic assignments (`label_cluster`, `normalized_exact`); high-confidence, no review needed.
    - `"provisional"` — high-confidence fuzzy match (SequenceMatcher ratio ≥ `_FUZZY_REVIEW_THRESHOLD = 0.92`); minor surface-form variant, review optional.
    - `"candidate"` — abbreviation/initialism match; identity is plausible but the abbreviated form is inherently ambiguous, so human review adds value.
    - `"review_required"` — borderline fuzzy match (ratio ≥ `0.85` but < `0.92`); relationship is tentative and should be verified before being relied upon.
  - `resolver_version` — value of `_CLUSTER_VERSION` constant.
  - `run_id` — the run that created the membership link.
  - `source_uri` — the per-mention origin URI read from the `:EntityMention` node; provenance metadata only, **not** part of cluster identity.
- `CANDIDATE_MATCH` edges for ambiguous memberships:
  - Written alongside `MEMBER_OF` for all `"candidate"` and `"review_required"` status memberships.
  - Carry the same provenance fields as `MEMBER_OF` (`score`, `method`, `resolver_version`, `run_id`, `status`, `source_uri`).
  - Provide a dedicated review queue: downstream systems can query `CANDIDATE_MATCH` edges independently without disturbing the cluster membership graph.
  - Semantics: `(:EntityMention)-[:CANDIDATE_MATCH]->(:ResolvedEntityCluster)`.
- `hybrid` resolution mode (Phase 3):
  - runs the full `unstructured_only` clustering pass first
  - after clustering, optionally queries `CanonicalEntity` nodes; if any exist, attempts label-exact then alias-exact alignment for each unique cluster
  - writes `ALIGNED_WITH` edges from matched `ResolvedEntityCluster` nodes to their `CanonicalEntity` counterparts
  - `ALIGNED_WITH` edge metadata: `alignment_method`, `alignment_score`, `alignment_status`, `alignment_version` (`_ALIGNMENT_VERSION` constant), `run_id`, `source_uri`
  - summary includes `aligned_clusters`, `alignment_breakdown`, `alignment_version`
  - gracefully degrades to pure unstructured clustering when no `CanonicalEntity` nodes are present
  - structured ingest is not required; all existing `MEMBER_OF` edges and cluster nodes remain unchanged

### What is not yet implemented (Phases 4–5)

- Cluster-aware retrieval and Q&A traversal (Phase 4).
- Audit workflow tooling and HITL review queue UI (Phase 5).

---

## 15) Cluster identity scope vs. provenance scope

This section resolves the ambiguity discussed in the implementation review about whether
`source_uri` should participate in cluster identity or remain provenance-only metadata.

### 15.1 Decision

**`source_uri` is provenance, not identity.**

The default cluster identity key is `(run_id, entity_type, normalized_text)`.
`source_uri` is **not** a component of cluster identity and does not affect which
`:ResolvedEntityCluster` node a mention is assigned to.

### 15.2 Identity scope

The following three dimensions uniquely identify a `:ResolvedEntityCluster` node:

| Dimension | Role |
|---|---|
| `run_id` | Prevents cross-run collision when the same text appears in multiple independent processing runs. |
| `entity_type` | Prevents merging semantically distinct clusters that share normalized text but belong to different entity types (e.g. "IBM" as ORG vs. "IBM" as PRODUCT). |
| `normalized_text` | The canonical text of the cluster representative. |

`cluster_id` format: `cluster::<run_id_enc>::<entity_type_enc>::<normalized_text_enc>`
(each component percent-encoded via RFC 3986, `safe=''`).

### 15.3 Provenance scope

`source_uri` is propagated as per-mention origin metadata on **edges**, not as a cluster
identity dimension.  This means:

- `MEMBER_OF` edge — carries the per-mention `source_uri` from the `:EntityMention` node.
- `RESOLVES_TO` edge — carries `coalesce(mention.source_uri, run-level source_uri)`.
- `ALIGNED_WITH` edge — carries the function-level `source_uri` (run-scoped provenance).

All three edge types preserve `source_uri` for traceability, but none of them use it to
determine cluster assignment.

### 15.4 Cross-document clustering (default behaviour)

Two mentions that share the same `(run_id, entity_type, normalized_text)` are assigned
to the **same** `:ResolvedEntityCluster` node regardless of which source document they
originated from.  Cross-document clustering within a run is intentional and is the
default behaviour.

Example: mentions of "IBM" (ORG) from `doc1.pdf` and `doc2.pdf` within `run-A` both
receive `MEMBER_OF` edges to the same cluster node.  Their individual `source_uri` values
are preserved on those edges as provenance.

### 15.5 Source-partitioned clustering (opt-in, not yet implemented)

If a workflow requires source-isolated clustering — where mentions from different
source documents within the same run must never merge — this should be expressed as an
explicit mode or policy parameter rather than baked into the default cluster key.  A
future `cluster_scope` parameter (e.g. `cluster_scope="per_source"`) could be added to
`run_entity_resolution()` to opt into source-partitioned behaviour.

**This mode is not implemented in v0.1.**  It is documented here as a future extension
point so that callers with strict source-isolation requirements have a clear upgrade path.