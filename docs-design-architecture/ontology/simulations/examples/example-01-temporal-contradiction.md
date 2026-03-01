# Example 01 — Temporal Ambiguity + Contradiction Coexistence + Revision Auditability

**Illustrative only; non-binding; does not prescribe implementation or workflow.**

## Simulation Name

Temporal overlap dispute with later supersession evidence

## Scenario Statement (Conceptual Narrative)

Two attributed claims describe whether Entity A held Relationship R to Entity B during 2021.

- Claim C1 (Source S1) asserts the relationship held during 2021-01 to 2021-12.
- Claim C2 (Source S2) asserts the relationship ended in 2020-09.
- Later, Claim C3 (Source S3) provides evidence suggesting the relationship resumed in 2021-06.

The simulation stresses whether the ontology can represent contradiction and revision over time without collapsing all claims into a single eternal fact.

## Semantic Primitives Involved

- Entity: A, B
- Relationship: R
- Claim: C1, C2, C3
- Evidence: artifacts associated with S1, S2, S3
- Provenance: source attribution and derivation context for each claim
- Time: valid-time intervals and record-time sequence
- Confidence: alleged/disputed/revised statuses across claims

## Assumptions (Explicit)

1. Claims are epistemic units and may conflict.
2. Valid-time and record-time are conceptually distinct.
3. Revision events do not erase prior claim states.
4. Derived interpretation remains candidate unless review-governed publication conditions are met.

## Stress Category Tags

- temporal-ambiguity
- contradiction-coexistence
- supersession-non-erasure
- inference-boundary

## Invariants Tested (map to v0.1 docs)

- Semantic Invariant #3: Temporal capability
- Semantic Invariant #5: Coexistence of contradiction
- Semantic Invariant #8: Replaceability thought test
- Epistemic Invariant #1: Attribution required
- Epistemic Invariant #4: Revision auditability
- Epistemic Invariant #6: Replaceability pass condition

References:

- [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)
- [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)

## Evaluation Checklist Results

- [x] **Replaceability:** Scenario meaning does not depend on storage/API/UI form.
- [x] **Provenance/lineage visibility:** Each claim remains attributable to source context.
- [x] **Temporal integrity:** Valid-time disagreement is explicit; record-time of revisions remains distinct.
- [x] **Contradiction coexistence:** C1 and C2 coexist as conflicting attributed claims.
- [x] **Non-escalation:** No motive, intent, or wrongdoing is inferred from contradiction alone.
- [x] **Auditability:** C3 revision context is additive; prior states remain inspectable.
- [x] **Candidate vs authoritative boundary:** Any synthesized conclusion remains candidate until explicitly reviewed/published.

## Pressure Points Found

1. **Temporal collapse risk:** If valid-time and record-time are merged, contradiction appears unrecoverable.
2. **Hidden supersession risk:** If C3 is treated as replacement rather than revision event, audit trail is lost.
3. **Interpretive escalation risk:** Reviewers may over-read contradiction as evidence of bad intent without supporting claims.

## Risk Notes

- **Defamation-by-ordering risk:** presenting “latest claim wins” as truth can overstate certainty.
- **Authority laundering risk:** derived summaries may mask source disagreement.
- **Privacy/reputational sensitivity:** unresolved identity context (if present) can amplify harm from premature merge conclusions.

## Resolution Options (Semantic-Level Only)

1. Keep conflicting claims concurrently representable with explicit attribution and time context.
2. Treat supersession as revision state transition, not deletion/erasure of prior claim states.
3. Require explicit distinction between sourced claims and derived synthesis.
4. Preserve non-escalation language in summaries of contradictory state.

## Follow-ups / Open Questions

1. Should temporal ambiguity guidance add stronger language for partially bounded intervals?
2. Should invariant text explicitly warn against “latest-record-time overrides valid-time” reasoning?
3. Should governance language tighten what constitutes publishable synthesis under unresolved contradiction?
