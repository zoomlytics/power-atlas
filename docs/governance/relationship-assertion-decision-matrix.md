# Relationship Assertion Decision Matrix (v0.1 Governance Draft)

**Status:** Experimental  
**Audience:** Contributors, curators, reviewers  
**Scope:** Conceptual governance for relationship assertions

---

## 1) Purpose

This governance draft defines conceptual decision guidance for relationship assertions in Power Atlas.

It aligns with:

- Ontology Charter v0.1: [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md)
- Provenance & Confidence Model Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)

This document is conceptual guidance only. It does not define schema, pipelines, algorithms, workflow tooling, or UI behavior.

---

## 2) Core Governance Invariant

Relationship assertions are **claim-mediated**: Power Atlas does not treat a relationship instance as automatically endorsed merely because it appears in imported, extracted, or derived data.

- A relationship assertion must be represented through an attributable claim context.
- Provenance and confidence apply to claims about relationships, not to implicit or baked-in structure.
- Contradictory claims may coexist when attribution, timing, and traceability are preserved.

---

## 3) Conceptual Matrix Axes

The decision matrix evaluates relationship assertions across these axes:

1. **Assertion category** — human-curated, structured import, automated extraction, derived inference.
2. **Evidence expectation** — what support should normally accompany the claim.
3. **Provenance completeness** — minimum conceptual traceability needed for governance confidence.
4. **Default confidence baseline** — initial epistemic stance prior to further review.
5. **Human review threshold** — when human review is conceptually recommended before stronger assertion status.
6. **Conflict and supersession posture** — how contradiction, updates, and replacement are handled without erasing history.

---

## 4) Relationship Assertion Decision Matrix (Conceptual)

| Assertion category | Evidence expectation (conceptual) | Provenance completeness expectation | Default confidence baseline (conceptual) | Human review threshold (conceptual) | Conflict & supersession posture |
| --- | --- | --- | --- | --- | --- |
| **Human-curated** | Curator-reviewed support, with evidence references where available | High: attributable curator/reviewer context, source origin, and assertion timing | **Verified** when support is explicit and review is accountable; otherwise **Alleged** pending completion | Review already present by definition; additional review recommended when sources conflict or evidence is partial | Keep prior and current claim states auditable; supersede by newer reviewed claim rather than overwrite |
| **Structured import** | Trustworthy structured source context (dataset/publication/release provenance) | Medium-high: source origin, release/ingest context, and transformation trace where applicable | **Alleged** by default; may move toward **Verified** after corroboration/review | Human review recommended before elevating status for sensitive or contested assertions | Permit coexistence of imported and other claims; supersession must preserve source lineage |
| **Automated extraction** | Extracted evidence artifacts (text spans, document references, extraction context) | Medium: derivation process trace plus source artifact linkage and timing | **Inferred** or **Alleged** by default (not auto-verified) | Human review recommended before treating as verified structural assertion | Contradictions remain represented as competing claims; later validated claims may supersede status, not erase lineage |
| **Derived inference** | Inputs to inference and inferential rationale/context should be referenceable | Medium: derivation lineage to input claims/evidence and process context | **Inferred** by default | Human review strongly recommended before high-trust or externally consequential use | Derived claims remain explicitly distinct from source-originated claims; supersession depends on updated inputs/evidence with audit trail |

---

## 5) Provenance Completeness Guidance

Provenance completeness is a conceptual quality threshold, not a fixed field checklist.

- **Complete enough for assertion:** origin and/or derivation path, responsible asserting agent/process, and timing context are answerable.
- **Partially complete:** some context exists but one or more attribution/lineage/timing dimensions are missing; confidence should remain conservative.
- **Insufficient:** provenance cannot meaningfully explain where a claim came from or how it was produced; assertion should remain unverified and contestable.

Provenance completeness should influence confidence posture but should not collapse contradiction or remove claim history.

---

## 6) Human Review Thresholds (Conceptual)

Human review is a governance signal that can revise epistemic status. This document does not prescribe workflow mechanics.

Human review is typically most important when:

- assertions are machine-extracted or inferred,
- provenance is partial or ambiguous,
- evidence is indirect, disputed, or weak,
- competing claims materially disagree,
- an assertion is being promoted from alleged/inferred posture toward verified posture.

---

## 7) Contradiction and Supersession Philosophy

- Contradictory relationship claims may coexist when each claim is attributable, traceable, and time-capable.
- Supersession should be modeled as a new epistemic state or claim relation, not destructive replacement.
- Governance should preserve contestability and auditability: users should be able to inspect what changed, when, and why.
- New evidence or review can revise confidence without rewriting historical claim context.

---

## 8) Non-Goals

This governance draft does **not** define:

- schema or storage models,
- ingestion/extraction/inference pipeline mechanics,
- ML scoring algorithms or numeric confidence models,
- enforcement implementation,
- UI decisions, labels, or layout.

---

## 9) Draft Acceptance Check (v0.1)

This draft is intended to satisfy v0.1 governance framing when it:

- covers all four relationship assertion categories,
- provides conceptual confidence baselines,
- defines conceptual review thresholds,
- explains provenance completeness effects,
- defines contradiction/supersession philosophy,
- references the Ontology and Provenance charters,
- preserves claim-mediated relationship assertion semantics.
