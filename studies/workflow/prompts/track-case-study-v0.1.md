# Track E Prompt Pack — Case Study (v0.1)

Use this pack for `Track: case-study` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track E case-study scout.
Output must include: scope framing, case boundary (who/what/when), source landscape, key unknowns, and Phase A decision line:
Decision: Stop | Continue to Phase B | Escalate to Phase C
Require at least one conflicting account/source for the case.
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready case-study summaries.

Brief path:
/studies/summaries/case-study/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/case-study/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include timeline, actors, evidence strength, uncertainties, and:
Decision: Stop | Continue in Phase B | Escalate to Phase C
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track E when depth rules or governance risk require Phase C.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include misuse/misread risks, unresolved evidence conflicts, and recommendation with:
Decision: Stop | Continue in Phase C
```

## Branch spawn prompt

```text
Task: Propose follow-on study branches from this case.
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source plan (include at least one counter-source)
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent citations.
Keep decision line and open-questions checklist visible.
```
