# Studies: Templates & Workflow (v0.1)

This directory contains templates for **developer/design background studies** that inform Power Atlas architecture, modeling, governance, and risk thinking.

These artifacts are distinct from any “research” the *system itself* may perform at runtime.

## Artifact Types (3-layer workflow)

### 1) Notes (raw capture, optional)
**Goal:** high-volume capture with minimal friction when useful.

Typical inputs:
- reading notes, excerpts, timestamps
- rough thoughts and questions
- agent-generated outputs (LLM summaries, extraction tables)

Template (optional): `source-note-v0.1.md`

Location (recommended): `/studies/_studies/<track-slug>/<study-slug>/notes/`

Guidance and conventions: `/studies/_system/workflow/run-book-v0.1.md`

### 2) Summaries (working synthesis, default start for AI-first flows)
**Goal:** medium-volume synthesis that’s readable and shareable.

Two levels:
- **Brief**: fast, minimal structure, “what is it + why it matters + cautions”
- **Detailed**: more complete notes, still flexible and not “paper-like” unless useful

Templates:
- `summary-brief-v0.1.md`
- `summary-detailed-v0.1.md`

Location (recommended): `/studies/_studies/<track-slug>/<study-slug>/summaries/`

Notes linkage rule:
- if Notes exist, link them from the summary/memo
- if Notes do not exist, state `Notes: N/A`

### 3) Memo (governance-facing synthesis)
**Goal:** low-volume, high-rigor synthesis that explicitly addresses assumptions, relevance, risks, and “what not to borrow.”

Template (stored in this `/studies/_system/templates/` directory; completed memos live in `/studies/_studies/<track-slug>/<study-slug>/memos/`): `research-memo-v0.1.md`

Location (recommended): `/studies/_studies/<track-slug>/<study-slug>/memos/`

## Naming Convention (required)

Use the following file naming convention:

`YYYY-MM-DD__slug__type.md`

Notes may add a short note label segment:

`YYYY-MM-DD__slug__note__<short-label>.md`

Examples:
- `2026-02-20__network-sampling__brief.md`
- `2026-02-20__network-sampling__detailed.md`
- `2026-02-20__network-sampling__note__triage.md`
- `2026-02-20__network-sampling__memo-v0.1.md`

Slug guidance:
- lowercase
- hyphen-separated
- stable over time (don’t rename unless necessary)

For split criteria, directory layout, cross-linking (`Related studies` block), and memo supersession policy, use `/studies/_system/workflow/run-book-v0.1.md`.

## Sources & Citations (v0.1 policy)

Links-first, minimal friction:
- Include a **Sources** section with URLs.
- For web sources, add **Accessed: YYYY-MM-DD** when helpful.
- If a source is likely to disappear, optionally add an archive link (Wayback/perma.cc).

A formal bibliography registry (BibTeX/YAML) may be introduced in a later version if needed.

## Assets (PDFs, videos, large binaries)

Default: **do not commit large binaries**.

Exceptions are allowed when:
- licensing permits redistribution, and
- the artifact is critical to audit or likely to disappear, and
- size is reasonable.

If you must store assets, place them under: `/studies/_assets/` and reference them from notes/summaries/memos.

## Agent-generated content (optional metadata)

If notes or summaries were produced with an AI tool/agent, include lightweight metadata in the document:
- tool name
- date run
- input source links
- prompt (optional)
- whether output was edited

This is recommended for auditability but not required in v0.1.

## Workflow Docs

- Process and taxonomy reference: `/studies/_system/workflow/README.md`
- Run book (phased execution + AI-first gating): `/studies/_system/workflow/run-book-v0.1.md`
- Track selection decision tree and track cards: `/studies/_system/workflow/`
- Study charter snippet: `/studies/_system/workflow/study-charter-snippet-v0.1.md`
