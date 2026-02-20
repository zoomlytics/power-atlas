# Track A — Conceptual / Scientific Research (conceptual-research) — v0.1

**Track slug:** conceptual-research  
**Applies to:** scientific literature, academic frameworks, theory (network science, sampling, temporal models, etc.)  
**Primary purpose:** extract transferable concepts + constraints without importing narrative authority.  
**Default depth level:** Level 2  
**Primary risks:** assumption smuggling, “centrality ⇒ importance” escalation, false universality across domains.

---

## 1) When to use this track
Use when:
- studying academic / scientific work for conceptual tools or cautions
- evaluating claims like “scale-free networks are robust” or “hubs imply influence”
Avoid when:
- your main goal is choosing a database/tool (use `tech-evaluation`)
- your main goal is licensing/privacy of a dataset (use `data-source`)

## 2) Required inputs (minimum)
- [ ] At least 1 primary source (paper/book/talk)
- [ ] At least 1 critique / counterpoint if the work is influential or contested

## 3) Required outputs (minimum)
- Level 2 default:
  - [ ] Notes
  - [ ] Detailed summary (recommended)
  - [ ] Brief summary (recommended)
- Level 3 if it could influence modeling/metrics/governance language:
  - [ ] Research memo

## 4) Track-specific evaluation checklist
- [ ] What are the core concepts (neutral definitions, not product framing)?
- [ ] What assumptions are embedded (static vs temporal, edge meaning, completeness, observability)?
- [ ] What claims are descriptive vs causal/normative?
- [ ] What breaks in contested domains (bias, partial observability, strategic behavior)?
- [ ] What operationalization hazards emerge (rankings, “hubs” labeling, defamation-by-ordering)?

## 5) Stop rules
Stop when:
- you can state 3 transferable concepts AND 3 risks/cautions in your own words
Continue to Level 3 if:
- the work is likely to shape ontology, metrics, or how you talk about “power/influence”

## 6) Integration targets
- Memo Section 5 (Relevance), 6 (Borrow), 7 (Do not borrow)
- Possible updates to `/docs/metrics/analysis-philosophy-v0.1.md`
- Optional simulation(s) under `/docs/ontology/simulations/`

## 7) Common pitfalls
- Treating network metrics as semantics rather than derived heuristics
- Copying academic rhetoric that implies authority, culpability, or “importance”

## 8) Suggested tags
- `network-science`, `sampling`, `robustness`, `assumptions`, `metrics-risk`
