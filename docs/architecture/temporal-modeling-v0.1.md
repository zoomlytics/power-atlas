# Power Atlas — Temporal Modeling Principles (v0.1, Draft)

**Status:** Experimental  
**Audience:** Contributors, architects, reviewers  
**Scope:** Semantic Core temporal capability boundaries

## 1) Purpose

This document defines temporal modeling principles for Power Atlas as an implementation-agnostic Semantic Core capability.

It extends and remains consistent with:

- Architecture Overview v0.1: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
- Ontology Charter v0.1: [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md)
- Provenance & Confidence Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)
- Epistemic Invariants v0.1: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)

This is a preliminary v0.1 boundary document, not a schema or implementation specification.

## 2) Temporal Scope in v0.1 (Conceptual Forms)

Power Atlas claims and relationships must be able to represent:

1. **Point-in-time assertions** ("as-of" semantics).
2. **Intervals / durations** ("valid from ... to ...").
3. **Open intervals** (known start with unknown end, known end with unknown start, or otherwise partially bounded).
4. **Record time** (when the system learned, recorded, asserted, or ingested the claim).
5. **Revision time / history** (how claim state changes over time without erasing prior states).

A useful lens is the distinction between **valid time** (when a claim is asserted to hold) and **record time** (when the system knew/recorded it). In v0.1, this is a capability requirement, not a field prescription.

## 3) Guiding Principles

1. **No eternal facts**
   - Structural statements are assumed time-scoped or time-capable, even when exact time is unknown.

2. **Time applies to claims (epistemics), not raw structure by default**
   - Relationships are not treated as universally true outside a claim context.

3. **Coexistence across time**
   - Conflicting claims may coexist when they differ by source, valid-time context, record-time context, or confidence state.

4. **Uncertainty is representable**
   - Unknown, approximate, disputed, or bounded temporal context must be representable without false precision.

5. **Auditability / non-erasure**
   - Revisions (e.g., supersession, retraction, confidence change) preserve prior claim states and their timestamps.

6. **Replaceability**
   - Temporal semantics must remain stable if storage, graph model, API, or UI choices are replaced.

## 4) Minimum Conceptual Temporal Requirements (v0.1)

Each claim must be able to express:

- **Valid-time context**: when the claim is asserted to hold (as-of or interval, including open intervals).
- **Record-time context**: when it was recorded, ingested, or asserted by the system/process.
- **Unknown / approximate / bounded time**: temporal uncertainty without forced exact timestamps.
- **Supersession / revision semantics**: that a claim state was revised, superseded, or retracted at time T without erasing prior states.

These are capability requirements only; this document does not define mandatory fields.

## 5) Uncertainty and Boundary Cases (Illustrative)

Examples are narrative and non-prescriptive:

- **Interval validity**: "Person A held board membership in Org B from 2018 to 2021."
- **Conflicting as-of claims**: Source X reports ownership stake as-of 2020-06; Source Y reports a different stake as-of 2021-01. Both claims coexist with attribution and time context.
- **Revision history**: A claim initially marked "alleged" has confidence increased after review at time T; prior epistemic state remains auditable.
- **Partial/approximate timing**: "Start date unknown, ended in 2017" or "circa 2019" without forcing exact day-level precision.

## 6) Alignment to Existing v0.1 Invariants

This document reinforces:

- **Temporal capability** from semantic invariants (claims/relationships are as-of or interval capable).
- **Revision auditability** from epistemic invariants (revision does not erase prior claim states).
- **Coexistence of contradiction** with attribution and temporal qualification.
- **Semantic Core independence** from implementation choices.

## 7) Non-Goals (v0.1)

This document does **not**:

- prescribe schema fields, graph edge patterns, or database structures,
- prescribe storage/index/query frameworks,
- prescribe API payloads or workflow engines,
- attempt to enumerate every temporal logic edge case.

## Closing Note (Draft Status)

Temporal modeling in v0.1 is defined as a semantic capability boundary. It is intentionally implementation-agnostic so future technical experiments can evolve without redefining temporal meaning.
