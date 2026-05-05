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