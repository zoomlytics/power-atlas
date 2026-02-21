# Track B Prompt Pack — Methods / Techniques (v0.1)

Use this pack for `Track: methods-techniques` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track B methods-techniques scout.
Output must include: problem framing, candidate methods, assumptions, required data/inputs, failure modes, and Phase A decision line:
Decision: Stop | Continue | Escalate
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready methods-techniques summaries.

Brief path:
/studies/summaries/methods-techniques/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/methods-techniques/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include comparison table (fit, assumptions, limits), implementation notes, and:
Decision: Stop | Continue | Escalate
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track B when method choice has governance or architecture impact.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include trade-off rationale, rejected alternatives, and:
Decision: Stop | Continue | Escalate
```

## Branch spawn prompt

```text
Task: Propose follow-on studies for unresolved method branches.
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source/benchmark plan
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent benchmark outcomes.
Keep decision line and backfill checklist visible.
```
