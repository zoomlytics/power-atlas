# Track F Prompt Pack — Similar Platforms (v0.1)

Use this pack for `Track: similar-platforms` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track F similar-platforms scout.
Output must include: comparison scope, platform set, inclusion/exclusion criteria, evidence quality, transferability risks, and Phase A decision line:
Decision: Stop | Continue | Escalate
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready similar-platforms summaries.

Brief path:
/studies/summaries/similar-platforms/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/similar-platforms/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include comparison matrix (claims vs evidence), context mismatch notes, and:
Decision: Stop | Continue | Escalate
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track F when findings shape strategic direction.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include portability limits, non-goals, and:
Decision: Stop | Continue | Escalate
```

## Branch spawn prompt

```text
Task: Propose follow-on studies by platform cluster or capability gap.
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Initial source plan (include at least one skeptical/critical source)
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent platform claims.
Keep decision line and backfill checklist visible.
```
