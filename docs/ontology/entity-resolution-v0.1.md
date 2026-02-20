# Power Atlas — Entity Resolution Philosophy (v0.1, Draft)

**Status:** Experimental  
**Audience:** Contributors, architects, reviewers  
**Scope:** Semantic Core boundary protection (identity, disambiguation, merge/split posture)  
**Review labels:** documentation, ontology

## 1) Purpose

- Define *entity resolution* as a **conceptual / semantic capability boundary** in Power Atlas (not an implementation).
- Clarify how resolution decisions relate to **claims, evidence, provenance, time, and confidence**.
- Establish a v0.1 default posture that reduces harm from conflation while preserving auditability.

**In scope:** philosophy, principles, conceptual requirements, boundary cases, risks.  
**Out of scope:** schema fields, storage patterns, algorithms, operational workflows.

## 2) Context & Alignment (v0.1)

This document extends and remains consistent with:

- Architecture Overview v0.1: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
- Ontology Charter v0.1: [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md)
- Provenance & Confidence Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Epistemic Invariants v0.1: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)

Entity resolution in v0.1 is epistemic: merge/split/link decisions are claim-mediated, attributed, evidence-linked, and revisable.

## 3) Definitions (Conceptual, Non-prescriptive)

- **Entity**: A distinguishable participant in structural modeling (per Ontology Charter v0.1).
- **Record / representation / mention**: A sourced reference to an entity.
- **Identity / equivalence**: An assertion that two or more records refer to the same real-world entity under stated context.
- **Identifier**: A handle, registry ID, account, or similar token that serves as evidence for identity, not identity by default.
- **Resolution claim**: An attributed, auditable identity assertion.
- **Resolution actions**:
  - **Link**: Two records may refer to the same entity.
  - **Merge**: Treat records as one entity for a stated purpose.
  - **Split**: Undo or avoid conflation.
  - **Defer**: Explicitly choose not to resolve yet.

## 4) Guiding Principles (v0.1)

1. **Claim-mediated identity**
   - Identity/equivalence assertions are claims: attributable, evidence-linked, time-scoped, and revisable.
2. **Conservative default posture**
   - Prefer *link-with-uncertainty* over irreversible merge when evidence is weak or ambiguous.
3. **No silent merges**
   - Consolidation decisions must be attributable, explainable, and auditable.
4. **Non-erasure / auditability**
   - Resolution revisions must preserve prior states, lineage, and rationale.
5. **Coexistence of contradiction**
   - Competing identity claims may coexist when properly attributed and qualified.
6. **Time-awareness**
   - Identity may shift over time (renames, relocations, identifier reuse); same string does not imply same entity for all time.
7. **Privacy and harm minimization**
   - Do not increase re-identification risk through aggressive cross-context merging without strong, attributable evidence.
8. **Replaceability**
   - Resolution semantics must remain stable across storage, graph, API, and UI changes.

## 5) Minimum Conceptual Requirements (v0.1)

Each identity-related assertion must be able to express:

- **Attribution:** who/what asserted the resolution (source, agent, process).
- **Evidence linkage:** supporting artifacts, or explicit "evidence absent/unknown."
- **Temporal context:** when the assertion applies (valid time and/or record time where meaningful).
- **Confidence / epistemic status:** verified/alleged/inferred/disputed/unknown (conceptually).
- **Revision trace:** supersession/retraction without erasing earlier resolution states.
- **Contestability:** ability to represent challenges/counterclaims and why they exist.

## 6) Entity Classes & Resolution Sensitivities (Illustrative)

- People
- Organizations
- Addresses / locations
- Accounts / identifiers
- Assets / properties (e.g., parcels, vessels, aircraft)
- Documents / source artifacts
- Events (e.g., filings, meetings, incorporations)
- Roles / positions
- Financial instruments / transactions (if/when modeled)

(These are illustrative categories encountered in v0.1, not a finalized ontology taxonomy.)

## 7) Boundary Cases (Illustrative, Narrative)

1. **Common-name collision (people):** Similar names with partial overlap should produce a link hypothesis claim, not immediate merge.
2. **Org naming / subsidiary confusion:** Closely named entities across datasets may remain separate while equivalence claims coexist with provenance.
3. **Identifier ambiguity:** Shared inboxes or reused handles are evidence signals, not merge decisions by default.
4. **Temporal identity drift:** Renames, relocations, and address reuse require time-qualified reasoning.
5. **Adversarial/deceptive records:** Shell entities and obfuscation require explicit uncertainty and defer/link options over forced resolution.

## 8) Risk and Ethics Considerations

- **False positive merges (conflation):** reputational harm, incorrect network links, and misleading downstream analysis.
- **False negative splits (fragmentation):** under-linking that hides structural relationships and inflates duplicate metrics.
- **Privacy / safety risk:** unintended re-identification via cross-context linkage.
- **Provenance integrity risk:** collapsing multiple sources into one apparent "voice" without preserving attribution history.

## 9) Non-Goals (v0.1)

This document does **not**:

- prescribe algorithms (embeddings, clustering, rules engines, etc.),
- prescribe schema fields, table/edge patterns, or canonical storage representations,
- define operational workflows, moderation policies, or reviewer queues,
- mandate a single "truth identity" or force resolution in ambiguous cases,
- define performance/latency targets for resolution.

## 10) Open Questions (v0.2+)

- Should link/merge thresholds vary by entity class or risk level?
- Do we need a semantic concept for sensitive-entity handling?
- How should cross-context linking be constrained to minimize harm?
- How should multiple competing resolution assertions from sources/agents be compared?
- What are the first infrastructure-independent invariants/tests for resolution semantics?

## Closing Note (Draft Status)

Entity resolution in v0.1 is defined as a semantic philosophy and capability boundary. It is intentionally implementation-agnostic so future experiments can evolve without redefining what identity assertions *mean* in the Semantic Core.
