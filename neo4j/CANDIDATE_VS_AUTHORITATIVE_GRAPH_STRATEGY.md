# Candidate vs Authoritative Graph Strategy

This document records the current accepted graph-environment posture for the
repo.

It is intentionally narrow. It describes what the checked-in local workflow
actually supports today, without inventing a larger deployment model that the
repo does not yet implement.

## Current Accepted Posture

At the current checkpoint, the repo supports one explicit graph posture:

- a single local Neo4j service provisioned by `docker compose up -d neo4j`,
- a single active local database selected by `NEO4J_DATABASE` when provided,
  otherwise Neo4j's default `neo4j` database,
- reset-driven demo validation and iteration through
  `python -m demo.reset_demo_db --confirm`.

Within that posture, the checked-in local graph should be treated as a
**candidate graph**, not as an authoritative production graph.

The repo does **not** currently provision or automate a separate authoritative
graph environment.

## Candidate Graph Definition

In the current repo-owned workflow, a candidate graph is the graph used for:

- local development,
- manual validation,
- demo pipeline runs,
- retrieval experiments,
- restructure safety-harness verification,
- repeatable reset-and-rerun workflows.

Operational properties of the current candidate graph are:

- it is created against the local compose-managed Neo4j service,
- it is populated by the `demo/` pipeline and related manual workflows,
- it may be reset destructively through `demo.reset_demo_db`,
- it is expected to be reproducible from fixtures, docs, and checked-in
  operational assets,
- it is the only graph posture that the repo currently documents end to end.

Today, this candidate graph is logically separated by workflow intent rather
than by a second compose service, a second checked-in database, or a promotion
pipeline.

## Authoritative Graph Definition

An authoritative graph is any longer-lived graph environment whose data should
not be cleared by the repo's reset-driven local workflow.

The current repo does not define:

- a second authoritative Neo4j service,
- an authoritative database name,
- a promotion pipeline from candidate to authoritative state,
- automated synchronization rules,
- an approved production reset contract.

That means authoritative graph handling remains a future operational concern,
not an active checked-in repo workflow.

## Reset Semantics

The reset path in `demo/reset_demo_db.py` is part of the candidate-graph
workflow only.

Use it when you are intentionally clearing the local demo-owned graph so you
can rerun ingest, extraction, resolution, or validation from a known clean
state.

Do **not** treat this reset contract as a generic graph lifecycle tool for any
authoritative environment.

The current executable reset scope is documented in:

- `neo4j/diagnostics/demo_reset_scope.md`
- `neo4j/diagnostics/check_demo_reset_scope.cypher`

## Database and Environment Interpretation

For current local development, the repo assumes:

- one compose-managed Neo4j server,
- one active working database selected by settings,
- one resettable candidate graph within that environment.

If `NEO4J_DATABASE` is unset, current docs and runtime behavior default to the
standard `neo4j` database. If it is set, the repo treats that as the active
database for the same candidate-graph workflow; it does not thereby create a
distinct authoritative posture.

In other words, the current distinction is:

- **candidate graph**: the repo-owned local/resettable workflow,
- **authoritative graph**: not yet implemented as a checked-in operational
  environment.

## Promotion Semantics

Promotion from candidate to authoritative state is not currently automated or
defined in the repo.

Until a broader operational model exists, the correct interpretation is:

- the repo proves candidate-graph behavior locally,
- accepted run evidence is captured through manifests and validation artifacts,
- any future authoritative graph promotion model must be documented explicitly
  before being treated as part of the active workflow.

## Implications for Phase 6

Decision 7 required the candidate-vs-authoritative distinction to be explicit
before Neo4j operationalization could be considered complete.

At the current checkpoint, that requirement is satisfied at the documentation
level by this rule:

- the checked-in repo owns and documents a local candidate-graph workflow,
- the repo does not yet claim a checked-in authoritative graph workflow.

This closes the ambiguity without overstating the maturity of the operational
model.

## Future Evolution

If the repo later introduces a broader graph-ops model, revisit this document
first and update it before changing workflow defaults.

Likely future options include:

- physical separation across databases or services,
- a promotion path from candidate to authoritative state,
- environment-specific reset restrictions,
- migration tooling that applies constraints/indexes/seeds differently by
  environment.

Until then, prefer the simplest accurate rule: the repo currently supports one
documented local candidate-graph workflow and no checked-in authoritative graph
workflow.