# Studies (Developer/Design Background Research) — v0.1

This folder contains **background studies** performed by developers, designers, and researchers to inform the development of Power Atlas.

It is intentionally distinct from any “research” the *system itself* may perform at runtime (e.g., analysis over data, graph construction, inference workflows). Artifacts here are for **human sensemaking, auditability, and design/architecture grounding**.

## What belongs here

Examples:
- literature-style reviews of relevant fields (network sampling, provenance, entity resolution, temporal modeling)
- analyses of journalistic investigations and how they achieved their outputs
- evaluations of potential data sources (with risk/licensing considerations)
- critiques of similar platforms and conceptual approaches
- notes from talks, videos, papers, books
- agent-assisted summaries (with optional metadata for traceability)

## What does *not* belong here

- product requirements / roadmaps (those belong in issues, specs, or project planning docs)
- implementation tickets or feature commitments
- large binary dumps (PDF collections, videos) unless explicitly justified (see Asset policy below)

## Directory layout (recommended)

- `templates/` — standardized starting points (see `templates/README.md`)
- `notes/` — raw capture (high volume, low structure)
- `summaries/` — working summaries (medium structure)
- `memos/` — governance-facing synthesis (highest rigor)
- `_assets/` — exception-only storage for small, license-permitted artifacts

## Workflow (3 layers)

1) **Notes** → capture raw findings quickly  
2) **Summaries** → synthesize into readable working documents  
3) **Memos** → curated, Power Atlas–relevant synthesis (assumptions, risks, pressure points)

## Naming convention (required)

All study artifacts should use:

`YYYY-MM-DD__slug__type.md`

Examples:
- `2026-02-20__network-sampling__notes.md`
- `2026-02-20__network-sampling__brief.md`
- `2026-02-20__network-sampling__detailed.md`
- `2026-02-20__network-sampling__memo-v0.1.md`

## Sources & citations (v0.1)

Links-first:
- include a **Sources** section with URLs in notes/summaries/memos
- add “Accessed: YYYY-MM-DD” for web sources when helpful
- optionally include archive links for high-value or fragile sources

A formal bibliography registry may be introduced in a later version if/when link rot or deduplication becomes a problem.

## Asset policy (PDFs, videos, binaries)

Default: **do not commit large binaries**.

Allowed only when:
- redistribution is permitted by licensing/terms, and
- the artifact is essential to audit or likely to disappear, and
- size is reasonable

If included, store under `_assets/` and reference from a note/summary/memo.

## Template entry point

Start with:

- `templates/source-note-v0.1.md`
- `templates/summary-brief-v0.1.md`
- `templates/summary-detailed-v0.1.md`
- (and the memo template used in `/studies/memos/`)

## Research workflow & tracks

- Use `/studies/workflow/README.md` for the shared workflow, depth levels, and track taxonomy.
- Track selection tree and track cards live in `/studies/workflow/` (Tracks A–G + M).
- The study charter snippet (`study-charter-snippet-v0.1.md`) can be pasted at the top of Notes docs.
