# Reusable Core Boundary

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-12  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`

## Purpose

This document turns the generic-research-runner feasibility memo into an
explicit working boundary for the current repo.

The migration question is no longer whether `power-atlas` is package-shaped.
That is already true. The current question is which package-owned surfaces are
ready to become an internal reusable research-runner core, which ones need
policy seams first, and which ones should remain Power Atlas application
surfaces.

## Current checkpoint

At this checkpoint:

- the package-first restructure is functionally closed,
- `src/power_atlas/` is installable and used through real consumer-facing
  proofs,
- the public backend import surface now exists through `power_atlas.api`,
- the remaining work for reuse is no longer packaging cleanup,
- the remaining work for reuse is policy-boundary extraction.

This document defines the minimum extraction boundary for that next phase.

## Boundary defined in this checkpoint

### 1. Reusable core candidates now

These areas already look strong enough to be treated as reusable-core
candidates with naming cleanup and extraction work, but without first needing a
new abstraction program.

- `power_atlas.settings`
- `power_atlas.context`
- `power_atlas.bootstrap`
- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.contracts.paths`
- `power_atlas.orchestration.*`
- `power_atlas.run_scope_queries`
- `power_atlas.neo4j_io`
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_result_prelude`
- `power_atlas.retrieval_request_helpers`
- `power_atlas.retrieval_path_diagnostics` as a reusable pattern, though its
  field taxonomy may later need cleanup
- `power_atlas.adapters.neo4j.*` modules whose responsibility is driver,
  session, query-execution, or runtime-envelope management rather than domain
  traversal policy
- interface-shell patterns under `power_atlas.interfaces.cli.*` and the public
  facade pattern used by `power_atlas.api`, while not assuming that the current
  Power Atlas route contracts themselves are the final shared API shape

### 2. Reusable only after explicit policy seams

These areas contain real reusable value, but they still encode the current
Power Atlas ontology, prompt posture, or structured-data assumptions too
directly to be treated as shared core yet.

- `power_atlas.contracts.retrieval_policy`
- `power_atlas.retrieval_query_builders`
- `power_atlas.contracts.prompts`
- `power_atlas.contracts.claim_schema`
- `power_atlas.extraction_rows`
- `power_atlas.extraction_writes`
- `power_atlas.entity_resolution_queries`
- `power_atlas.entity_resolution_writes`
- `power_atlas.structured_ingest_writes`
- stage runtimes that still assume the current ontology path even after driver
  lifecycle and bootstrap concerns were extracted

These modules are the right extraction targets for domain policy providers or
protocols. They are not good candidates for immediate namespace moves while the
current Power Atlas defaults remain implicit.

### 3. Power Atlas application surfaces

These areas should remain with the Power Atlas app layer unless a second app
proves that the same exact semantics should be shared.

- `demo/` operator workflows and CLI docs
- Power Atlas fixture datasets and current fixture-backed validation posture
- benchmark cases tied to current named entities or current fixture families
- operator-facing copy and prompt wording that names Power Atlas explicitly
- the concrete backend route contracts exposed today through `power_atlas.api`
  and `backend/main.py`, even though the facade and shell pattern behind them
  may inform a shared integration layer later
- the current in-repo `frontend/` placeholder shell and its Power Atlas-specific
  documentation posture
- domain framing and editorial voice in the current docs set

## First seam recommendation

The first extraction seam should be **retrieval expansion policy**.

This is the highest-leverage next slice because it sits at the center of the
repo's current reusable value while also remaining one of the clearest places
where Power Atlas semantics still shape package behavior.

### Why this seam is the right first slice

- it affects core runtime behavior rather than branding alone,
- it is already partially isolated,
- it can be proven with focused tests before any broader package split,
- it avoids introducing a broad plugin framework before a second app exists.

### Evidence from the current code

The repo already has a partial retrieval-policy boundary:

- `power_atlas.contracts.retrieval_policy` defines `RetrievalOntology` and
  `RetrievalPolicy`
- `power_atlas.retrieval_query_builders` already accepts a
  `retrieval_ontology` parameter and can build queries from non-default labels
  and relationships

But the seam is not yet a complete reusable policy surface:

- the default retrieval policy is still the Power Atlas policy object,
- runtime call paths still rely on those defaults implicitly,
- the ontology and prompt policy are not yet threaded end-to-end through an
  explicit request/app-context-owned provider boundary,
- there is not yet a focused proof showing that an alternate retrieval policy
  can be swapped in without monkeypatching implementation modules.

## Acceptance criteria for this first seam

The retrieval expansion policy slice should be considered complete only when:

- retrieval runtime entrypoints accept an explicit retrieval policy or provider
  from app/request-owned context rather than silently re-resolving Power Atlas
  defaults,
- retrieval query construction uses that injected policy end to end,
- prompt/template selection for retrieval also follows the same injected policy
  path,
- at least one alternate test policy can be exercised without monkeypatching
  implementation modules,
- existing Power Atlas retrieval behavior remains unchanged when the default
  Power Atlas policy is supplied.

## Non-goals for this checkpoint

This boundary does **not** authorize the following yet:

- renaming `power_atlas` as if it were already a generic package,
- splitting files into a new shared namespace before one explicit policy seam is
  proven,
- introducing a large plugin system across prompts, ontology, extraction,
  entity resolution, and structured ingest all at once,
- genericizing Power Atlas-specific docs or operator flows prematurely,
- treating the existence of `RetrievalPolicy` as proof that the broader reuse
  extraction is already done.

## Immediate sequence

The next bounded steps should proceed in this order:

1. treat this document as the working extraction boundary,
2. implement the missing runtime/provider injection boundary around retrieval
   expansion policy,
3. add one alternate retrieval-policy test that exercises the seam without
   monkeypatching implementation modules,
4. re-evaluate whether the shared-core namespace split is justified after that
   proof exists.

## Success condition for the broader reuse plan

The repo should be considered ready for a shared-kernel extraction only after:

- at least one policy seam has been made explicit and proven,
- the reusable-core candidates above no longer depend implicitly on Power Atlas
  policy defaults,
- a second app or constrained second-domain pilot can consume the shared runtime
  without copying the current Power Atlas runtime modules.