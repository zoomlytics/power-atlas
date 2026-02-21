# Context Packs (v0.1) — Phase A/B/C

Purpose: define exactly what to attach/paste into GPT at each phase, while keeping early exploration broad.

---

## 1) Phase checklist (attach only what is listed)

### Phase A — Orientation (minimal by design)
- [ ] Study orientation snippet only:
  - study question (1–2 sentences)
  - why now
  - non-goals
  - initial risk sensitivities
  - timebox + depth target
- [ ] Do **not** attach track cards, summary templates, or memo/guardrail docs yet.

### Phase B — Structured synthesis
- [ ] Attach selected **track card** (A–G or M).
- [ ] Attach relevant summary template(s):
  - `/studies/_system/templates/summary-brief-v0.1.md` (required for brief output)
  - `/studies/_system/templates/summary-detailed-v0.1.md` (required for detailed output)
- [ ] Keep context limited to the selected track + summary format needed for current depth.

### Phase C — Governance memo
- [ ] Attach `/studies/_system/templates/research-memo-v0.1.md`.
- [ ] Attach selective guardrails **only if relevant to the study decision**:
  - risk: `/docs/risk/risk-model-v0.1.md`
  - metrics posture: `/docs/metrics/analysis-philosophy-v0.1.md`
  - provenance/epistemics: `/docs/provenance/v0.1.md`, `/docs/provenance/epistemic-invariants-v0.1.md`
- [ ] Avoid attaching unrelated guardrail docs “just in case.”

---

## 2) Track-specific bundle manifests

### Phase A manifest (all tracks)
- **Attach:** orientation snippet only (from Section 1 / Phase A).
- **Do not attach yet:** track card, summary templates, memo template, guardrail docs.

### Phase B manifest (by selected track)

| Track | Attach track card | Attach summary template(s) |
|---|---|---|
| Track A (`conceptual-research`) | `/studies/_system/workflow/track-conceptual-research-v0.1.md` | brief and/or detailed as needed |
| Track B (`methods-techniques`) | `/studies/_system/workflow/track-methods-techniques-v0.1.md` | brief and/or detailed as needed |
| Track C (`tech-evaluation`) | `/studies/_system/workflow/track-tech-evaluation-v0.1.md` | brief and/or detailed as needed |
| Track D (`data-source`) | `/studies/_system/workflow/track-data-source-v0.1.md` | brief and/or detailed as needed |
| Track E (`case-study`) | `/studies/_system/workflow/track-case-study-v0.1.md` | brief and/or detailed as needed |
| Track F (`similar-platforms`) | `/studies/_system/workflow/track-similar-platforms-v0.1.md` | brief and/or detailed as needed |
| Track G (`internal-spike`) | `/studies/_system/workflow/track-internal-spike-v0.1.md` | brief and/or detailed as needed |
| Track M (`misc`) | `/studies/_system/workflow/track-misc-v0.1.md` | brief and/or detailed as needed |

Use the summary template that matches the current output target/depth:
- fast triage synthesis: brief
- Level 2 default: brief + detailed
- escalation-ready synthesis: detailed (plus brief when useful)

### Phase C manifest (all tracks)
- **Required:** `/studies/_system/templates/research-memo-v0.1.md`
- **Optional (relevance-gated):** risk/metrics/provenance guardrails listed in Section 1 / Phase C.

---

## 3) Deep research mode (when to switch, what to ask)

Use deep research mode only when Phase A or B reveals one or more of:
- contested claims with meaningful disagreement
- high decision pressure with uncertain evidence quality
- non-trivial misuse/escalation risk
- likely impact on architecture, ontology, metrics, or governance posture

When switched on, ask GPT to:
- build a source acquisition plan that includes primary sources + strongest critiques
- produce a contested/debate map (empirical vs definitional vs normative disagreements)
- identify disconfirming evidence to look for before recommendation language
- surface assumptions, transfer limits, and “what would change our mind” triggers
- draft Phase B/C decision record language (stop/continue/escalate) with rationale

Keep deep research mode bounded:
- keep the active question narrow
- keep explicit stop rules/timebox
- avoid adding full governance packs until Phase C is actually triggered
