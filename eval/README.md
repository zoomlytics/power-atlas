# Eval Boundary

`eval/` is the reserved top-level home for benchmark datasets, evaluation
reports, and other non-correctness evaluation assets as Phase 7 test/eval
separation proceeds.

At the current checkpoint, this directory defines the target boundary without
changing the active operator artifact roots under `demo/artifacts/`,
`demo/artifacts_compare/`, or `pipelines/runs/`.

Those existing roots remain in place for now because they are still part of the
accepted live workflow and manual validation posture. Future Phase 7 slices
should migrate only the assets that can move without changing active runtime or
operator paths.

## Intended contents

- benchmark datasets that are not correctness fixtures
- evaluation scenario definitions and rubrics
- retained evaluation reports and comparison outputs after their producing
  workflows no longer require `demo/`-local paths
- supporting documentation for evaluation-only workflows

## Out of scope for this checkpoint

- changing the default runtime output path for demo commands
- relocating Phase 1 verification artifacts
- moving active manual-validation output roots that are still documented as
  accepted operator seams