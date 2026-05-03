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
- a bounded follow-up audit later found `_archive/initial_experimentation_2026_02_28/` to be an isolated stale subtree inside that retained archive boundary,
- nothing outside the subtree still referenced that dated experimentation path,
- the subtree has now been removed while keeping the accepted `_archive/` root boundary in place.
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
- `studies/SYSTEM-INDEX-v0.1.md` has now been removed as a low-risk stale-doc retirement slice,
- exact filename searches showed no remaining workspace references outside the file itself,
- the surviving studies-system docs already treat `/studies/_studies/` plus the workflow/template docs as the canonical inventory and entrypoints.

## Retirement classes

### 1. Likely early retirement or archive candidates

These look like the best first shortlist once implementation work begins:

- `_archive/`
  - currently contains historical experimentation material
  - now explicitly labeled as archival/non-active in repo docs
  - accepted decision: keep it at the repo root as the explicit archival boundary for now
  - rationale: no non-doc/runtime coupling was found, and moving it would create reference churn without reducing current product risk

`__queuestorage__/` no longer belongs on the active shortlist because that low-risk retirement slice has already been completed.

`studies/SYSTEM-INDEX-v0.1.md` no longer belongs on the active shortlist because that low-risk stale-doc retirement slice has already been completed.

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
  - still the stable backend container seam via `backend/Dockerfile` (`uvicorn main:app`)
  - still the import seam exercised by `tests/test_backend_main.py`
- `frontend/`
  - documented as a transitional non-core health-check client, not yet a retired surface
- `pipelines/query/*.py` and `scripts/sync_vendor_version.py`
  - now thin compatibility entrypoints, but still the stable invocation surfaces
- compatibility re-export modules noted in the decisions register under the package root

These are legacy-shaped surfaces, but they are not yet expired. Removing them before the active execution posture changes would create churn without closing the real migration obligations.

Script-specific audit result:

- `scripts/sync_vendor_version.py` is currently a defer-in-place shell rather
  than a live retirement candidate,
- it still serves as the stable operator and CI seam for vendor metadata sync:
  the repo README, vendor docs, and `.github/workflows/vendor-version-consistency.yml`
  still invoke this exact script path,
- `tests/test_sync_vendor_version.py` still imports and patches symbols from
  `scripts.sync_vendor_version`, so deleting it now would change the active
  script/test seam rather than retire dead compatibility debt.

Query-entrypoint audit result:

- `pipelines/query/graph_health_diagnostics.py` is also currently a
  defer-in-place shell rather than a live retirement candidate,
- it still serves as the documented manual diagnostics entrypoint in
  `pipelines/query/README.md`, `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`,
  and `docs/architecture/warning-channel-conventions.md`,
- `demo/tests/test_graph_health_diagnostics_cli.py` still imports and patches
  `pipelines.query.graph_health_diagnostics`, so deleting it now would change
  the active CLI/test seam rather than retire dead compatibility debt.

- `pipelines/query/retrieval_benchmark.py` is also currently a
  defer-in-place shell rather than a live retirement candidate,
- it still serves as the documented manual benchmark CLI seam in
  `demo/README.md`, `pipelines/query/README.md`,
  `docs/architecture/legacy-dataset-id-migration-v0.1.md`, and
  `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`,
- `demo/tests/test_retrieval_benchmark_cli.py` still imports and patches
  `pipelines.query.retrieval_benchmark`, so deleting it now would change the
  active CLI/test seam rather than retire dead compatibility debt.

Backend-specific audit result:

- `backend/main.py` is currently a defer-in-place shell rather than a live
  retirement candidate,
- the nearby caller inventory is intentionally small, but it is not empty:
  `backend/Dockerfile` still launches the backend through this seam and
  `tests/test_backend_main.py` still imports `app` from it,
- retiring the file now would force an execution-seam change rather than close
  dead compatibility debt.

Frontend-specific audit result:

- `frontend/` is currently a defer-in-place non-core surface rather than a
  live retirement candidate,
- it still participates in the checked-in local execution posture through the
  `frontend` service in `docker-compose.yml`,

Manual-validation artifact audit result:

- `demo/artifacts_compare/` is currently a defer-in-place manual validation
  artifact root rather than a live retirement candidate,
- no code or automated test callers currently depend on that path family,
  but the current repo still documents it as an accepted output surface in
  `demo/README.md`, `demo/VALIDATION_RUNBOOK.md`, and
  `docs/repository_restructure/repository_restructure_safety_harness.md`,
- deleting it now would change the accepted manual validation posture and
  retained-artifact guidance rather than retire dead compatibility debt.

Vendor-reference subtree audit result:

- `vendor-resources/tests/` has now been retired as a low-risk stale duplicate
  subtree,
- exact path searches found no live workspace references to
  `vendor-resources/tests`,
- the retained vendor-reference usage in this repo still points to
  `vendor-resources/examples` instead, so removing the duplicate test mirror did
  not change the accepted vendor-reference posture.
- `vendor-resources/docs/` has now also been retired as a low-risk stale
  duplicate vendor subtree,
- exact path searches found no live workspace references to
  `vendor-resources/docs`,
- the subtree mirrored the upstream vendored docs tree, so removing it narrowed
  the retained vendor-reference posture to `vendor-resources/examples/` and
  `vendor-resources/images/` without affecting live repo behavior.
- the direct runtime seam is intentionally small but real:
  `frontend/app/page.tsx` still reads `NEXT_PUBLIC_BACKEND_URL` and performs a
  placeholder `GET /health` check against the backend stub surface,
- the root README and restructure docs still document it as a disconnected but
  accepted placeholder UI surface, so deleting it now would change the current
  local scaffold posture rather than retire dead compatibility debt.

Phase-1 verification artifact-root audit result:

- `artifacts/repository_restructure/phase1/` is currently a defer-in-place
  verification-evidence root rather than a live retirement candidate,
- it still serves as the checked-in output root for `make phase1-verify` /
  `bash scripts/phase1_verify.sh`,
- the current verification harness, checklist, plan, safety-harness docs, and
  Phase 1 execution log all still anchor accepted run evidence to this exact
  path family,
- retiring or relocating it now would change the accepted Phase 1 proof and
  artifact-capture posture rather than retire dead compatibility debt.

Phase-1 execution-run-log audit result:

- `docs/repository_restructure/repository_restructure_phase1_execution_run_log.md`
  is currently a defer-in-place verification document rather than a live
  retirement candidate,
- it is still referenced by `scripts/phase1_verify.sh` as canonical execution
  context for the accepted automation entrypoint,
- it still records the accepted run evidence and automation history that the
  current verification posture points back to,
- retiring or archiving it now would change the accepted Phase 1 verification
  documentation surface rather than retire dead compatibility debt.

Phase-1 agent-task-breakdown audit result:

- `docs/repository_restructure/repository_restructure_agent_task_breakdown.md`
  is currently a defer-in-place verification/planning-history document rather
  than a live retirement candidate,
- its own checkpoint note marks it as historical setup context rather than the
  canonical current plan, but the accepted Phase 1 execution run log still
  references it as part of the authoritative context for interpreting runs,
- retiring or archiving it now would change the accepted Phase 1 verification
  documentation surface rather than retire dead compatibility debt.

`demo/contracts` retirement-task audit result:

- `docs/repository_restructure/repository_restructure_phase2_demo_contracts_retirement_task.md`
  is currently a defer-in-place historical planning/execution record rather
  than a live retirement candidate,
- its own status and body already describe the underlying `demo/contracts`
  retirement lane as completed historical work,
- the current Phase 10 shortlist and checklist still reference it as the
  executed follow-up planning task behind that now-closed lane,
- retiring or archiving it now would change the accepted restructuring record
  for the completed `demo/contracts` retirement lane rather than retire dead
  compatibility debt.

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

This is now the active follow-up lane after the bounded shell audits closed the
remaining obvious defer-or-retire decisions:

- root `README.md`
  - now keeps describing `demo/` as the working implementation and `backend/` / `frontend/` as disconnected scaffolding, while clarifying that `backend/main.py` remains the accepted launch seam for the placeholder backend surface
- `demo/README.md`
  - remains the active operator walkthrough and should only be downgraded after the active execution path changes
- restructure docs that still describe compatibility shells or shim deferment as current posture
  - should now point to explicit accepted defer-in-place decisions for `backend/main.py`, `scripts/sync_vendor_version.py`, `pipelines/query/graph_health_diagnostics.py`, and `pipelines/query/retrieval_benchmark.py`

Documentation changes should follow actual retirement or defer decisions, not
lead them.

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

1. Update README and restructure docs to remove stale references to retired surfaces and to normalize wording around accepted defer-in-place shells.

This documentation/caller-surface cleanup lane has now landed across the root
README, operator docs, architecture docs, vendor docs, and secondary reference
docs.

At the current checkpoint, the `demo/contracts` retirement implementation lane is complete, the `_archive/` placement decision is accepted, the mixed `demo/artifacts/` / `pipelines/runs/` output-root question is resolved as a defer-in-place decision, and the accepted compatibility-shell documentation cleanup lane is also complete. The remaining Phase 10 work is later legacy-surface retirement outside those closed lanes.

## Acceptance gate before any code deletion

Before removing a shortlisted surface, require at minimum:

- a caller/reference inventory for that surface,
- confirmation that the surface is not the active documented execution path,
- focused validation for any affected CLI/API/test path,
- documentation updates prepared in the same change,
- explicit confirmation that the retirement does not violate previously accepted compatibility decisions.

## Initial recommendation

Treat the next Phase 10 implementation slice as a legacy-surface retirement lane other than `_archive/` placement, `demo/contracts`, or the already-classified defer-in-place shells.

Do not mix archive cleanup with broader compatibility-shell deletion into a single pass.