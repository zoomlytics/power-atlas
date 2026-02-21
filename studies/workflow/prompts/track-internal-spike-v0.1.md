# Track G Prompt Pack — Internal Spike (v0.1)

Use this pack for `Track: internal-spike` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track G internal-spike scout.
Output must include: spike objective, assumptions, experiment shape, constraints/timebox, success/fail signals, and Phase A decision line:
Decision: Stop | Continue to Phase B | Escalate to Phase C
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready internal-spike summaries.

Brief path:
/studies/summaries/internal-spike/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/internal-spike/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include setup, findings, limitations, reproducibility notes, and:
Decision: Stop | Continue in Phase B | Escalate to Phase C
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track G when spike results affect architecture/governance decisions.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include recommendation, rollback/fallback options, and:
Decision: Stop | Continue in Phase C
```

## Branch spawn prompt

```text
Task: Propose follow-on studies (validation, scale test, or alternative approach).
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source/experiment plan
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent experiment evidence.
Keep decision line and replication checklist visible.
```
