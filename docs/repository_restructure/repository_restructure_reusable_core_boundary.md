# Reusable Core Boundary

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-12  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`
- `docs/repository_restructure/repository_restructure_second_domain_pilot_contract.md`
- `docs/repository_restructure/repository_restructure_second_domain_gap_inventory.md`

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
- request-context and stage/runtime paths already accept and forward explicit
  retrieval policy objects, but that boundary is still concentrated in the
  current Power Atlas retrieval flow rather than locked as a broader reusable
  package contract,
- some runtime call paths still rely on Power Atlas defaults when no explicit
  policy is supplied,
- the current proof posture is still stronger in demo-stage coverage than in
  shared-package extraction coverage,
- there is not yet a second-app or second-domain proof showing that the same
  policy surface is sufficient outside the current Power Atlas retrieval stack.

## Acceptance criteria for this first seam

The retrieval expansion policy slice should be considered complete only when:

- retrieval runtime entrypoints accept an explicit retrieval policy or provider
  from app/request-owned context and keep that behavior locked at the package
  seam rather than only in demo-stage coverage,
- retrieval query construction uses that injected policy end to end,
- prompt/template selection for retrieval also follows the same injected policy
  path,
- at least one alternate test policy can be exercised through the shared
  package-owned retrieval seam without monkeypatching implementation modules,
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
2. lock the current runtime/provider boundary around retrieval expansion policy
  with focused package-level proofs,
3. define the constrained second-domain pilot contract for the first non-Power
  Atlas proof target,
4. close any remaining implicit-default gaps in retrieval policy threading that
  those focused proofs or pilot work uncover,
5. re-evaluate whether the shared-core namespace split is justified after that
   proof exists.

## Success condition for the broader reuse plan

The repo should be considered ready for a shared-kernel extraction only after:

- at least one policy seam has been made explicit and proven,
- the reusable-core candidates above no longer depend implicitly on Power Atlas
  policy defaults,
- a second app or constrained second-domain pilot can consume the shared runtime
  without copying the current Power Atlas runtime modules.