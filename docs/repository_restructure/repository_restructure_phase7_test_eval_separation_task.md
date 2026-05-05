# Phase 7 Follow-Up Task — Test And Eval Separation

**Status:** in progress  
**Owner:** Ash  
**Date context:** 2026-05-05  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `eval/README.md`

## Purpose

This document records the first deliberate implementation lane for Phase 7:

- define the target correctness-test layout,
- define the target evaluation-asset boundary,
- prevent active runtime artifact paths from being moved prematurely under the
  label of test/eval cleanup,
- give later Phase 7 slices a stable destination for evaluation-only assets.

## Current repo state

At the start of this lane:

- the repository had no top-level `eval/` directory,
- correctness tests already lived primarily in two active roots:
  - `demo/tests/` for stage, workflow, and CLI correctness coverage,
  - `tests/` for repository-level and package-surface coverage,
- benchmark and manual-validation outputs still used accepted live roots under
  `demo/artifacts/`, `demo/artifacts_compare/`, and `pipelines/runs/`,
- accepted defer decisions already treated those output roots as active seams
  rather than archive payload that could be moved wholesale.

## Target boundary defined in this checkpoint

### Correctness-test layout

Until a later consolidation move is explicitly accepted, the target correctness
test layout is:

- `demo/tests/`
  - stage-level, workflow-level, and CLI/interface correctness coverage for the
    demo pipeline and preserved compatibility shells
- `tests/`
  - repository-level, package-surface, and cross-cutting correctness coverage
- no benchmark datasets, retained evaluation reports, or manual comparison
  output directories should be added under either correctness-test root

This means benchmark-named tests such as retrieval-benchmark code tests remain
valid correctness tests when they verify application logic or CLI contracts.
They are not evaluation assets solely because they mention benchmark behavior.

### Evaluation boundary

`eval/` is now the reserved top-level destination for assets that are not part
of correctness verification, including:

- benchmark datasets that are not fixtures for correctness tests,
- evaluation scenario definitions and rubrics,
- retained evaluation reports,
- comparison outputs once their producing workflows no longer require
  `demo/`-local paths.

## Non-goals for this checkpoint

This checkpoint does **not**:

- change default runtime output paths for demo or query commands,
- relocate Phase 1 verification artifacts,
- move `demo/artifacts/`, `demo/artifacts_compare/`, or `pipelines/runs/`
  while they remain documented active workflow seams,
- reclassify current correctness tests as eval assets based only on naming.

## Immediate follow-up sequence

The next bounded Phase 7 slices should proceed in this order:

1. classify which currently retained outputs are evaluation-only versus active
   operator seams,
2. move only the evaluation-only retained assets whose workflows no longer
   require `demo/`-local paths,
3. update docs and CI scope only after those assets have a stable `eval/`
   destination.

## Initial classification checkpoint (2026-05-05)

The first asset inventory after defining the Phase 7 boundary shows three
distinct classes:

### 1. Active output seams that should not move yet

- `demo/artifacts/`
  - remains the active demo output root for reset reports and run artifacts,
    and its own README still marks it as a live output seam rather than a pure
    retained-asset bucket
- `pipelines/runs/`
  - remains the active output root for the query-side CLIs
- documented manual-validation comparison paths under `demo/artifacts_compare/`
  - `q3/` is still referenced by `demo/README.md`
  - `pre_hybrid_plain`, `pre_hybrid_expand`, `post_hybrid_cluster_aware`,
    `post_hybrid_bridge`, and `post_hybrid_person` remain part of the current
    validation runbook posture in `demo/VALIDATION_RUNBOOK.md`

### 2. Local working-tree artifacts under an active root

The initial directory inventory showed local `demo/artifacts/manifest.json`,
`demo/artifacts/manifest.md`, and multiple `reset_report_*.json` files in the
working tree. A follow-up git inventory confirmed that these are not currently
tracked repository payload.

So, for repository-restructure purposes, these files are local generated
artifacts sitting under an active output seam, not committed assets that are
waiting for relocation into `eval/`.

### 3. First concrete move candidates once a narrow move is approved

The following retained comparison-output roots currently have no live doc or
code references in the workspace outside the directories themselves:

- `demo/artifacts_compare/base_vs_expand_graph/`
- `demo/artifacts_compare/expand_graph_vs_cluster_aware/`
- `demo/artifacts_compare/run_scoped_vs_all_runs/`

At this checkpoint, these three directories are the best Phase 7 candidates for
the first actual relocation into `eval/`, subject to one last tracked-file
inventory and a small doc sweep to confirm no missing operator guidance still
depends on them.

### 4. Tracked-file inventory result

The follow-up inventory on the three candidate directories showed that they are
currently represented in the working tree only as ignored local run-output
trees under `runs/`, not as tracked repository payload.

The same git inventory check also confirmed that `demo/artifacts/` currently
has no tracked payload beyond its `.gitignore` control file, matching the
accepted Phase 10 documentation posture.

That means there is no repository-side file move to perform for those
directories in the current checkpoint. The next real relocation slice must
therefore target either:

- future retained comparison payload that becomes intentionally tracked, or
- another eval-only retained asset family that is both documented and checked
  into the repository.

For now, the concrete Phase 7 implementation outcome is classification clarity:
the repo no longer has an obvious committed comparison-artifact subtree ready
for relocation from those three paths.

### 5. Correctness-test root audit result

The follow-up inventory of `demo/tests/` and `tests/` also found no obvious
evaluation-only retained assets living under the active correctness-test roots.

- `demo/tests/` is almost entirely Python correctness coverage plus one
  machine-readable contract scenario fixture file,
  `demo/tests/contract_fixtures/retrieval_citation_scenarios.yaml`, that is
  explicitly used as correctness-test input rather than as an evaluation report
  or benchmark dataset
- `tests/` is repository-level correctness coverage without any comparable
  eval-only retained artifact family

So, at the current checkpoint, Phase 7 has clarified the target boundaries but
has not yet identified a safe committed asset move under the active
correctness-test roots themselves.