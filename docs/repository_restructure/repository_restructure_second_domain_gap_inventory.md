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
  `power_atlas.structured_ingest_runner`.

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

This does **not** yet solve the next blocker, which is the graph shape that the
structured ingest path writes after those files are read.

### 2. Structured ingest writes a fixed Power Atlas graph shape

`src/power_atlas/structured_ingest_writes.py` writes a fixed graph model built
around `CanonicalEntity`, `Fact`, `Relationship`, and `Claim`, using fixed edge
names such as `ABOUT`, `TARGETS`, `SUPPORTED_BY`, `ASSERTED_IN`, and
`CITED_FROM`.

This is not just a file-schema issue. Even if alternate CSV headers were
accepted, the write path would still project them into the current Power Atlas
canonical graph vocabulary.

For a real second-domain pilot, this surface needs an explicit graph-shape
contract or policy boundary rather than only alternate input files.

### 3. Entity resolution has a narrow policy seam but a fixed graph model

`src/power_atlas/entity_resolution_entrypoint.py` already forwards
`request_context.policies.entity_type_normalization`, which means the package
has a small existing policy seam for normalizing entity types.

That seam is materially narrower than the retrieval seam.

The owning query and write modules still hardcode the current graph model:

- `src/power_atlas/entity_resolution_queries.py` matches
  `EntityMention`, `CanonicalEntity`, and `ResolvedEntityCluster`, and measures
  alignment through `MEMBER_OF` and `ALIGNED_WITH`,
- `src/power_atlas/entity_resolution_writes.py` writes
  `RESOLVES_TO`, `MEMBER_OF`, `CANDIDATE_MATCH`, and `ALIGNED_WITH` against the
  same fixed labels,
- `src/power_atlas/entity_resolution_entrypoint.py` still resolves the
  effective dataset through the current dataset-root path.

This means the second domain cannot yet swap in an alternate canonical node or
cluster vocabulary without changing shared implementation modules.

### 4. Canonical alignment strategy is fixed to exact label/alias matching

`src/power_atlas/entity_resolution_alignment.py` currently aligns clusters to
canonical entities by exact normalized label or alias lookup.

That may be acceptable for the current domain, but it is not a configurable
alignment strategy seam. A market/trade pilot may need issuer/security-specific
matching rules, symbol handling, or event-aware disambiguation.

At the moment, that would require editing shared implementation code rather than
supplying an alternate package contract.

## What is not a blocker at this checkpoint

The gap inventory should stay narrow and not overstate missing work.

The following are **not** currently the first blockers:

- retrieval ontology labels and relationships,
- retrieval prompt/template selection,
- retrieval traversal defaults,
- package-owned retrieval request-context consumption.

Those are already covered by the retrieval policy seam and the market/trade
pilot proof.

## Recommended extraction order

The next extraction slices should proceed in this order:

1. define the graph-shape contract for structured ingest writes so alternate
   domains are not forced into the current canonical graph vocabulary,
2. widen entity resolution from entity-type normalization only into an explicit
   graph-model and alignment-policy seam,
3. only then decide whether the second-domain pilot warrants a broader shared
   kernel namespace split.

## Minimum acceptance for the next slice

The next reuse slice should be considered sufficient only if it does one of the
following:

1. introduces a package-owned structured-schema contract that a second-domain
   pilot can customize without copying Power Atlas ingest/runtime code, or
2. introduces a package-owned entity-resolution graph/alignment contract that
   makes the current fixed labels and relationships configurable.

The first half of item 1 is now complete for file/schema assumptions. The next
meaningful reduction is the structured graph-shape contract.