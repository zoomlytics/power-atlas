# Current Demo Constraints Posture

This note documents the current constraint posture for the local candidate-graph
workflow.

At the current checkpoint, the repo does **not** define a stable checked-in
demo-owned Neo4j constraint asset under `neo4j/constraints/`, and the local
candidate database is expected to function without an applied demo-specific
constraint bundle.

## Current accepted posture

- there is no repo-owned Cypher file today that creates the current demo graph
  constraints
- the maintained local candidate-graph workflow relies on fixture inputs,
  runtime ingest behavior, and the documented vector-index contract rather than
  on an externalized constraint bundle
- `demo.reset_demo_db` preserves constraints that may already exist in the
  database unless they are explicitly named as demo-owned reset targets
- the current local Neo4j baseline may legitimately report zero matching
  demo-relevant constraints

## Evidence for this posture

- the local database can return no rows for `SHOW CONSTRAINTS` while the demo
  pipeline and retrieval workflow still operate correctly
- runtime/demo surfaces currently document index behavior and reset scope, but
  they do not expose a parallel checked-in constraint-creation contract
- `demo/README.md` explicitly treats reset behavior as preserving indexes and
  constraints not named by the reset workflow

## Operational implication

For the current local/test workflow, constraints are a future graph-ops concern
rather than an active required setup step. The execution order documented in
`neo4j/README.md` still reserves a slot for constraints because that is the
correct long-term place for them, but there is no concrete demo-owned
constraint asset to apply today.

## Future promotion rule

Add versioned files under `neo4j/constraints/` only when both are true:

- a stable demo- or package-owned constraint contract has been identified
- that contract is intended to be applied deliberately as part of graph setup,
  rather than remaining an implicit byproduct of runtime behavior or manual
  experimentation

Until then, this folder should document the absence of a checked-in constraint
bundle rather than pretend one exists.