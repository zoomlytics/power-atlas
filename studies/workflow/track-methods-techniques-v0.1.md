# Track Card — Methods / Techniques (methods-techniques) — v0.1

**Track slug:** methods-techniques  
**Applies to:** methods that could shape core capabilities (ER, extraction, uncertainty, evaluation, review workflows)  
**Primary purpose:** identify method requirements + failure modes + governance obligations.  
**Default depth level:** Level 2 (often escalates to Level 3)

---

## 1) When to use this track
Use when:
- studying a technique you might implement or rely on
Avoid when:
- you’re primarily assessing an external tool/vendor (use `tech-evaluation`)

## 2) Required inputs (minimum)
- [ ] At least 1 “how it works” source
- [ ] At least 1 “failure mode / critique” source (paper, blog, postmortem) when available

## 3) Required outputs (minimum)
- Level 2:
  - [ ] Notes
  - [ ] Detailed summary (recommended)
- Level 3 when method could become governance policy:
  - [ ] Research memo

## 4) Track-specific evaluation checklist
- [ ] What are the known failure modes (FP/FN, drift, bias, temporal collapse)?
- [ ] What inputs/metadata are required (provenance granularity, timestamps, evidence links)?
- [ ] What is reversible vs irreversible (merge/split, publication, confidence revision)?
- [ ] Where does the method risk collapsing candidate → authoritative?
- [ ] What guardrails are required (HITL, disclosure, contestability)?

## 5) Stop rules
Stop when:
- you can state: required inputs, failure modes, and minimal safe operating constraints
Continue to Level 3 if:
- outputs could change how claims are asserted, reviewed, revised, or presented

## 6) Integration targets
- Ontology/provenance/risk boundary docs (as clarifications)
- Simulations that stress the method under v0.1 invariants

## 7) Common pitfalls
- Over-indexing on benchmark scores without epistemic/audit requirements
- Treating “method output” as truth rather than claim-mediated candidate output

## 8) Suggested tags
- `entity-resolution`, `extraction`, `uncertainty`, `evaluation`, `workflow`
