# Target Shape Current Surface Map

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_target_shape_roles.md`
- `docs/repository_restructure/repository_restructure_target_shape_extraction_sequence.md`
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `docs/repository_restructure/repository_restructure_shared_mechanics_pilot_contract.md`

## Purpose

This document turns the target-shape roles model into a current-tense map of
the repo.

It is not a final package split plan. It is a checkpoint inventory of which
surfaces currently look most like reusable kernel material, domain-pack
material, application-shell material, or still-mixed transitional surfaces.

## Classification posture

The map below is intentionally conservative.

- A surface is **kernel-leaning** only when it already works primarily as
  reusable runtime or workflow plumbing.
- A surface is **domain-pack-leaning** when it mainly encodes Power Atlas
  semantics, ontology, retrieval posture, or domain wording.
- A surface is **application-shell-leaning** when it mainly exists to operate
  this repo as a product for humans or future agents.
- A surface is **mixed/transitional** when the mechanics are promising but the
  current API still carries Power Atlas defaults, app context, or repo-local
  authority.

## Kernel-leaning surfaces

These are the highest-confidence candidates for a reusable research kernel.

- `src/power_atlas/contracts/runtime.py`
  - runtime config carriers and run-id helpers are already mechanics-heavy.
- `src/power_atlas/contracts/manifest.py`
  - manifest shaping and write helpers are reusable execution support.
- `src/power_atlas/neo4j_io.py`
  - low-level Neo4j IO and identifier handling sit below app semantics.
- `src/power_atlas/run_scope_queries.py`
  - explicit run-scope query helpers operate on provided runtime inputs.
- `src/power_atlas/retrieval_postprocessing.py`
  - citation normalization and fallback handling are mechanics rather than
    Power Atlas policy.
- `src/power_atlas/retrieval_request_helpers.py`
  - retrieval parameter shaping is request mechanics, not operator workflow.
- `src/power_atlas/retrieval_runtime_bindings.py`
  - request-free retrieval binding is the clearest example of extracted
    execution mechanics below `RequestContext`.
- `src/power_atlas/shared_mechanics.py`
  - this is the current explicit inventory of high-confidence reusable
    mechanics.
- `src/power_atlas/adapters/neo4j/retrieval_session.py`
  - the retrieval session builder is now admitted as a mechanics-only factory
    helper.
- `src/power_atlas/bootstrap/domain_pack.py`
  - the descriptor itself is generic composition vocabulary, even though the
    first real pack still lives inside Power Atlas.

## Domain-pack-leaning surfaces

These surfaces mainly teach the system how to reason in the Power Atlas domain
or prove the domain-pack seam with a second domain.

- `src/power_atlas/policy_packs/market_trade.py`
  - explicit proof that retrieval ontology, prompt posture, and domain
    semantics belong in a pack rather than in the kernel.
- `src/power_atlas/claim_extraction_*.py`
  - claim labels, extraction posture, and claim-specific graph behavior are
    domain semantics first.
- `src/power_atlas/claim_participation_*.py`
  - participation edges and claim-role semantics are Power Atlas graph policy.
- `src/power_atlas/entity_resolution_*.py`
  - canonical alignment, clustering, and resolution posture are currently
    shaped around Power Atlas semantics and graph expectations.
- `src/power_atlas/narrative_extraction_*.py`
  - narrative extraction behavior is tied to current research framing and
    output expectations.
- `src/power_atlas/contracts/claim_extraction_policy.py`
  - the contract form is reusable, but the default policy authority is part of
    domain posture.
- `src/power_atlas/contracts/retrieval_policy.py`
  - the shape is reusable, but current defaults still encode project-specific
    retrieval posture.
- `src/power_atlas/contracts/prompts.py`
  - prompt identifiers and wording authority belong with domain semantics once
    they are fully separated.

## Application-shell-leaning surfaces

These surfaces primarily operate the repo as a working product.

- `src/power_atlas/backend_app.py`
  - FastAPI app assembly, route behavior, and API defaults are shell concerns.
- `src/power_atlas/backend_*.py`
  - backend catalog, graph, router, and response adapter modules are app-facing
    operating surfaces.
- `src/power_atlas/api.py`
  - public package facade is part of how this repo exposes its shell/runtime
    to consumers.
- `src/power_atlas/cli/*.py`
  - CLI entrypoints and reports are operator workflow surfaces.
- `backend/main.py`
  - backend process entrypoint is application hosting posture.
- `frontend/`
  - frontend UI is shell behavior by definition.
- `demo/`
  - demo drivers, fixtures, and runbooks are repo-specific operator workflows.
- `docker-compose.yml`
  - local environment composition is app/deployment posture.
- `README.md`
  - current top-level framing is branded and operator-facing.

## Mixed or transitional surfaces

These are the important boundaries that still blend roles.

- `src/power_atlas/context.py`
  - `AppContext` and `RequestContext` still bundle app settings, pipeline
    contract state, and default policies into one carrier.
- `src/power_atlas/settings.py`
  - settings mechanics are reusable in principle, but current env naming and
    defaults still reflect the Power Atlas app shell.
- `src/power_atlas/bootstrap/app.py`
  - composition is kernel-worthy, but the current baseline still carries repo
    paths, environment names, and host-app default authority.
- `src/power_atlas/retrieval_request_context_adapters.py`
  - now thinner, and can bind through `RequestRuntime`, but still remains
    app-owned because that runtime carrier still comes from `context.py` and
    the `RequestContext` wrappers remain shell-side bridges.
- `src/power_atlas/claim_extraction_entrypoint.py`
  - now has the same initial `RequestRuntime` bridge shape, but still remains
    app-owned because policy/runtime ownership still comes from
    `context.py`-owned carriers and `RequestContext` compatibility wrappers.
- `src/power_atlas/entity_resolution_entrypoint.py`
  - now has the same initial `RequestRuntime` bridge shape, but still remains
    app-owned because dataset/policy/runtime ownership still comes from
    `context.py`-owned carriers and `RequestContext` compatibility wrappers.
- `src/power_atlas/adapters/neo4j/*.py`
  - some modules are clean mechanics, others remain stage-specific runtime
    surfaces.
- `src/power_atlas/pdf_ingest_*.py`
  - ingest mechanics and repo-local dataset/source assumptions are still mixed.
- `src/power_atlas/structured_ingest_*.py`
  - same issue: reusable processing shape, but current dataset conventions are
    still app-local.
- `src/power_atlas/retrieval_runtime.py`
  - retrieval execution contains reusable mechanics but still sits near
    Power Atlas policy and runtime defaults.
- `src/power_atlas/graph_health_*.py`
  - diagnostics logic is promising kernel material, but current checks are not
    yet separated cleanly from the present graph contract.

## What this map says about `power_atlas`

This map reinforces the current interpretation from the target-shape roles doc:
`power_atlas` is still playing more than one role.

Inside the same package today, it contains:

- emerging kernel mechanics,
- Power Atlas domain semantics,
- and application-shell operating surfaces.

That is a workable transitional state, but it is not yet a clean generic
system identity.

## Implication for near-term extraction work

The practical order of operations remains:

1. keep promoting only the high-confidence mechanics into explicit kernel-style
   surfaces,
2. keep moving Power Atlas policy/default authority toward explicit domain-pack
   seams,
3. keep app entrypoints, dataset authority, and operator posture in the shell
   until another real consumer proves a broader split.

This is why the next high-value work is still explicit default/domain
authority, not rename-driven restructuring.

The ordered follow-up sequence for those mixed boundaries now lives in
`docs/repository_restructure/repository_restructure_target_shape_extraction_sequence.md`.