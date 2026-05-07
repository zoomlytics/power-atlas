# Manual Comparison Artifacts

`demo/artifacts_compare/` is the accepted output root for the current manual
comparison workflow.

Use this directory for reviewable retrieval-comparison runs such as:

- pre-hybrid plain retrieval outputs,
- pre-hybrid expanded retrieval outputs,
- post-hybrid cluster-aware comparison outputs,
- targeted manual question-review outputs under `q3/`.

This directory should currently be treated as an active operator seam, not as a
retained archive payload to be moved mechanically into `eval/`.

Current posture:

- commands in `demo/README.md` and `demo/VALIDATION_RUNBOOK.md` still use
  `demo/artifacts_compare/...` as their example `--output-dir` destinations,
- the restructure record explicitly keeps this root defer-in-place until the
  manual validation workflow itself is intentionally migrated or retired,
- the important retained artifacts here are the per-run manifests under
  `runs/<run_id>/...`, not the top-level directory names by themselves.

If the manual comparison workflow is redesigned later, update the demo docs and
the restructure records first, then reconsider whether this root should move to
an `eval/`-owned location.
