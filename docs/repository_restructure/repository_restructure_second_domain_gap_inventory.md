# Second-Domain Gap Inventory

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-12  
**Related documents:**
- `docs/repository_restructure/repository_restructure_second_domain_pilot_contract.md`
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`

## Purpose

This document records the first additional seams exposed by the constrained
market/trade pilot after the retrieval-policy proof was completed.

The retrieval seam is now strong enough to support a package-owned alternate
policy pack and a package-only consumer example. The next question is not
whether alternate retrieval policy fits the current package boundary. The next
question is which adjacent surfaces remain Power Atlas-shaped once a second
domain needs structured ingest or canonical alignment.

## Current checkpoint

The following second-domain proof now exists:

- `src/power_atlas/policy_packs/market_trade.py` defines a package-owned
  alternate retrieval policy pack,
- `examples/market_trade_retrieval_policy_consumer.py` proves the package-owned
  retrieval request-context adapter can consume that pack without importing
  `demo.*`,
- `src/power_atlas/contracts/structured.py` now defines a package-owned
  `StructuredSchemaContract`, and the package structured-ingest path accepts it
  through `power_atlas.structured_ingest_entrypoint` and
  `power_atlas.structured_ingest_runner`,
- `src/power_atlas/contracts/structured.py` now also defines a package-owned
  `StructuredGraphShapeContract`, and the package structured-ingest write path
  accepts it through `power_atlas.structured_ingest_writes`,
  `power_atlas.structured_ingest_runner`, and the live Neo4j adapter.
- `src/power_atlas/contracts/resolution.py` now defines a package-owned
  `EntityResolutionGraphContract`, and the package entity-resolution query,
  write, runtime, and entrypoint paths accept it through
  `power_atlas.entity_resolution_queries`,
  `power_atlas.entity_resolution_writes`,
  `power_atlas.entity_resolution_runner`, and
  `power_atlas.entity_resolution_entrypoint`,
- `src/power_atlas/contracts/resolution.py` now also defines a package-owned
  `EntityResolutionCanonicalLookupContract`, and the package canonical fetch,
  lookup-table build, mention resolution, cluster alignment, runtime, and
  entrypoint paths accept it through
  `power_atlas.entity_resolution_queries`,
  `power_atlas.entity_resolution_resolver`,
  `power_atlas.entity_resolution_alignment`,
  `power_atlas.entity_resolution_runner`, and
  `power_atlas.entity_resolution_entrypoint`,
- `src/power_atlas/contracts/resolution.py` now also defines a package-owned
  `EntityResolutionAlignmentContract`, and the package cluster-alignment,
  runtime, and entrypoint paths accept it through
  `power_atlas.entity_resolution_alignment`,
  `power_atlas.entity_resolution_runner`, and
  `power_atlas.entity_resolution_entrypoint`.

That proof is sufficient to close the question of whether a second-domain
retrieval pack can ride the current policy seam.

It is not sufficient to claim that the reusable core can already support a
second domain end-to-end.

## First seam gaps beyond retrieval policy

### 1. Structured-schema contract is extracted, but only at the file/schema layer

`src/power_atlas/contracts/structured.py` no longer has to be consumed only as a
fixed constant set. The package now exposes `StructuredSchemaContract`, which
externalizes:

- structured file names,
- column headers,
- identifier patterns,
- predicate-label assumptions,
- allowed value types.

That reduces the first second-domain blocker: a market/trade pilot can now
adopt alternate structured file names and alternate identifier formats through a
package-owned contract rather than by editing lint/runtime code.

This no longer blocks the second-domain pilot at the file/schema layer.

### 2. Structured graph-shape contract is extracted for ingest writes

`src/power_atlas/structured_ingest_writes.py` no longer has to be consumed only
through the fixed Power Atlas labels and relationship types. The package now
exposes `StructuredGraphShapeContract`, which externalizes:

- source node label,
- entity/fact/relationship/claim labels,
- ingest relationship types such as asserted-in, cited-from, about, targets,
  supported-by, subject, and object.

That reduces the second second-domain blocker: alternate structured inputs no
longer have to be projected into the exact Power Atlas canonical ingest graph
shape.

This still does **not** solve the next blocker, which is entity-resolution and
canonical alignment over a fixed graph model.

### 3. Entity-resolution graph contract is extracted, and canonical lookup is now configurable

`src/power_atlas/entity_resolution_entrypoint.py` already forwards
`request_context.policies.entity_type_normalization`, which means the package
has a small existing policy seam for normalizing entity types.

That seam is still narrower than the retrieval seam, but the graph vocabulary
is no longer fully hardcoded.

The package now exposes `EntityResolutionGraphContract`, which externalizes:

- mention/canonical/cluster labels,
- `RESOLVES_TO`, `MEMBER_OF`, `CANDIDATE_MATCH`, and `ALIGNED_WITH`
  relationship types,
- entity-resolution graph coverage queries and alignment coverage queries.

That reduces the next second-domain blocker: alternate domains no longer have
to reuse the exact Power Atlas entity-resolution graph vocabulary to run the
package-owned resolution flow.

`EntityResolutionCanonicalLookupContract` now externalizes:

- canonical id/run/name/aliases field names,
- alias delimiters,
- qid-pattern matching,
- exact-match method names and confidence values,
- the unresolved-method label used when exact lookup misses.

That reduces the next second-domain blocker again: alternate domains no longer
have to reuse the exact Power Atlas canonical property names or the exact `Q...`
identifier convention to participate in the package-owned lookup flow.

`EntityResolutionAlignmentContract` now externalizes:

- the ordered alignment steps,
- which lookup table each step consults,
- how candidate cluster keys are derived for each step,
- emitted method/score/status metadata per step.

That reduces the remaining blocker again: alternate domains can now change the
package-owned alignment strategy without editing shared alignment code, as long
as the strategy can be expressed in terms of lookup-table steps.

### 4. Dataset selection is still fixed to the current package flow

`src/power_atlas/entity_resolution_entrypoint.py` still resolves the effective
dataset through the current dataset-root path, and
`src/power_atlas/entity_resolution_runtime.py` still assumes canonical lookup is
performed against dataset-scoped canonical rows selected through the current
dataset-resolution flow.

That means a second domain can now rename both the graph vocabulary and the
canonical lookup field surface, but it still cannot replace the dataset
selection strategy itself without editing shared implementation code.

## What is not a blocker at this checkpoint

The gap inventory should stay narrow and not overstate missing work.

The following are **not** currently the first blockers:

- retrieval ontology labels and relationships,
- retrieval prompt/template selection,
- retrieval traversal defaults,
- structured file names, headers, identifier patterns, and value-type rules,
- structured ingest write labels and relationship types,
- entity-resolution labels and relationship types,
- canonical id/run/name/aliases field names,
- ordered alignment steps and emitted alignment metadata,
- exact-match method names and confidence defaults,
- package-owned retrieval request-context consumption.

Those are already covered by the retrieval policy seam and the market/trade
pilot proof plus the structured ingest contracts.

## Recommended extraction order

The next extraction slices should proceed in this order:

1. decide whether dataset selection should also become an explicit package
  contract,
2. only then decide whether the second-domain pilot warrants a broader shared
  kernel namespace split.

## Minimum acceptance for the next slice

The next reuse slice should be considered sufficient only if it decides whether
dataset selection should become a package-owned contract rather than remaining
tied to the current dataset-root resolution path.

The structured ingest layer, entity-resolution graph vocabulary, and canonical
lookup and alignment strategy surfaces are now materially improved. The next
meaningful reduction is dataset selection if the second-domain pilot requires it.