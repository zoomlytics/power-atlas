# Demo Reset Scope

This document externalizes the current demo-owned graph wipe contract that is
still executed by `python -m demo.reset_demo_db --confirm`.

It exists so the operational reset scope is visible under `neo4j/` instead of
being defined only inside runtime/demo code.

## Current reset-owned node labels

The current demo reset removes all nodes with these labels and all attached
relationships via `DETACH DELETE`:

- `Document`
- `Chunk`
- `CanonicalEntity`
- `Claim`
- `Fact`
- `Relationship`
- `Source`
- `ExtractedClaim`
- `EntityMention`
- `UnresolvedEntity`
- `ResolvedEntityCluster`

## Current reset-owned relationship cleanup

As a defense-in-depth / historical cleanup step, the reset also explicitly
removes stale pre-v0.3 participation edge types when present:

- `HAS_SUBJECT`
- `HAS_OBJECT`
- `HAS_SUBJECT_MENTION`
- `HAS_OBJECT_MENTION`

These are retained only as cleanup targets for old demo graphs. They are not
part of the current supported graph model.

## Current reset-owned index drop scope

The reset currently drops the demo vector index named:

- `demo_chunk_embedding_index`

That index contract is also defined operationally at
`neo4j/indexes/demo_chunk_embedding_index.cypher`.

## Source-of-truth note

Today the executable reset behavior still lives in `demo/reset_demo_db.py` and
its tests. This document is an externalized operational inventory, not yet an
independent reset runner.

If the reset contract changes, keep this document aligned with:

- `demo/reset_demo_db.py`
- `neo4j/indexes/demo_chunk_embedding_index.cypher`
- `demo/config/pdf_simple_kg_pipeline.yaml`
- `src/power_atlas/contracts/pipeline.py`