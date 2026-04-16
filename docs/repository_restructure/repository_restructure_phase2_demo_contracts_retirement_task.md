# Phase 2 Follow-Up Task — `demo/contracts` Deprecation Planning

**Status:** in progress  
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

## Initial inventory snapshot

The first classification pass on 2026-04-16 found no remaining active
non-shim runtime imports of `demo.contracts` outside the compatibility layer
itself.

The remaining references fall into the following classes.

### A. Active shim modules

These files are the compatibility layer itself and remain active by design:

- `demo/contracts/__init__.py`
- `demo/contracts/claim_schema.py`
- `demo/contracts/manifest.py`
- `demo/contracts/paths.py`
- `demo/contracts/pipeline.py`
- `demo/contracts/prompts.py`
- `demo/contracts/resolution.py`
- `demo/contracts/retrieval_early_return_policy.py`
- `demo/contracts/retrieval_metadata_policy.py`
- `demo/contracts/runtime.py`
- `demo/contracts/structured.py`

### B. Compatibility-test callers

These references intentionally verify that the compatibility surface still
behaves as documented and should not be treated as accidental cleanup debt.

- `tests/test_power_atlas_package.py`
  - verifies package-owned objects remain reachable via demo shim modules
  - verifies `demo.contracts.pipeline` is the same module object as
    `power_atlas.contracts.pipeline`
- `demo/tests/test_retrieval_metadata_policy.py`
  - verifies `demo.contracts` root re-exports for metadata policy objects
- `demo/tests/test_retrieval_result_contract.py`
  - verifies `demo.contracts` root re-exports for early-return policy objects
- `demo/tests/test_orchestrator_modules.py`
  - preserves explicit demo prompt-shim checks
  - preserves explicit demo pipeline-module checks
- `demo/tests/test_pipeline_contract.py`
  - preserves logger-name and pipeline module behavior coverage
- `demo/tests/test_demo_workflow.py`
  - asserts warning logs under the preserved `demo.contracts.pipeline` logger
    name
- `demo/tests/test_retrieval_metadata_projection_parity.py`
  - docs/tests reference the demo surface as the policy anchor for parity

### C. Documentation-only compatibility references

These references are intentional documentation of compatibility posture rather
than runtime dependency.

- `README.md`
- `docs/architecture/retrieval-citation-result-contract-v0.1.md`
- canonical restructure docs under `docs/repository_restructure/`

### D. Deliberate special-case runtime exception

- `src/power_atlas/contracts/pipeline.py`
  - preserves the logger name `demo.contracts.pipeline`
  - this is not an import dependency, but it is a compatibility-facing runtime
    identity that must be treated as part of the shim surface

### E. Generated metadata

Generated package metadata may continue to echo compatibility wording copied
from the README:

- `src/power_atlas.egg-info/PKG-INFO`
- virtualenv `dist-info/METADATA`

These are not first-class retirement blockers; they follow the canonical docs.

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

#### Current classification

- **Simple package-owned contract shims**
  - `claim_schema.py`
  - `manifest.py`
  - `paths.py`
  - `prompts.py`
  - `resolution.py`
  - `retrieval_early_return_policy.py`
  - `retrieval_metadata_policy.py`
  - `runtime.py`
  - `structured.py`
- **Root compatibility proxy**
  - `demo/contracts/__init__.py`
  - special because it defines the demo-root compatibility surface and lazy
    attributes
- **Stateful module-alias shim**
  - `demo/contracts/pipeline.py`
  - special because it preserves shared mutable module identity, not just object
    re-export behavior

### 3. What would count as safe retirement readiness?

Define explicit retirement prerequisites, such as:

- remaining non-test callers migrated or intentionally exempted,
- compatibility tests either retired or relocated with replacement coverage,
- documentation updated,
- operator impact reviewed,
- an agreed stance on whether any deprecation window is required.

#### Initial readiness assessment

The repo is not yet retirement-ready because:

- compatibility tests still intentionally depend on demo-surface imports,
- the demo-root proxy and pipeline alias still encode explicit compatibility
  promises,
- the logger-name compatibility surface has not been reviewed for change
  tolerance,
- the accepted phase-placement decision is to defer actual shim-retirement
  implementation to Phase 10 while `demo/` remains the active execution
  surface.

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

## Initial recommendation

### Recommended retirement order

1. **Plan only first**
   - keep the current shims in place while the compatibility contract is made
     explicit
2. **Simple package-owned contract shims**
   - these are the best first retirement candidates once the keep/remove
     contract is agreed because they are mechanically simpler and already have
     package-owned authoritative implementations
3. **`demo/contracts/__init__.py` root proxy**
   - retire only after the intended root-surface compatibility promise is either
     removed or replaced with explicit package-native guidance
4. **`demo/contracts/pipeline.py` module-alias shim and associated logger-name
   compatibility**
   - treat as the last retirement candidate because it carries mutable-state and
     logging identity behavior that simple re-export shims do not

### Recommended phase placement

The planning work belongs in Phase 2 now.

Actual shim-removal implementation should be treated as **deferred to Phase 10**
unless a later repo state materially changes the current execution posture.

#### Current recommendation

Based on the current repo state, the retirement implementation should not be
scheduled as a late-Phase-2 slice.

Reasons:

- `demo/` remains the active execution center of gravity,
- the remaining demo contract surface is now primarily an explicit compatibility
  promise rather than stray runtime coupling,
- the root proxy and pipeline alias still encode compatibility behavior that is
  broader than a simple import cleanup,
- Phase 10 is already defined as the legacy-retirement phase where transitional
  structures and compatibility shims are removed deliberately.

This means the right Phase 2 outcome is:

- keep the shim inventory and compatibility contract explicit,
- avoid more blind import cleanup framed as retirement,
- continue package adoption and broader architectural movement elsewhere,
- defer actual shim-removal implementation to Phase 10 unless the repo later
  stops treating `demo/` as an active execution surface.

### Validation gate for any future implementation

Before any shim-removal code change, require at minimum:

- `tests/test_power_atlas_package.py`
- compatibility-focused demo tests that currently import or assert against
  `demo.contracts`
- any focused tests covering the affected contract surface
- `make phase1-verify` for any change that can affect runtime behavior or the
  accepted CLI path

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

## Current decision outcome

As of 2026-04-16, this planning task recommends:

- **Phase 2:** finish planning, classification, and compatibility-boundary
  documentation only
- **Phase 10:** perform actual `demo/contracts` retirement work, unless a future
  checkpoint shows that `demo/` is no longer an active execution surface and the
  compatibility promise has already been narrowed materially