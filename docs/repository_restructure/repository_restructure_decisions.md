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
- a final 2026-04-27 audit also moved the last policy-bearing `run_demo.py` helper decisions behind package-owned bridges and confirmed that the remaining `demo/run_demo.py` surface is now primarily deliberate compatibility/composition scaffolding rather than a substantive runtime owner,
- the live retrieval path is no longer just RequestContext-aware at its entrypoints: `retrieval_and_qa` now delegates request-context binding, live-session bootstrap, execution-context prep, interactive-session prelude, and single-shot session binding to package-owned helper modules while preserving the remaining stage-level patch seams,
- the remaining config-form graph-analysis stage APIs in `demo/stages/graph_health.py` and `demo/stages/retrieval_benchmark.py` are now treated as explicit standalone analysis surfaces, while orchestrated and query-pipeline callers prefer the request-context entrypoints,
- the latest live `make phase1-verify` rerun on 2026-04-27 succeeded at commit `8e57fb2856b153ec0fad36fd5e8dd73ab3807ac6`, with artifacts under `artifacts/repository_restructure/phase1/20260427T201502Z` and fully cited baseline, companion, and isolation asks,
- the remaining work under this decision is the residual mutable-global inventory and any explicit disposition around the remaining cached pipeline-contract state, and this checkpoint should be read as caller migration plus boundary consolidation rather than a default mandate to delete the surviving standalone config-form stage APIs or the now-intentional `demo/run_demo.py` CLI/test seam surface.

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

- explicit adapter-local owners now exist for live retrieval session construction plus the `claim_extraction_runtime`, `graph_health`, `retrieval_benchmark`, and `run_scope_queries` modules under `src/power_atlas/adapters/neo4j/`,
- `power_atlas.retrieval_session_setup`, `power_atlas.claim_extraction_runtime`, `power_atlas.graph_health_queries`, `power_atlas.retrieval_benchmark_queries`, and `power_atlas.run_scope_queries` remain as compatibility re-export surfaces so existing stage/test callers do not need to migrate in lockstep,
- the current remaining direct `create_neo4j_driver(...)` owners outside `adapters/neo4j` are `claim_participation_runtime.py`, `entity_resolution_runtime.py`, `narrative_extraction_runtime.py`, `pdf_ingest_runtime.py`, `retrieval_runtime.py`, and `structured_ingest_runtime.py`,
- the next recommended slices under this decision are those remaining runtime-owner moves and any documentation of intentional layering exceptions rather than more wrapper-only cleanup in `demo/run_demo.py`.

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

- When to begin formal deprecation planning for `demo/contracts/*`.
- Whether shim retirement should be grouped into a dedicated later-phase task.

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
