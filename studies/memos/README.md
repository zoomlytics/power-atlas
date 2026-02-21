# Studies Memos Index (v0.1)

`/studies/memos/` contains governance-facing research memos (highest-rigor study artifacts).

## Purpose

Use memos when findings may influence architecture, ontology, metrics, provenance posture, or misuse/risk handling.

Memos should synthesize what to borrow, what not to borrow, and where assumptions/risks remain.

## Structure

Default layout is flat:
- `/studies/memos/`

Exception layout (only for large grouped series):
- `/studies/memos/<track-slug>/`

## Naming pattern

Use:
- `YYYY-MM-DD__slug__memo-v0.1.md`

This follows the base convention `YYYY-MM-DD__slug__type.md`.

## Example artifacts

- Memo example:
  `/studies/memos/2026-02-20__scale-free-preferential-attachment__memo-v0.1.md`

## Lifecycle and cross-links

- Use controlled statuses: `Draft`, `In Review`, `Superseded`, `Abandoned`
- If replaced, older memo should include `Status: Superseded` and `Superseded by: [link]`
- Include `Related studies` links and `Notes` links (or `Notes: N/A`)

## Navigation pointers

- System entrypoint: `/studies/SYSTEM-INDEX-v0.1.md`
- Workflow backbone: `/studies/workflow/README.md`
- Run book: `/studies/workflow/run-book-v0.1.md`
- Memo template: `/studies/templates/research-memo-v0.1.md`
