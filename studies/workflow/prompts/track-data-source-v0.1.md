# Track D Prompt Pack — Data Source (v0.1)

Use this pack for `Track: data-source` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track D data-source scout.
Output must include: source scope, access/licensing constraints, provenance quality, update cadence, known biases, and Phase A decision line:
Decision: Stop | Continue | Escalate
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready data-source summaries.

Brief path:
/studies/summaries/data-source/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/data-source/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include source metadata, confidence limits, legal/ethical constraints, integration readiness, and:
Decision: Stop | Continue | Escalate
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track D when depth rules or governance risk require Phase C.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include risk acceptance/rejection rationale, required safeguards, and:
Decision: Stop | Continue | Escalate
```

## Branch spawn prompt

```text
Task: Propose follow-on studies (acquisition, validation, or integration branches).
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source plan
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent provenance/licensing facts.
Keep decision line and backfill checklist visible.
```
