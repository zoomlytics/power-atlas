# Study artifact lanes (v0.1)

This is the authoritative lane guidance for study artifact placement under `/studies/_studies/<track-slug>/<study-slug>/`.

## Lanes

- `notes/` (optional) — raw capture and triage artifacts.
  - File pattern: `YYYY-MM-DD__slug__note__<label>.md`
- `summaries/` (recommended) — brief/detailed synthesis artifacts.
  - File patterns: `YYYY-MM-DD__slug__brief.md`, `YYYY-MM-DD__slug__detailed.md`
- `memos/` (when governance-relevant) — high-rigor synthesis for architecture/ontology/metrics/risk decisions.
  - File pattern: `YYYY-MM-DD__slug__memo-v0.1.md`

## Minimum cross-linking

- Summaries and memos should link notes when they exist.
- If notes do not exist, set `Notes: N/A` in summaries/memos.
