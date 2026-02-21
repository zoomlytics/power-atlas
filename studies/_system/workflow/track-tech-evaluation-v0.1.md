# Track C — Technology / Platform Evaluation (tech-evaluation) — v0.1

**Track slug:** tech-evaluation  
**Applies to:** databases, engines, frameworks, pipelines, infra/tooling candidates  
**Primary purpose:** assess capability fit + lock-in vectors while protecting semantic independence.  
**Default depth level:** Level 2; Level 3 if adoption is plausible

---

## 1) When to use this track
Use when:
- evaluating graph DBs, search stacks, lineage tools, workflow engines, etc.
Avoid when:
- evaluating a dataset’s licensing/privacy/bias (use `data-source`)

## 2) Required inputs (minimum)
- [ ] Official docs/specs for the tech
- [ ] At least 1 independent critique / limitations discussion if available

## 3) Required outputs (minimum)
- Level 2:
  - [ ] Notes
  - [ ] Brief summary (recommended)
- Level 3 (recommended if plausible adoption):
  - [ ] Research memo focused on semantic fit + replaceability

## 4) Track-specific evaluation checklist
- [ ] What semantic commitments might this tech accidentally force (time model, contradiction handling, provenance expressiveness)?
- [ ] Replaceability: what are lock-in vectors (query language, proprietary features, data model coupling)?
- [ ] Can it support auditability/non-erasure (revision history, lineage, immutable logs)?
- [ ] What minimum experiment answers our question without commitment?
- [ ] What would we have to *give up* to use it safely (features we must not use)?

## 5) Stop rules
Stop when:
- you can articulate (a) fit, (b) constraints, (c) lock-in risks, and (d) a minimal experiment plan
Continue to Level 3 if:
- the tech is likely to be adopted or will shape contributor assumptions

## 6) Integration targets
- Architecture docs (replaceability notes)
- A “tech experiments” backlog (research follow-ups, not roadmap)

## 7) Common pitfalls
- Optimizing for convenience/performance while ignoring semantic coupling
- Treating vendor concepts as ontology language

## 8) Suggested tags
- `graph-db`, `infra`, `replaceability`, `lineage`, `locking`
