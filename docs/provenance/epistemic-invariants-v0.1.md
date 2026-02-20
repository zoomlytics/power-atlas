# Provenance & Confidence — Epistemic Invariants (v0.1, Companion Draft)

This companion document defines testable epistemic invariants aligned to:

- Provenance & Confidence Model Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)

It is implementation-agnostic and does not introduce schema, API, or storage requirements.

## Invariants

1. **Attribution required** — Every claim is attributable to source origin, derivation process, asserting agent, or a documented combination.
2. **Derived lineage visibility** — Every derived claim exposes traceable lineage to its inputs and derivation context.
3. **Coexistence of contradiction** — Conflicting attributed claims may coexist without forced resolution.
4. **Revision auditability** — Confidence revision does not erase prior claim provenance or epistemic state history.
5. **Structural independence** — Removing or changing confidence metadata does not alter structural meaning.
6. **Replaceability pass condition** — Replacing storage/API/UI does not change provenance or confidence semantics.
