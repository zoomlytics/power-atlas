# Track Misc Prompt Pack — Misc / Unclassified (v0.1)

Use this pack for `Track: misc` studies.

## Tier 0

Reuse Tier 0 orientation from:
`/studies/workflow/prompts/track-conceptual-research-v0.1.md`

## Phase A prompt (Scout)

```text
Task: Run a Track misc scout.
Output must include: why this does not yet fit A-G, provisional scope, candidate destination tracks, immediate risks, and Phase A decision line:
Decision: Stop | Continue to Phase B | Escalate to Phase C
```

## Phase B prompt (Brief + detailed outputs)

```text
Task: Produce file-ready misc summaries.

Brief path:
/studies/summaries/misc/<study-slug>/YYYY-MM-DD__<study-slug>__brief.md

Detailed path:
/studies/summaries/misc/<study-slug>/YYYY-MM-DD__<study-slug>__detailed.md

Use v0.1 summary templates. Include a required "Track resolution plan" section to migrate from misc to a controlled track, and:
Decision: Stop | Continue in Phase B | Escalate to Phase C
```

## Phase C prompt (Memo; when depth/escalation warrants)

```text
Task: Draft escalation memo for Track misc when ambiguity or governance risk remains unresolved.
Path: /studies/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md
Include classification recommendation, unresolved blockers, and:
Decision: Stop | Continue in Phase C
```

## Branch spawn prompt

```text
Task: Propose follow-on studies that move work from misc into a controlled track.
Output fields only:
- Parent study slug
- Proposed new slug
- Track recommendation
- Why split now (2-4 bullets)
- Resolution/source plan
```

## Self-heal snippet

```text
If templates/context are missing: ask once, then continue with minimal v0.1 structure.
Mark unknown fields as "N/A (pending input)" and do not invent classification certainty.
Keep decision line and explicit track-resolution checklist visible.
```
