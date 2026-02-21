# Studies Workflow Prompt Library (v0.1)

This directory contains reusable, track-specific prompt packs for study execution.

## Phase usage (A/B/C)

Use prompts according to the workflow phases in `/studies/workflow/run-book-v0.1.md`:

- **Phase A — Scope and route:** define study question, choose track/depth/timebox, and set non-goals.
- **Phase B — Capture and synthesize:** produce notes and summaries with explicit sources, assumptions, and uncertainty.
- **Phase C — Evaluate and land outputs:** produce governance-facing evaluation when needed and route outputs into docs/simulations/follow-up questions.

## File-ready outputs + naming conventions

Prompts should request **file-ready markdown outputs** (not chat prose) that can be saved directly under `/studies/` using repository naming rules:

- `YYYY-MM-DD__slug__type.md` (see `/studies/README.md`)
- include `Track` near the top using controlled slugs
- include a `Sources` section (links-first)
- when `Track = misc`, include a resolution plan

## Self-heal pattern (missing templates/context)

If referenced templates or context are missing, prompts should self-heal by:

1. stating what is missing,
2. creating a minimal placeholder structure using v0.1 conventions,
3. continuing with explicit assumptions,
4. flagging missing inputs as follow-up items (not hidden omissions).

## Posture guardrails

Prompt language should:

- avoid product framing and feature-spec language,
- preserve Power Atlas posture (semantic-core independence, claim-mediated modeling, provenance/time/confidence discipline, non-escalation),
- stay neutral, structural, and evidence-first.

## Track prompt files

- `track-conceptual-research-v0.1.md`
- `track-methods-techniques-v0.1.md`
- `track-tech-evaluation-v0.1.md`
- `track-data-source-v0.1.md`
- `track-case-study-v0.1.md`
- `track-similar-platforms-v0.1.md`
- `track-internal-spike-v0.1.md`
- `track-misc-v0.1.md`
