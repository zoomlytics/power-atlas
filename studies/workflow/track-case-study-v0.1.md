# Track Card — Journalistic / Investigative Case Study (case-study) — v0.1

**Track slug:** case-study  
**Applies to:** investigative workflows, published network maps, case reconstructions  
**Primary purpose:** learn methods + produce evaluation scenarios without importing narrative conclusions.  
**Default depth level:** Level 2

---

## 1) When to use this track
Use when:
- you want benchmark-like scenarios: “could PA surface similar structure under evidence constraints?”
Avoid when:
- you’re evaluating a data source’s terms (use `data-source`)

## 2) Required inputs (minimum)
- [ ] Primary publication(s)
- [ ] If possible, supporting methodology notes / source lists / appendices

## 3) Required outputs (minimum)
- Level 2:
  - [ ] Notes
  - [ ] Detailed summary (recommended)
  - [ ] Brief summary (recommended)
- Level 3 if used as a design/architecture anchor:
  - [ ] Research memo

## 4) Track-specific evaluation checklist
- [ ] What sources did the journalist use (and what’s the evidence chain)?
- [ ] What transformations occurred (cleaning, linking, timeline building)?
- [ ] Where were judgment calls made (merge/split, inclusion criteria)?
- [ ] What claims are strongly evidenced vs narrative/interpretive?
- [ ] How could we test PA without copying conclusions (simulation, evaluation harness)?

## 5) Stop rules
Stop when:
- you can describe the investigative method as a reproducible conceptual pipeline
Continue to Level 3 if:
- the case study will influence major UX/metrics framing or be used as a recurring benchmark

## 6) Integration targets
- Ontology stress simulations and evaluation scenarios
- Risk notes (defamation-by-association/order)

## 7) Common pitfalls
- Treating published diagrams as ground truth rather than authored argument
- Accidentally importing accusatory framing into semantics

## 8) Suggested tags
- `investigation`, `workflow`, `benchmark`, `evidence`, `case-study`
