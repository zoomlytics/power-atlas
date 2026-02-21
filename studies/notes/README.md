# Studies Notes Lane (v0.1)

`/studies/notes/` is an **optional** lane for fast human capture.

Notes are first-class when they help, but they are not required to start or complete a study. In AI-first workflows, studies often begin in summaries; in human/manual workflows, studies often begin with triage notes.

## Intent

Use notes for:
- quick triage logs (`looked at it`, `not relevant`, `continue`, `stop`)
- gut checks and early hypotheses
- evidence snippets that are not ready for synthesis
- branch/split moments where one study becomes multiple studies
- link dumps and source breadcrumbs

Notes can be incomplete, contradictory, messy, link-heavy, and low on prose.

## Structure

Choose the lightest structure that works:
- freeform markdown, or
- template-driven using `/studies/templates/source-note-v0.1.md`

Avoid ceremony; optimize for speed and auditability.

## Directory convention (recommended)

- `/studies/notes/<track-slug>/<study-slug>/`
- keep empty placeholders with `.keep` files when needed

Example:

`/studies/notes/conceptual-research/scale-free-preferential-attachment/`

## Naming convention

One study can have many notes. Recommended filename pattern:

`YYYY-MM-DD__<study-slug>__note__<short-label>.md`

Examples:
- `2026-02-21__scale-free-preferential-attachment__note__triage.md`
- `2026-02-21__scale-free-preferential-attachment__note__gut-check.md`
- `2026-02-22__scale-free-preferential-attachment__note__split-trigger.md`

If preferred, you may also use `source-note-v0.1.md` as a base structure.

For high-volume studies, an optional per-study index file is allowed (for example: `notes-index.md`).

## Minimum metadata in each note (recommended)

State these near the top whenever possible:
- study slug
- track slug
- date and author/tool
- short rationale (`why this note exists`)

## Cross-linking rule

- If notes exist, summaries/memos should link to them.
- If notes do not exist, summaries/memos should explicitly state: `Notes: N/A`.

This keeps traceability explicit without forcing unnecessary files.
