# Phase 10 Planning Task — Legacy Retirement Shortlist

**Status:** in progress  
**Owner:** Ash  
**Date context:** 2026-04-30  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`

## Purpose

This document starts the concrete planning lane for Phase 10 legacy retirement.

The immediate goal is not to delete code opportunistically. The goal is to:

- classify which legacy-shaped surfaces are plausible retirement candidates,
- separate blocked compatibility surfaces from genuinely archivable ones,
- define a small, ordered shortlist for later implementation work.

## Current repo posture

As of 2026-04-30:

- `demo/` is still the active implementation and operator-facing walkthrough surface,
- CLI and API transport logic has moved package-side under `src/power_atlas/interfaces/`,
- several legacy entrypoint files now remain intentionally as compatibility shells,
- `demo/contracts` remains a tracked compatibility layer rather than expired debt,
- the backend API and frontend UI are both documented as minimal or transitional surfaces rather than the primary product path.

Phase 10 therefore cannot be treated as a blanket instruction to remove everything outside `src/`.

### Implementation checkpoint (2026-04-30)

- `__queuestorage__/` was verified to have no remaining workspace references outside the Phase 10 planning docs,
- no Azure Functions or queue-storage-specific tooling was found in the repository,
- the directory was empty in the checked workspace,
- the directory has now been removed as the first low-risk Phase 10 retirement slice.

## Retirement classes

### 1. Likely early retirement or archive candidates

These look like the best first shortlist once implementation work begins:

- `_archive/`
  - currently contains historical experimentation material
  - already reads as intentionally archival rather than active product code
  - likely action: keep archived but make its non-active status explicit in final docs or move it behind a clearer archival boundary if needed

`__queuestorage__/` no longer belongs on the active shortlist because that low-risk retirement slice has already been completed.

The remaining early candidate in this class is `_archive/`, which still appears operationally low-coupling compared with the compatibility layers.

### 2. Deferred shim-retirement candidates

These remain the main compatibility-retirement lane, but they are not yet ready for blind removal:

- `demo/contracts/__init__.py`
- `demo/contracts/*.py` simple package-owned contract shims
- `demo/contracts/pipeline.py` module-alias shim

Why deferred:

- compatibility tests still intentionally exercise the demo contract surface,
- `demo.contracts.pipeline` still preserves logger-name and shared-module identity behavior,
- the dedicated planning document for this surface already concludes that removal belongs in deliberate Phase 10 work, not incidental cleanup.

Recommended treatment:

- keep this as the highest-value shim-retirement lane,
- do not combine it with unrelated directory cleanup,
- retire simple re-export shims separately from the special pipeline alias.

### 3. Not-yet-retirable compatibility shells

These files or directories still have an accepted role and should not yet be put on a deletion shortlist:

- `demo/`
  - still the active implementation and walkthrough surface referenced by the root README
- `backend/main.py`
  - now a thin compatibility shell for the package-owned FastAPI app factory
- `frontend/`
  - documented as a transitional non-core health-check client, not yet a retired surface
- `pipelines/query/*.py` and `scripts/sync_vendor_version.py`
  - now thin compatibility entrypoints, but still the stable invocation surfaces
- compatibility re-export modules noted in the decisions register under the package root

These are legacy-shaped surfaces, but they are not yet expired. Removing them before the active execution posture changes would create churn without closing the real migration obligations.

### 4. Documentation normalization candidates

These are likely to become follow-up work once any retirement implementation starts:

- root `README.md`
  - currently states that `demo/` is the working implementation and that `backend/` / `frontend/` are scaffolding or transitional surfaces
- `demo/README.md`
  - remains the active operator walkthrough and should only be downgraded after the active execution path changes
- restructure docs that still describe compatibility shells or shim deferment as current posture

Documentation changes should follow actual retirement work, not lead it.

## Initial readiness assessment

### Ready for Phase 10 planning

- classify `_archive/` as archival/non-active,
- define the implementation order for `demo/contracts` shim retirement,
- define the documentation updates that must accompany any actual deletion.

### Not ready for direct removal

- `demo/` as a whole,
- compatibility entrypoint shells under `demo/`, `pipelines/query/`, `scripts/`, and `backend/`,
- `frontend/` as a whole,
- `demo/contracts/pipeline.py` until logger-name and shared-module identity obligations are intentionally retired.

## Recommended implementation order

1. Make `_archive/` status explicit as archived/non-active and decide whether its current location is acceptable.
2. Execute the already-planned `demo/contracts` retirement lane in classes:
   - simple re-export shims,
   - root compatibility proxy,
   - stateful pipeline alias shim.
3. Only after actual retirement work lands, update README and restructure docs to remove stale references to retired surfaces.

## Acceptance gate before any code deletion

Before removing a shortlisted surface, require at minimum:

- a caller/reference inventory for that surface,
- confirmation that the surface is not the active documented execution path,
- focused validation for any affected CLI/API/test path,
- documentation updates prepared in the same change,
- explicit confirmation that the retirement does not violate previously accepted compatibility decisions.

## Initial recommendation

Treat the next Phase 10 implementation slice as one of these, not both at once:

1. a low-risk cleanup lane around explicit archive labeling for `_archive/`, or
2. the higher-value but more constrained `demo/contracts` shim-retirement lane.

Do not mix archive cleanup, shim retirement, and compatibility-shell deletion into a single pass.