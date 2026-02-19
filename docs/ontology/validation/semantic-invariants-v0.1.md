# Semantic Invariants for Testing (v0.1)

This document is a validation instrument derived from the Ontology Charter v0.1 at [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md).

It does not redefine ontology primitives. It defines invariant checks that should hold independent of storage engine, API, serialization format, and UI.

## Invariants

1. **Claim attribution completeness** — claims are provenance-linked and source-identifiable.
2. **Relationship is not interpretation** — structural connections do not encode motive or legal judgment.
3. **Temporal capability** — claims/relationships can be interval or as-of qualified.
4. **Confidence representability** — claims can express verified/alleged/inferred/disputed status.
5. **Coexistence of contradiction** — conflicting attributed claims may coexist.
6. **Primitive vs derived separation** — removing metrics does not alter structural claims.
7. **Provenance traceability** — origin, ingestion/derivation path, and revision timing are answerable.
8. **Replaceability thought test** — changing storage/API/UI does not change primitive meanings.
