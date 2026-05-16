# Shared-Mechanics Pilot Contract

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_plan.md`
- `README.md`

## Purpose

This document defines the next bounded reuse slice after the explicit
namespace-split no-go decision on 2026-05-16.

The goal is not to reopen the shared-core namespace question. The goal is to
prove whether a smaller mechanics-only extraction lane can move forward without
pulling Power Atlas dataset/default authority into a would-be shared layer.

At this checkpoint, the repo already has:

- an installable package-first layout,
- bootstrap-owned baseline composition through `AppBaseline`,
- backend and package-only proofs that explicit host-app baseline composition
  works,
- a recorded decision to keep the remaining dataset/default-owning runtime
  surfaces app-owned for now.

The missing definition is no longer architectural direction. The missing
definition is a concrete implementation contract for the smaller pilot that the
boundary doc now recommends.

## Pilot defined in this checkpoint

The next reuse slice is a **shared-mechanics pilot**.

This pilot is intentionally conservative. It targets modules whose primary
responsibility is runtime mechanics rather than Power Atlas dataset selection,
pipeline-source defaults, prompt posture, ontology policy, or backend route
semantics.

### Initial pilot scope

The first candidate set for this pilot is:

- `power_atlas.context`
- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.adapters.neo4j.*`
- `power_atlas.neo4j_io`
- `power_atlas.run_scope_queries`
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_request_helpers`
- `power_atlas.retrieval_request_context_adapters`

These modules are in scope because they mostly provide execution envelopes,
request/config carriers, run-manifest shaping, driver/query helpers, and other
support mechanics that are useful outside a single domain posture.

## Minimum proof surface

The pilot does **not** need to introduce a new package name or physically move
files into a second namespace yet. The minimum acceptable proof is narrower.

### Required

- one explicit inventory that classifies the in-scope modules by responsibility
  and flags any remaining hidden Power Atlas assumptions,
- one package-owned pilot surface that groups or documents the mechanics-only
  candidate set without changing dataset/default authority,
- one focused executable proof that imports or consumes that mechanics-only
  pilot surface without going through `demo.*`,
- one short note naming the first assumptions that still block widening this
  pilot into a broader shared-core split.

### Not required yet

- moving `power_atlas.settings`, `power_atlas.contracts.paths`,
  `power_atlas.contracts.pipeline`, or `power_atlas.contracts.resolution`,
- changing `pdf_ingest_runner`, `structured_ingest_runner`, or backend route
  helpers,
- introducing plugin discovery, a second published namespace, or a second app,
- externalizing dataset-root ownership before this pilot proves additional
  leverage.

## Boundaries this pilot is expected to preserve

The pilot should make progress only if it keeps the current application/default
boundary intact.

### 1. Dataset authority stays app-owned

This pilot must not change which layer owns:

- dataset root resolution,
- dataset-id inference from repo fixture layout,
- ambient `POWER_ATLAS_*` / `FIXTURE_DATASET` environment naming,
- default pipeline-config source selection.

If a candidate module unexpectedly depends on one of those behaviors, the pilot
should record that dependency and narrow its scope rather than quietly absorb
it.

### 2. Backend/public app semantics stay app-owned

This pilot must not treat current backend route contracts or current app-facing
API helpers as generic shared API surface. The mechanics pilot is below that
layer.

### 3. Domain policy stays out of scope

This pilot is not a new policy-pack or ontology abstraction pass. Retrieval
policy, prompt posture, claim schema, structured schema, and entity-resolution
policy remain separate questions.

## Deliverables for this pilot checkpoint

The next acceptable shared-mechanics slice should produce all of the following:

1. a short mechanics inventory or grouping surface for the initial candidate
   set,
2. a focused executable proof that exercises that surface without importing
   `demo.*`,
3. a short follow-up note classifying any candidate that turned out to still
   carry Power Atlas assumptions,
4. confirmation that the slice did not widen into dataset/default authority
   work.

## Acceptance criteria

This pilot should be considered successful only if:

- the resulting scope remains smaller than a broad namespace split,
- the proof uses package-owned mechanics surfaces directly,
- the proof does not require copying runtime modules or reintroducing repo-root
  import hacks,
- the slice leaves the current dataset/default-owning modules explicitly in the
  Power Atlas application layer.

## Failure conditions

This pilot should be considered unsuccessful if any of the following are true:

- the pilot immediately needs `resolve_dataset_root(...)` ownership or pipeline
  default loading to move with it,
- the proof only works by importing higher-level app shells or backend helpers,
- the work degenerates into a rename-only namespace exercise,
- the slice broadens into a new shared-core program before the pilot proves
  incremental leverage.

## Immediate next sequence

The next bounded steps should proceed in this order:

1. create a small inventory or facade plan for the in-scope mechanics modules,
2. add one focused executable consumer proof for that mechanics-only surface,
3. record any newly discovered hidden app/default assumptions,
4. only then decide whether another mechanics slice is worthwhile before any
   dataset-authority externalization.

## 2026-05-16 implementation checkpoint

The first bounded shared-mechanics slice has now landed.

The repo now has a package-owned inventory/grouping surface at
`power_atlas.shared_mechanics` plus an executable package-only consumer proof at
`examples/shared_mechanics_consumer.py`.

That surface currently includes the following mechanics-heavy modules or
helpers:

- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.neo4j_io`
- `power_atlas.run_scope_queries`
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_request_helpers`

It also records the first hidden-assumption set that still blocks widening the
pilot:

- `power_atlas.context` remains deferred because `AppContext` /
  `RequestContext` still bundle app settings, default policy ownership, and
  pipeline-contract runtime state,
- `power_atlas.retrieval_request_context_adapters` remains deferred because it
  still depends on the app-owned `RequestContext` surface and forwards
  retrieval policy plus Neo4j settings from that layer,
- the broader `power_atlas.adapters.neo4j.*` family remains deferred because it
  still mixes clean query mechanics with stage-specific runtime modules; the
  current pilot only includes the run-scope query lane via
  `power_atlas.run_scope_queries`.

Focused validation for this checkpoint passed with:

- `pytest -q tests/test_shared_mechanics_pilot.py tests/test_installed_package_adoption.py -k shared_mechanics`

That means the pilot has now satisfied its first three required deliverables:
inventory, package-owned grouping surface, and executable proof. The next
decision is narrower: whether another mechanics-only slice should extract a
request-free retrieval execution helper below `RequestContext`, or whether the
pilot should pause here until dataset/default authority work becomes worth the
cost.

## Non-goals

This pilot contract does **not** authorize:

- starting a broad shared-core namespace split,
- moving the remaining dataset/default-owning runtime surfaces out of the Power
  Atlas app layer,
- rewriting the backend/public API around a generic abstraction,
- treating this pilot as evidence that the package should be renamed now.
