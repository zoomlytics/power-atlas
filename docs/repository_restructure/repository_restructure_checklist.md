# Repository Restructure Checklist

Status: Accepted  
Applies to: `zoomlytics/power-atlas`  
Related documents:
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_safety_harness.md`

This document converts the canonical repository restructure plan and accepted decision register into an execution tracker.

It is intended to:

- track restructuring progress by phase,
- define phase owners, status, blockers, and exit criteria,
- make Phase 1 safety-harness work concrete,
- prevent structural movement from starting before required safeguards exist,
- track temporary compatibility shims introduced during migration.

It is **not** intended to restate the full migration plan.  
The plan document and accepted decision register remain the canonical sources for architecture direction and sequencing.

---

## 1. Status definitions

Use the following status values consistently:

- `not started`
- `in progress`
- `blocked`
- `ready for review`
- `complete`

---

## 2. Phase tracker

## Phase 0 — Decision freeze and architecture contract

**Status:** complete  
**Owner:**  
**Blockers:**  
**Notes:** Decision register accepted and plan/checklist alignment completed on 2026-04-14.  

### Exit criteria

- decision register is accepted,
- canonical migration plan is current,
- unresolved foundational decisions are explicitly listed,
- package boundary guidance is available for code review,
- worker scope is explicitly deferred or approved.

---

## Phase 1 — Migration safety harness

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- critical-path smoke scenarios are defined,
- baseline outputs are captured for selected golden-path scenarios,
- at least one Neo4j-backed integration path is runnable,
- package/import behavior is validated in CI or a reproducible local command,
- the team has written down what counts as “behavior preserved” for the first migration moves.

### Phase 1 deliverables checklist

- [ ] identify critical CLI flow
- [ ] identify critical API flow, if backend/API exists
- [ ] identify critical graph retrieval flow
- [ ] identify critical answer/citation flow
- [ ] identify critical ingestion or enrichment flow, if in active scope
- [ ] choose at least one golden-path scenario for stable output comparison
- [ ] define at least one Neo4j-backed integration path
- [ ] define package/import validation check
- [ ] document how baseline outputs will be captured and reviewed
- [ ] document what failures block Phase 2

---

## Phase 2 — Package foundation and composition root

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- `src/power_atlas/` exists,
- package installation works,
- bootstrap entrypoint exists,
- typed config/settings entrypoint exists,
- entrypoints can import through installed package layout,
- no new repo-root-only import hacks are introduced.

### Phase 2 deliverables checklist

- [ ] create `src/power_atlas/`
- [ ] add package `__init__.py`
- [ ] add or update packaging metadata (`pyproject.toml` or equivalent)
- [ ] verify editable install
- [ ] add initial `bootstrap/`
- [ ] add initial typed settings/config entrypoint
- [ ] prove imports work through installed package path

---

## Phase 3 — Mechanical promotion of current implementation

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- current product flows run from the new package location,
- behavior is materially unchanged,
- smoke checks still pass,
- compatibility shims are tracked explicitly,
- `demo/` is no longer the active center of execution.

### Phase 3 deliverables checklist

- [ ] identify code to be promoted from legacy location
- [ ] move code with minimal renames
- [ ] update imports
- [ ] add temporary shims only where necessary
- [ ] record each shim in the shim tracker
- [ ] run smoke checks
- [ ] verify critical paths still behave as expected

---

## Phase 4 — First-order seam extraction

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- no raw Cypher remains in API/CLI/application orchestration code,
- no direct driver/client construction remains in business logic,
- interfaces are thinner and primarily call application services,
- infrastructure assembly is routed through bootstrap,
- layering violations are identified and either fixed or explicitly tracked.

### Phase 4 deliverables checklist

- [ ] isolate Neo4j runtime access to adapter modules
- [ ] isolate LLM/embedding access behind adapter-facing services or interfaces
- [ ] thin API entrypoints
- [ ] thin CLI entrypoints
- [ ] move dependency construction into `bootstrap/`
- [ ] document unresolved layering leaks

---

## Phase 5 — Runtime state cleanup

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- `AppContext` is defined and used where required,
- `RequestContext` is defined and used where relevant,
- known mutable process-global runtime state is removed or explicitly tracked,
- new runtime state follows explicit injection/context rules.

### Phase 5 deliverables checklist

- [ ] define `AppContext`
- [ ] define `RequestContext`
- [ ] inventory existing mutable global runtime state
- [ ] replace or isolate high-risk globals
- [ ] document any deferred state cleanup

---

## Phase 6 — Neo4j operationalization

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- top-level `neo4j/` structure is established,
- graph schema/index setup is reproducible,
- candidate vs authoritative graph strategy is documented,
- local/test graph lifecycle is documented,
- ownership boundary between runtime graph code and graph operational assets is clear.

### Phase 6 deliverables checklist

- [ ] create or normalize top-level `neo4j/`
- [ ] define migrations approach
- [ ] define constraints/indexes approach
- [ ] define seed/diagnostics approach
- [ ] document candidate vs authoritative graph handling
- [ ] document local/test provisioning workflow
- [ ] document execution order for graph setup

---

## Phase 7 — Test and eval separation cleanup

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- correctness tests are clearly separated from evaluation assets,
- `eval/` holds benchmark/evaluation assets only,
- obsolete or archive-only tests are removed from active CI,
- active vs archived assets are clearly distinguished.

### Phase 7 deliverables checklist

- [ ] define target `tests/` layout
- [ ] define target `eval/` layout
- [ ] move benchmark/evaluation artifacts out of correctness test paths
- [ ] remove or quarantine obsolete tests
- [ ] update CI scope where needed

---

## Phase 8 — Interface consolidation

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- CLI lives under `interfaces/cli`,
- API lives under `interfaces/api`,
- transport concerns are separated from orchestration,
- worker interfaces are added only if explicitly approved.

### Phase 8 deliverables checklist

- [ ] consolidate CLI entrypoints
- [ ] consolidate API entrypoints
- [ ] verify worker need before adding worker interfaces
- [ ] document transport/application boundaries

---

## Phase 9 — Frontend decision and contract alignment

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- frontend repository position is explicit,
- backend contract expectations are documented,
- `frontend/` is either active and aligned, or explicitly deferred/non-core.

### Phase 9 deliverables checklist

- [ ] decide active status of frontend
- [ ] document how frontend consumes backend contracts
- [ ] defer or normalize `frontend/` intentionally

---

## Phase 10 — Legacy retirement

**Status:** not started  
**Owner:**  
**Blockers:**  
**Notes:**  

### Exit criteria

- legacy execution paths are removed or archived,
- temporary shims are removed or explicitly justified,
- docs are updated to reflect the final active structure,
- obsolete structures are no longer treated as active product paths.

### Phase 10 deliverables checklist

- [ ] remove or archive legacy directories
- [ ] remove expired compatibility shims
- [ ] update docs and README references
- [ ] verify no active workflows depend on retired paths

---

## 3. Phase 1 safety harness definition

The full Phase 1 safety harness definition, scenario templates, and inventory are in `docs/repository_restructure/repository_restructure_safety_harness.md`.

The restructuring must not proceed into broad package movement until the following minimum safeguards exist.

### 3.1 Critical-path scenarios to define

At minimum, define and document:

- one critical CLI flow,
- one critical API flow, if the backend/API currently exists,
- one critical graph retrieval flow,
- one critical answer/citation flow,
- one critical ingestion or enrichment flow, if it is part of the active product path.

### 3.2 Golden-path scenarios

Select at least one stable scenario that can be used for before/after comparison.

A golden-path scenario should ideally include:

- representative input,
- a reproducible execution path,
- expected structural output or observable invariants,
- enough stability to detect accidental behavioral drift.

Golden-path checks do **not** need to require byte-for-byte LLM output equality if that is unrealistic.  
They may instead verify stable invariants such as:

- required citations are present,
- graph retrieval returns expected categories or entities,
- response structure is preserved,
- key intermediate artifacts are produced.

### 3.3 Neo4j-backed integration path

At least one integration path must exercise real graph-backed behavior, not only mocked logic.

This path should validate at least one of:

- graph retrieval,
- graph-backed enrichment,
- graph-backed citation assembly,
- graph-backed answering support.

### 3.4 Package/import validation

Before structural moves proceed, there must be a reproducible check that verifies the project is being exercised through the intended package/import path.

Acceptable forms include:

- CI installation + test command,
- local reproducible setup command documented in the repo,
- import validation script or smoke command.

---

## 4. Do not start package movement until...

The following gate must be satisfied before Phase 2 and especially Phase 3 are allowed to expand:

- [x] decision register is accepted
- [x] canonical migration plan is current
- [ ] critical-path scenarios are documented
- [ ] at least one golden-path scenario is defined
- [ ] at least one Neo4j-backed integration path is defined
- [ ] package/import validation approach is defined
- [ ] “behavior preserved” criteria are documented
- [ ] initial owners for Phase 1 and Phase 2 are assigned

If these boxes are not checked, structural movement should be treated as premature.

---

## 5. Behavior preservation notes

Use this section to document what “behavior preserved” means for the first migration moves.

### Current definition

Behavior is considered preserved for early restructuring if:

- the selected critical flows still execute successfully,
- required outputs/artifacts are still produced,
- graph-backed behavior remains functionally available,
- contract-breaking regressions are not introduced,
- any known differences are documented and intentionally accepted.

### Known acceptable differences

Document any allowed differences here, for example:

- output formatting changes that do not alter contract semantics,
- logging changes,
- file location changes for internal implementation details,
- non-user-facing naming cleanup.

---

## 6. Temporary compatibility shim tracker

Use this table to track temporary migration shims so they do not become permanent architecture.

| Shim path / module | Introduced in PR | Purpose | Owner | Removal trigger | Status |
|---|---|---|---|---|---|
| _none yet_ |  |  |  |  |  |

### Shim tracking rules

- every temporary shim must be recorded here,
- every shim must have an owner,
- every shim must have an explicit removal trigger,
- shims without a removal condition should be treated as architecture debt immediately.

---

## 7. Open follow-up decisions

Track follow-up decisions that must be resolved before later phases can complete.

| Decision area | Needed by phase | Owner | Status | Notes |
|---|---|---|---|---|
| Config library/tooling | Phase 2 |  | not started |  |
| Neo4j migration tooling | Phase 6 |  | not started |  |
| Candidate vs authoritative graph implementation model | Phase 6 |  | not started |  |
| Prompt storage/versioning model | Phase 4 / 7 |  | not started |  |
| API schema versioning approach | Phase 8 / 9 |  | not started |  |
| Worker necessity decision | Phase 8 |  | not started |  |
| Critical-path safety harness scenarios | Phase 1 |  | not started |  |

---

## 8. Immediate next actions

Use this section as the working short list.

- [ ] assign owner for Phase 1
- [ ] assign owner for Phase 2
- [ ] enumerate critical-path scenarios
- [ ] choose initial golden-path scenario
- [ ] define first Neo4j-backed integration path
- [ ] document package/import validation command
- [ ] decide what failures block Phase 2