# Studies — Research Workflow (v0.1)

This document defines a **repeatable workflow** for conducting background studies that inform Power Atlas architecture, ontology, provenance/governance posture, metrics philosophy, risk thinking, and implementation exploration.

It complements (and does not replace) the **artifact templates** under [`/studies/templates/`](/studies/templates/).

**Key intent (v0.1):**
- keep research **consistent and searchable** across contributors,
- keep outputs **governance-relevant** when needed,
- avoid “research theater” by using explicit **timeboxes** and **stop rules**,
- support **human-only**, **AI-assisted**, and **AI-first with human review** research modes,
- preserve Power Atlas boundary posture: **Semantic Core independence**, **claim-mediated modeling**, **provenance/time/confidence discipline**, **non-escalation**.

---

## 0) Quick start (what to do first)

1) Pick a **Track** (A–G or Track M for Misc/Hybrid) using the canonical decision tree: `/studies/workflow/track-selection-decision-tree-v0.1.md`.  
2) Choose a **Depth level** (Level 1/2/3) and a **timebox**.  
3) Start a **Notes** document (raw capture) using the template:
   - `/studies/templates/source-note-v0.1.md`
4) As you learn, create a **Brief** and/or **Detailed** summary:
   - `/studies/templates/summary-brief-v0.1.md`
   - `/studies/templates/summary-detailed-v0.1.md`
5) If the study is governance-relevant or likely to affect architecture/ontology/metrics/risk posture, create a **Research Memo**:
   - `/studies/templates/research-memo-v0.1.md`

---

## 1) Core principle: one workflow backbone, tailored by track

All studies follow the same backbone stages:

1. **Intake & scoping**
2. **Acquisition & capture (Notes)**
3. **Synthesis (Summaries)**
4. **Governance-facing evaluation (Memo when warranted)**
5. **Integration outputs (where findings land)**
6. **Review & lifecycle (Draft → In Review → Superseded/Abandoned)**

Tracks do **not** change this backbone; tracks change:
- the *primary goal* and *evaluation checklist*,
- which outputs are *expected*,
- what “done enough” means (stop rules),
- where results should integrate back into the repo.

---

## 2) Track taxonomy (v0.1)

Choose exactly **one Primary track** (A–G or M). Optionally assign Secondary tracks in tags.

### Tracks (primary)
- **Track A — Conceptual / Scientific Research** (`conceptual-research`)
- **Track B — Methods / Techniques Research** (`methods-techniques`)
- **Track C — Technology / Platform Evaluation** (`tech-evaluation`)
- **Track D — Data Source Assessment** (`data-source`)
- **Track E — Journalistic / Investigative Case Study** (`case-study`)
- **Track F — Similar Platforms Review** (`similar-platforms`)
- **Track G — Internal Design Spike / Thought Experiment** (`internal-spike`)
- **Track M — Misc / Hybrid** (`misc`) *(temporary classification; requires a resolution plan)*

Track cards live in `/studies/workflow/`:
- `track-conceptual-research-v0.1.md`
- `track-methods-techniques-v0.1.md`
- `track-tech-evaluation-v0.1.md`
- `track-data-source-v0.1.md`
- `track-case-study-v0.1.md`
- `track-similar-platforms-v0.1.md`
- `track-internal-spike-v0.1.md`
- `track-misc-v0.1.md`

---

## 3) Track selection decision tree (v0.1)

Use the canonical decision tree in `/studies/workflow/track-selection-decision-tree-v0.1.md`.

Quick guidance:
- answer the prompts in order,
- pick the first strong match,
- choose one **primary track**,
- if no track fits, use **Track M — Misc / Hybrid (misc)** with a resolution plan.

If you have any process question about track routing, refer to the standalone decision-tree doc first.
- For phased execution guidance (A/B/C, split rule, AI-first gating), use `/studies/workflow/run-book-v0.1.md`.
- For reusable track prompt packs, use `/studies/workflow/prompts/README.md`.

### Hybrid guidance (important)
- Always choose one **primary track**.
- If the study spans multiple tracks, prefer **splitting into multiple studies** rather than overloading one memo.
  - Example: Similar platform review reveals an ER method worth deeper study → create a second study under `methods-techniques`.

---

## 4) Depth levels (and stop rules)

Choose a level up front. Most studies should stop at Level 1 or Level 2.

### Level 1 — Triage scan (fast)
**Use when:** deciding whether to invest more time.  
**Outputs:**
- Notes (required)
- Brief summary (recommended)

**Stop rule:** you can answer:
- what this is,
- whether it seems relevant,
- top 3 risks/cautions,
- recommended next sources (or “stop here”).

### Level 2 — Working understanding (default)
**Use when:** likely relevant, but not yet governance-critical.  
**Outputs:**
- Notes (required)
- Detailed summary (recommended)
- Brief summary (recommended)

**Stop rule:** you can:
- explain concepts neutrally,
- identify assumptions and failure modes,
- map pressure points to Power Atlas constraints.

### Level 3 — Governance-facing evaluation (high rigor)
**Use when:** it may influence architecture/ontology/metrics/governance OR carries elevated harm risk.  
**Outputs:**
- Research memo (recommended)
- Appendix A in memo (recommended for data-source studies)

**Stop rule:** memo clearly states:
- what to borrow,
- what not to borrow,
- operationalization hazards,
- misuse/threat notes (as appropriate),
- follow-up research questions (not implementation tickets).

---

## 5) Workflow stages (how to run a study)

### 5.1 Intake & scoping (always do)
Write a short “study charter” at the top of your Notes doc (or in a separate charter doc if/when introduced).

Minimum fields (recommended):
- Track (primary + optional secondary)
- Study question (1–2 sentences)
- Why now (what decision/uncertainty does it reduce?)
- Non-goals (explicit)
- Depth target (1/2/3) + timebox
- Output target (notes only / brief / detailed / memo expected)
- Any risk sensitivities (privacy, defamation-by-ordering, licensing)

### 5.2 Acquisition & capture (Notes)
Use `/studies/templates/source-note-v0.1.md`.

Guidance:
- capture quotes sparingly; prefer links + page/timestamp pointers
- record uncertainties and contradictions explicitly
- if AI is used, include tool metadata (see Section 6)

### 5.3 Synthesis (Summaries)
Use brief/detailed summary templates.

Guidance:
- summaries should be readable without the raw notes
- include Sources section (links-first)

### 5.4 Governance-facing evaluation (Memo when warranted)
Use `/studies/templates/research-memo-v0.1.md`.

Guidance:
- keep language neutral and implementation-agnostic
- emphasize Section 5 (Relevance to Power Atlas), Section 6 (Borrow), Section 7 (Do Not Borrow)
- explicitly call out operationalization hazards and misuse risks when relevant

### 5.5 Integration outputs (required to avoid “dead memos”)
Every Level 2+ study should end with one of:
- explicit “No action / not relevant” (and why), OR
- at least one integration output:
  - proposed simulation(s) under `/docs/ontology/simulations/`
  - suggested clarifications to boundary docs under `/docs/` (conceptual language updates)
  - follow-up research questions (memo Section 9.1), explicitly not implementation tickets

---

## 6) Research modes (human / AI-assisted / AI-first)

v0.1 supports three modes. Choose one and record minimal metadata in Notes (and optionally summaries).

### Mode H — Human-only
No additional metadata required.

### Mode A — AI-assisted (recommended default)
Human sets scope/stop rules; AI helps summarize/extract; human edits.

Minimum metadata (recommended):
- tool name
- run date
- input links
- whether output was edited

### Mode F — AI-first (allowed, gated by human review)
AI generates notes/summaries/memo drafts; a human reviewer validates.

Recommended gating rule (v0.1 posture):
- AI-first artifacts must remain **Draft** unless the Research Memo has **Reviewers** populated and **Reviewed on** set (or explicitly `N/A` with rationale), then it may move to **In Review**.

---

## 7) Status and lifecycle

Use the controlled status set from templates:
- Draft
- In Review
- Superseded
- Abandoned

### Supersession rule (recommended)
If a memo changes materially:
- create a new memo file and mark the older one **Superseded** with a link.

### Staleness note (recommended for tech/data sources)
If time-sensitive:
- add “Last re-checked: YYYY-MM-DD” near the top of the memo.

---

## 8) Minimal conventions (v0.1)

1) Every study artifact must state **Track** near the top (even Notes). Use controlled slugs: `conceptual-research | methods-techniques | tech-evaluation | data-source | case-study | similar-platforms | internal-spike | misc`.  
2) If Track = `misc`, include a **resolution plan** (reclassify or split).  
3) Follow naming convention: `YYYY-MM-DD__slug__type.md` (see `/studies/README.md`).  
4) Include a **Sources** section (links-first).  
5) Default: do not commit large binaries; use `/studies/_assets/` only when justified.

---

## 9) Examples (routing)

- “Review Barabási scale-free claims for transferable concepts + risks”  
  → Track A (`conceptual-research`), Level 2 → Level 3 if it affects metrics/UX language.

- “Evaluate Neo4j vs Postgres+AGE vs Memgraph for temporal + provenance constraints”  
  → Track C (`tech-evaluation`), likely Level 3 if adoption plausible.

- “Assess OpenCorporates licensing and re-identification risks”  
  → Track D (`data-source`), Level 1 triage, Level 3 if real candidate.

- “Study how a journalist built a shell-company network and what judgment calls occurred”  
  → Track E (`case-study`), Level 2; often produces simulations.

- “Review Palantir-like link analysis UX patterns and their escalation hazards”  
  → Track F (`similar-platforms`), Level 2; Level 3 if it will shape your UI language.

- “What happens if we show default leaderboards?”  
  → Track G (`internal-spike`), Level 1–2; likely outputs a simulation.
