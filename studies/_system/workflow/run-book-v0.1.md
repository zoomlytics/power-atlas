# Studies Run Book (v0.1)

Practical, phased workflow for running studies in an **AI-first (human-gated)** way with progressive context.

---

## Bundle map (what to attach, when)

- **Start bundle (Phase A):** minimal study orientation snippet only (do not attach broader templates yet).
- **Track bundle (Phase B):** selected track card + summary-brief template + summary-detailed template.
- **Memo bundle (Phase C):** research-memo template (+ Appendix A when relevant for data-source studies).
- For phase checklists + track manifests, see `/studies/_system/workflow/context-packs-v0.1.md`.

---

## Phase A — Orientation + wide scan

### Objective
Decide whether the study should stop, continue, or escalate.

### Minimal context pack (required)
Capture only what is needed to orient:
- Study question (1–2 sentences)
- Why now (decision/uncertainty reduced)
- Non-goals
- Initial risk sensitivities
- Timebox + depth target (initially Level 1 unless clearly deeper; see depth levels in `/studies/_system/workflow/README.md`)

### Scout map outputs (required)
Produce a short scout map section in your first artifact (notes or summary) with:
- **Angles:** 3–6 plausible interpretive angles/frame choices
- **Glossary:** key terms with working definitions
- **Hazards:** obvious misuse, policy, epistemic, or framing hazards

### Source landscape plan (required)
Before deep reading, list:
- **Primary sources:** foundational papers/books/specs/data docs/interviews
- **Critiques/counters:** rebuttals, replication failures, critical perspectives
- Initial source quality notes (authority, recency, incentives, known blind spots)

### Phase A decision record (required)
End Phase A with a visible decision block:
- **Stop** — low relevance or low evidence quality
- **Continue to Phase B** — enough signal for structured synthesis
- **Escalate now to Phase C** — governance/risk urgency already clear

Include rationale, open questions, and explicit trigger(s) for next step.

---

## Phase B — Structured synthesis

### When to attach the track bundle
Attach the track bundle as soon as Phase A says **Continue**:
- selected track card from `/studies/_system/workflow/`
- `/studies/_system/templates/summary-brief-v0.1.md`
- `/studies/_system/templates/summary-detailed-v0.1.md`

### Produce file-ready summaries
Build both summary artifacts as ready-to-commit files (even if one is short):
- **Brief:** concise relevance + cautions + recommendation posture
- **Detailed:** assumptions, pressure points, evidence quality, transfer limits

Both must be readable without raw notes and include a links-first **Sources** section.
Add `Notes:` links when note artifacts exist; otherwise mark `Notes: N/A`.

### Contested / debate map (required for Track A; optional otherwise)
In detailed summary, include a dedicated **Contested / debate map** section:
- major claims and strongest counterclaims
- which disagreements are empirical vs definitional vs normative
- what evidence would change current stance
- unresolved uncertainties that should not be flattened in synthesis

### Phase B decision record (required)
- **Stop** — synthesis complete; no governance lift needed
- **Continue in Phase B** — needs additional sources/debate resolution
- **Escalate to Phase C** — potential architecture/ontology/metrics/governance impact

Record decision, rationale, and escalation trigger(s).

---

## Phase C — Governance memo

### When to escalate to memo
Escalate when any of the below are true:
- findings could change architecture, ontology, metrics, or governance posture
- risk of misuse/escalation is non-trivial
- evidence quality is contested but decision pressure exists
- recommendation language could be misread as operational mandate

### Attach the memo bundle
- `/studies/_system/templates/research-memo-v0.1.md`
- include Appendix A when needed (especially data-source studies)
- link back to the source notes + summaries used as evidence base (or explicitly `Notes: N/A` if no notes were created)

### Required safeguards in memo
- **What not to say** vocabulary list (phrases that overclaim, decontextualize, or launder authority)
- **Red-team misuse audit** (how outputs could be misinterpreted, weaponized, or overextended)

---

## Split / branch rule (required)

Run **multiple studies when they become meaningfully distinct**. Create a new study slug once any one of these diverges:
- **Question:** distinct core question or decision
- **Sources:** different primary corpus or critique ecosystem
- **Failure modes:** different harms, errors, or misuse patterns
- **Integration target:** different landing zone in docs/ontology/simulations/memo posture

Default bias: if uncertain, **split** rather than forcing mixed concerns into one study.

### Naming rules (required)
- Use **hyphenated, lowercase slugs** (example: `scale-free-mechanisms`).
- Use file suffixes: `YYYY-MM-DD__slug__note__<short-label>.md`, `YYYY-MM-DD__slug__brief.md`, `YYYY-MM-DD__slug__detailed.md`, `YYYY-MM-DD__slug__memo-v0.1.md`.

### Directory layout rules (required)
- Notes and summaries live under track + slug:
  - `/studies/_studies/<track-slug>/<study-slug>/notes/`
  - `/studies/_studies/<track-slug>/<study-slug>/summaries/`
- Notes lane is optional; summaries/memos remain valid with `Notes: N/A`.
- Keep empty placeholder folders with `.keep` files when needed.
- Memos live under track + slug:
  - `/studies/_studies/<track-slug>/<study-slug>/memos/`

### Cross-linking + supersession rules (required)
- Include a **Related studies** block near the top of each artifact:
  - `Parent study:` upstream study link (or `N/A`)
  - `Follow-on studies:` child study links (or `None yet`)
- If a memo is replaced, create a new memo file and mark the older memo `Status: Superseded` with `Superseded by: [link]`.

### Track A pilot split mapping (example)
If starting from the pilot topic “scale-free preferential attachment,” likely split map:
- `scale-free-measurement` (diagnostics + evidence quality)
- `scale-free-mechanisms` (generative assumptions)
- `scale-free-robustness` (replication limits + critiques)

---

## AI-first with human gating

### Draft by default (required)
All AI-generated notes/summaries/memos are **Draft** by default.

### Minimum to move to “In Review”
Before status can move from Draft → In Review:
- human reviewer named
- review date set (or explicit `N/A` with rationale)
- key claims spot-checked against cited sources
- unresolved assumptions listed explicitly

### Reviewer checklist (required)
- authority laundering check (prestige/source status used as proxy for truth)
- assumptions surfaced and bounded
- citation quality (traceable, relevant, not citation-padding, not circular)

---

## Self-heal guidance (when setup is incomplete)

If required templates were not attached at the start:
1) continue with **approximate structure** matching required sections
2) mark missing fields as **`N/A (pending)`** instead of inventing content
3) backfill with canonical templates as soon as practical
4) keep decision records explicit so phase transitions remain auditable

Safety rule: never hide uncertainty; use explicit placeholders and proceed transparently.
