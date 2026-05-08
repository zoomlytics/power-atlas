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

## Classification guidance

Use this boundary to separate evaluation assets from correctness tests.

Treat a surface as **evaluation** when its primary purpose is to:

- measure retrieval or answer quality over time,
- compare competing prompts, retrieval modes, or workflow variants,
- retain benchmark scenarios, review rubrics, or score-oriented reports,
- preserve comparison outputs whose value is review and regression analysis
  rather than API/runtime correctness.

Treat a surface as **correctness** when its primary purpose is to:

- verify a runtime contract, API shape, policy projection, or invariant,
- ensure two execution paths remain behaviorally identical for the same inputs,
- validate a debug or operator-facing output surface,
- catch silent drift in shared helper wiring, request-context handling, or
  metadata projection.

The key distinction is intent: correctness tests protect supported behavior;
evaluation assets compare the quality or usefulness of that behavior.

## Borderline surfaces that remain correctness-owned

Some test files may look evaluation-adjacent because they use retrieval
language or compare multiple execution paths. At the current checkpoint, the
following surfaces still belong with correctness tests rather than under
`eval/`:

- `demo/tests/test_retrieval_parity.py`
  verifies parity between single-shot and interactive retrieval entrypoints,
  including query selection, parameter building, citation repair, and fallback
  behavior. Its purpose is runtime-contract drift detection, not scoring or
  benchmark comparison.
- `demo/tests/test_interactive_debug.py`
  verifies the interactive debug output surface for
  `run_interactive_qa_request_context(...)`. Its purpose is to protect the
  supported debug/result contract, not to evaluate answer quality.
- `demo/tests/test_retrieval_metadata_projection_parity.py`
  verifies that runtime retrieval result shapes correctly project the declared
  metadata policy onto canonical, mirrored, and forbidden surfaces. Its purpose
  is contract enforcement, not evaluation.

These files should remain in correctness-oriented test paths unless their role
changes from contract enforcement to quality measurement.

## Out of scope for this checkpoint

- changing the default runtime output path for demo commands
- relocating Phase 1 verification artifacts
- moving active manual-validation output roots that are still documented as
  accepted operator seams

This includes `demo/artifacts_compare/`: it remains an accepted manual
validation output root and should not be treated as the next automatic move
candidate for `eval/`.