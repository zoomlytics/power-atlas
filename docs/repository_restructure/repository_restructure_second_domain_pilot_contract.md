# Second-Domain Pilot Contract

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-12  
**Related documents:**
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `README.md`

## Purpose

This document defines the minimum proof target for the next reuse checkpoint:
not a full second application, but a constrained second-domain pilot that is
strong enough to validate whether the current shared seams are sufficient for a
real multi-app kernel direction.

The repo already has:

- installable package structure,
- package-owned runtime/bootstrap/context seams,
- a public backend facade,
- package-level proof that retrieval policy can be forwarded through package
  request-context adapters,
- a package-only retrieval policy consumer example outside `demo/`.

The missing proof is no longer “can a caller inject a different retrieval
policy?” The missing proof is “what additional seams beyond retrieval policy are
required before a second domain can use the same runtime without copying Power
Atlas modules?”

## Pilot defined in this checkpoint

The pilot target for the next phase is a **market/trade research** domain.

This domain is intentionally chosen because it is close enough to the current
research-runner shape to reuse the same runtime ideas, but different enough to
stress the parts of the package that are still Power Atlas-specific.

### Example concepts

- `Security`
- `Exchange`
- `Filing`
- `CalendarEvent`
- `EarningsCall`
- `RegulatoryBody`

### Example relationships

- `LISTED_ON`
- `FILED_WITH`
- `REPORTS_AT`
- `GUIDES_ON`
- `AFFECTED_BY_EVENT`

These are illustrative only. The pilot does not require implementing this full
ontology yet. It does require using this domain shape to test whether the
shared runtime can host a materially different policy pack.

## Minimum proof surface

The second-domain pilot does **not** need to implement the entire Power Atlas
pipeline. The minimum acceptable proof is narrower.

### Required

- a second-domain retrieval policy pack with:
  - alternate ontology labels/relationships,
  - alternate retrieval prompt/template,
  - alternate default traversal settings when needed
- one package-owned consumer path that uses that second-domain retrieval policy
  without importing `demo.*`
- one explicit statement of what the pilot still cannot customize without more
  extraction work

### Not required yet

- a live second-domain Neo4j dataset,
- a production-ready second frontend or second API app,
- a full structured ingest pipeline,
- a full benchmark suite,
- a new published package namespace.

## Seams this pilot is expected to validate

The pilot should tell us whether the current reusable-core direction is real or
whether more Power Atlas-specific assumptions remain hidden in shared modules.

### 1. Retrieval policy seam

This seam should already be the strongest current candidate.

The pilot must prove that a second-domain retrieval policy can control:

- ontology labels/relationships used for retrieval query construction,
- retrieval prompt/template selection,
- traversal defaults such as graph-expansion or cluster-aware defaults,
- package-owned request-context consumer behavior.

### 2. Prompt-pack seam

The pilot should identify whether retrieval prompt customization is sufficient
through `RetrievalPolicy`, or whether additional Power Atlas-specific prompt
assumptions remain coupled elsewhere.

The pilot does not need to solve all prompt abstraction. It does need to expose
where the current prompt surface stops being reusable.

### 3. Structured-schema seam

The pilot should not implement full alternate structured ingest, but it must
explicitly classify this as a follow-up seam if the second domain would require
different source rows, identifiers, or canonical alignment inputs.

For this pilot, an explicit documented gap is acceptable. Silent assumption is
not.

### 4. Entity-resolution policy seam

The pilot should determine whether alternate retrieval policy alone is enough,
or whether the second domain immediately runs into Power Atlas-specific cluster
and canonical-alignment assumptions.

Again, the pilot may stop at classification rather than implementation, but it
must make the dependency visible.

## Deliverables for this pilot checkpoint

The next acceptable second-domain pilot slice should produce all of the
following:

1. a package-owned second-domain retrieval policy example or module,
2. a focused executable proof that runs without importing `demo.*`,
3. a short gap inventory naming the first additional seams required beyond
   retrieval policy,
4. confirmation that no shared runtime module had to be copied to support the
   pilot.

## Acceptance criteria

This pilot should be considered successful only if:

- the second-domain proof uses package-owned shared runtime surfaces,
- the proof does not rely on monkeypatching implementation modules to inject
  the alternate policy,
- the proof does not copy current Power Atlas retrieval/runtime modules into a
  second app shell,
- the resulting gap inventory is concrete enough to sequence the next seam
  extraction slices.

## Failure conditions

This pilot should be considered unsuccessful if any of the following are true:

- the alternate domain works only by rewriting or copying retrieval runtime
  modules,
- the proof bypasses package-owned context/policy surfaces,
- the second domain requires a broad plugin system before even a constrained
  retrieval proof works,
- the work only renames Power Atlas concepts without proving a materially
  different domain shape.

## Immediate next sequence

The next bounded steps should proceed in this order:

1. define one package-owned market/trade retrieval policy pack,
2. add one executable package-only consumer proof using that pack,
3. record the first additional seam gaps the proof exposes,
4. only then decide whether to widen extraction into structured-schema or
   entity-resolution policy seams.

## Non-goals

This pilot contract does **not** authorize:

- announcing a generic package,
- creating a full second app repository,
- extracting every domain policy seam at once,
- replacing Power Atlas-specific docs with generic wording prematurely.