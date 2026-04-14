# Final Proposed Migration Plan for Repository Restructure

## Objective

Restructure `zoomlytics/power-atlas` into a production-oriented, layered monorepo that reflects the actual architecture of the system:

- the current implementation is the real product core, not disposable demo code
- semantic/domain concerns should be separated from orchestration and infrastructure
- Neo4j-specific operational assets should become first-class
- API/CLI/worker entrypoints should stay thin
- evaluation assets should be separated from correctness tests
- candidate vs authoritative graph boundaries should be made explicit

This migration plan assumes we are targeting the following end-state structure:

```
power-atlas/
├── pyproject.toml
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
│
├── src/
│   └── power_atlas/
│       ├── __init__.py
│       ├── core/
│       ├── application/
│       ├── adapters/
│       ├── interfaces/
│       ├── schemas/
│       └── bootstrap/
│
├── web/
├── tests/
├── eval/
├── neo4j/
├── config/
├── docs/
├── scripts/
├── runs/
├── studies/
├── vendor/
├── vendor-resources/
└── _archive/
```

---

## Architectural principles

These principles should govern every migration step.

### 1. Dependency direction

Enforce the following dependency flow:

- `core` has no dependency on Neo4j, FastAPI, queue systems, or vendor SDKs
- `application` depends on `core`
- `adapters` implements infrastructure concerns
- `interfaces` depends on `application`, not directly on `adapters`
- `web` talks to API contracts, not Python internals

### 2. No hidden mutable runtime state

Eliminate process-global mutable pipeline state. Replace it with explicit context objects such as:

- `AppContext`
- `RequestContext`
- `RunContext`
- `DatasetContext` where needed

### 3. No raw Cypher in orchestration or transport layers

Cypher should live under Neo4j adapter modules such as:

- `src/power_atlas/adapters/neo4j/cypher/`
- `src/power_atlas/adapters/neo4j/repositories/`

It should not live in:

- `application/`
- `interfaces/api/`
- CLI entrypoints

### 4. Separate correctness tests from evaluation assets

- `tests/` is for correctness and regression coverage
- `eval/` is for benchmark datasets, rubrics, benchmark scenarios, and reports

### 5. Make candidate vs authoritative boundaries explicit

This must become a real architectural boundary reflected in:

- runtime context
- configuration
- graph namespaces or DB separation strategy
- promotion workflows
- evaluation scenarios
- operational docs

---

## Migration strategy

Use a staged migration with the following goals:

1. make the repository structurally honest
2. establish a proper package and entrypoint model
3. move code into the revised layered structure
4. eliminate architectural hazards
5. re-home tests, eval assets, and Neo4j operations
6. decide what remains scaffold vs what becomes active product surface

This should be done incrementally with tests passing at each stage.

---

## Phase 0 — Freeze architectural intent and define rules

### Goal

Create a stable decision record before moving code.

### Tasks

- Add an ADR in `docs/decisions/` describing the target layered structure.
- Document the dependency rules above.
- Document that the current implementation under `demo/` is the canonical functional core being promoted.
- Document that `backend/` and `frontend/` are scaffolding unless wired into application services.
- Define target language for:
  - candidate graph
  - authoritative graph
  - run artifacts
  - evaluation assets
  - interface layers
- Decide naming conventions for:
  - graph namespaces
  - dataset versions
  - run IDs
  - migration identifiers

### Deliverables

- `docs/decisions/ADR-*.md`
- updated root `README.md`
- glossary of migration terms

### Exit criteria

- team alignment on final target structure
- no ambiguity about what “core”, “application”, “adapters”, and “interfaces” mean

---

## Phase 1 — Establish package layout and repo skeleton

### Goal

Create the final top-level structure without fully moving logic yet.

### Tasks

Create the following directories:

```
src/power_atlas/
src/power_atlas/core/
src/power_atlas/application/
src/power_atlas/adapters/
src/power_atlas/interfaces/
src/power_atlas/schemas/
src/power_atlas/bootstrap/

web/
tests/unit/
tests/integration/
tests/e2e/
tests/fixtures/
tests/golden/

eval/datasets/
eval/rubrics/
eval/benchmark_scenarios/
eval/reports/

neo4j/migrations/
neo4j/constraints/
neo4j/indexes/
neo4j/seed/
neo4j/diagnostics/

config/base/
config/dev/
config/test/
config/prod/

docs/architecture/
docs/ontology/
docs/provenance/
docs/operations/
docs/api/
docs/schema/
docs/decisions/

runs/
```

### Packaging tasks

- Add or finalize `pyproject.toml`
- Move to `src/` layout
- Define package entrypoints for CLI
- Ensure local editable installation works
- Add baseline lint/test commands to `Makefile`

### Deliverables

- skeleton directory structure
- working package install
- baseline project tooling

### Exit criteria

- `pip install -e .` or equivalent works
- tests can be invoked against package imports
- no dependency on `sys.path` hacks going forward

---

## Phase 2 — Promote current implementation into `src/power_atlas/`

### Goal

Move the current real implementation out of `demo/` into the durable Python package with minimal behavioral change.

### Tasks

#### 2.1 Initial move with minimal churn

Promote current modules into temporary mapped locations under `src/power_atlas/` before deeper refinement.

Recommended transitional mapping:

- `demo/contracts/` → `src/power_atlas/core/`
- `demo/stages/` → `src/power_atlas/application/pipeline/stages/`
- `demo/io/` → `src/power_atlas/adapters/neo4j/` or `src/power_atlas/application/pipeline/io/` depending on responsibility
- `demo/run_demo.py` →
  - orchestration logic to `src/power_atlas/application/pipeline/`
  - CLI parsing to `src/power_atlas/interfaces/cli/`

#### 2.2 Transitional import compatibility

During migration, maintain temporary compatibility shims if needed to reduce blast radius, but plan to remove them.

### Rules for classification

#### Move to `core/` if the module primarily contains:
- contracts
- schemas
- types
- prompt specifications
- retrieval metadata policies
- domain invariants
- ontology or provenance semantics

#### Move to `application/` if the module primarily contains:
- orchestration
- stage sequencing
- multi-step retrieval flow
- answer composition
- evaluation execution
- citation assembly
- ingestion/enrichment coordination

#### Move to `adapters/` if the module primarily contains:
- Neo4j driver use
- Cypher execution
- LLM provider calls
- embedding provider calls
- filesystem/object persistence
- config loading
- queue integration
- telemetry

### Deliverables

- canonical code now lives under `src/power_atlas/`
- `demo/` no longer contains the primary implementation

### Exit criteria

- CLI and core workflows run from package code
- `demo/` is either removed or reduced to compatibility wrappers pending deletion

---

## Phase 3 — Introduce the revised internal layering

### Goal

Refine the promoted code into the final layered structure:

- `core/`
- `application/`
- `adapters/`
- `interfaces/`

### Tasks

### 3.1 Narrow and harden `core/`

Organize `core/` into:

```
src/power_atlas/core/
├── ontology/
├── provenance/
├── temporal/
├── policies/
├── prompts/
├── contracts/
├── types/
└── errors/
```

Move only durable semantic concepts here.

Examples:
- ontology primitives
- evidence/citation/provenance contracts
- retrieval metadata contract models
- temporal semantics
- policy rules
- result schemas not tied to transport
- prompt specs treated as policy assets

Remove any direct dependency on:
- Neo4j driver
- FastAPI
- filesystem layout assumptions
- environment bootstrapping

### 3.2 Evolve `pipeline/` into `application/`

Structure `application/` as:

```
src/power_atlas/application/
├── pipeline/
├── retrieval/
├── ingestion/
├── enrichment/
├── answering/
├── citations/
├── evaluation/
└── services/
```

Guidelines:
- `pipeline/` holds orchestration sequences
- `retrieval/` holds graph/vector retrieval coordination
- `answering/` holds answer assembly and grounded synthesis logic
- `citations/` holds provenance stitching and citation attachment behavior
- `evaluation/` holds evaluation execution logic
- `services/` exposes use-case level application services called by interfaces

### 3.3 Create explicit `interfaces/`

Structure:

```
src/power_atlas/interfaces/
├── api/
├── cli/
└── workers/
```

Rules:
- routers, commands, and worker handlers should be thin
- interfaces call application services only
- no embedded retrieval policy in routers or commands
- no direct Cypher in interfaces

### 3.4 Formalize `adapters/`

Structure:

```
src/power_atlas/adapters/
├── neo4j/
│   ├── driver.py
│   ├── repositories/
│   ├── cypher/
│   ├── vector_indexes/
│   ├── fulltext_indexes/
│   └── graph_schema/
├── llm/
├── embeddings/
├── storage/
├── config/
├── queue/
└── telemetry/
```

Rules:
- centralize Neo4j driver lifecycle
- move Cypher query text/builders/templates under Neo4j adapter boundaries
- keep provider-specific logic out of application services
- move environment/config loading into config adapters

### Deliverables

- code is organized by durable layer
- dependency direction is enforceable
- transport and infra concerns are separated from semantic logic

### Exit criteria

- application code depends on abstractions or clean adapter seams
- API/CLI/worker layers are thin
- no new code is added to legacy locations

---

## Phase 4 — Eliminate global mutable state and formalize runtime context

### Goal

Remove architectural hazards that would block service embedding and concurrent execution.

### Tasks

### 4.1 Introduce context models

Create explicit context types such as:

- `AppContext`
- `RequestContext`
- `RunContext`
- `DatasetContext`

Suggested responsibilities:

#### `AppContext`
- settings
- driver pools
- provider registries
- shared telemetry/logging wiring

#### `RequestContext`
- request id
- user / auth scope
- tracing metadata
- deadlines or time budgets

#### `RunContext`
- run id
- dataset identifier
- graph namespace
- output location
- model/version metadata
- dry-run / execution mode flags

#### `DatasetContext`
- corpus or dataset id
- source set
- schema version
- promotion state
- indexing state

### 4.2 Remove process-global pipeline state

Refactor:
- global dataset state
- mutable config globals
- hidden singleton runtime data

Replace with explicit context passed through application service boundaries.

### 4.3 Standardize run manifests

Every run should emit a structured manifest under `runs/` capturing:
- run id
- input dataset/version
- graph namespace
- model versions
- prompts used
- config snapshot
- outputs
- trace locations

### Deliverables

- explicit runtime model
- safer concurrency and background execution
- improved reproducibility

### Exit criteria

- application workflows run without hidden mutable module state
- CLI and API share the same application services and context model

---

## Phase 5 — First-class Neo4j operational structure

### Goal

Promote Neo4j operational concerns into stable repo structure.

### Tasks

Create and populate:

```
neo4j/
├── migrations/
├── constraints/
├── indexes/
├── seed/
└── diagnostics/
```

### Responsibilities

#### `neo4j/migrations/`
- schema evolution scripts
- graph shape changes
- migration manifests

#### `neo4j/constraints/`
- uniqueness constraints
- property existence assumptions where applicable
- constraint definitions by environment or graph namespace if needed

#### `neo4j/indexes/`
- vector indexes
- fulltext indexes
- lookup/index setup scripts
- index verification scripts

#### `neo4j/seed/`
- minimal seed data
- local dev bootstrap graph content if needed

#### `neo4j/diagnostics/`
- graph health checks
- retrieval-path diagnostics
- query plan checks
- coverage and integrity probes

### Additional requirement

Explicitly model candidate vs authoritative graph strategy. Decide and document:
- same DB with namespace separation
- separate DBs
- separate labels/indexes
- promotion workflow rules
- evaluation and review pathway

This decision must appear in:
- config
- runtime context
- docs
- operational scripts

### Deliverables

- graph operations are first-class
- graph schema/index lifecycle is no longer implicit in application code

### Exit criteria

- graph setup and diagnostics can run independently of the application flow
- graph promotion model is documented and testable

---

## Phase 6 — Consolidate CLI/API/worker entrypoints

### Goal

Replace ad hoc wrappers and placeholder surfaces with thin, intentional interfaces.

### Tasks

### 6.1 CLI consolidation

Move current CLI behavior into:

```
src/power_atlas/interfaces/cli/
```

Suggested commands:
- ingest
- retrieve/query
- benchmark/evaluate
- diagnostics
- graph health
- promotion/review workflows if applicable

Retire:
- ad hoc wrappers under `pipelines/`
- `sys.path` import hacks

### 6.2 API consolidation

Move real backend logic into:

```
src/power_atlas/interfaces/api/
```

Rules:
- endpoints call application services
- endpoints do not build Cypher
- endpoints do not own retrieval strategy
- endpoints should support run submission and run status where appropriate

### 6.3 Worker model

Introduce:

```
src/power_atlas/interfaces/workers/
```

Responsibilities:
- long-running ingestion jobs
- evaluation/benchmark jobs
- backfills / re-indexing
- enrichment tasks
- promotion workflows if asynchronous

### Deliverables

- clear interface entrypoints
- no false product surfaces
- shared business logic across CLI/API/worker flows

### Exit criteria

- the real backend/API lives in `interfaces/api/`
- command-line paths use the same application services as API/worker paths
- placeholder-only backend/frontend code is either wired up or retired

---

## Phase 7 — Frontend decision and `web/` integration

### Goal

Treat frontend as a real surface or explicitly keep it out of the critical path.

### Tasks

- Rename or replace `frontend/` with `web/`
- Align frontend contracts with API response models
- Build only against explicit backend contracts:
  - search and retrieval results
  - answer payloads
  - provenance panels
  - citation cards
  - graph neighborhood views
  - job status
  - review/promote actions if applicable

### Rules

- frontend should not define the system ontology implicitly
- frontend should not require direct access to internal Python structures
- UI contracts should be versioned at the API boundary

### Deliverables

- `web/` reflects actual frontend role
- UI surface becomes a consumer of the backend, not a false architecture placeholder

### Exit criteria

- either the frontend is real and wired to application services through API
- or it is explicitly marked as scaffold and removed from core dev/runtime assumptions

---

## Phase 8 — Rebuild tests into a unified correctness strategy

### Goal

Replace fragmented and stale test structure with a single intentional test hierarchy.

### Tasks

Create:

```
tests/
├── unit/
├── integration/
├── e2e/
├── fixtures/
└── golden/
```

### Test boundaries

#### `tests/unit/`
Use for:
- pure semantic invariants
- policy behavior
- prompt rendering/spec logic
- citation assembly
- result transformation
- query-building logic that stops before DB execution

#### `tests/integration/`
Use for:
- Neo4j repositories
- Cypher correctness
- transaction behavior
- index/constraint assumptions
- ingestion persistence
- retrieval fusion

Run these against ephemeral Neo4j environments.

#### `tests/e2e/`
Use for:
- CLI-to-output flows
- API-to-answer flows
- worker/job orchestration
- promotion flows
- graph diagnostics paths

#### `tests/fixtures/`
Store:
- tiny semantic fixtures
- ontology edge cases
- contradictory claims
- temporal cases
- provenance chains
- entity resolution conflict cases
- realistic retrieval fixtures

#### `tests/golden/`
Store stable expected outputs where useful:
- answer payloads
- citation structures
- retrieval traces
- benchmark report samples

### Cleanup requirement

- move or delete obsolete tests from legacy top-level `tests/`
- remove tests that target dead archive-era paths
- keep archive tests only if relocated under `_archive/`

### Deliverables

- coherent correctness strategy
- no ambiguity about live vs obsolete coverage

### Exit criteria

- one canonical pytest tree
- no dead-path tests in active CI

---

## Phase 9 — Separate evaluation assets from correctness tests

### Goal

Make benchmark and evaluation assets first-class.

### Tasks

Create:

```
eval/
├── datasets/
├── rubrics/
├── benchmark_scenarios/
└── reports/
```

### Responsibilities

#### `eval/datasets/`
- curated benchmark question sets
- expected evidence sets
- graph-aware challenge corpora
- candidate vs authoritative comparison sets where needed

#### `eval/rubrics/`
- citation correctness scoring
- groundedness scoring
- provenance completeness scoring
- temporal correctness scoring
- contradiction preservation / unsupported-claim suppression scoring

#### `eval/benchmark_scenarios/`
- predefined retrieval/evaluation scenarios
- config bundles for repeatable eval runs

#### `eval/reports/`
- generated benchmark output
- historical evaluation snapshots as appropriate

### Deliverables

- evaluation becomes a maintained product asset
- benchmarks stop being mixed into generic test coverage

### Exit criteria

- benchmark workflows read from `eval/`
- correctness tests do not depend on benchmark report artifacts

---

## Phase 10 — Configuration, runs, and operational discipline

### Goal

Make environment config and run artifacts explicit and production-friendly.

### Tasks

### 10.1 Organize config

Populate:

```
config/
├── base/
├── dev/
├── test/
└── prod/
```

Config should cover:
- graph namespace strategy
- Neo4j connection settings
- model/provider settings
- queue settings
- storage paths
- evaluation settings
- candidate vs authoritative promotion settings

### 10.2 Standardize `runs/`

Use `runs/` for:
- run manifests
- logs
- prompts used
- retrieval traces
- output payloads
- benchmark summaries

Rules:
- generated outputs do not live under package source trees
- `runs/` is not a source of truth for business logic
- outputs should be reproducible from code + config + input datasets

### 10.3 Update operations docs

Document:
- local dev startup
- graph bootstrapping
- migration execution
- index verification
- evaluation execution
- worker execution
- promotion workflows
- failure diagnostics

### Deliverables

- clean operational model
- reduced ambiguity around artifacts and environments

### Exit criteria

- no hardcoded source-tree artifact assumptions remain in application logic
- environment behavior is controlled by explicit config and context

---

## Phase 11 — Retire or quarantine legacy structures

### Goal

Remove misleading architecture signals.

### Tasks

Review and retire or isolate:
- `demo/`
- `pipelines/`
- `backend/`
- `frontend/`
- obsolete top-level `tests/`

### Rules

#### `demo/`
- remove if all logic has been promoted
- or keep only as compatibility wrappers during short transition

#### `pipelines/`
- remove once CLI behavior is consolidated under `interfaces/cli/`

#### `backend/`
- remove if replaced by `src/power_atlas/interfaces/api/`
- otherwise clearly mark as deprecated scaffold

#### `frontend/`
- replace with `web/`
- or quarantine if not active

#### Legacy tests
- move archive-only tests under `_archive/`
- remove dead-path tests from active test runs

### Deliverables

- architecture truth matches repository shape
- no decoy product surfaces remain

### Exit criteria

- root structure reflects actual active product architecture
- contributors are not misled by stale directories

---

## Proposed migration order

Recommended practical sequence:

1. Phase 0 — ADR and repo documentation
2. Phase 1 — create package and target skeleton
3. Phase 2 — promote implementation into `src/power_atlas/`
4. Phase 3 — refine into `core/application/adapters/interfaces`
5. Phase 4 — remove global mutable runtime state
6. Phase 5 — establish `neo4j/` operational assets
7. Phase 6 — consolidate CLI/API/workers
8. Phase 8 — unify tests
9. Phase 9 — create `eval/`
10. Phase 10 — formalize config and runs
11. Phase 7 — finalize `web/` integration or de-scope it
12. Phase 11 — retire legacy structures

This order prioritizes correctness and package integrity before product-surface cleanup.

---

## Cross-cutting review checklist

Use this checklist throughout the migration.

### Layering checklist

- Does this module belong in `core`, `application`, `adapters`, or `interfaces`?
- Does it depend inward only?
- Is infrastructure logic leaking into semantic code?
- Is transport logic leaking into application services?

### Neo4j checklist

- Is Cypher located only under Neo4j adapter boundaries?
- Is graph schema/index logic externalized into `neo4j/`?
- Is candidate vs authoritative graph strategy explicit?
- Are diagnostics and graph health checks represented structurally?

### Runtime checklist

- Does this flow depend on hidden global state?
- Can the same use-case run from CLI, API, and worker entrypoints?
- Is run metadata explicitly captured?

### Testing checklist

- Is this a correctness test or an evaluation asset?
- Does this test belong in unit, integration, or e2e?
- Is any obsolete or archive-era coverage still mixed into live CI?

### DX and operations checklist

- Are generated artifacts outside the source tree?
- Can local dev be bootstrapped predictably?
- Are migration/index/constraint steps documented and scriptable?

---

## Success criteria for the final state

The migration is complete when the following are true:

1. The real implementation lives under `src/power_atlas/`
2. `core`, `application`, `adapters`, and `interfaces` are structurally distinct
3. Neo4j operations are represented explicitly in top-level `neo4j/`
4. Cypher is isolated to Neo4j adapter boundaries
5. runtime state is explicit, not process-global
6. CLI, API, and worker flows share application services
7. correctness tests live under unified `tests/`
8. benchmarks and scoring assets live under `eval/`
9. `runs/` holds generated artifacts, not logic
10. candidate vs authoritative graph strategy is operationally explicit
11. legacy scaffolding and obsolete structures no longer send false architecture signals

---

## Final recommendation

Proceed with the restructure toward the revised layered architecture, but treat it as a **controlled migration**, not a rewrite.

The key priorities are:

- promote the real implementation into a durable package
- enforce dependency direction early
- isolate Neo4j-specific logic and operations
- eliminate global mutable runtime state
- separate correctness, evaluation, and operations clearly
- retire misleading scaffolding once the new structure is functional

This plan will align the repository with the system it already is becoming: a serious Neo4j-backed Graph RAG application with durable semantic contracts, explicit graph operations, and multiple product surfaces built on one canonical core.