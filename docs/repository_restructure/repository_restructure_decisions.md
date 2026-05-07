# Repository Restructure Decision Register

Status: Accepted  
Applies to: `zoomlytics/power-atlas`  
Related plan: `docs/repository_restructure/repository_restructure_plan.md`

This document records the minimum architecture and migration decisions that must be explicit before major repository restructuring begins.

It is intended to:

- eliminate ambiguity before implementation,
- prevent architectural drift during migration,
- provide decision-level guidance for code review and sequencing,
- complement the canonical migration plan.

During restructuring work, this document should be used as the default decision reference for sequencing, boundary enforcement, and code review expectations.

It is **not** intended to be a full ADR archive.  
If a decision becomes large or controversial, it can be split into a dedicated ADR later.

---

## Decision 1 — Canonical package target

### Decision

The product codebase will be migrated toward a `src/`-based package layout rooted at:

```text
src/power_atlas/
```

The initial package structure will remain intentionally shallow:

```text
src/power_atlas/
├── core/
├── application/
├── adapters/
├── interfaces/
├── schemas/
└── bootstrap/
```

Fine-grained subpackage expansion is deferred until the code naturally stabilizes into clear clusters.

### Why

- The current repository structure does not clearly reflect the true product core.
- A `src/` layout improves import discipline, packaging, and test realism.
- A shallow first-pass structure reduces migration churn and avoids premature taxonomy decisions.

### Consequences

- Early migration work should focus on package rooting and behavior preservation, not subdirectory proliferation.
- New code should target the package structure, not legacy execution paths.
- Additional subpackages should be created only when there is clear cohesion and sustained need.

### Open Questions

None blocking for initial migration.

## Decision 2 — Layering model and dependency direction

### Decision

The restructuring will follow a layered architecture with the following intended dependency direction:

- `core` -> depends on no internal infrastructure layers
- `application` -> may depend on `core` and `schemas`
- `adapters` -> may depend on `application`, `core`, and `schemas`
- `interfaces` -> may depend on `application`, `schemas`, and `bootstrap`
- `bootstrap` -> may depend on all layers needed to assemble the application

Layer intent:

- `core`: holds domain concepts, invariants, value objects, and narrowly scoped pure logic.
- `application`: holds use cases, orchestration, service coordination, and application workflows.
- `adapters`: holds infrastructure implementations such as Neo4j, LLMs, embeddings, storage, telemetry, and config loading.
- `interfaces`: holds user/system entrypoints such as API and CLI boundaries.
- `bootstrap`: holds composition-root wiring for settings, clients, services, and entrypoint assembly.

### Why

- The current repo needs enforceable dependency boundaries.
- The application needs a durable center of gravity that is not coupled directly to transport or storage layers.
- A composition root reduces scattered construction and hidden runtime coupling.

### Consequences

- `application` should become the practical center of the codebase.
- `core` must remain intentionally narrow.
- `interfaces` must stay thin and avoid turning into orchestration layers.
- `bootstrap` becomes the only place where broad dependency construction is allowed.

### Implementation checkpoint (2026-04-30)

- Phase 8 has now established a concrete thin-interface pattern rather than only a future intent: first-party CLI and API entrypoints increasingly remain as compatibility shells while package-owned `interfaces` modules own parser, transport, and entrypoint glue.
- Under `interfaces/cli`, package-owned support and entrypoint modules now own the transport flow for `demo/run_demo.py`, the package-native `power_atlas.narrative_extraction_cli` caller surface, `demo/reset_demo_db.py`, `demo/smoke_test.py`, `pipelines/query/graph_health_diagnostics.py`, `pipelines/query/retrieval_benchmark.py`, and `scripts/sync_vendor_version.py`; the reset behavior and the retained narrative-extraction CLI surface now both live under `src/power_atlas/`, while `demo/reset_demo_db.py` remains the stable compatibility seam.
- The accepted boundary rule is now explicit rather than inferred from code motion: parser/defaults, request-context assembly, password/confirm guards, dispatch, stdout/stderr formatting, and route registration belong under `interfaces`; artifact construction, dry-run/live branching, stage-specific writes, query/runtime execution, and other behavior that materially changes application outcomes stay with application or runtime owners.
- Compatibility shells are now a deliberate migration device, not a sign that ownership is unresolved. A legacy `demo/`, `pipelines/`, `scripts/`, or `backend/` file may remain as a stable import or execution seam even after its transport logic has moved package-side.
- The earlier narrative-extraction runtime-side exception is now closed: the retained caller surface is `src/power_atlas/narrative_extraction_cli.py`, and `demo/narrative_extraction.py` is retired under Decision 40 rather than remaining a current `interfaces/cli` exception.
- Under `interfaces/api`, `backend/main.py` is now a compatibility shell, `src/power_atlas/interfaces/api/backend_app.py` owns app creation and middleware setup, and `src/power_atlas/interfaces/api/backend_routes.py` owns the current route table. This establishes the same pattern for API transport as the CLI lane without prematurely inventing a larger backend architecture.

### Follow-up checkpoint (2026-05-07)

- The Phase 4 interface-thinning goal should now be read as satisfied rather than merely underway: the active API and CLI entrypoints already behave as thin transport/compatibility shells over package-owned `interfaces` helpers.
- The surviving `demo/run_demo.py` shell is now a deliberate compatibility/composition seam. It still owns `parse_args`, lazy local patch seams, and a small amount of operator-facing glue, but the policy-bearing ask-scope, dispatch, and runtime-resolver assembly now live behind package-owned helpers.
- The focused `main()` workflow regressions in `demo/tests/test_demo_workflow.py` no longer force additional shell thinning. Aside from the intentional `parse_args` seam, the remaining `demo.run_demo` workflow tests already patch package-owned interception points; the remaining shell-local patches in that file belong to the separate `reset_demo_db` lane.
- Focused 2026-05-07 verification also confirms that the last plausible query-pipeline Phase 4 holdouts are closed: `pipelines/query/graph_health_diagnostics.py` and `pipelines/query/retrieval_benchmark.py` both build request context through package-owned CLI support helpers and dispatch through their `RequestContext` stage entrypoints, and the narrow request-scope plus CLI regression slices for both lanes pass.
- The remaining work under the interface-layer decisions is therefore architectural choice rather than cleanup pressure: either keep `demo/run_demo.py` as a long-term compatibility shell and track it as such, or move the final `run_demo_main(...)` construction package-side only if that materially simplifies ownership.

### Open Questions

Whether any shared contracts should live in `schemas/` or be localized more aggressively can be refined later.

## Decision 3 — Composition root and infrastructure construction

### Decision

`bootstrap/` will be the composition root for the application.

This means:

- settings are loaded there or delegated from there,
- infrastructure clients are assembled there,
- adapter implementations are created there,
- application services are wired there,
- entrypoints obtain dependencies from there rather than constructing them ad hoc.

### Why

- Construction logic is currently at risk of being scattered across scripts, APIs, and utilities.
- Centralized wiring makes testing, configuration, and context handling more explicit.
- This reduces the chance of hidden singletons and inconsistent runtime initialization.

### Consequences

- New interface code should not directly construct Neo4j drivers, model clients, or config loaders.
- Existing code that performs infrastructure construction outside of `bootstrap` should be treated as migration debt.
- Dependency injection can remain lightweight and manual; a framework is not required.

### Implementation checkpoint (2026-04-23)

- typed settings plus `bootstrap`-owned runtime config assembly are already the active path for the main `demo/` entrypoints,
- first-party default resolution and most live Neo4j construction now already flow through package-owned seams,
- the remaining work under this decision is primarily orchestration thinning and adapter relocation rather than basic bootstrap adoption.

### Follow-up checkpoint (2026-05-07)

- The active interface and orchestration lanes now route their dependency construction through package/bootstrap-owned seams strongly enough that the original Phase 4 bootstrap objective should be treated as satisfied.
- The remaining bootstrap-related work is sign-off and exception handling, not broad interface-local constructor removal: the question now is whether any deliberate compatibility shell or cached-state exception should stay documented, not whether the codebase still broadly constructs runtime dependencies ad hoc from CLI/API surfaces.

### Open Questions

Whether `bootstrap` will be a small module tree or a single assembly module can be decided during implementation.

## Decision 4 — Runtime context model v1

### Decision

The initial explicit runtime context model will include only:

- `AppContext`
- `RequestContext`

`RunContext` and `DatasetContext` are deferred unless the code demonstrates they solve active confusion that cannot be handled cleanly otherwise.

Intended semantics:

- `AppContext`: long-lived process-level dependencies and configuration, such as settings, service registry/assembled services, client factories, telemetry/logging handles, and other long-lived shared dependencies.
- `RequestContext`: per-invocation or per-request execution metadata, such as correlation IDs, user/request metadata, trace metadata, deadlines, and request-scoped options.

### Why

- The migration plan should remove mutable process-global runtime state.
- Starting with too many context types too early creates overlap and confusion.
- `AppContext` and `RequestContext` cover most practical first-pass needs.

### Consequences

- New code should not introduce new mutable global runtime state.
- Existing globals should be inventoried and incrementally replaced.
- If `RunContext` or `DatasetContext` are later introduced, they should be justified by concrete pain, not speculation.

### Implementation checkpoint (2026-04-23)

- `AppContext` and `RequestContext` now both exist in the package,
- `RequestContext` is already used across the main `demo/run_demo.py` ask and ingest execution lanes plus the active stage-facing entrypoints,
- `demo/run_demo.py` now mostly preserves patchable CLI/test seam names while package orchestration helpers own the independent-stage coordination logic,
- a final 2026-04-27 audit also moved the last policy-bearing `run_demo.py` helper decisions behind package-owned bridges and confirmed that the remaining `demo/run_demo.py` surface is now primarily deliberate compatibility/composition scaffolding rather than a substantive runtime owner; a follow-up 2026-05-06 interface-consolidation pass then moved the remaining ask-scope support wiring behind package-owned `run_demo_entrypoint` helpers while preserving the local `demo.run_demo` patch seams, the next shell-thinning follow-ups on the same day collapsed the remaining local wrapper assembly for ask-scope support, orchestrated and independent-stage runner wiring, and `main()` dispatch into helper builders so the shell is now even more clearly a patch-seam-preserving compatibility layer, the package-owned `run_demo_entrypoint.py` layer now also hides its remaining inline CLI dispatch dependency assembly behind a local helper rather than rebuilding that coordination block at the `run_demo_main(...)` call site, the `stage_dependency_registry` plus `cli_dispatch` boundary now groups the `run_demo` CLI dependencies by command shape rather than threading one flat bundle through the dispatcher, an initial test-surface cleanup slice now patches the package-owned ask-preparation seam in the focused interactive workflow regression instead of shell-local `_resolve_ask_scope`, a follow-up prep slice now routes the shell `_resolve_ask_scope(...)` wrapper through the package module dynamically so future tests can intercept that seam without patching shell-local wiring, a second test-surface cleanup slice now injects the fake dataset lookup for one direct wrapper warning regression through the package-owned ask-scope seam instead of shell-local `_fetch_dataset_id_for_run`, a third slice now applies that same package-owned seam pattern to the focused explicit `--run-id` wrong-dataset warning regression in `demo/tests/test_orchestrator_modules.py`, a fourth slice now applies it to the adjacent explicit `--run-id` correct-dataset no-warning regression as well, a fifth slice now applies it to the neighboring explicit `--run-id` cases that assert the dataset lookup must not be called, a sixth slice now applies it to the remaining explicit `--run-id` not-found and fixture-dataset warning variants in that same file, clearing the focused ask-scope family there of shell-local `_fetch_dataset_id_for_run` patching, a small follow-up shell-thinning pass now makes both `_resolve_ask_scope(...)` and `_resolve_ask_request_context(...)` in `demo/run_demo.py` consume the existing `_build_ask_scope_resolution_kwargs()` helper directly instead of re-spelling that dependency bundle inline, a final follow-up in that same lane now removes the unused shell-local `_resolve_ask_request_context(...)` shim entirely, one more bounded step now removes the shell-local `_prepare_ask_request_context(...)` wrapper by moving the direct source-uri regression onto the package-owned ask-preparation helper with shell callback injection while leaving `main()` to pass only a small lambda into `run_demo_main(...)`, a further package-entrypoint cleanup now moves that remaining inline ask-preparation lambda behind a package-owned builder helper so the shell no longer assembles even that callback inline, a final follow-up in the same composition lane now moves the remaining zero-arg runtime resolver assembly for interactive ask, Neo4j driver creation, and reset loader resolution behind a package-owned helper as well, and a matching test-surface cleanup slice now migrates the `main()`-driven interactive ask and reset-warning workflow regressions in `demo/tests/test_demo_workflow.py` off shell-local `run_interactive_qa_request_context` and `_load_demo_reset_runner_impl` patching onto that same package-owned runtime-resolver builder seam,
- the live retrieval path is no longer just RequestContext-aware at its entrypoints: `retrieval_and_qa` now delegates request-context binding, live-session bootstrap, execution-context prep, interactive-session prelude, and single-shot session binding to package-owned helper modules while preserving the remaining stage-level patch seams,
- the graph-analysis stage boundaries in `demo/stages/graph_health.py` and `demo/stages/retrieval_benchmark.py` now use their `RequestContext` entrypoints as the canonical runtime-owned paths, while the config-form APIs remain as explicit standalone analysis surfaces for notebooks, manual diagnostics, and direct scripts,
- the latest live `make phase1-verify` rerun on 2026-05-07 succeeded at commit `4666f6ec2b97d9f158737ae537d6a8f2f1481383`, with artifacts under `artifacts/repository_restructure/phase1/20260507T063610Z` and fully cited baseline, companion, and isolation asks,
- the remaining work under this decision is the residual mutable-global inventory and any explicit disposition around the remaining cached pipeline-contract state, and this checkpoint should be read as caller migration plus boundary consolidation rather than a default mandate to delete the surviving standalone config-form stage APIs or the now-intentional `demo/run_demo.py` CLI/test seam surface.

### Follow-up checkpoint (2026-05-07)

- The remaining runtime-state exceptions have now been explicitly accepted rather than left at a review-only checkpoint.
- The `UNSTRUCTURED_RUN_ID` override remains a deliberate demo-owned CLI behavior in `demo/run_demo.py`, and the focused regression surface still covers both precedence and dataset-mismatch warning behavior for that exception.
- The stateful `power_atlas.contracts.pipeline` cache boundary remains narrow and explicit: bootstrap reads snapshots/config data from it, runtime code consumes injected snapshots or request/app context, and direct imports outside those type/bootstrap boundaries no longer indicate broad mutable-global coupling.
- With those exceptions documented and bounded, Phase 5 should be read as complete; future work in this area is optional exception retirement, not required migration cleanup.
- The end-to-end migration closure validation has also now been re-proven live: `bash scripts/phase1_verify.sh` completed successfully on 2026-05-07 at commit `4666f6ec2b97d9f158737ae537d6a8f2f1481383`, with artifacts under `artifacts/repository_restructure/phase1/20260507T063610Z` and fully cited baseline, companion, and isolation asks.

### Open Questions

Whether offline batch execution needs a distinct run-scoped context will be revisited after safety harness and seam extraction work.

## Decision 5 — Neo4j code boundary

### Decision

All Neo4j runtime access will be isolated to adapter code under `src/power_atlas/adapters/neo4j/` or equivalent adapter-local modules.

The following rules apply:

- no raw Neo4j driver/session usage outside Neo4j adapters,
- no raw Cypher in API, CLI, or application orchestration code,
- application code may call query services, repositories, or adapter-facing interfaces,
- graph operational assets do not live inside the runtime package.

### Why

- Graph RAG systems accumulate storage-specific leakage quickly.
- Allowing Cypher in orchestration layers will weaken architecture almost immediately.
- Separating runtime graph access from graph operations reduces confusion and improves maintainability.

### Consequences

- Existing direct Cypher usage outside graph adapters becomes migration work.
- Query design should remain practical; not every query must fit a generic repository abstraction.
- Use-case-specific query services are acceptable where they better match graph retrieval behavior.

### Open Questions

The exact internal structure of the Neo4j adapter package can remain shallow at first and evolve later.

### Implementation checkpoint (2026-04-28)

- explicit adapter-local owners now exist for live retrieval session construction plus the `claim_extraction_runtime`, `claim_participation_runtime`, `entity_resolution_runtime`, `narrative_extraction_runtime`, `pdf_ingest_runtime`, `structured_ingest_runtime`, `retrieval_runtime`, `graph_health`, `retrieval_benchmark`, and `run_scope_queries` modules under `src/power_atlas/adapters/neo4j/`,
- `power_atlas.retrieval_session_setup`, `power_atlas.claim_extraction_runtime`, `power_atlas.claim_participation_runtime`, `power_atlas.entity_resolution_runtime`, `power_atlas.narrative_extraction_runtime`, `power_atlas.pdf_ingest_runtime`, `power_atlas.structured_ingest_runtime`, `power_atlas.retrieval_runtime`, `power_atlas.graph_health_queries`, `power_atlas.retrieval_benchmark_queries`, and `power_atlas.run_scope_queries` remain as compatibility re-export surfaces so existing stage/test callers do not need to migrate in lockstep,
- the direct `create_neo4j_driver(...)` runtime-owner inventory outside `adapters/neo4j` is now exhausted,
- the remaining intentional layering exception at this checkpoint is `demo/run_demo.py` as deliberate compatibility/composition scaffolding; the `graph_health` and `retrieval_benchmark` config-form stage APIs remain intentional standalone/manual analysis surfaces rather than orchestration-owned paths,
- the remaining explicit runtime-state exceptions are the private `power_atlas.contracts.pipeline` cache boundary and the demo-owned `UNSTRUCTURED_RUN_ID` environment override for manual CLI scope selection,
- the next recommended slices under this decision are interface consolidation, residual test-surface cleanup, and any future non-Neo4j adapter boundaries rather than more wrapper-only cleanup in `demo/run_demo.py`.

## Decision 6 — Neo4j operational asset boundary

### Decision

Neo4j operational assets will live in the top-level `neo4j/` directory, not under runtime package code.

This directory is expected to contain, over time:

- migrations,
- constraints,
- indexes,
- seed data,
- diagnostics,
- graph lifecycle documentation.

### Why

- Schema/index/migration concerns are operational assets, not application runtime logic.
- A top-level location makes ownership and environment lifecycle clearer.
- It helps distinguish runtime query code from graph administration.

### Consequences

- `src/power_atlas/adapters/neo4j/` is for runtime access code.
- `neo4j/` is for graph operations and lifecycle artifacts.
- The team must document how these are coordinated to avoid split-brain maintenance.

### Open Questions

Exact migration tooling and execution order are still open and must be decided separately.

## Decision 7 — Candidate vs authoritative graph strategy must be explicit

### Decision

The system will explicitly distinguish candidate graph workflows from authoritative graph workflows, and this distinction must be documented before graph operationalization is considered complete.

This decision does not yet lock the implementation mechanism.

Possible implementation models still to be decided include:

- physical separation across databases,
- logical separation within one database,
- distinct labels/namespaces/subgraphs,
- staged promotion pipelines.

### Why

- This is a foundational product/data boundary, not a naming preference.
- If left ambiguous, ingestion, retrieval, evaluation, and operational workflows will drift.
- Neo4j migrations, testing, and evaluation design all depend on this boundary eventually being explicit.

### Consequences

- Teams should avoid baking accidental assumptions about graph authority into application flows.
- Graph setup and test design should anticipate this distinction.
- A concrete implementation decision is still required before later migration phases.

### Open Questions

- Physical vs logical separation.
- Promotion semantics.
- Environment-specific lifecycle and reset strategy.

## Decision 8 — Configuration system must be typed and centralized

### Decision

The repository will adopt a typed, centralized configuration approach rather than ad hoc environment lookups scattered through the codebase.

The specific library/tooling is not locked in this document, but the configuration approach must support:

- explicit source precedence,
- environment-file loading rules,
- secret handling,
- test overrides,
- local/dev/prod configuration shapes.

### Why

- Configuration affects `bootstrap`, testability, runtime context, and operational behavior.
- Deferring config design until late in the migration would increase churn.
- Typed settings reduce hidden assumptions and improve maintainability.

### Consequences

- New code should avoid direct, scattered `os.environ` access outside config handling.
- `bootstrap` should become the main entrypoint for resolved settings.
- Existing configuration sprawl should be treated as restructuring debt.

### Implementation checkpoint (2026-04-23)

- typed settings are already present and active in the repo,
- `bootstrap` is already the main entrypoint for resolved settings/default ownership across the main `demo/` entrypoints and helper flows,
- remaining environment-touch cases are now mostly intentional local overrides or operator-visible guardrails rather than broad configuration sprawl.

### Open Questions

- Exact settings library.
- Whether separate environment profiles are file-based, class-based, or both.

## Decision 9 — Prompt handling must be centralized before deeper refactor

### Decision

Prompts must be treated as managed application assets, not as arbitrary inline strings distributed throughout the codebase.

The final prompt asset model is still open, but until it is decided:

- prompt definitions should be centralized,
- new prompt sprawl should be avoided,
- prompt changes should remain traceable.

Candidate future models:

- code-defined prompt templates,
- file-based prompt assets,
- versioned strategy objects,
- hybrid model with explicit metadata.

### Why

- Prompt behavior is a core part of Graph RAG behavior.
- Evaluation reproducibility depends on prompt traceability.
- Scattered prompt logic becomes difficult to test, review, and version.

### Consequences

- New features should not introduce ad hoc prompt placement.
- The eventual prompt/versioning strategy must align with evaluation and run artifact tracking.
- Prompt decisions should be made before evaluation infrastructure grows.

### Open Questions

- File-vs-code storage model.
- Versioning mechanism.
- How runs will record prompt/model/retrieval settings together.

## Decision 10 — API contracts are owned as explicit schemas

### Decision

If the repository exposes API boundaries consumed by other interfaces such as `web/`, those contracts must be represented through explicit schemas rather than implicit Python internals.

### Why

- The frontend should consume contracts, not application internals.
- Contract drift becomes a major risk during a repository restructure.
- Explicit schema ownership creates a stable collaboration boundary.

### Consequences

- `schemas/` is the default home for shared transport and API contracts unless a later documented decision establishes a better localized structure.
- Backend changes that affect contracts should be reviewed as contract changes, not just internal refactors.
- Frontend positioning should remain secondary until backend contracts stabilize.

### Implementation checkpoint (2026-04-30)

- The repository currently contains a minimal Next.js frontend under `frontend/`, but it is not yet the primary product surface for graph workflows.
- The current frontend-to-backend contract is intentionally narrow: `frontend/app/page.tsx` reads `NEXT_PUBLIC_BACKEND_URL` and performs a simple health check against `GET /health` on the backend API.
- The backend contract exposed to that frontend is currently limited to the existing stub endpoints in `src/power_atlas/interfaces/api/backend_routes.py`: `GET /`, `GET /health`, and placeholder `GET /graph/status`.
- This means the frontend is best classified at this checkpoint as a transitional/non-core interface shell rather than a stabilized product UI. It is allowed to exist in-repo, but it should not drive backend contract design ahead of the package-first restructure.
- Formal schema versioning is therefore still deferred for the current placeholder API surface. The next contract-bearing decision should happen only when the backend exposes non-placeholder graph operations that the frontend is expected to consume beyond health/status checks.

### Open Questions

- Versioning approach for API schemas.
- Whether schemas are generated or maintained manually.

## Decision 11 — Workers are deferred by default

### Decision

Worker architecture is not assumed to be part of the first-pass restructure.

`interfaces/workers/` and queue-related abstractions should be introduced only if there is an already-real or immediately committed async execution model that requires them.

### Why

- Worker architecture is not a harmless placeholder; it implies queue, retry, idempotency, and observability decisions.
- Premature worker formalization adds surface area without proven value.
- The current restructure should prioritize the product core and runtime boundaries first.

### Consequences

- The migration should not create worker abstractions "just in case."
- If async jobs become necessary, that decision should be documented explicitly and introduced intentionally.
- Current planning should assume CLI/API first unless the product already proves otherwise.

### Open Questions

Whether ingestion, evaluation, or enrichment flows will require asynchronous execution soon.

## Decision 12 — Correctness testing and evaluation are separate concerns

### Decision

The repository will explicitly separate:

- `tests/` for correctness verification,
- `eval/` for benchmark datasets, rubrics, benchmark scenarios, and evaluation reports.

### Why

- Correctness and evaluation have different goals, cadence, and failure semantics.
- Mixing them creates CI confusion and weakens both.
- The migration plan depends on a safety harness before deeper movement.

### Consequences

- Safety harness work belongs in correctness testing.
- Evaluation artifacts should not be treated as ordinary test fixtures.
- CI should distinguish correctness gates from benchmark/evaluation workflows.

### Open Questions

- Exact `eval/` directory taxonomy.
- Whether reports are committed, generated, or externalized.

## Decision 13 — First migration implementation must prioritize safety harness over package beautification

### Decision

After this decision register is accepted, the next implementation priority is a migration safety harness, not a broad structural move.

This means the first practical implementation work should focus on:

- critical-path smoke tests,
- one or more golden-path scenarios,
- at least one Neo4j-backed integration path,
- package/import validation in CI or reproducible local execution.

### Why

- Large repository movement without behavioral feedback is high risk.
- The migration plan explicitly changed sequencing to bring safety earlier.
- This is the most important control against accidental rewrites.

### Consequences

- Package movement should not begin until the team has at least minimal behavioral checks.
- The first code PRs should be small and control-oriented.
- Success is defined by preserved behavior, not just cleaner folders.
- Temporary compatibility shims are allowed only as migration aids and must be tracked with an owner and explicit removal condition.

### Open Questions

Which exact flows are designated as critical-path scenarios.

## Decision 14 — The revised migration plan is the canonical execution plan

### Decision

`docs/repository_restructure/repository_restructure_plan.md` is the canonical execution plan for repository restructuring and supersedes prior drafts.

### Why

- The repository should not maintain multiple conflicting migration plans as parallel authority.
- The revised plan incorporates sequencing and scope corrections that are essential before implementation begins.

### Consequences

- Future restructure guidance should update or reference the canonical plan rather than creating redundant plan documents.
- Older drafts should be treated as background context only if preserved at all.
- Companion documents such as this decision register and future checklists should support the canonical plan, not compete with it.

### Open Questions

None blocking.

## Decision 15 — Stateful pipeline contract stays submodule-only at package root

### Decision

`power_atlas.contracts.pipeline` is the canonical package location for the
stateful pipeline contract, but its mutable names are intentionally not
re-exported from `power_atlas.contracts`.

In practice this means:

- `power_atlas.contracts.pipeline` is the explicit import path for stateful
	pipeline access,
- package-root exports in `power_atlas.contracts` are reserved for stable,
	stateless contract values and helpers,
- mutable pipeline symbols such as dataset overrides and refreshed config-bound
	globals must not be treated as package-root imports.

### Why

- The pipeline contract owns mutable module state.
- Re-exporting those names from package root would blur the state boundary.
- Root-level imports of mutable names would encourage stale bindings after
	config refreshes or dataset overrides.

### Consequences

- Code that needs pipeline state must import from
	`power_atlas.contracts.pipeline` explicitly.
- `power_atlas.contracts.__all__` should not grow stateful pipeline exports.
- Compatibility tests should continue to enforce this boundary.

### Open Questions

None for the current package-first migration lane.

## Decision 16 — `demo.contracts` remains an intentional compatibility layer during Phase 2

### Decision

`demo.contracts` remains in the repository as an intentional compatibility
surface during the current Phase 2 package-first migration work. It is not the
long-term package-native target surface.

The preferred contract locations are:

- `power_atlas.contracts`
- `power_atlas.contracts.<submodule>`

The `demo.contracts` package should be treated as a tracked compatibility layer
until there is an explicit deprecation/removal plan.

### Implementation checkpoint (2026-04-30)

That deprecation/removal plan was later executed in Phase 10.

- the simple package-owned `demo/contracts/*.py` shims were retired,
- the `demo/contracts/__init__.py` root proxy was retired,
- the `demo/contracts/pipeline.py` module-alias shim was retired,
- the `demo/contracts/` directory itself has been removed.

The current contract surface is therefore package-native:

- `power_atlas.contracts`
- `power_atlas.contracts.<submodule>`

### Why

- The migration is being executed additively rather than as a flag day.
- Existing demo runtime paths and compatibility tests still depend on the shim
	surface.
- Remaining `demo.contracts` references are not automatically proof of missed
	cleanup; some are deliberate compatibility coverage.

### Consequences

- Package-first migration work should prefer package-owned imports for stable
	symbols.
- Remaining `demo.contracts` references should be classified before cleanup,
	not removed blindly.
- Shim removal should be planned deliberately rather than folded into incidental
	import cleanup.

### Open Questions

- No open questions remain for the `demo.contracts` shim lane.

---

## Decision 17 — `_archive/` remains at the repo root as the archival boundary for now

### Decision

`_archive/` should remain at the repository root as the accepted archival
boundary for historical experimentation material.

### Why

- workspace searches found no live runtime coupling to `_archive/` beyond
	documentation references,
- `_archive/README.md` and the root `README.md` already mark the directory as
	historical, non-active material,
- moving the directory now would create reference churn without reducing
	current product or migration risk.

### Consequences

- Phase 10 should treat `_archive/` placement as resolved unless a broader
	repository-layout change creates a stronger reason to move archival material,
- future documentation can refer to `_archive/` as the explicit historical
	boundary without implying active product ownership,
- archive cleanup should focus on labeling and reference hygiene rather than
	path relocation by default.

### Open Questions

- None for the current Phase 10 lane.

---

## Decision 18 — Active output roots remain in place; tracked exemplar payload is retired from them

### Decision

The active output roots `demo/artifacts/` and `pipelines/runs/` should remain
in place for now rather than being moved behind `_archive/` or another archival
boundary immediately. Within that scope, tracked committed exemplar payload has
been retired from both roots in the working tree, leaving only their control
files once the deletions are accepted.

### Why

- both directories are still active output roots used by current commands,
- `demo/artifacts/` remains the default destination for reset reports and demo
	run artifacts,
- `pipelines/runs/` remains the active destination for graph-health and
	retrieval-benchmark CLI artifacts,
- a git inventory of `demo/artifacts/` shows no tracked historical payload
	beyond the ignore control file, even though ignored local run residue may be
	present in a working tree,
- the previously committed `pipelines/runs/` exemplar files were doc-anchored
	rather than runtime-anchored, so they could be replaced by durable
	documentation summaries without changing live output paths,
- moving them now would mix archival cleanup with live output-path changes and
	create path churn without reducing current runtime risk.

### Consequences

- do not treat `demo/artifacts/` as an outstanding tracked-file retirement
	bucket; there is currently nothing there to drop later except ignored local
	outputs,
- do not treat `pipelines/runs/` as an outstanding tracked-file retirement
	bucket once the current deletions are accepted; historical benchmark facts now
	live in durable documentation instead of committed run-output payload,
- keep the active output paths unchanged for now,
- only revisit relocation after runtime defaults and documentation references
	are intentionally decoupled from those roots.

### Open Questions

- None for the current Phase 10 lane; the decision is to defer relocation until
	the output roots are no longer mixed active/historical surfaces.

---

## Decision 19 — `backend/main.py` stays as a defer-in-place compatibility shell for now

### Decision

`backend/main.py` should remain in place for now as a thin compatibility shell
rather than being retired in the current Phase 10 lane.

### Why

- it is already reduced to a minimal package bridge that delegates app creation
	to `power_atlas.interfaces.api.create_backend_app`,
- the remaining direct caller surface is small but still real,
- `backend/Dockerfile` still launches the backend through this seam with
	`uvicorn main:app`,
- `tests/test_backend_main.py` still imports `app` from `backend.main` as the
	dedicated backend compatibility test seam,
- deleting the file now would change the active backend execution posture
	rather than retire dead compatibility debt.

### Consequences

- treat `backend/main.py` as an accepted defer-in-place shell,
- do not open a deletion lane for it until the backend container entrypoint and
	test seam are intentionally migrated,
- keep the package-owned API app factory under
	`src/power_atlas/interfaces/api/` as the authoritative implementation while
	`backend/main.py` remains the stable outer seam.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional container/test-seam migration rather than another caller search.

---

## Decision 20 — `scripts/sync_vendor_version.py` stays as a defer-in-place compatibility shell for now

### Decision

`scripts/sync_vendor_version.py` should remain in place for now as a thin
compatibility shell rather than being retired in the current Phase 10 lane.

### Why

- it is already reduced to a package-backed CLI bridge that delegates argument
	parsing and main-entry dispatch to `power_atlas.interfaces.cli`,
- the remaining caller surface is still an active operator seam rather than a
	dead wrapper,
- `.github/workflows/vendor-version-consistency.yml` still invokes
	`python3 scripts/sync_vendor_version.py --check`,
- the root README and `docs/vendor/neo4j-graphrag-python.md` still document
	this exact script path for local operator use,
- `tests/test_sync_vendor_version.py` still imports and patches symbols from
	`scripts.sync_vendor_version`, so deleting the file now would change the
	active script/test seam rather than retire obsolete compatibility debt.

### Consequences

- treat `scripts/sync_vendor_version.py` as an accepted defer-in-place shell,
- do not open a deletion lane for it until the workflow/docs invocation surface
	and test seam are intentionally migrated,
- keep the package-owned CLI support modules under `src/power_atlas/interfaces/cli/`
	as the authoritative implementation while this script remains the stable
	outer seam.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional workflow/doc/test-seam migration rather than another caller
	search.

---

## Decision 21 — `pipelines/query/graph_health_diagnostics.py` stays as a defer-in-place compatibility shell for now

### Decision

`pipelines/query/graph_health_diagnostics.py` should remain in place for now as
a thin compatibility shell rather than being retired in the current Phase 10
lane.

### Why

- it is already reduced to a package-backed CLI bridge that delegates argument
	parsing and main-entry dispatch to `power_atlas.interfaces.cli`,
- the remaining caller surface is still an active manual/operator seam rather
	than dead wrapper glue,
- `pipelines/query/README.md`,
	`eval/rubrics/retrieval-benchmark-review-rubric-v0.1.md`, and
	`docs/architecture/warning-channel-conventions.md` still describe or link to
	this exact script path for manual diagnostics usage,
- `demo/tests/test_graph_health_diagnostics_cli.py` still imports and patches
	`pipelines.query.graph_health_diagnostics`, so deleting the file now would
	change the active CLI/test seam rather than retire obsolete compatibility
	debt.

### Consequences

- treat `pipelines/query/graph_health_diagnostics.py` as an accepted
	defer-in-place shell,
- do not open a deletion lane for it until the manual-doc invocation surface
	and test seam are intentionally migrated,
- keep the package-owned CLI support modules under `src/power_atlas/interfaces/cli/`
	as the authoritative implementation while this script remains the stable
	outer seam.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional documentation/test-seam migration rather than another caller
	search.

---

## Decision 22 — `pipelines/query/retrieval_benchmark.py` stays as a defer-in-place compatibility shell for now

### Decision

`pipelines/query/retrieval_benchmark.py` should remain in place for now as a
thin compatibility shell rather than being retired in the current Phase 10
lane.

### Why

- it is already reduced to a package-backed CLI bridge that delegates argument
	parsing and main-entry dispatch to `power_atlas.interfaces.cli`,
- the remaining caller surface is still an active manual/operator seam rather
	than dead wrapper glue,
- `demo/README.md`, `pipelines/query/README.md`,
	`docs/architecture/legacy-dataset-id-migration-v0.1.md`, and
	`eval/rubrics/retrieval-benchmark-review-rubric-v0.1.md` still describe
	or invoke this exact script path for manual benchmark usage,
- `demo/tests/test_retrieval_benchmark_cli.py` still imports and patches
	`pipelines.query.retrieval_benchmark`, so deleting the file now would change
	the active CLI/test seam rather than retire obsolete compatibility debt.

### Consequences

- treat `pipelines/query/retrieval_benchmark.py` as an accepted
	defer-in-place shell,
- do not open a deletion lane for it until the manual-doc invocation surface
	and test seam are intentionally migrated,
- keep the package-owned CLI support modules under `src/power_atlas/interfaces/cli/`
	as the authoritative implementation while this script remains the stable
	outer seam.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional documentation/test-seam migration rather than another caller
	search.

---

## Decision 23 — `frontend/` stays as a defer-in-place non-core surface for now

### Decision

`frontend/` should remain in place for now as a defer-in-place non-core surface
rather than being retired in the current Phase 10 lane.

### Why

- the current runtime seam is intentionally narrow but still real,
- `docker-compose.yml` still includes the checked-in `frontend` service as part
	of the local scaffold posture,
- `frontend/app/page.tsx` still reads `NEXT_PUBLIC_BACKEND_URL` and performs a
	placeholder `GET /health` check against the backend stub surface,
- the root README and existing restructure notes still describe `frontend/` as
	a disconnected but accepted placeholder UI surface,
- deleting it now would change the accepted local scaffold posture rather than
	retire dead compatibility debt.

### Consequences

- treat `frontend/` as an accepted defer-in-place non-core surface,
- do not open a deletion lane for it until the local scaffold posture and the
	placeholder frontend-to-backend health-check contract are intentionally
	migrated or removed,
- keep formal frontend contract/versioning work deferred until the backend
	exposes non-placeholder graph operations that the frontend is actually
	expected to consume.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional local-scaffold or frontend-contract migration rather than another
	caller search.

---

## Decision 24 — `artifacts/repository_restructure/phase1/` stays as a defer-in-place verification-evidence root for now

### Decision

`artifacts/repository_restructure/phase1/` should remain in place for now as a
defer-in-place verification-evidence root rather than being retired or moved in
the current Phase 10 lane.

### Why

- it still serves as the checked-in output root for `make phase1-verify` /
	`bash scripts/phase1_verify.sh`,
- `scripts/phase1_verify.sh` still writes accepted Phase 1 proof artifacts into
	`artifacts/repository_restructure/phase1/<timestamp>/`,
- the current checklist, safety harness, plan, and Phase 1 execution log still
	anchor accepted verification evidence to this exact path family,
- the directory contents are historical in one sense, but they are also part of
	the current reproducible verification posture rather than dead runtime debris,
- relocating or deleting the root now would change the accepted artifact-capture
	contract rather than retire obsolete compatibility debt.

### Consequences

- treat `artifacts/repository_restructure/phase1/` as an accepted defer-in-place
	verification-evidence root,
- do not open a deletion or relocation lane for it until the accepted
	`phase1-verify` artifact-capture posture is intentionally migrated,
- keep the current Phase 1 proof docs pointed at this path family until a later
	verification-contract change is explicitly approved.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional verification-contract migration rather than another caller search.

---

## Decision 25 — `docs/repository_restructure/repository_restructure_phase1_execution_run_log.md` stays as a defer-in-place verification document for now

### Decision

`docs/repository_restructure/repository_restructure_phase1_execution_run_log.md`
should remain in place for now as a defer-in-place verification document rather
than being retired or archived in the current Phase 10 lane.

### Why

- it is still referenced by `scripts/phase1_verify.sh` as canonical execution
	context for the accepted automation entrypoint,
- it still records the accepted run evidence and automation history behind the
	current Phase 1 verification posture,
- the file is historical in one sense, but it is also part of the current
	reproducible verification documentation surface rather than dead planning
	residue,
- retiring or archiving it now would change the accepted verification-document
	contract rather than retire obsolete compatibility debt.

### Consequences

- treat `docs/repository_restructure/repository_restructure_phase1_execution_run_log.md`
	as an accepted defer-in-place verification document,
- do not open an archival or deletion lane for it until the accepted Phase 1
	verification documentation surface is intentionally migrated,
- keep `scripts/phase1_verify.sh` and the current proof docs pointed at this
	run log until a later verification-document contract change is explicitly
	approved.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional verification-document migration rather than another caller search.

---

## Decision 26 — `docs/repository_restructure/repository_restructure_agent_task_breakdown.md` stays as a defer-in-place verification/planning-history document for now

### Decision

`docs/repository_restructure/repository_restructure_agent_task_breakdown.md`
should remain in place for now as a defer-in-place verification/planning-history
document rather than being retired or archived in the current Phase 10 lane.

### Why

- its own checkpoint note already marks it as historical setup context rather
	than the canonical current plan,
- but the accepted Phase 1 execution run log still references it as part of the
	authoritative context for interpreting runs,
- that means the file is historical in one sense while still participating in
	the accepted verification documentation surface,
- retiring or archiving it now would change that accepted documentation surface
	rather than retire obsolete compatibility debt.

### Consequences

- treat `docs/repository_restructure/repository_restructure_agent_task_breakdown.md`
	as an accepted defer-in-place verification/planning-history document,
- do not open an archival or deletion lane for it until the accepted Phase 1
	verification documentation surface is intentionally migrated,
- keep the current run-log references in place until a later
	verification-document contract change is explicitly approved.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional verification-document migration rather than another caller search.

---

## Decision 27 — `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md` stays as a defer-in-place historical planning/execution record for now

### Decision

`docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`
should remain in place for now as a defer-in-place historical planning/execution
record rather than being retired or archived in the current Phase 10 lane.

### Why

- its own status and body already mark the underlying `demo/contracts`
	retirement lane as completed historical work,
- but the current Phase 10 shortlist and checklist still reference it as the
	executed follow-up planning task behind that closed lane,
- that means the file no longer participates in accepted execution or
	verification, but it still participates in the accepted restructuring record
	for completed work,
- retiring or archiving it now would change that accepted restructuring record
	rather than retire obsolete compatibility debt.

### Consequences

- treat `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`
	as an accepted defer-in-place historical planning/execution record,
- do not open an archival or deletion lane for it until the accepted
	restructuring record for the closed `demo/contracts` lane is intentionally
	migrated,
- keep the current shortlist/checklist references in place until a later
	documentation-record migration is explicitly approved.

### Open Questions

- None for the current slice; the next meaningful move would require an
	intentional documentation-record migration rather than another caller search.

---

## Decision 28 — `studies/SYSTEM-INDEX-v0.1.md` is retired as a stale unreferenced studies index

### Decision

`studies/SYSTEM-INDEX-v0.1.md` should be removed from the repository as a stale
studies index rather than retained as an active or deferred legacy surface.

### Why

- exact filename and title searches found no remaining workspace references
	outside the file itself,
- the surviving studies-system docs already establish a different canonical
	posture: `/studies/_studies/` is the inventory, while the workflow and
	template docs are the real entrypoints,
- keeping the stale index in place would preserve a conflicting description of
	the studies-system navigation model without providing any live compatibility or
	verification value.

### Consequences

- treat `studies/SYSTEM-INDEX-v0.1.md` as a completed low-risk stale-doc
	retirement slice,
- do not preserve it as an accepted defer-in-place surface,
- keep the surviving studies docs as the authoritative studies-system entry
	points unless a later studies-workflow change introduces a genuinely used
	index surface again.

### Open Questions

- None for the current slice; the file had no live caller or documentation
	dependencies to migrate.

---

## Decision 29 — `_archive/initial_experimentation_2026_02_28/` is retired as a stale archive subtree

### Decision

`_archive/initial_experimentation_2026_02_28/` should be removed from the
retained `_archive/` boundary as a stale dated experimentation subtree.

### Why

- nothing outside that subtree still referenced the dated experimentation path,
- its README still documented the old `/examples` demo layout rather than the
	current repo posture,
- leaving it in place would preserve an isolated historical snapshot without
	adding live execution, verification, or restructuring-record value,
- removing the subtree does not change the accepted Phase 10 decision to keep
	`_archive/` itself as the explicit archive boundary.

### Consequences

- treat `_archive/initial_experimentation_2026_02_28/` as a completed low-risk
	archive cleanup slice,
- keep `_archive/README.md` and the retained `_archive/` root boundary in
	place,
- do not infer from this subtree removal that the broader `_archive/` root
	placement decision has changed.

### Open Questions

- None for the current slice; no live caller or documentation dependencies had
	to be migrated.

---

## Decision 30 — `demo/artifacts_compare/` stays as a defer-in-place manual validation artifact root for now

### Decision

`demo/artifacts_compare/` should remain in place for now as a defer-in-place
manual validation artifact root rather than being retired in the current Phase
10 lane.

### Why

- no code or automated test callers currently depend on that path family,
- but the current repo still documents it as an accepted comparison-output
	surface in `demo/README.md`, `demo/VALIDATION_RUNBOOK.md`, and
	`docs/repository_restructure/repository_restructure_safety_harness.md`,
- the validation runbook also treats specific manifests under that tree as part
	of the minimal retained artifact set for reviewable manual validation runs,
- deleting it now would therefore change the accepted manual validation posture
	rather than retire dead compatibility debt.

### Consequences

- treat `demo/artifacts_compare/` as an accepted defer-in-place manual
	validation artifact root,
- do not open a deletion lane for it unless the current manual comparison flow
	and retained-artifact guidance are intentionally migrated or retired,
- keep the documented comparison-output examples in place until that broader
	validation-posture change is approved.

### Open Questions

- whether the current manual comparison flow should later be replaced by a more
	automated validation posture remains a separate follow-up decision.

---

## Decision 31 — `vendor-resources/tests/` is retired as a stale duplicate vendor subtree

### Decision

`vendor-resources/tests/` should be removed from the repository as a stale
duplicate vendor subtree.

### Why

- exact path searches found no live workspace references to
	`vendor-resources/tests`,
- the repo's retained vendor-reference usage still points to
	`vendor-resources/examples` rather than to the duplicated test mirror,
- the subtree mirrored the upstream vendor test layout already present under
	`vendor/neo4j-graphrag-python/tests/`,
- removing it therefore retires duplicate historical payload without changing
	the accepted vendor-reference posture.

### Consequences

- treat `vendor-resources/tests/` as a completed low-risk stale vendor-subtree
	retirement slice,
- keep the remaining `vendor-resources/examples/` surface in place,
- do not infer from this subtree removal that the broader retained
	`vendor-resources/` reference posture has changed.

### Open Questions

- None for the current slice; no live caller or documentation dependencies had
	to be migrated.

---

## Decision 32 — `vendor-resources/docs/` is retired as a stale duplicate vendor subtree

### Decision

`vendor-resources/docs/` should be removed from the repository as a stale
duplicate vendor subtree.

### Why

- exact path searches found no live workspace references to
	`vendor-resources/docs`,
- the subtree mirrored the upstream vendored docs tree already present under
	`vendor/neo4j-graphrag-python/docs/`,
- the repo's retained vendor-reference usage still points to
	`vendor-resources/examples` rather than to the duplicated docs mirror,
- removing it therefore retires duplicate historical payload without changing
	live repo behavior.

### Consequences

- treat `vendor-resources/docs/` as a completed low-risk stale vendor-subtree
	retirement slice,
- keep the remaining `vendor-resources/examples/` surface in place,
- do not infer from this subtree removal that the broader retained
	`vendor-resources/` reference posture has changed.

### Open Questions

- None for the current slice; no live caller or documentation dependencies had
	to be migrated.

---

## Decision 33 — `vendor-resources/images/` is retired as a stale duplicate vendor subtree

### Decision

`vendor-resources/images/` should be removed from the repository as a stale
duplicate vendor subtree.

### Why

- exact path searches found no live workspace references to
	`vendor-resources/images`,
- the subtree contained only a duplicated upstream image asset already present
	under `vendor/neo4j-graphrag-python/images/`,
- the repo's retained vendor-reference usage still points to
	`vendor-resources/examples` rather than to the duplicated image mirror,
- removing it therefore retires duplicate historical payload without changing
	live repo behavior.

### Consequences

- treat `vendor-resources/images/` as a completed low-risk stale vendor-subtree
	retirement slice,
- keep the remaining `vendor-resources/examples/` surface in place,
- do not infer from this subtree removal that the broader retained
	`vendor-resources/` reference posture has changed.

### Open Questions

- None for the current slice; no live caller or documentation dependencies had
	to be migrated.

---

## Decision 34 — `demo/fixtures/wikidata_extraction_prompts/` stays as a defer-in-place operator-facing prototyping template subtree for now

### Decision

`demo/fixtures/wikidata_extraction_prompts/` should remain in place for now as
a defer-in-place operator-facing prototyping template subtree rather than being
retired in the current Phase 10 lane.

### Why

- it is not code-called, but it is still intentionally used by operators during
	external Wikidata dataset construction in the prototyping phase,
- that makes the subtree part of a retained human workflow rather than dead
	compatibility debris,
- deleting it now would remove useful operator templates rather than retire
	obsolete execution or verification surfaces.

### Consequences

- treat `demo/fixtures/wikidata_extraction_prompts/` as an accepted
	defer-in-place operator-facing template subtree,
- keep the retained dataset-based fixture surface under `demo/fixtures/` in
	place alongside those prototyping templates,
- do not reopen a deletion lane for these files unless the operator-facing
	prototyping workflow is intentionally retired or migrated.

### Open Questions

- whether these operator templates should later be documented more explicitly as
	part of the prototyping workflow remains a follow-up documentation question.

---

## Decision 35 — `docs/governance/relationship-assertion-decision-matrix.md` is retired as a stale governance draft

### Decision

`docs/governance/relationship-assertion-decision-matrix.md` should be removed
from the repository as a stale governance draft.

### Why

- exact filename and title searches found no live workspace references outside
	the file itself,
- the document described itself as experimental conceptual guidance only,
- removing it therefore retires isolated historical draft material without
	changing any accepted execution, verification, or operator workflow surface.

### Consequences

- treat `docs/governance/relationship-assertion-decision-matrix.md` as a
	completed low-risk stale-governance-draft retirement slice,
- do not infer from this removal that the referenced ontology or provenance
	charters have changed,
- only reopen this area if a new governance-matrix document is intentionally
	reintroduced as part of an active governance workflow.

### Open Questions

- None for the current slice; no live caller or documentation dependencies had
	to be migrated.

---

## Decision 36 — Demo reset runtime now belongs under `src/power_atlas/`, and no package-to-demo runtime back-edge remains

### Decision

The demo reset runtime should remain package-owned under
`src/power_atlas/reset_demo_runtime.py`, while `demo/reset_demo_db.py` stays in
place only as the operator-facing compatibility entrypoint.

### Why

- the package-side `run_demo` entrypoint was still reaching back into
	`demo.reset_demo_db` for live reset execution, which meant the package layer
	still depended on a repo-root demo runtime module,
- that reset seam was the last remaining `src -> demo` runtime import found by
	a bounded import audit after the refactor,
- moving the reset behavior under `src/power_atlas/` removes that structural
	back-edge without changing the accepted operator CLI seam,
- a nearby read also confirmed that `demo/narrative_extraction.py` should not be
	treated as the same class of candidate: it still owns stage artifact paths,
	dry/live branching, manifest emission, and runtime collaborator composition.

### Consequences

- treat `power_atlas.reset_demo_runtime` as the owned runtime boundary for demo
	graph reset behavior,
- treat `demo/reset_demo_db.py` as a retained compatibility entrypoint rather
	than the runtime owner,
- treat the bounded `src/**/*.py` import audit result as a current checkpoint:
	the earlier reset and narrative-extraction back-edges are closed, but
	`src/power_atlas/orchestration/stage_entrypoints.py` still acts as a
	package-owned import bridge into `demo.stages.*`,
- do not misclassify `demo/narrative_extraction.py` as a thin compatibility
	shell in later Phase 10 retirement passes; it remains an explicit runtime-side
	exception until a separate structural slice intentionally moves its owned
	behavior.

### Open Questions

- whether `demo/narrative_extraction.py` should later be split further into
	package-owned runtime collaborators remains a follow-up structural question,
	not a current Phase 10 retirement slice.

---

## Decision 37 — Narrative extraction artifact serialization now belongs under `src/power_atlas/`, while the demo stage remains the runtime owner

### Decision

The narrative extraction stage should now treat summary and manifest
serialization as package-owned helper behavior under
`src/power_atlas/narrative_extraction_artifacts.py`, while
`demo/narrative_extraction.py` remains the runtime owner for stage path
selection, dry/live branching, and collaborator composition.

### Why

- a bounded read of `demo/narrative_extraction.py` showed that not every part of
	the file belonged to the same ownership class,
- the summary-building and manifest-writing helpers were package-safe and did
	not need to stay in `demo/`,
- extracting that helper block narrows the demo runtime exception without
	pretending that the full stage is already a thin compatibility shell,
- the focused `demo/tests/test_narrative_extraction.py` slice continued to pass
	after the extraction, which confirms the wrapper behavior and artifact
	contract stayed stable.

### Consequences

- treat `power_atlas.narrative_extraction_artifacts` as the owned helper
	boundary for summary/manifest serialization in this stage,
- keep `demo/narrative_extraction.py` classified as an explicit runtime-side
	exception for now, but with a narrower ownership surface than before,
- do not treat this extraction as evidence that the whole file is delete-ready;
	the stage still owns artifact-path decisions, dry/live branching, and runtime
	collaborator assembly.

### Open Questions

- whether the remaining runtime-owned behavior in
	`demo/narrative_extraction.py` should later move behind package-owned runtime
	services remains a follow-up structural slice.

---

## Decision 38 — Narrative extraction chunk-read/extract execution now belongs under `src/power_atlas/`, while the demo stage keeps the compatibility patch seam

### Decision

The narrative extraction chunk-read/extract helper should now remain
package-owned under `src/power_atlas/narrative_extraction_readers.py`, while
`demo/narrative_extraction.py` keeps only the compatibility alias that its
focused tests patch.

### Why

- after the artifact-helper extraction, the next bounded read showed that the
	chunk-reader plus LLM extractor path was also package-safe,
- `RunScopedNeo4jChunkReader`, the extraction schema, and the OpenAI LLM
	construction path already had package-owned homes,
- the remaining reason to keep a demo-local symbol was test seam stability:
	`demo/tests/test_narrative_extraction.py` still patches
	`demo.narrative_extraction._read_chunks_and_extract`,
- restoring that alias after the move preserved the existing patch seam while
	still relocating the actual implementation under `src/power_atlas/`.

### Consequences

- treat `power_atlas.narrative_extraction_readers` as the owned helper
	boundary for chunk read/extract execution in this stage,
- treat the `_read_chunks_and_extract` symbol left in
	`demo/narrative_extraction.py` as a compatibility alias rather than the
	implementation owner,
- keep `demo/narrative_extraction.py` classified as a narrower runtime-side
	exception for now; it still owns stage path selection, dry/live branching,
	and top-level collaborator wiring.

### Open Questions

- whether the remaining stage-level orchestration in
	`demo/narrative_extraction.py` should later move behind a package-owned
	runtime service remains a follow-up structural slice.

---

## Decision 39 — Narrative extraction stage execution now runs through a package-owned service, while the demo module remains the compatibility wrapper

### Decision

The main narrative extraction stage execution flow should now remain
package-owned under `src/power_atlas/narrative_extraction_service.py`, while
`demo/narrative_extraction.py` remains only as the compatibility wrapper that
provides stage-specific constants, config type exposure, lexical-config setup,
and retained patch seams.

### Why

- after moving artifact serialization and chunk-read/extract execution under
	`src/power_atlas/`, the remaining `run_narrative_extraction(...)` body had
	become an injected orchestration block rather than a demo-specific runtime
	implementation,
- extracting that orchestration into a package-owned service further narrows the
	demo runtime exception without forcing a caller-surface or test-surface
	rewrite,
- the focused `demo/tests/test_narrative_extraction.py` slice still passed after
	the move, which confirms the wrapper preserved its public behavior and patch
	seams.

### Consequences

- treat `power_atlas.narrative_extraction_service` as the owned execution
	boundary for the stage flow,
- treat `demo/narrative_extraction.py` as a thin compatibility/orchestration
	wrapper rather than the execution owner,
- keep the retained `_read_chunks_and_extract` symbol and exported config
	surface in the demo module only as compatibility/test seams until a later
	caller migration intentionally removes them.

### Open Questions

- whether the remaining compatibility exports in `demo/narrative_extraction.py`
	should later be migrated or retired remains a follow-up caller-surface
	question rather than a current runtime-ownership gap.

---

## Decision 40 — `demo/narrative_extraction.py` is retired after caller migration to a package-native CLI module

### Decision

`demo/narrative_extraction.py` should now be removed from the repository.
Its remaining focused caller surface has been migrated to the package-native
module `src/power_atlas/narrative_extraction_cli.py`.

### Why

- an exact caller/reference sweep found no remaining non-test code callers and
	no operator-facing docs anchored to `demo/narrative_extraction.py`,
- the only live caller surface left was the focused
	`demo/tests/test_narrative_extraction.py` file,
- that focused test surface was migrated to `power_atlas.narrative_extraction_cli`,
	which now preserves the needed config/constants/patch seams under `src/`,
- after the caller migration, the focused narrative-extraction test slice still
	passed, so removing the demo file no longer changed an accepted runtime or
	operator workflow surface.

### Consequences

- treat `demo/narrative_extraction.py` as a completed retirement slice rather
	than a defer-in-place compatibility seam,
- treat `power_atlas.narrative_extraction_cli` as the retained package-native
	CLI/test surface for this workflow,
- update restructure notes that previously described
	`demo/narrative_extraction.py` as a runtime exception or thin wrapper; those
	statements are now historical context only.

### Open Questions

- whether `power_atlas.narrative_extraction_cli` should later be folded further
	into a broader package CLI layout remains a follow-up packaging question, not
	a reason to restore the retired demo wrapper.

---

## Decision 41 — `demo/smoke_test.py` stays as a defer-in-place compatibility seam for now

### Decision

`demo/smoke_test.py` should remain in the repository as a defer-in-place
compatibility shell for now.

### Why

- the operator walkthrough in `demo/README.md` still directs users to run the
	exact command `python demo/smoke_test.py`,
- the focused smoke-test unit and scenario coverage in
	`demo/tests/test_demo_workflow.py` still imports that exact file path through
	`SMOKE_TEST_PATH = DEMO_DIR / "smoke_test.py"`,
- deleting or renaming the file now would therefore change both the accepted
	operator CLI seam and the current focused test seam rather than retire dead
	compatibility debt.

### Consequences

- treat `demo/smoke_test.py` as an accepted compatibility shell rather than a
	live retirement candidate,
- keep future work in this area scoped to an intentional caller-surface
	migration if the project later wants a package-native smoke-test CLI path,
- do not reopen this file as low-risk Phase 10 deletion work unless the docs
	and test seam are migrated first.

### Open Questions

- whether the smoke-test CLI should later gain a package-native caller surface
	remains open, but that is a migration task rather than a current retirement
	decision.

---

## Decision 42 — `demo/reset_demo_db.py` stays as a defer-in-place compatibility seam for now

### Decision

`demo/reset_demo_db.py` should remain in the repository as a defer-in-place
compatibility shell for now.

### Why

- the active operator and workflow docs still anchor reset execution to that
	exact entrypoint, including `README.md`, `demo/README.md`,
	`neo4j/README.md`, `neo4j/local_dev_workflow.md`, and
	`demo/VALIDATION_RUNBOOK.md`,
- the package runtime refactor moved reset behavior into
	`src/power_atlas/reset_demo_runtime.py`, but the accepted CLI seam still runs
	through `python -m demo.reset_demo_db --confirm` and related help text,
- the focused reset coverage in `demo/tests/test_demo_workflow.py` still loads
	that exact file path through `reset_path = DEMO_DIR / "reset_demo_db.py"`
	and patches exported wrapper symbols on that module,
- deleting or renaming the file now would therefore change both the accepted
	operator CLI seam and the current focused test seam rather than retire dead
	compatibility debt.

### Consequences

- treat `demo/reset_demo_db.py` as an accepted compatibility shell rather than
	a live retirement candidate,
- keep future work in this area scoped to an intentional caller-surface
	migration if the project later wants a package-native reset CLI path,
- do not reopen this file as low-risk Phase 10 deletion work unless the docs
	and focused reset test seam are migrated first.

### Open Questions

- whether the reset CLI should later collapse fully into a package-native
	entrypoint remains open, but that is a migration task rather than a current
	retirement decision.

---

## Decision 43 — `demo/run_demo.py` stays as a defer-in-place compatibility seam for now

### Decision

`demo/run_demo.py` should remain in the repository as a defer-in-place
compatibility shell for now.

### Why

- the active operator workflow still anchors heavily to that exact module
	invocation across `README.md`, `demo/README.md`, `demo/VALIDATION_RUNBOOK.md`,
	`neo4j/local_dev_workflow.md`, and other execution/validation docs through
	`python -m demo.run_demo ...`,
- the focused workflow test surface still loads that exact file path through
	`RUN_DEMO_PATH = DEMO_DIR / "run_demo.py"` in
	`demo/tests/test_demo_workflow.py`, and additional tests also import
	`demo.run_demo` directly,
- earlier orchestration thinning already moved the substantive runtime owners
	behind package-owned helpers, so the remaining file is deliberate
	compatibility/composition scaffolding rather than an unreviewed ownership
	hotspot,
- deleting or renaming the file now would therefore change the accepted
	operator CLI seam and a broad focused test surface rather than retire dead
	compatibility debt.

### Consequences

- treat `demo/run_demo.py` as an accepted compatibility shell rather than a
	live retirement candidate,
- keep future work in this area scoped to an intentional caller-surface
	migration only if the project later wants to replace the current demo CLI
	module path,
- do not reopen this file as low-risk Phase 10 deletion work unless the docs
	and the focused `RUN_DEMO_PATH` / direct-import test seams are migrated first.

### Open Questions

- whether the long-term CLI should consolidate further under a package-native
	entrypoint remains open, but that is a caller-migration task rather than a
	current retirement decision.

---

## Summary of decisions that still require follow-up

The following areas are intentionally narrowed but not fully finalized yet:

- exact configuration library/tooling,
- exact Neo4j migration tooling,
- physical vs logical candidate/authoritative graph separation,
- prompt storage/versioning implementation model,
- API schema versioning approach,
- whether async worker architecture becomes necessary,
- exact critical-path scenarios for the migration safety harness.

These should be resolved in small, explicit follow-up decisions before the corresponding migration phases are considered complete.
