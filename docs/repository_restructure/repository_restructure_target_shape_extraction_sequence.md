# Target Shape Extraction Sequence

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_target_shape_roles.md`
- `docs/repository_restructure/repository_restructure_target_shape_current_surface_map.md`
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `docs/repository_restructure/repository_restructure_shared_mechanics_pilot_contract.md`

## Purpose

This document turns the current surface map into an ordered extraction sequence.

It does **not** authorize a broad namespace split or a rename-first program.
Its purpose is to define the next bounded restructuring slices in the order
most likely to produce an honest kernel/domain-pack/application-shell split.

## Ordering rule

The sequence below follows one rule: extract the authority boundaries before
extracting more mechanics.

That means the next slices should target the places where Power Atlas defaults,
domain policy, dataset authority, and app context are still ambient. Those are
the boundaries currently preventing a cleaner kernel identity.

## Priority 1: make default authority explicit

**Why first:** the current repo is still blocked most by ambient defaults, not
by missing mechanics seams.

**Primary targets:**

- `src/power_atlas/context.py`
- `src/power_atlas/settings.py`
- `src/power_atlas/bootstrap/app.py`
- `src/power_atlas/contracts/retrieval_policy.py`
- `src/power_atlas/contracts/claim_extraction_policy.py`
- `src/power_atlas/contracts/prompts.py`

**Goal:** stop treating Power Atlas retrieval policy, prompt posture, env
naming, and similar defaults as if they are universal runtime behavior.

**Desired outcome:**

- app-shell defaults stay with the app shell,
- domain defaults move toward explicit domain-pack surfaces,
- reusable runtime helpers accept explicit inputs instead of silently reading
  Power Atlas assumptions.

**What success looks like:**

- bootstrap can compose runtime state without assuming the Power Atlas policy
  set by default,
- at least one package-owned flow can accept explicit domain/app defaults
  without compatibility theater,
- no backend or CLI shell contract has to move yet.

**Current checkpoint:**

- `AppBaseline` now owns explicit retrieval, claim-extraction, and
  entity-type-normalization policy selection for package-owned app-context
  composition,
- `resolve_app_baseline(...)` can now also shape the default retrieval QA
  prompt id, retrieval RAG template, and claim-extraction prompt id before
  those defaults are baked into baseline-owned policies,
- `contracts/prompts.py` now exposes a prompt-default carrier that preserves
  the Power Atlas constants as compatibility surfaces while giving baseline-
  owned composition a single prompt-default object to override,
- `narrative_extraction_cli.py` can now consume baseline-owned narrative prompt
  defaults in its stage path instead of reading only the ambient prompt
  registry constant,
- the market-trade retrieval consumer proof now uses baseline-owned retrieval
  policy selection rather than mutating `app_context.policies` after the fact,
- prompt/default authority and env-naming authority still remain active follow-
  up work inside Priority 1.

## Priority 2: split kernel runtime carriers from app-owned context

**Why second:** `RequestContext` and `AppContext` still bundle together too many
roles, which prevents lower layers from having a clean kernel-facing identity.

**Primary targets:**

- `src/power_atlas/context.py`
- `src/power_atlas/retrieval_request_context_adapters.py`
- `src/power_atlas/bootstrap/app.py`
- request-context entrypoints that only need execution/runtime fields

**Goal:** separate reusable execution/runtime carriers from app-owned context
wrappers.

**Desired outcome:**

- kernel-facing helpers accept request-free runtime state or a thinner generic
  carrier,
- app-owned wrappers remain responsible for binding shell defaults and policy,
- the existing request-context adapters become visibly shell-side bridges.

**What success looks like:**

- another small set of helpers can move below `RequestContext` the way
  retrieval runtime binding already did,
- `context.py` stops being a single blended authority surface.

## Priority 3: externalize dataset and source authority for ingest/runtime flows

**Why third:** once defaults and context are explicit, the next remaining mixed
boundary is repo-local dataset/source authority.

**Primary targets:**

- `src/power_atlas/pdf_ingest_*.py`
- `src/power_atlas/structured_ingest_*.py`
- `src/power_atlas/bootstrap/app.py`
- `src/power_atlas/contracts/paths.py`
- runtime helpers that still infer repo-local layout

**Goal:** make dataset roots, source connectors, and repo-layout assumptions an
explicit shell concern rather than a hidden runtime dependency.

**Desired outcome:**

- ingest/runtime mechanics can run from explicit dataset/source contracts,
- repo-local fixture layout stays shell-owned,
- a future second app shell would not need to imitate the Power Atlas repo
  layout just to reuse the runtime.

**What success looks like:**

- ingest flows no longer rely on hidden repo-shape assumptions below the shell,
- current shell defaults still work, but now through explicit authority seams.

## Priority 4: separate reusable diagnostics primitives from Power Atlas graph contracts

**Why fourth:** diagnostics are promising kernel material, but only after the
runtime/default/domain boundaries above are clearer.

**Primary targets:**

- `src/power_atlas/graph_health_*.py`
- `src/power_atlas/claim_extraction_diagnostics*.py`
- reusable report/summary helpers that do not require Power Atlas graph
  semantics

**Goal:** distinguish reusable diagnostic mechanics from checks that are only
meaningful for the current graph contract.

**Desired outcome:**

- generic diagnostic/reporting helpers can move downward,
- Power Atlas-specific graph expectations remain in the domain pack or shell.

**What success looks like:**

- reusable diagnostics become identifiable as a kernel-facing family,
- graph-contract-specific checks stay explicitly scoped to Power Atlas.

## Priority 5: do narrower follow-up audits, not another broad shared-core push

**Why last:** the repo already proved that mechanics extraction is valuable, but
the remaining hard questions are about authority, not inventory.

**Primary targets:**

- `src/power_atlas/adapters/neo4j/*.py`
- any remaining mixed helper families revealed by priorities 1 through 4

**Goal:** resume extraction only after the higher-value authority boundaries are
clearer.

**Desired outcome:**

- subsequent audits can classify additional helpers with less ambiguity,
- extraction work remains small, local, and evidence-based.

**What success looks like:**

- no renewed pressure for a premature namespace split,
- any future mechanics promotion is justified by a now-cleaner boundary.

## Things this sequence does not authorize

This sequence does **not** recommend:

- renaming the repo as if the generic kernel already exists,
- starting a broad shared-core namespace split,
- treating backend or frontend shell surfaces as generic kernel API,
- moving dataset authority or operator posture into a would-be shared layer by
  accident.

## Practical interpretation

If only one lane is resumed next, it should be Priority 1.

That is the point where the current architecture is least honest: the repo has
already proven some reusable mechanics, but Power Atlas policy/default
authority is still too ambient for the kernel identity to be real.

After that, Priority 2 becomes the next local step, because a thinner runtime
carrier boundary makes later ingest, diagnostics, and adapter decisions much
easier to classify correctly.