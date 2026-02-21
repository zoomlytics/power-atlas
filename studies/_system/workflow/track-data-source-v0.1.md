# Track D — Data Source Assessment (data-source) — v0.1

**Track slug:** data-source  
**Applies to:** datasets/APIs/registries/leaks/collections considered for ingestion or reference  
**Primary purpose:** assess legality/ethics + provenance/bias + identity/linkage + misuse risk.  
**Default depth level:** Level 1 for triage; Level 3 for real candidates

---

## 1) When to use this track
Use when:
- you might ingest, reference, or build workflows around a source
Avoid when:
- you’re mainly evaluating a tool/platform (use `tech-evaluation`)

## 2) Required inputs (minimum)
- [ ] Source terms/licensing page (or explicit note “unknown”)
- [ ] Provenance statement (who made it, how compiled) if available
- [ ] Bias/coverage discussion if available

## 3) Required outputs (minimum)
- Level 1:
  - [ ] Notes
  - [ ] Brief summary including a “Go/No-go/Unknown” triage
- Level 3 for real candidates:
  - [ ] Research memo
  - [ ] Appendix A — Data Source Assessment (recommended)

## 4) Track-specific evaluation checklist
- [ ] Terms/licensing + redistribution/derivative constraints + revocation risk
- [ ] Access method + update cadence + versioning
- [ ] Provenance granularity (record-level citations? source artifacts?)
- [ ] Coverage + known bias modes + missingness
- [ ] Identity/linkage risk (PII, re-identification, sensitive attributes)
- [ ] Misuse scenarios + export/context stripping risks

## 5) Stop rules
Stop when:
- you can clearly state “safe to explore / unsafe / unknown” and why
Continue to Level 3 if:
- source is a serious candidate OR carries elevated harm risk

## 6) Integration targets
- Risk model doc if it introduces new misuse classes
- Ingestion spike notes (separate from commitments)

## 7) Common pitfalls
- Confusing availability with permission
- Ignoring revocation and downstream export harms

## 8) Suggested tags
- `licensing`, `provenance`, `bias`, `pii`, `misuse`
