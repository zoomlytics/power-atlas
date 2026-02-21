# Studies Summaries Index (v0.1)

`/studies/summaries/` contains study synthesis artifacts intended to be readable without raw notes.

## Purpose

Use summaries to convert source capture into structured understanding:
- **Brief** for fast triage and recommendation posture
- **Detailed** for assumptions, pressure points, evidence quality, and transfer limits

Notes are optional; if none exist, summary artifacts should state `Notes: N/A`.

## Structure

Recommended path layout:

`/studies/summaries/<track-slug>/<study-slug>/`

Example track folder currently in use:
- `/studies/summaries/conceptual-research/`

Example study folder currently in use:
- `/studies/summaries/conceptual-research/scale-free-preferential-attachment/`

## Naming patterns

Within each study folder, use:
- `YYYY-MM-DD__slug__brief.md`
- `YYYY-MM-DD__slug__detailed.md`

Both follow the base convention `YYYY-MM-DD__slug__type.md`.

## Example artifacts

- Detailed summary example:
  `/studies/summaries/conceptual-research/scale-free-preferential-attachment/2026-02-20__scale-free-preferential-attachment__detailed.md`

## Navigation pointers

- System entrypoint: `/studies/SYSTEM-INDEX-v0.1.md`
- Workflow backbone: `/studies/workflow/README.md`
- Summary templates: `/studies/templates/summary-brief-v0.1.md`, `/studies/templates/summary-detailed-v0.1.md`
