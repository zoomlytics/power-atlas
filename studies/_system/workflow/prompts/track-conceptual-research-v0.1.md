# Track A Prompt Pack — Conceptual / Scientific Research (v0.1)

Use this pack for `Track: conceptual-research` studies.

---

## Tier 0 — Minimal Power Atlas orientation snippet (reuse at start)

```text
You are supporting Power Atlas research. Stay evidence-first, neutral, and structural.
Do not narrow too early to one theory, one metric, one author, or one rhetorical frame.
Treat centrality/statistical prominence as descriptive signals, not proof of influence/importance.
Surface assumptions explicitly, separate descriptive vs normative claims, and avoid false universality across domains.
Never launder authority via prestige language (e.g., “hub,” “key actor,” “important node”) without source-bounded qualifiers.
```

---

## Phase A prompt (Scout: wide scan + route decision)

```text
Task: Run Phase A scout for a Track A conceptual-research study.

Inputs:
- Study question
- Why now
- Non-goals
- Timebox + target depth (initially Level 1 unless justified)
- Any seed sources (optional)

Output file format: markdown section that can be pasted into study notes.

Required sections:
1) Scope framing (2-4 bullets)
   - What this scan includes/excludes
   - Early risk sensitivities

2) Wide scan map (3-6 angles)
   - Competing conceptual lenses
   - Include at least one angle that challenges mainstream framing

3) Glossary (working definitions)
   - Key terms + neutral definitions
   - Mark terms likely to be rhetorically overloaded (e.g., “hub,” “influence,” “power”)

4) Source landscape
   - Primary sources (foundational)
   - Critiques/counterpoints (required)
   - Quality notes: recency, methods, incentives, blind spots

5) Hazards map
   - Assumption smuggling risks
   - “Centrality ⇒ importance” risk
   - False universality risk
   - Authority laundering via “hub” rhetoric
   - Any misuse/escalation concerns

6) Candidate split map (required when branches appear)
   - If multiple branches emerge, recommend likely next study split(s)
   - For each split: draft study slug + one-line question + why separate

7) Phase A Decision Record (must be last)
   - Decision: Stop | Continue to Phase B | Escalate to Phase C
   - Rationale (3-6 bullets)
   - Key uncertainties
   - Trigger(s) that would change this decision
```

---

## Phase B prompt (File-ready brief summary)

```text
Task: Produce a file-ready brief summary for Track A.

Output path convention:
/studies/_studies/conceptual-research/<study-slug>/summaries/YYYY-MM-DD__<study-slug>__brief.md

Use template shape from /studies/_system/templates/summary-brief-v0.1.md.

Hard requirements:
- Keep Track as conceptual-research
- Include explicit "Assumptions" section (bulleted)
- Include "Contested / debate map" section (concise bullets: claims vs strongest counterclaims)
- Include decision line exactly:
  Decision: Stop | Continue in Phase B | Escalate to Phase C
- Include links-first Sources; when source is a web link include accessed date

Guardrails:
- Do not present centrality as equivalent to importance/influence
- Do not universalize claims beyond studied domain
- Do not rely on prestige/authority language as evidence
- Label uncertainty directly; do not smooth over contradictions
```

---

## Phase B prompt (File-ready detailed summary)

```text
Task: Produce a file-ready detailed summary for Track A.

Output path convention:
/studies/_studies/conceptual-research/<study-slug>/summaries/YYYY-MM-DD__<study-slug>__detailed.md

Use template shape from /studies/_system/templates/summary-detailed-v0.1.md.

Hard requirements:
- Include explicit assumptions list (separate implicit vs explicit assumptions)
- Include dedicated "Contested / debate map" section with:
  - major claim(s)
  - strongest counterclaim(s)
  - disagreement type (empirical / definitional / normative)
  - what evidence would change stance
- Include decision line exactly:
  Decision: Stop | Continue in Phase B | Escalate to Phase C
- Include links-first Sources; when source is a web link include accessed date

Track A risk checks (must be explicit):
- Assumption smuggling audit
- "Centrality ⇒ importance" rejection unless source-bounded and qualified
- False universality check (state boundary conditions)
- Authority laundering check for "hub" rhetoric
```

---

## Phase C prompt (File-ready memo draft)

```text
Task: Draft a file-ready research memo for Track A escalation.

Output path convention:
/studies/_studies/<track-slug>/<study-slug>/memos/YYYY-MM-DD__<study-slug>__memo-v0.1.md

Follow /studies/_system/templates/research-memo-v0.1.md section order. If a section is not applicable, write N/A with brief reason.

Required additions in the memo body:
1) What not to say (rhetorical guardrails)
   - List phrases/frames to avoid because they overclaim, launder authority, or imply unsupported causality

2) Red-team misuse audit
   - Likely misuse actors
   - How findings could be weaponized/misread
   - Amplifying UI/reporting patterns to avoid
   - Mitigations / friction recommendations

3) Sources discipline
   - Links-first source list
   - If source uses web URL, append "Accessed: YYYY-MM-DD"

4) Decision line near close:
   Decision: Stop | Continue in Phase C

Non-negotiable Track A guardrails:
- Separate descriptive structure from normative interpretation
- Never equate centrality with importance/power without explicit caveats
- Mark assumptions and boundary conditions explicitly
- Avoid authority laundering via “hub/important actor” rhetoric
```

---

## Branch spawn prompt (create follow-on study)

```text
Task: Propose a new branch study from current Track A findings.

Output: markdown block with these fields only:
- Parent study slug:
- Proposed new slug:
- Track recommendation:
- Why split now (2-4 bullets):
- Proposed filenames:
  - notes:
  - brief summary:
  - detailed summary:
  - memo (if likely):
- Initial source plan:
  - Primary sources (2-5)
  - Critiques/counterpoints (1-3)
- Related studies cross-links:
  - Parent:
  - Follow-on candidates:

Rules:
- New slug must be specific, reusable, and decision-relevant
- Track recommendation must be one controlled track slug
- Include at least one counter-source in the source plan
```

---

## Self-heal snippet (missing templates/context)

```text
If referenced templates are missing:
1) Ask once for the missing template path(s).
2) If unavailable, proceed with approximate v0.1 structure and mark unknown fields as "N/A (pending template)".
3) Do not invent citations, metadata, or review status.
4) Keep required decision line and risk checks visible.
5) Add a short "Backfill needed" checklist for exact template alignment.
```

---

## Suggested pilot flow (scale-free / preferential attachment)

1. Run Tier 0 snippet.
2. Run Phase A scout prompt and capture split recommendations (measurement vs mechanisms vs robustness when applicable).
3. Run Phase B brief + detailed prompts as file-ready outputs.
4. Escalate to Phase C memo when architecture/metrics/governance pressure is non-trivial.
