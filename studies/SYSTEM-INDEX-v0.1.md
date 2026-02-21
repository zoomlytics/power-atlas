# Studies System Index (v0.1)

This is the primary entrypoint for navigating the `/studies` system.

Use it to quickly understand artifact types, naming and track conventions, lifecycle states, and where to start for AI-assisted or manual review.

## Purpose and artifact ladder

The studies system captures background research that informs Power Atlas architecture, governance posture, ontology, and risk reasoning.

Artifact ladder (increasing rigor):
- **Notes** (optional, freeform): fast capture, triage, breadcrumbs
- **Summaries** (brief/detailed): synthesized, readable study outputs
- **Memo** (governance): high-rigor synthesis for architecture/ontology/metrics/risk relevance

## Workflow backbone docs (v0.1)

- `/studies/workflow/README.md`
- `/studies/workflow/run-book-v0.1.md`
- `/studies/workflow/context-packs-v0.1.md`
- `/studies/templates/README.md`
- `/studies/notes/README.md`
- `/studies/workflow/prompts/README.md`

## Canonical track slugs

Use one primary track slug per study:

- `conceptual-research`
- `methods-techniques`
- `tech-evaluation`
- `data-source`
- `case-study`
- `similar-platforms`
- `internal-spike`
- `misc` (temporary classification; include a dedicated `Resolution plan` section in the artifact body with target track and reclassification/split trigger)

Track cards and prompt packs live under `/studies/workflow/` and `/studies/workflow/prompts/`.

## Naming conventions (v0.1)

Core file pattern:

`YYYY-MM-DD__slug__type.md`

Common outputs:
- Brief summary: `YYYY-MM-DD__slug__brief.md`
- Detailed summary: `YYYY-MM-DD__slug__detailed.md`
- Memo: `YYYY-MM-DD__slug__memo-v0.1.md`
- Notes: `YYYY-MM-DD__slug__note__<short-label>.md`

## Lifecycle states and cross-linking

Controlled states:
- `Draft`
- `In Review`
- `Superseded`
- `Abandoned`

Cross-link practices:
- Include a `Related studies` block near the top of artifacts:
  - `Parent study: ...`
  - `Follow-on studies: ...`
- Summaries and memos should link notes when they exist; otherwise set `Notes: N/A`.
- If a memo is replaced, mark the prior memo `Status: Superseded` and add `Superseded by: [link]`.

## Directory layout

- `/studies/templates/` — canonical templates
- `/studies/notes/` — optional capture lane
- `/studies/summaries/` — brief/detailed synthesis lane
- `/studies/memos/` — governance-facing synthesis lane
- `/studies/workflow/` — process and track definitions
- `/studies/workflow/prompts/` — reusable prompt packs
- `/studies/_assets/` — exception-only small assets

## Minimum review set (newcomers and AI)

Read these first:
1. `/studies/SYSTEM-INDEX-v0.1.md`
2. `/studies/workflow/README.md`
3. `/studies/workflow/run-book-v0.1.md`
4. `/studies/templates/README.md`
5. Directory indexes:
   - `/studies/notes/README.md`
   - `/studies/summaries/README.md`
   - `/studies/memos/README.md`
   - `/studies/workflow/prompts/README.md`

## Registry pointer

Registry precedence rules:
- If `/studies/REGISTRY.md` exists (including when directory indexes also exist), use it as the canonical inventory entrypoint and treat directory indexes as navigation helpers.
- In v0.1, use the directory indexes in `notes/`, `summaries/`, and `memos/` as the practical registry layer.

## Review checklist

### Strategic review
- [ ] Track choice is explicit and appropriate
- [ ] Study question, non-goals, and timebox/depth are visible
- [ ] Summary or memo clearly states relevance to Power Atlas constraints
- [ ] Evidence quality and uncertainty are explicit (not flattened)
- [ ] Recommendations distinguish “borrow” vs “do not borrow” where relevant

### Critical review (high-risk / governance-impacting)
- [ ] Lifecycle state is correct (`Draft` vs `In Review`)
- [ ] Human review gating is satisfied for AI-first artifacts before advancing status
- [ ] Sources are traceable and non-circular
- [ ] Misuse/escalation risks are surfaced and bounded
- [ ] Supersession and cross-links are accurate (`Related studies`, `Superseded by`, `Notes` links or `Notes: N/A`)
