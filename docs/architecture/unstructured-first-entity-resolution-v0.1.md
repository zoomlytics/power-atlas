# Power Atlas — Unstructured-First Entity Resolution (v0.1, Draft)

**Status:** Accepted — Phase 1 implemented  
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

### Mode C — `hybrid_additive`

Resolve unstructured mentions into clusters first, then optionally align clusters to structured/canonical entities.

Behavior:
- preserves the usefulness of unstructured extraction on its own
- adds structured verification/enrichment later
- supports additive graph growth

Use case:
- the intended long-term default product posture

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
6. align or re-resolve in `hybrid_additive` mode
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
Implement `hybrid_additive` alignment:
- align clusters to canonical entities
- preserve additive enrichment semantics
- avoid canonical override behavior

### Phase 4
Update retrieval and Q&A behavior:
- allow traversal via provisional clusters
- keep answers grounded in original evidence
- surface ambiguity where appropriate

### Phase 5
Add review-oriented features if needed:
- threshold bands
- review-required states
- audit trail for resolution decisions

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

These questions should be resolved in implementation issues and follow-on design notes.

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

1. Add a second issue for `hybrid_additive` structured alignment
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
- Added `MEMBER_OF` and `ALIGNED_WITH` `RelationshipType` entries to `resolution_layer_schema()`.
  Keeping these out of `claim_extraction_schema()` ensures the LLM extractor never attempts to
  produce resolution-layer nodes or edges directly.

### Graph model (Phase 1)

```
(:EntityMention)-[:MENTIONED_IN]->(:Chunk)
(:ExtractedClaim)-[:SUPPORTED_BY]->(:Chunk)
(:ExtractedClaim)-[:MENTIONS]->(:EntityMention)
(:EntityMention)-[:RESOLVES_TO]->(:CanonicalEntity)   ← structured match
(:EntityMention)-[:MEMBER_OF]->(:ResolvedEntityCluster) ← provisional cluster
(:ResolvedEntityCluster)-[:ALIGNED_WITH]->(:CanonicalEntity) ← future Phase 3
```

### What is implemented (Phase 1 + `unstructured_only`)

- `unstructured_only` resolution mode flag on `run_entity_resolution()` and `Config`.
- `--resolution-mode` CLI argument on the `resolve-entities` command.
- Matching pipeline in `unstructured_only` mode: normalized exact, abbreviation/initialism, basic fuzzy (difflib).
- `ResolvedEntityCluster` nodes and `MEMBER_OF` edges persist provisional clusters; summary metrics emitted.
- `MEMBER_OF` edge metadata in `unstructured_only` mode:
  - `method` — the actual strategy used: `"normalized_exact"`, `"abbreviation"`, `"fuzzy"`, or `"label_cluster"` (singleton fallback).
  - `score` — `1.0` for deterministic assignments (`label_cluster`, `normalized_exact`), `0.75` for `abbreviation`, actual SequenceMatcher ratio for `fuzzy`.
  - `status` — `"accepted"` for deterministic assignments (`label_cluster`, `normalized_exact`); `"provisional"` for probabilistic assignments (`abbreviation`, `fuzzy`) to distinguish high-confidence memberships from those warranting downstream review.
  - `resolver_version` — value of `_CLUSTER_VERSION` constant.
  - `run_id` — the run that created the membership link.

### What is not yet implemented (Phases 2–5)

- `hybrid_additive` explicit mode flag on `run_entity_resolution()`.
- Advanced fuzzy lexical or semantic similarity clustering (Phase 2 resolution methods).
- `ALIGNED_WITH` edge creation from `ResolvedEntityCluster` → `CanonicalEntity` (Phase 3).
- Cluster-aware retrieval and Q&A traversal (Phase 4).
- Review-required threshold bands and audit workflow (Phase 5).