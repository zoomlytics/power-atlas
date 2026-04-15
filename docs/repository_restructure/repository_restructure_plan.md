# Revised Migration Plan for `zoomlytics/power-atlas`

## 0. Goals

This migration is intended to:

- promote the current product core into a durable Python package,
- establish enforceable runtime and infrastructure boundaries,
- isolate Neo4j operational concerns from application logic,
- separate correctness testing from evaluation assets,
- reduce architectural drift,
- avoid a rewrite.

This migration is **not** intended to:

- fully perfect the domain model up front,
- pre-build abstractions for unproven future needs,
- formalize workers before the execution model is real,
- redesign the frontend before backend contracts stabilize.

---

## 1. Migration principles

These principles govern all phases.

### 1.1 Controlled migration over rewrite

- preserve current behavior whenever possible,
- prefer mechanical moves before conceptual reorganization,
- introduce temporary shims only when needed,
- time-box shims and remove them deliberately.

### 1.2 Stabilize seams before deep taxonomy

- create top-level package boundaries early,
- delay fine-grained subpackages until the code naturally clusters,
- avoid directory proliferation based on speculative future architecture.

### 1.3 Tests before trust

- create a migration safety harness before major moves,
- require smoke and integration coverage for critical flows,
- do not rely on "it still imports" as proof of correctness.

### 1.4 One composition root

- dependency wiring belongs in `bootstrap/`,
- interfaces should not construct infrastructure directly,
- application code should not instantiate Neo4j drivers, SDK clients, or config loaders directly.

### 1.5 Explicit runtime state

- no new mutable process-global runtime state,
- all new runtime dependencies must flow through explicit context or injected services.

### 1.6 Operational assets are first-class

- Neo4j migrations, constraints, indexes, seeds, and diagnostics are repo-level operational assets,
- benchmark datasets and evaluation reports are not test fixtures,
- run artifacts must be managed deliberately.

---

## 2. Initial target structure

This is the **first-pass target**, not the final fully expanded taxonomy.

```text
power-atlas/
├── pyproject.toml
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── src/
│   └── power_atlas/
│       ├── __init__.py
│       ├── core/
│       ├── application/
│       ├── adapters/
│       ├── interfaces/
│       ├── schemas/
│       └── bootstrap/
├── tests/
├── eval/
├── neo4j/
├── config/
├── docs/
├── scripts/
├── runs/
├── web/              # only if retained as active frontend
└── _archive/
```

### Directory intent

#### `src/power_atlas/core/`

Pure domain concepts and policies:

- value objects,
- domain errors,
- graph-agnostic invariants,
- narrowly scoped pure logic.

Do **not** force all important logic here.

#### `src/power_atlas/application/`

Use cases and orchestration:

- retrieval workflows,
- ingestion workflows,
- answer generation orchestration,
- citation assembly orchestration,
- evaluation execution logic,
- service coordination.

This should be the main center of gravity.

#### `src/power_atlas/adapters/`

Infrastructure implementations:

- Neo4j access,
- LLM clients,
- embedding providers,
- storage,
- telemetry,
- config loaders,
- optional queues.

#### `src/power_atlas/interfaces/`

Boundary entrypoints:

- API,
- CLI,
- workers only if justified later.

#### `src/power_atlas/schemas/`

Contracts and transport/data schemas shared across boundaries.

#### `src/power_atlas/bootstrap/`

Composition root:

- settings initialization,
- dependency wiring,
- adapter construction,
- application service assembly,
- entrypoint bootstrapping.

#### `neo4j/`

Operational graph assets only:

- migrations,
- constraints,
- indexes,
- seed data,
- diagnostics,
- documentation for graph lifecycle.

#### `tests/`

Correctness verification only.

#### `eval/`

Benchmark datasets, rubrics, scenarios, and evaluation reports.

---

## 3. Boundary rules

### 3.1 Dependency direction

Allowed dependency flow:

- `core` -> depends on nothing internal
- `application` -> may depend on `core` and `schemas`
- `adapters` -> may depend on `application`, `core`, `schemas`
- `interfaces` -> may depend on `application`, `schemas`, `bootstrap`
- `bootstrap` -> may depend on everything needed for wiring

Not allowed:

- `core` importing Neo4j, FastAPI, queue systems, or SDKs,
- `application` directly constructing infrastructure clients,
- `interfaces` embedding Cypher or orchestration logic,
- raw Neo4j driver usage outside adapter implementations.

### 3.2 Neo4j boundary

- all driver/session usage stays in `adapters/neo4j`,
- Cypher lives in `adapters/neo4j` implementations or adjacent query modules,
- schema/index/migration assets live in top-level `neo4j/`,
- application services call query/repository interfaces or adapter services, not raw Cypher.

### 3.3 Prompt boundary

Prompts must not be treated as random inline strings across the codebase.

Before large-scale refactor, decide whether prompts are:

- code-defined templates,
- file-based assets,
- versioned strategy objects.

Until that decision is finalized:

- centralize prompt definitions,
- avoid scattering prompt logic through interfaces and adapters.

### 3.4 Runtime state

Start with only:

- `AppContext`
- `RequestContext`

Defer `RunContext` and `DatasetContext` until proven necessary.

---

## 4. Decisions required before implementation starts

These decisions must be made first because later phases depend on them.

### 4.1 Config system

Decide:

- settings source precedence,
- env-file strategy,
- secret handling,
- test overrides,
- local/dev/prod configuration shape.

### 4.2 Neo4j lifecycle model

Decide:

- how candidate vs authoritative graphs are separated,
- whether separation is physical or logical,
- how migrations are applied,
- how indexes/constraints are managed,
- how local/test environments are provisioned,
- how graph resets or rebuilds work.

### 4.3 Prompt/version tracking

Decide:

- where prompts live,
- how prompt changes are versioned,
- how runs record prompt/model/retrieval settings.

### 4.4 API contract approach

Decide:

- schema ownership,
- backward-compatibility expectations,
- how `web/` consumes contracts.

### 4.5 Worker status

Decide:

- whether workers are in scope now,
- or explicitly defer them until a real async execution model exists.

---

## 5. Revised execution phases

### Phase 0 — Decision freeze and architecture contract

#### Objectives

- lock the minimum required architecture decisions,
- create a shared classification guide,
- prevent drift during migration.

#### Deliverables

- ADR set or short architecture decision register,
- boundary rules document,
- package classification guide,
- temporary shim policy,
- initial Neo4j lifecycle policy,
- config policy,
- prompt handling policy,
- worker deferral or scope decision.

#### Exit criteria

- team agrees on package intent,
- team agrees on first-pass directory scope,
- unresolved foundational decisions are documented explicitly.

#### Risks

- producing too much documentation,
- pretending ambiguous items are solved.

#### Guidance

Keep documents short and operational.

---

### Phase 1 — Migration safety harness

#### Objectives

- establish confidence before moving code,
- capture current behavior on the critical path.

#### Deliverables

- smoke tests for critical current flows,
- at least one golden-path retrieval/answering scenario,
- at least one Neo4j-backed integration test,
- packaging/import check in CI,
- explicit definition of what "behavior preserved" means.

#### Suggested minimum coverage

- one CLI flow,
- one API flow if backend exists,
- one graph retrieval path,
- one answer/citation path,
- one ingestion or enrichment path if it is core.

#### Exit criteria

- current critical flows are executable in CI or a reproducible local command,
- baseline outputs are captured,
- package-install/import behavior is validated.

#### Risks

- overbuilding tests before migration,
- trying to comprehensively test the whole system.

#### Guidance

This is a safety harness, not a testing overhaul.

---

### Phase 2 — Package foundation and composition root

#### Objectives

- establish the new package root cleanly,
- get installable structure and bootstrap wiring in place.

#### Deliverables

- `src/power_atlas/` created,
- `pyproject.toml` updated,
- editable install working,
- initial `bootstrap/` created,
- initial typed settings/config entrypoint created,
- interface entrypoints can import from installed package path.

#### Exit criteria

- package installs cleanly,
- current entrypoints can load through package imports,
- no repo-root-only import hacks are required for new work.

#### Risks

- mixing package setup with deep refactoring,
- accidental relative-import breakage.

#### Guidance

Keep this phase mostly structural.

---

### Phase 3 — Mechanical promotion of current implementation

#### Objectives

- move the real product code out of `demo/`,
- preserve behavior with minimal conceptual changes.

#### Deliverables

- current implementation moved into `src/power_atlas/...`,
- minimal renames only,
- compatibility shims added where necessary,
- imports updated,
- smoke tests passing.

#### Rules

- no broad redesign,
- no premature subpackage explosion,
- no "while we're here" rewrites.

#### Exit criteria

- core product flows run from the new package,
- behavior is materially unchanged,
- `demo/` is no longer the execution center of gravity.

#### Risks

- import churn,
- hidden runtime assumptions,
- accidental layer changes during movement.

#### Guidance

This is a relocation phase, not an architecture cleanup phase.

---

### Phase 4 — First-order seam extraction

#### Objectives

Extract only the seams that offer immediate architectural value.

#### Priority seams

1. Neo4j access seam
2. LLM/embedding seam
3. API/CLI boundary seam
4. runtime context seam

#### Deliverables

- Neo4j access isolated to adapter modules,
- orchestration moved toward `application/`,
- interfaces made thinner,
- infrastructure construction moved into `bootstrap/`.

#### Exit criteria

- no raw Cypher in API/CLI/application orchestration,
- no direct driver/client construction in business logic,
- interfaces mostly call application services rather than coordinating infra directly.

#### Risks

- circular imports,
- over-abstracted ports,
- generic repository designs that fit poorly for graph retrieval.

#### Guidance

Prefer practical query services over overgeneralized repositories where needed.

---

### Phase 5 — Runtime state cleanup

#### Objectives

- remove mutable process-global state,
- make runtime dependencies explicit.

#### Deliverables

- `AppContext` defined and adopted,
- `RequestContext` defined and adopted where relevant,
- hidden singletons/globals identified and removed incrementally,
- run metadata handling standardized where already needed.

#### Exit criteria

- critical flows do not rely on mutable global runtime state,
- new code follows explicit dependency/context injection rules.

#### Risks

- underestimating hidden globals,
- introducing too many overlapping context objects.

#### Guidance

Only introduce `RunContext` or `DatasetContext` if the actual code shows they solve real confusion.

---

### Phase 6 — Neo4j operationalization

#### Objectives

- make graph lifecycle and operational assets explicit,
- align code boundary with graph operations.

#### Deliverables

- `neo4j/` populated with:
  - migrations,
  - constraints,
  - indexes,
  - seed data,
  - diagnostics,
  - usage docs
- candidate vs authoritative graph strategy documented,
- local/test graph lifecycle documented,
- operational commands/scripts standardized.

#### Exit criteria

- graph schema/index setup is reproducible,
- environments have a documented provisioning path,
- ownership boundary between runtime Neo4j code and operational graph assets is clear.

#### Risks

- split-brain between code and ops assets,
- undocumented ordering of constraints/indexes/migrations.

#### Guidance

Document the execution order clearly.

---

### Phase 7 — Test and eval separation cleanup

#### Objectives

- separate correctness verification from benchmark/evaluation work,
- reduce CI and repo clutter.

#### Deliverables

- `tests/` restructured for correctness,
- `eval/` created or normalized,
- obsolete or archive-only tests moved out of active CI,
- benchmark datasets and reports removed from test fixtures.

#### Exit criteria

- CI correctness suite is clearly defined,
- eval assets are not mixed into test directories,
- active vs archived assets are distinguishable.

#### Risks

- overdesigning test taxonomies,
- breaking existing workflows that rely on messy layouts.

#### Guidance

Organize around practical behavior and workflow, not just abstract layering.

---

### Phase 8 — Interface consolidation

#### Objectives

- normalize API/CLI entrypoints after backend seams settle,
- defer workers unless justified.

#### Deliverables

- CLI moved under `interfaces/cli`,
- backend/API moved under `interfaces/api`,
- worker interfaces added only if real job execution is already in scope.

#### Exit criteria

- entrypoints are thin,
- transport concerns are separated from orchestration,
- no speculative worker architecture unless it is operationally needed.

#### Risks

- redoing interface work too early,
- adding workers with no stable async contract.

#### Guidance

CLI/API first. Workers only by proof, not anticipation.

---

### Phase 9 — Frontend decision and contract alignment

#### Objectives

- settle frontend positioning only after backend contracts are stable enough.

#### Deliverables

One of:

- `web/` established as active frontend package with documented API contract consumption,
- or frontend marked as non-core / deferred / transitional.

#### Exit criteria

- frontend repository position is explicit,
- backend contract expectations are documented.

#### Risks

- moving frontend too early,
- backend contract churn forcing frontend rework.

#### Guidance

This is intentionally late.

---

### Phase 10 — Legacy retirement

#### Objectives

- remove transitional structures,
- prevent permanent dual architecture.

#### Deliverables

- legacy directories removed or archived,
- compatibility shims deleted,
- README/docs updated,
- CI checks updated to reflect final layout.

#### Exit criteria

- `demo/`, old backend/frontend scaffolds, and obsolete pathways are not active production paths,
- transitional architecture is fully retired.

#### Risks

- shims lingering indefinitely,
- archived paths still used informally.

#### Guidance

Time-box removals and assign owners.

---

## 6. Initial implementation scope limits

To avoid over-engineering, these are **out of scope for the first pass unless already proven necessary**:

- deep subpackage taxonomy inside `core/` and `application/`,
- worker framework formalization,
- elaborate queue abstractions,
- premature plugin systems,
- generic repository abstractions for every graph interaction,
- frontend restructuring before backend contract stability,
- broad rethinking of all domain semantics.

---

## 7. Initial architectural rules to enforce in code review

### Must enforce now

- no new raw Cypher outside Neo4j adapters,
- no new process-global mutable runtime state,
- no direct infrastructure construction in interface or application code,
- package imports must flow through installed package layout,
- prompts must not be newly scattered across the codebase,
- temporary shims require explicit removal tracking.

### Do not over-enforce yet

- perfect purity of `core`,
- overly formal port/interface layers for every dependency,
- complete elimination of all legacy patterns before stabilization.

---

## 8. Highest-priority risks and mitigation

### Risk 1 — moving code before safety checks exist

**Mitigation:** complete Phase 1 before large code movement.

### Risk 2 — turning structural migration into conceptual rewrite

**Mitigation:** keep Phase 3 mechanical; defer redesign to later phases.

### Risk 3 — hidden global state breaking runtime behavior

**Mitigation:** inventory globals during Phase 3, remove incrementally in Phase 5.

### Risk 4 — Neo4j logic leaking back upward

**Mitigation:** enforce Cypher/driver boundary during Phase 4 and in code review.

### Risk 5 — temporary compatibility shims becoming permanent

**Mitigation:** track each shim with owner and removal condition.

### Risk 6 — overbuilding future architecture

**Mitigation:** defer workers and deep subpackage splits until justified.

---

## 9. Recommended immediate next work items

If implementation starts this week, do these in order:

1. accept and finalize the decision register,
2. define the safety harness scenarios,
3. create the restructuring checklist / phase tracker,
4. set up `src/power_atlas/`, packaging, and bootstrap shell,
5. move current implementation mechanically,
6. stabilize imports and green the safety harness.

---

## 10. Definition of success

This migration is successful if, at the end:

- the real product runs from `src/power_atlas`,
- the architecture is cleaner without having been rewritten,
- Neo4j concerns are isolated and operationalized,
- runtime state is explicit,
- tests and eval are clearly separated,
- legacy structures are retired,
- future work can proceed without continuing to route through "temporary" paths.
