# Track C Prompt Pack — Tech Evaluation (v0.1)

Use this pack for `Track: tech-evaluation` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track C tech-evaluation scout.
Output must include: evaluation objective, candidate options, constraints, decision criteria, risk flags, and Phase A decision line:
Decision: Stop | Continue to Phase B | Escalate to Phase C
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready tech-evaluation summaries.

Brief path:
/studies/summaries/tech-evaluation/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/tech-evaluation/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include option comparison, assumptions, operational/security implications, and:
Decision: Stop | Continue in Phase B | Escalate to Phase C
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track C when evaluation informs architecture/governance commitments.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include recommendation rationale, exit strategy, and:
Decision: Stop | Continue in Phase C
```

## Branch spawn prompt

```text
Task: Propose follow-on studies for unresolved options or risk tracks.
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source/test plan
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent performance/security evidence.
Keep decision line and backfill checklist visible.
```
