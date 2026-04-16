# Phase 2 Follow-Up Task — `demo/contracts` Deprecation Planning

**Status:** not started  
**Owner:** Ash  
**Date context:** 2026-04-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`

## Purpose

This document defines the next deliberate Phase 2 follow-up task for the
package-first migration lane:

- determine how `demo/contracts` should be deprecated and eventually retired,
- keep the current compatibility-preserving posture explicit until that work is
  accepted,
- prevent incidental import cleanup from turning into untracked compatibility
  breakage.

This is a planning and scoping task, not an immediate deletion or refactor task.

## Current repo state

As of 2026-04-16:

- package-owned contract modules live under `src/power_atlas/contracts/`,
- `power_atlas.contracts` is the preferred stable contract surface,
- `power_atlas.contracts.pipeline` remains intentionally submodule-only for
  stateful pipeline access,
- `demo/contracts` remains an intentional compatibility layer,
- compatibility tests still exercise the demo contract surface deliberately,
- remaining `demo.contracts` references are a mix of:
  - compatibility tests,
  - compatibility notes in docs,
  - the preserved `demo.contracts.pipeline` logger name,
  - active compatibility shims.

The repository is therefore past blind package-foundation work but not yet ready
to treat shim removal as a mechanical cleanup pass.

## Non-goals

This follow-up task does not authorize:

- immediate removal of `demo/contracts/*`,
- runtime behavior changes unrelated to compatibility planning,
- changes to the accepted Phase 1 execution posture,
- broad restructuring outside the contract-surface boundary,
- warning spam or deprecation mechanics without an agreed migration path.

## Questions this task must answer

### 1. What compatibility commitment still exists?

Determine which `demo/contracts` entrypoints are still intentionally supported
for:

- active runtime code,
- tests that enforce compatibility behavior,
- operator-facing documentation,
- any likely external or automation-facing usage.

### 2. Which shims are equivalent and which are special?

At minimum, distinguish between:

- simple re-export shims,
- package-root compatibility proxy behavior in `demo/contracts/__init__.py`,
- the stateful module-alias shim in `demo/contracts/pipeline.py`.

The pipeline shim must be handled separately because it preserves shared mutable
module identity.

### 3. What would count as safe retirement readiness?

Define explicit retirement prerequisites, such as:

- remaining non-test callers migrated or intentionally exempted,
- compatibility tests either retired or relocated with replacement coverage,
- documentation updated,
- operator impact reviewed,
- an agreed stance on whether any deprecation window is required.

### 4. What should happen before any code removal?

Define the acceptance gate for implementation work, including:

- the validation suite required before shim removal,
- whether shim retirement belongs in Phase 2 completion or Phase 10 legacy
  retirement,
- whether `demo/contracts` should be retired in one step or in classes of shims.

## Required deliverables

The planning task should produce:

1. a classified inventory of `demo/contracts` shims and remaining callers,
2. a recommended retirement order,
3. explicit keep/deprecate/remove criteria for each shim class,
4. a validation plan for any future retirement implementation,
5. a recommendation on whether retirement belongs to late Phase 2 work or should
   remain deferred to Phase 10.

## Suggested execution sequence

1. Re-inventory `demo/contracts` callers and classify them as runtime,
   compatibility-test, documentation-only, or deliberate exception.
2. Separate simple package-owned contract shims from the special stateful
   pipeline shim.
3. Decide whether a deprecation window is needed or whether removal can remain a
   repo-internal migration task.
4. Propose a retirement order with explicit validation gates.
5. Review the result against the canonical restructure checklist before any
   implementation work begins.

## Completion criteria

This follow-up task is complete when the repo has an accepted answer to all of
the following:

- what `demo/contracts` still promises today,
- which shim classes can be retired together and which cannot,
- what validation is required before retirement,
- whether shim retirement is a late-Phase-2 task or a Phase-10 legacy-retirement
  task.

Until then, `demo/contracts` should continue to be treated as an intentional,
tracked compatibility layer.