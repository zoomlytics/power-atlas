# Neo4j Operational Assets

This directory is the repo-owned home for Neo4j operational assets.

Runtime Neo4j access code belongs under `src/power_atlas/adapters/neo4j/`.
Operational graph assets belong here.

## Scope

Use this directory for assets and procedures that shape or operate the graph
outside the application runtime package, including:

- versioned migrations
- constraints and indexes
- seed data or seed-loading helpers
- repeatable diagnostics
- local/test lifecycle notes

Do not put application retrieval code, orchestration code, or runtime adapter
logic here.

## Current Repo Posture

The repo is at an initial operationalization checkpoint rather than a fully
externalized graph-ops model.

- Local Neo4j provisioning is currently done with `docker compose up -d neo4j`.
- Demo graph reset is currently handled by `python -m demo.reset_demo_db --confirm`.
- The active demo vector index contract is `demo_chunk_embedding_index` on
  `:Chunk(embedding)` with `1536` dimensions.
- That vector index contract now has a concrete operational asset at
  `neo4j/indexes/demo_chunk_embedding_index.cypher`, while runtime creation is
  still driven by the live PDF-ingest path and mirrored through
  `demo/config/pdf_simple_kg_pipeline.yaml` and
  `src/power_atlas/contracts/pipeline.py`.
- Read-only diagnostics currently live in the runtime/query surfaces
  `demo/stages/graph_health.py`, `demo/stages/retrieval_benchmark.py`,
  the documented manual diagnostics CLI seam
  `pipelines/query/graph_health_diagnostics.py`, and the documented manual
  benchmark CLI seam `pipelines/query/retrieval_benchmark.py`.
- The first concrete operational diagnostic asset now exists at
  `neo4j/diagnostics/check_demo_chunk_embedding_index.cypher`.
- The current demo reset scope is now also externalized under
  `neo4j/diagnostics/demo_reset_scope.md` and
  `neo4j/diagnostics/check_demo_reset_scope.cypher`.
- Seed-like demo source assets currently live under `demo/fixtures/`.

This means the folder structure is now explicit even though some concrete graph
assets are still managed by the demo/runtime path and should be moved here only
when their ownership is stable enough to avoid split-brain maintenance.

## Directory Layout

- `constraints/`: named Cypher assets for schema and uniqueness constraints
- `indexes/`: named Cypher assets for indexes, including vector index setup
- `migrations/`: ordered migration assets or migration manifests
- `diagnostics/`: repeatable operational checks and graph inspection assets
- `seed/`: seed data, seed manifests, or seed-loading notes
- `local_dev_workflow.md`: current local/test Neo4j provisioning and validation workflow

## Current Operating Workflow

For local development and validation, the effective workflow today is:

1. Start Neo4j with `docker compose up -d neo4j`.
2. Load environment variables from `.env`.
3. Optionally reset the demo-owned graph with `python -m demo.reset_demo_db --confirm`.
4. Run the demo pipeline (`ingest-pdf`, `extract-claims`, `resolve-entities`, optional `ingest-structured`).
5. Run read-only diagnostics (`graph-health`, `retrieval-benchmark`) or retrieval validation.

See `neo4j/local_dev_workflow.md` for the consolidated local/test procedure.

## Execution Order For Future Graph Setup

Until a dedicated migration runner is adopted, the intended execution order for
graph operational assets is:

1. Provision the Neo4j server and plugins.
2. Apply constraints.
3. Apply indexes.
4. Load seed/reference data when needed.
5. Run ingest/enrichment pipelines.
6. Run diagnostics and validation checks.

## Candidate vs Authoritative Graph Handling

The repo now treats this as a required documented distinction, but the concrete
implementation mechanism is still open.

See `docs/repository_restructure/repository_restructure_decisions.md`,
Decision 7, for the accepted boundary: candidate and authoritative graph flows
must be explicit before Phase 6 can be considered complete.

## Near-Term Migration Rule

When a graph operational concern is currently enforced by runtime/demo code but
has stabilized into a durable operational contract, move the durable asset here
and leave the runtime path as a caller/consumer rather than a second source of
truth.