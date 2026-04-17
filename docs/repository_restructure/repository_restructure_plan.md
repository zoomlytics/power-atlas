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

#### Current checkpoint status

Phase 2 is materially in progress as of 2026-04-16.

The package foundation work that was originally planned as the entry condition for
later migration has already landed in the repo:

- `src/power_atlas/` exists and is installable via the committed `pyproject.toml`,
- editable install has been verified repeatedly,
- initial `bootstrap/` and typed settings entrypoints exist,
- package/import proof exists in `tests/test_power_atlas_package.py`,
- multiple contract modules have been promoted into `src/power_atlas/contracts/`,
- more active entrypoints now resolve defaults and infrastructure through package-owned bootstrap seams,
- maintainer-facing docs now point at package-owned contract paths,
- `demo/contracts` remains in place intentionally as a compatibility layer.

This means Phase 2 should no longer be treated as untouched future intent.
However, it should also not yet be treated as full legacy retirement: the active
CLI path remains `demo/`, the compatibility layer is still deliberate, and the
next useful work is broader bootstrap/composition-root adoption than additional
blind import cleanup. Shim/deprecation planning is now documented separately and
should not be confused with the next implementation lane.

Since the previous documentation checkpoint, the package/bootstrap lane has
expanded beyond structural foundation work into active entrypoint ownership:

- `demo/smoke_test.py` now builds dry-run config through package bootstrap,
- `demo/reset_demo_db.py` now resolves most Neo4j CLI defaults through package settings while preserving its missing-password guardrail,
- `demo/run_demo.py` now routes remaining direct Neo4j driver creation through `create_neo4j_driver(...)` and aligns dataset/default selection with package settings,
- query CLIs now use package-backed parser defaults for Neo4j URI, username, and database while preserving their intentional early-exit password behavior,
- `power_atlas.contracts.paths.resolve_dataset_root(...)` now resolves dataset selection through `AppSettings.from_env(...)` rather than direct env reads.

Subsequent narrow slices tightened this further:

- first-party live `OPENAI_API_KEY` checks now route through a shared bootstrap guard helper,
- the `pdf_ingest` vendor bridge now uses a shared temporary-environment helper rather than hand-rolling process env mutation,
- `run_demo` dataset-env selection now routes through bootstrap instead of reading `POWER_ATLAS_DATASET` and `FIXTURE_DATASET` directly.

At this checkpoint, the remaining first-party env-touch cases appear to be
intentional local behavior rather than migration debt:

- `UNSTRUCTURED_RUN_ID` remains a demo-specific runtime override in `run_demo`,
- `reset_demo_db.py` still preserves a special password-default path so its
  missing-password guard remains operator-visible.

The strongest current proof point is the latest full `make phase1-verify` run on
2026-04-16, which passed with fully cited baseline, companion, and isolation
asks and no citation fallback.

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

At the current checkpoint, the structural package foundation is already proven.
The remaining Phase 2 work should preserve the additive migration posture:

- keep package-owned stable contract surfaces authoritative,
- keep `demo/contracts` explicitly documented as compatibility-only,
- avoid re-opening Phase 1 execution posture,
- avoid treating remaining compatibility references as accidental by default.

---

### Phase 3 — Mechanical promotion of current implementation

#### Current checkpoint status

Phase 3 should still be treated as incomplete, but it is no longer purely
theoretical.

Several low-risk contract modules have already been promoted into
`src/power_atlas/contracts/` under the Phase 2 package-first lane, with
compatibility shims preserved in `demo/contracts`. That progress should be read
as additive early promotion work, not as proof that the broader implementation
has left `demo/` as its execution center.

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

#### Current checkpoint status

Phase 4 is no longer untouched future work, but it is still materially
incomplete.

Early seam extraction has already landed additively:

- first-party live Neo4j driver construction now mostly flows through the shared
  bootstrap seam,
- more entrypoints resolve config/default ownership through package settings,
- direct env/default resolution has started moving out of package-owned and
  entrypoint-owned helper code,
- the env/default cleanup lane now appears to be nearing exhaustion, with most
  remaining cases looking intentional rather than accidental,
- first package-owned query/write seams now exist for run-scope lookup,
  claim-participation writes, and structured-ingest writes,
- the main stage-level ambient dataset-id fallbacks have been removed from
  `structured_ingest`, `pdf_ingest`, and `entity_resolution`, and the
  orchestrator no longer writes dataset scope through `set_dataset_id(...)`.

That progress should not be overstated. The repo has not yet reached a true
adapter/application/interface split for graph access, raw Cypher still appears in
live stage modules, and interface/orchestration code is still thicker than the
target architecture allows.

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

#### Current checkpoint status

Phase 5 is no longer purely future work, but it is still early and partial.

The repo has now completed a first concrete runtime-state reduction pass:

- `structured_ingest`, `pdf_ingest`, and `entity_resolution` no longer depend on
  ambient dataset state from `power_atlas.contracts.pipeline.get_dataset_id()`,
- `demo/run_demo.py` no longer writes dataset scope via `set_dataset_id(...)`,
- `demo/run_demo.py` no longer snapshots pipeline contract embedding/index settings
  into import-time module globals for its live stage execution path,
- `claim_schema` and `reset_demo_db` now read pipeline embedding/index settings
  through an explicit immutable snapshot helper rather than direct import-time
  constant bindings,
- `pdf_ingest` and `retrieval_and_qa` now also resolve pipeline embedding/index
  settings through snapshot-backed stage helpers rather than direct import-time
  bindings to mutable pipeline globals,
- the remaining non-dataset mutable pipeline exports now sit behind private
  backing state in `power_atlas.contracts.pipeline`, with deprecated
  compatibility access for legacy global reads/writes plus an explicit
  `get_pipeline_contract_config_data()` helper for raw config inspection,
- `demo.contracts` root no longer eagerly imports those deprecated non-dataset
  pipeline globals, and `demo.run_demo` now reads live pipeline settings
  through the snapshot seam rather than relaying deprecated global access,
- the mutable dataset-state surface is now effectively reduced to compatibility
  exports and the pipeline submodule itself rather than active stage/orchestrator
  behavior.

That remaining compatibility surface is now explicitly deprecated:

- `power_atlas.contracts.pipeline.DATASET_ID`,
- `power_atlas.contracts.pipeline.get_dataset_id()`,
- `power_atlas.contracts.pipeline.set_dataset_id()`,
- `power_atlas.contracts.pipeline.PIPELINE_CONFIG_DATA`,
- `power_atlas.contracts.pipeline.CHUNK_EMBEDDING_INDEX_NAME`,
- `power_atlas.contracts.pipeline.CHUNK_EMBEDDING_LABEL`,
- `power_atlas.contracts.pipeline.CHUNK_EMBEDDING_PROPERTY`,
- `power_atlas.contracts.pipeline.CHUNK_EMBEDDING_DIMENSIONS`,
- `power_atlas.contracts.pipeline.EMBEDDER_MODEL_NAME`,
- `power_atlas.contracts.pipeline.CHUNK_FALLBACK_STRIDE`.

That is meaningful progress, but it does not yet satisfy the phase. The pipeline
contract still contains mutable module-level state, `AppContext` / `RequestContext`
 do not exist, and the remaining stateful pipeline surface still needs an explicit
 disposition rather than simple coexistence.

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

The repo is past the original Phase 1/early-Phase 2 setup posture. The most
useful next work in sequence is now:

1. keep Phase 2 open, but treat its structural foundation deliverables as complete,
2. treat Phase 3 as additive in-progress movement rather than the next untouched phase,
3. treat Phase 4 as partially underway and use that framing to prioritize the next lane,
4. treat the first-party env/default cleanup lane as mostly complete and avoid reopening it unless new real debt is found,
5. take the next narrow migration slices on broader Phase 4 seam extraction, especially raw Cypher isolation and thinner orchestration boundaries,
6. defer actual shim retirement until late migration unless the active execution surface changes materially.

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
