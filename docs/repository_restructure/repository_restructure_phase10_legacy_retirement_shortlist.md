# Phase 10 Planning Task — Legacy Retirement Shortlist

**Status:** completed as a planning shortlist  
**Owner:** Ash  
**Date context:** 2026-04-30  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`

## Purpose

This document records the concrete planning shortlist for Phase 10 legacy retirement.

The immediate goal of this shortlist was not to delete code opportunistically. The goal was to:

- classify which legacy-shaped surfaces were plausible retirement candidates,
- separate blocked compatibility surfaces from genuinely archivable ones,
- define a small, ordered shortlist for later implementation work.

## Current repo posture

As of 2026-04-30:

- `demo/` is still the active implementation and operator-facing walkthrough surface,
- CLI and API transport logic has moved package-side under `src/power_atlas/interfaces/`,
- several legacy entrypoint files now remain intentionally as compatibility shells,
- the former `demo/contracts` compatibility layer has now been retired,
- the backend API and frontend UI are both documented as minimal or transitional surfaces rather than the primary product path.

Phase 10 therefore cannot be treated as a blanket instruction to remove everything outside `src/`.

### Implementation checkpoint (2026-04-30)

- `__queuestorage__/` was verified to have no remaining workspace references outside the Phase 10 planning docs,
- no Azure Functions or queue-storage-specific tooling was found in the repository,
- the directory was empty in the checked workspace,
- the directory has now been removed as the first low-risk Phase 10 retirement slice.
- `_archive/` has now been labeled explicitly as archived, non-active material via `_archive/README.md` and the root `README.md`,
- the current decision is to keep its historical contents in place for reference rather than delete them during this low-risk slice.
- a fresh 2026-04-30 `demo.contracts` caller re-inventory found no remaining non-test runtime imports outside the compatibility layer itself,
- at that checkpoint, the simple shim class was mechanically simple one-line package re-exports, while `demo/contracts/__init__.py` and `demo/contracts/pipeline.py` still required special handling.
- the first simple-shim retirement slice has now removed `demo/contracts/resolution.py`, `demo/contracts/retrieval_early_return_policy.py`, and `demo/contracts/retrieval_metadata_policy.py`,
- post-removal searches found no remaining references to those retired submodule paths.
- the second zero-caller simple-shim retirement slice has now removed `demo/contracts/claim_schema.py`, `demo/contracts/manifest.py`, `demo/contracts/paths.py`, `demo/contracts/runtime.py`, and `demo/contracts/structured.py`,
- post-removal searches found no remaining references to those retired submodule paths, and `tests/test_power_atlas_package.py` continues to pass.
- the final simple-shim retirement slice has now removed `demo/contracts/prompts.py`,
- post-removal searches found no remaining references to `demo.contracts.prompts`, and a nearby prompt-focused orchestrator slice continues to pass.
- the root compatibility proxy in `demo/contracts/__init__.py` has now been retired after rewriting the remaining direct root-import test callers to use package-native imports,
- the final stateful module-alias shim in `demo/contracts/pipeline.py` has now also been retired,
- the now-empty `demo/contracts/` directory has been removed,
- the remaining `demo.contracts` work is now documentation wording cleanup only.

## Retirement classes

### 1. Likely early retirement or archive candidates

These look like the best first shortlist once implementation work begins:

- `_archive/`
  - currently contains historical experimentation material
  - now explicitly labeled as archival/non-active in repo docs
  - accepted decision: keep it at the repo root as the explicit archival boundary for now
  - rationale: no non-doc/runtime coupling was found, and moving it would create reference churn without reducing current product risk

`__queuestorage__/` no longer belongs on the active shortlist because that low-risk retirement slice has already been completed.

The remaining early candidate in this class is `_archive/`, but its placement decision is now resolved: it should remain at the repo root until a broader repository-layout change creates a stronger reason to move archival material elsewhere.

### 2. Deferred shim-retirement candidates

There are no remaining `demo/contracts` code shims in the repository.

Current outcome:

- the simple shim class is retired,
- the root compatibility proxy is retired,
- the pipeline module-alias shim is retired,
- the remaining work in this lane is documentation normalization only.

Recommended treatment:

- keep `demo.contracts` retirement closed as a completed code lane,
- treat any remaining `demo.contracts` mentions as wording cleanup rather than a live shim boundary.

Current checkpoint:

- the simple package-owned contract shims are now the first concrete Phase 10 shim-retirement class,
- the first zero-caller simple-shim subset has already been retired successfully,
- the second zero-caller simple-shim subset has also been retired successfully,
- the simple package-owned contract shim class is now fully retired,
- the root compatibility proxy in `demo/contracts/__init__.py` is now retired,
- the stateful `demo/contracts/pipeline.py` alias is now retired as well,
- the full `demo/contracts` shim family is now gone from the codebase.

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

### 3a. Mixed active-output roots and committed exemplar boundaries

These paths are still part of the active output contract and therefore should
not be moved behind `_archive/` or another archival boundary wholesale:

- `demo/artifacts/`
  - still the default output root for reset reports and demo run artifacts
  - referenced by `scripts/phase1_verify.sh`, CLI help/defaults, validation
    docs, and historical restructure logs
  - current git inventory shows no tracked historical payload under this root
    beyond its ignore control file; the visible run outputs here are ignored
    local artifacts rather than committed exemplars
- `pipelines/runs/`
  - still the active output root for graph-health and retrieval-benchmark CLI
    artifacts
  - `.gitignore` still preserves the active-output posture even though the
    tracked exemplar payload has now been removed from the working tree

Accepted treatment:

- keep both roots in place as active output locations,
- treat committed exemplar handling as path-specific rather than root-wide,
- for `demo/artifacts/`, there is currently no tracked historical payload to
  retire after references disappear,
- for `pipelines/runs/`, the tracked exemplar-retirement lane has already been
  executed in the working tree and only the control file remains once the
  deletions are accepted,
- defer any move behind a stronger archival boundary until runtime defaults and
  documentation references are intentionally decoupled.

### 3b. Exact current drop-candidate inventory under `pipelines/runs/`

The current working tree removes the last tracked exemplar payload that had
been kept under `pipelines/runs/`. After these deletions are accepted, only the
control file `.gitkeep` remains tracked there.

Cheap discriminating check outcome:

- no runtime code or tests currently point at these exact tracked files,
- the exact-path references are documentation and sibling provenance links.

That means the tracked exemplar-retirement lane under `pipelines/runs/` has now
been executed in the working tree.

Reference anchors cleared in this slice:

- v1 `retrieval_benchmark.json`
  - referenced by `pipelines/query/README.md`
  - referenced by `docs/cross-dataset-validation-report-v1-v2.md`
  - referenced by `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`
- v1 `PROVENANCE.md`
  - referenced by `pipelines/query/README.md`
  - referenced by `docs/cross-dataset-validation-report-v1-v2.md`
  - referenced by `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`

Resulting state:

- `demo/artifacts/` has no tracked historical payload beyond its control file,
- `pipelines/runs/` is reduced to its control file in the working tree,
- the historical benchmark facts formerly carried by the committed v1 files are
  now summarized in durable documentation instead.

### 4. Documentation normalization candidates

These are likely to become follow-up work once any retirement implementation starts:

- root `README.md`
  - currently states that `demo/` is the working implementation and that `backend/` / `frontend/` are scaffolding or transitional surfaces
- `demo/README.md`
  - remains the active operator walkthrough and should only be downgraded after the active execution path changes
- restructure docs that still describe compatibility shells or shim deferment as current posture

Documentation changes should follow actual retirement work, not lead it.

## Current readiness assessment

### Already completed in this lane

- the `demo/contracts` shim-retirement order was executed,
- the required documentation updates for that lane have been landed.

### Not ready for direct removal

- `demo/` as a whole,
- compatibility entrypoint shells under `demo/`, `pipelines/query/`, `scripts/`, and `backend/`,
- `frontend/` as a whole,
- any remaining legacy compatibility shells outside the now-retired `demo.contracts` lane.

## Recommended implementation order

1. Update README and restructure docs to remove stale references to retired surfaces.

At the current checkpoint, the `demo/contracts` retirement implementation lane is complete, the `_archive/` placement decision is accepted, and the mixed `demo/artifacts/` / `pipelines/runs/` output-root question is resolved as a defer-in-place decision. The remaining Phase 10 work is broader documentation cleanup or later legacy-surface retirement outside those closed lanes.

## Acceptance gate before any code deletion

Before removing a shortlisted surface, require at minimum:

- a caller/reference inventory for that surface,
- confirmation that the surface is not the active documented execution path,
- focused validation for any affected CLI/API/test path,
- documentation updates prepared in the same change,
- explicit confirmation that the retirement does not violate previously accepted compatibility decisions.

## Initial recommendation

Treat the next Phase 10 implementation slice as a legacy-surface cleanup or retirement lane other than `_archive/` placement or `demo/contracts`.

Do not mix archive cleanup with broader compatibility-shell deletion into a single pass.