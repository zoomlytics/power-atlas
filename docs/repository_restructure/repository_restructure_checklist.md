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

**Status:** complete  
**Owner:** Ash  
**Blockers:**  
**Notes:** The accepted Phase 1 posture is now proven and documented. Canonical execution uses the `demo/` CLI path against live Neo4j with explicit dataset and run-id targeting. The validated baseline uses `demo_dataset_v1`; the validated companion isolation path uses `demo_dataset_v2`; the accepted automation entrypoint is `make phase1-verify` or `bash scripts/phase1_verify.sh`. Python 3.11+ is required. The accepted model posture is `gpt-5.4`, either via the patched default path with `OPENAI_MODEL` unset or by explicitly setting `OPENAI_MODEL=gpt-5.4`. The latest full harness rerun on 2026-04-27 completed successfully at commit `8e57fb2856b153ec0fad36fd5e8dd73ab3807ac6`; artifacts were written to `artifacts/repository_restructure/phase1/20260427T201502Z`, and baseline, companion, plus isolation re-ask flows all remained fully cited with no citation fallback.

### Exit criteria

- critical-path smoke scenarios are defined,
- baseline outputs are captured for selected golden-path scenarios,
- at least one Neo4j-backed integration path is runnable,
- package/import behavior is validated in CI or a reproducible local command,
- the team has written down what counts as “behavior preserved” for the first migration moves.

### Phase 1 deliverables checklist

- [x] identify critical CLI flow
- [x] identify critical API flow, if backend/API is an active product boundary
- [x] identify critical graph retrieval flow
- [x] identify critical answer/citation flow
- [x] identify critical ingestion or enrichment flow, if in active scope
- [x] choose at least one golden-path scenario for stable output comparison
- [x] define at least one Neo4j-backed integration path
- [x] define package/import validation check
- [x] document how baseline outputs will be captured and reviewed
- [x] document what failures block Phase 2

---

## Phase 2 — Package foundation and composition root

**Status:** in progress  
**Owner:** Ash  
**Blockers:**  
**Notes:** The package foundation has landed and is validated, so this phase is no longer untouched future work. `src/power_atlas/`, `pyproject.toml`, editable install, initial `bootstrap/`, typed settings, and installed-package import proof are all present. The package-first migration has already promoted multiple contract modules into `src/power_atlas/contracts/` while preserving `demo/contracts` as a compatibility layer. Since the last documentation refresh, bootstrap/settings ownership has expanded across active entrypoints and helpers: `demo/smoke_test.py`, `demo/reset_demo_db.py`, `demo/run_demo.py`, `demo/narrative_extraction.py`, `pipelines/query/graph_health_diagnostics.py`, `pipelines/query/retrieval_benchmark.py`, and `power_atlas.contracts.paths.resolve_dataset_root(...)` now route more of their settings/default-resolution and Neo4j construction through package-owned seams. Follow-up slices also moved first-party live OpenAI guards, temporary vendor env mutation in `pdf_ingest`, and dataset-env selection in `run_demo` behind shared bootstrap helpers. The remaining first-party env-touch cases now appear intentionally local: the demo-specific `UNSTRUCTURED_RUN_ID` runtime override in `run_demo` and the preserved missing-password guard path in `reset_demo_db`. The current checkpoint should be read as: Phase 2 foundation deliverables are complete, the env/default-resolution cleanup lane has reached a strong local checkpoint, broader compatibility-preserving package adoption/bootstrap work is still in progress, formal shim retirement has not started, and the latest full `make phase1-verify` run on 2026-04-27 finished with fully cited baseline, companion, and isolation asks and no citation fallback.  

### Exit criteria

- `src/power_atlas/` exists,
- package installation works,
- bootstrap entrypoint exists,
- typed config/settings entrypoint exists,
- entrypoints can import through installed package layout,
- no new repo-root-only import hacks are introduced.

### Phase 2 deliverables checklist

- [x] create `src/power_atlas/`
- [x] add package `__init__.py`
- [x] add or update packaging metadata (`pyproject.toml` or equivalent)
- [x] verify editable install
- [x] add initial `bootstrap/`
- [x] add initial typed settings/config entrypoint
- [x] prove imports work through installed package path

---

## Phase 3 — Mechanical promotion of current implementation

**Status:** in progress  
**Owner:**  
**Blockers:**  
**Notes:** Low-risk contract promotion has already started additively: multiple contract modules now live under `src/power_atlas/contracts/` and remain reachable through tracked `demo/contracts` compatibility shims. Do not read this as full Phase 3 closure. `demo/` is still the active execution center, and broader implementation movement plus intentional shim retirement planning remain open.  

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

**Status:** in progress  
**Owner:**  
**Blockers:**  
**Notes:** Initial seam extraction is underway but incomplete. In first-party live code, Neo4j driver construction now largely routes through `power_atlas.bootstrap.create_neo4j_driver(...)`, more entrypoint config/default ownership now flows through `build_settings(...)` plus `build_runtime_config(...)`, and the remaining env/default cleanup work has been reduced mostly to intentional runtime overrides rather than scattered initialization debt. Follow-on slices have now also landed package-owned run-scope query seams plus first write/query seams for `claim_participation` and `structured_ingest`, and the stage/orchestrator dataset-scope behavior has been thinned materially. Additional 2026-04-23 tightening passes also removed the remaining raw Neo4j config fallbacks from the query-style `graph_health` and `retrieval_benchmark` stages, so the stage-level settings-ownership lane has reached a strong local checkpoint. Subsequent query-pipeline caller cleanup moved `pipelines/query/graph_health_diagnostics.py` and `pipelines/query/retrieval_benchmark.py` onto the corresponding request-context entrypoints, while the underlying config-form stage APIs remain intentionally supported as standalone analysis surfaces for notebooks, manual diagnostics, and direct scripts. Follow-up orchestrator-thinning work then moved independent-stage spec dispatch, execution plumbing, run-id selection, and stage-manifest writing out of `demo/run_demo.py` into `power_atlas.orchestration.independent_stage_runners`, leaving `demo/run_demo.py` primarily as a seam-preserving CLI/interface layer for the current test surface rather than the owner of that coordination logic. The next retrieval-specific thinning wave also moved `retrieval_and_qa` request-context binding helpers, live-session bootstrap, execution-context prep, interactive-session prelude, and the single-shot session runner behind package-owned helpers, so that stage is now closer to a test-preserving orchestration layer than a generic helper owner. A final 2026-04-27 audit then moved the last policy-bearing `run_demo.py` helper decisions behind package-owned orchestration bridges and confirmed that the remaining `demo/run_demo.py` surface is now deliberate compatibility/composition scaffolding: local patch seams, environment/loader hooks, and small adapter callbacks rather than an unresolved ownership hotspot. The 2026-04-28 adapter-boundary pass then finished the direct Neo4j runtime-owner relocation lane by moving the remaining retrieval/runtime/query owners under `src/power_atlas/adapters/neo4j/` while preserving historical import surfaces as compatibility re-exports. That closes the Neo4j runtime-isolation subgoal for Phase 4. The remaining documented layering exceptions at this checkpoint are the config-form `graph_health` and `retrieval_benchmark` stage APIs plus `demo/run_demo.py` as an intentional compatibility/composition seam. The next Phase 4 work should therefore shift away from more Neo4j-owner relocation and toward residual interface thinning, LLM/embedding boundary cleanup, and eventual caller/shim consolidation.

### Exit criteria

- no raw Cypher remains in API/CLI/application orchestration code,
- no direct driver/client construction remains in business logic,
- interfaces are thinner and primarily call application services,
- infrastructure assembly is routed through bootstrap,
- layering violations are identified and either fixed or explicitly tracked.

### Phase 4 deliverables checklist

- [x] isolate Neo4j runtime access to adapter modules
- [ ] isolate LLM/embedding access behind adapter-facing services or interfaces
- [ ] thin API entrypoints
- [ ] thin CLI entrypoints
- [ ] move dependency construction into `bootstrap/`
- [x] document unresolved layering leaks

---

## Phase 5 — Runtime state cleanup

**Status:** ready for review  
**Owner:**  
**Blockers:**  
**Notes:** This phase is now at a reviewable checkpoint. Recent slices removed the main active dataset-state dependencies from `demo/stages/structured_ingest.py`, `demo/stages/pdf_ingest.py`, and `demo/stages/entity_resolution.py`, and `demo/run_demo.py` no longer writes dataset scope through `set_dataset_id(...)`. `demo/run_demo.py` also no longer depends on import-time snapshots of pipeline contract embedding/index settings for its live execution path, and `claim_schema`, `reset_demo_db`, `pdf_ingest`, plus `retrieval_and_qa` now read those settings through explicit snapshot-backed helpers instead of direct import-time constant bindings to mutable pipeline globals. The deprecated dataset-state compatibility API and the remaining public non-dataset pipeline globals have now been removed from `power_atlas.contracts.pipeline`; that module's remaining private cache/backing state has now also been narrowed from multiple field-level mutable globals to a single cached state object plus explicit snapshot/raw-config getters and narrow test override helpers. The old process-wide page-tracking coordinator singleton in `demo/io/page_tracking.py` has also been replaced with task-local `ContextVar` storage, so loader/splitter page offsets no longer travel through mutable process-global state. `demo/stages/graph_health.py` also no longer freezes the cluster-fragmentation query at import time; it now generates the query on demand from the live entity-resolution normalization helper instead. `demo/stages/retrieval_and_qa.py` now also rebuilds the selected retrieval query on demand for the active dry-run/live execution paths and manifest contract recording, while preserving the historical exported `_RETRIEVAL_QUERY_*` constants only as compatibility snapshots for the heavy query-contract test surface. `demo/stages/claim_participation.py` now also has a RequestContext entrypoint, and the orchestrated `demo/run_demo.py` ingest path routes both claim participation and its retrieval passes through request-context helpers rather than dropping back to older config-parameter stage calls mid-pipeline. `demo/run_demo.py` also no longer forces `refresh_pipeline_contract()` at module import time; pipeline reloads now happen only through explicit test-owned refresh calls or the normal bootstrap/snapshot path. The pipeline contract module's unused private compatibility interception and dead backing globals have also now been removed, leaving the cached state, snapshot getter, raw-config getter, and explicit refresh helpers as the remaining supported surface. The duplicated stage-local pipeline contract compatibility helper logic in `demo/stages/pdf_ingest.py` and `demo/stages/retrieval_and_qa.py` has also now been centralized into a shared stage utility, and the remaining dynamic stage export compatibility hooks in those modules have now been removed as well; focused tests now assert live runtime outputs directly instead of relying on pseudo-constant stage attributes. The pipeline contract module itself also no longer forces a load at import time; the remaining cache boundary is now exercised only through explicit refresh calls or the snapshot/raw-config getters used by bootstrap and runtime consumers. Claim extraction lexical config and the reset path now also accept explicit pipeline contract snapshots, and the request/app-context owned callers in `demo/stages/claim_extraction.py`, `demo/reset_demo_db.py`, and `demo/run_demo.py` pass those snapshots directly instead of re-reading the cache in those flows. The shared stage pipeline contract helper plus the active `pdf_ingest` and retrieval helpers now also accept explicit snapshots, and their request-context paths pass owned contract state through those internals instead of falling back to the module cache. The final tightening pass now moves the active runtime stage helpers onto bootstrap-built `Config` / `RequestContext` ownership for pipeline contract state, removes the remaining direct stage-level reads from `power_atlas.contracts.pipeline`, and makes claim-schema lexical-config runtime use explicit via an injected snapshot. The next follow-up slice also removes the remaining reset/runtime fallback: `demo/reset_demo_db.py` now requires an explicit `PipelineContractSnapshot` for `run_reset(...)`, and both its CLI help text and `main()` resolve that snapshot through bootstrap-built app context instead of direct pipeline-module reads. An initial `AppContext` / `RequestContext` seam now exists in the package and is already used by bootstrap helpers plus `demo/run_demo.py` argument handling, ask-scope resolution, orchestrated/independent execution paths, and a dedicated ask-specific preparation/execution lane that preserves pre-resolved request metadata directly through the RequestContext-based orchestration helpers. The first stage-facing retrieval entrypoints now also accept `RequestContext` directly for both single-turn and interactive ask execution, claim extraction now has a matching context-aware entrypoint used by both orchestrated ingest and independent `extract-claims` execution, claim participation now follows the same pattern for the orchestrated ingest path, entity resolution now follows the same pattern for both orchestrated ingest and independent `resolve-entities` execution, `pdf_ingest` now also has a context-aware entrypoint used by both orchestrated ingest and independent `ingest-pdf` execution, and `structured_ingest` now follows the same pattern for both orchestrated ingest and independent `ingest-structured` execution. Additional 2026-04-23 tightening passes removed the remaining stage-level raw Neo4j compatibility fallbacks from `claim_extraction`, `pdf_ingest`, `entity_resolution`, `graph_health`, and `retrieval_benchmark`; removed the historical default dataset fallback from `entity_resolution`; and moved the remaining live `openai_model` reads in `claim_extraction` and `pdf_ingest` onto settings-backed/request-context-owned inputs. Follow-up retrieval thinning then moved the `retrieval_and_qa` request-context binding helpers, live-session bootstrap, execution-context prep, interactive-session prelude, and single-shot session runner behind package-owned helper modules, leaving the stage mostly as a test-preserving orchestration layer around patch-sensitive callbacks and stage-local test seams. Follow-up caller migration then moved the standalone query-pipeline scripts for graph health and retrieval benchmark onto request-context entrypoints as well, while the config-form stage functions themselves remain intentionally supported standalone analysis surfaces rather than accidental compatibility leftovers. A final 2026-04-27 audit then moved the last policy-bearing `demo/run_demo.py` helper decisions behind package-owned orchestration bridges and confirmed that the remaining `demo/run_demo.py` surface is now intentional compatibility/composition scaffolding rather than residual mutable-state ownership. The remaining explicit runtime-state exceptions are now documented rather than implicit: the private `power_atlas.contracts.pipeline` cache boundary and the demo-owned `UNSTRUCTURED_RUN_ID` environment override for manual CLI scope selection. That leaves this lane at a verified local checkpoint: the mutable runtime-state inventory is closed, high-risk globals have been removed or isolated, the latest full `make phase1-verify` rerun remains green, and future work in this area should center on test-surface cleanup plus broader interface consolidation rather than more seam-by-seam state tightening.  

### Exit criteria

- `AppContext` is defined and used where required,
- `RequestContext` is defined and used where relevant,
- known mutable process-global runtime state is removed or explicitly tracked,
- new runtime state follows explicit injection/context rules.

### Phase 5 deliverables checklist

- [x] define `AppContext`
- [x] define `RequestContext`
- [x] inventory existing mutable global runtime state
- [x] replace or isolate high-risk globals
- [x] document any deferred state cleanup

---

## Phase 6 — Neo4j operationalization

**Status:** in progress  
**Owner:**  
**Blockers:**  
**Notes:** The top-level `neo4j/` boundary now exists in the repo with an initial operational README plus tracked subdirectories for `constraints/`, `indexes/`, `migrations/`, `diagnostics/`, and `seed/`. This closes the “directory does not exist” gap from Decision 6 and gives the migration a single home for graph operational assets. Current workflow and ownership are now documented without over-claiming implementation maturity: local provisioning still uses `docker compose up -d neo4j`, demo reset still flows through `demo/reset_demo_db.py`, candidate-vs-authoritative graph handling still depends on Decision 7 rather than a finalized implementation mechanism, the first concrete externalized index asset now exists at `neo4j/indexes/demo_chunk_embedding_index.cypher`, the first concrete operational diagnostic now exists at `neo4j/diagnostics/check_demo_chunk_embedding_index.cypher`, the current demo reset wipe/index-drop scope is now externalized under `neo4j/diagnostics/demo_reset_scope.md` plus `neo4j/diagnostics/check_demo_reset_scope.cypher`, and the current local/test provisioning workflow is now consolidated at `neo4j/local_dev_workflow.md`. Phase 6 is therefore active but not complete: the boundary, execution order, local/test workflow, one stable index asset, multiple stable read-only diagnostics, and the current demo reset inventory are now documented, while broader externalization of constraints, migrations, diagnostics, and seed assets remains future work.  

### Exit criteria

- top-level `neo4j/` structure is established,
- graph schema/index setup is reproducible,
- candidate vs authoritative graph strategy is documented,
- local/test graph lifecycle is documented,
- ownership boundary between runtime graph code and graph operational assets is clear.

### Phase 6 deliverables checklist

 [x] create or normalize top-level `neo4j/`
 [x] define migrations approach
 [x] define constraints/indexes approach
 [x] define seed/diagnostics approach
 [x] document candidate vs authoritative graph handling
 [x] document local/test provisioning workflow
 [x] document execution order for graph setup

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

**Status:** completed  
**Owner:**  
**Blockers:**  
**Notes:** Interface consolidation is now at its intended Phase 8 checkpoint rather than just underway. First-party CLI parsing and transport flow now live under `src/power_atlas/interfaces/cli/` for the maintained `demo/`, `pipelines/query/`, and `scripts/` entrypoints, while those historical files remain as stable compatibility shells and runtime-bearing functions stay with their existing application/runtime owners. API transport follows the same pattern: `backend/main.py` is a compatibility shell, `src/power_atlas/interfaces/api/backend_app.py` owns app creation and middleware, and `src/power_atlas/interfaces/api/backend_routes.py` owns the current route table. The accepted boundary rule is now documented in the decisions register: parser/default resolution, request-context assembly, guards, dispatch, warning routing, stdout emission, and route registration belong under `interfaces`, while outcome-bearing runtime behavior remains outside that layer. The explicit worker decision is also now verified for this phase: Decision 11 continues to defer worker architecture by default, and no first-party async job surface was identified that would justify introducing `interfaces/workers/` during this checkpoint.  

### Exit criteria

- CLI lives under `interfaces/cli`,
- API lives under `interfaces/api`,
- transport concerns are separated from orchestration,
- worker interfaces are added only if explicitly approved.

### Phase 8 deliverables checklist

- [x] consolidate CLI entrypoints
- [x] consolidate API entrypoints
- [x] verify worker need before adding worker interfaces
- [x] document transport/application boundaries

---

## Phase 9 — Frontend decision and contract alignment

**Status:** completed  
**Owner:**  
**Blockers:**  
**Notes:** Frontend positioning is now explicit at the current checkpoint. The in-repo `frontend/` package remains a transitional/non-core Next.js shell rather than the primary product execution surface. Its current backend dependency is intentionally narrow: `frontend/app/page.tsx` reads `NEXT_PUBLIC_BACKEND_URL` and calls `GET /health`, while the backend API remains a stub surface exposing `GET /`, `GET /health`, and placeholder `GET /graph/status` from `src/power_atlas/interfaces/api/backend_routes.py`. That is sufficient to treat the frontend as intentionally deferred from the main graph-product lane rather than unresolved. Backend contract expectations are therefore documented as placeholder-only for now, and formal schema-versioning work remains deferred until the backend exposes non-placeholder graph operations that a frontend is expected to consume materially.  

### Exit criteria

- frontend repository position is explicit,
- backend contract expectations are documented,
- `frontend/` is either active and aligned, or explicitly deferred/non-core.

### Phase 9 deliverables checklist

- [x] decide active status of frontend
- [x] document how frontend consumes backend contracts
- [x] defer or normalize `frontend/` intentionally

---

## Phase 10 — Legacy retirement

**Status:** in progress  
**Owner:**  
**Blockers:**  
**Notes:** Phase 10 planning has now started with a concrete shortlist document in `docs/repository_restructure/repository_restructure_phase10_legacy_retirement_shortlist.md`, and the first retirement implementation slices are complete. First, the empty `__queuestorage__/` directory was verified unused and removed after a workspace search found no supported queue-storage or Azure Functions dependency. Second, `_archive/` is now explicitly labeled as archival, non-active material in both `_archive/README.md` and the root `README.md`, while its historical contents remain in place for reference. Third, the first `demo.contracts` simple-shim slice removed `demo/contracts/resolution.py`, `demo/contracts/retrieval_early_return_policy.py`, and `demo/contracts/retrieval_metadata_policy.py` after caller re-inventory showed no non-test runtime usage. Fourth, the second zero-caller simple-shim slice removed `demo/contracts/claim_schema.py`, `demo/contracts/manifest.py`, `demo/contracts/paths.py`, `demo/contracts/runtime.py`, and `demo/contracts/structured.py`, and `tests/test_power_atlas_package.py` continued to pass after retiring the matching compatibility tests. The remaining shim lane is now effectively `demo/contracts/prompts.py`, followed later by the root proxy and the pipeline alias. The compatibility shells under `demo/`, `pipelines/query/`, `scripts/`, and `backend/` remain intentionally out of scope for deletion.  

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
- one critical API flow, if the backend/API is an active product boundary,
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
- [x] critical-path scenarios are documented
- [x] at least one golden-path scenario is defined
- [x] at least one Neo4j-backed integration path is defined
- [x] package/import validation approach is defined
- [x] “behavior preserved” criteria are documented
- [x] initial owners for Phase 1 and Phase 2 are assigned

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

### Accepted Phase 1 criteria

For Phase 1 gate purposes, behavior is explicitly accepted as preserved when all of the following remain true:

- the canonical command path runs through module invocation (`python -m demo.run_demo ...`) under Python 3.11+,
- the validated execution posture uses `gpt-5.4` either by leaving `OPENAI_MODEL` unset or by explicitly setting `OPENAI_MODEL=gpt-5.4`,
- the baseline sequence for `demo_dataset_v1` completes end-to-end from reset with explicit `UNSTRUCTURED_RUN_ID` capture and explicit `--run-id` targeting on `ask`,
- the companion `demo_dataset_v2` run-isolation sequence completes without reset after the baseline and preserves run-scoped retrieval isolation,
- answer generation succeeds with citation-quality invariants intact for known-good baseline and isolation checks (`all_answers_cited: true`, `citation_fallback_applied: false`, `citation_quality.evidence_level: "full"`),
- `make phase1-verify` or `bash scripts/phase1_verify.sh` captures logs, manifests, validation summary, and run metadata under `artifacts/repository_restructure/phase1/<timestamp>/`.

### Known acceptable differences

Document any allowed differences here, for example:

- output formatting changes that do not alter contract semantics,
- logging changes,
- file location changes for internal implementation details,
- non-user-facing naming cleanup.

For Phase 1, the following are explicitly accepted:

- natural-language answer wording may vary as long as the accepted structural invariants and citation-quality signals hold,
- retrieval hit counts may vary across clean runs as long as retrieval is non-empty for known-good prompts and cross-run isolation is preserved,
- warning-not-error handling for deliberate cross-dataset mismatch probes remains acceptable because it is visible to operators and is not part of the accepted Phase 1 verification harness,
- minor helper-text drift that does not affect the canonical module-invocation path does not block Phase 1 closure.

---

## 6. Temporary compatibility shim tracker

Use this table to track temporary migration shims so they do not become permanent architecture.

| Shim path / module | Introduced in PR | Purpose | Owner | Removal trigger | Status |
|---|---|---|---|---|---|
| `demo/contracts/__init__.py` | local Phase 2 package-first slices through 2026-04-16 | Compatibility proxy to package-owned contract exports while legacy demo imports remain supported | Ash | Replace demo-root contract imports with package-native imports and approve a formal shim deprecation/removal plan | active |
| `demo/contracts/*.py` package-owned contract shims | local Phase 2 package-first slices through 2026-04-16 | Preserve import compatibility while package-owned contract modules under `src/power_atlas/contracts/` become authoritative | Ash | Complete deliberate shim retirement plan; remove only after callers and compatibility obligations are intentionally closed | active |
| `demo/contracts/pipeline.py` module-alias shim | local Phase 2 pipeline promotion slice on 2026-04-16 | Preserve shared mutable module identity between `demo.contracts.pipeline` and `power_atlas.contracts.pipeline` | Ash | Only remove after stateful pipeline access no longer needs demo-surface compatibility and a dedicated retirement plan is accepted | active |

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
| API schema versioning approach | Phase 8 / 9 |  | in progress | Placeholder-only API/frontend contract documented; formal versioning deferred until non-placeholder frontend-consumed graph APIs exist |
| Worker necessity decision | Phase 8 |  | completed | Deferred by Decision 11; no current first-party async job surface justifies `interfaces/workers/` |
| `demo.contracts` deprecation / retirement strategy | Phase 2 / 10 | Ash | in progress | Follow-up task is captured in `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`; current recommendation is to complete planning in Phase 2 and defer actual shim-removal implementation to Phase 10 while `demo/` remains the active execution surface |

---

## 8. Immediate next actions

Use this section as the working short list.

- [x] decide whether to close Phase 2 formally now that the foundation deliverables are complete or keep it open until broader package adoption/bootstrap work reaches a clearer checkpoint
- [x] execute the follow-up planning task in `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`
- [x] start the next migration lane on broader bootstrap/composition-root adoption in first-party live code instead of treating shim retirement as the next implementation slice
- [x] audit remaining first-party env/default reads and direct infrastructure construction to separate true initialization debt from intentional runtime guards
- [ ] pick the next substantive Phase 4 seam after the env/default cleanup checkpoint, with priority on raw Cypher isolation and thinner orchestration boundaries rather than more env/default refactors
- [x] re-run the full `make phase1-verify` gate after the recent bootstrap/default-resolution cleanup and record whether the earlier one-off citation fallback reproduces