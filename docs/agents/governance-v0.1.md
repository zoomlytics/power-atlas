# Power Atlas — Agent Governance & Human-in-the-Loop Model (v0.1, Draft)

**Status:** Experimental  
**Audience:** Contributors, architects, reviewers  
**Scope:** Semantic Core boundary protection for agent/automation behavior and review controls

---

## 1) Purpose & Scope (v0.1)

This document defines why human-in-the-loop (HITL) governance exists in Power Atlas v0.1 and the minimum governance boundary for agent/automation behavior.

This draft is aligned with:

- Architecture Overview v0.1: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
- Temporal Modeling Principles v0.1: [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md)
- Provenance & Confidence Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Epistemic Invariants v0.1: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)
- Metrics & Network Analysis Philosophy v0.1: [`/docs/metrics/analysis-philosophy-v0.1.md`](/docs/metrics/analysis-philosophy-v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)

v0.1 intent: automation supports quality, speed, and coverage, while humans remain accountable for semantic publication decisions, error correction, and ethical boundary enforcement.

This document is conceptual and implementation-agnostic. It does **not** define infrastructure buildout, role-permission schema, or exhaustive workflow catalogs.

---

## 2) Definitions (v0.1)

- **Agent / automation:** Any system process that generates, transforms, ranks, or proposes semantic artifacts.
- **Candidate output:** A non-authoritative, reviewable artifact (for example proposed entities/claims/links) that is explicitly marked as unreviewed.
- **Review event:** An attributable decision event performed by a human reviewer that records decision and rationale.
- **Approval:** A review decision that permits candidate output to enter authoritative semantic use.
- **Audit trail:** Non-erasing record of who/what did what, when, and why.
- **Publishing (v0.1):** Any action that makes new or revised semantic content available for downstream interpretation outside a private draft context.

### What counts as publishing in v0.1

Publishing includes:

- **UI-visible:** content shown in primary user-facing views as part of shared graph/dataset context.
- **API-visible:** content returned by non-debug endpoints intended for consumption as asserted structure.
- **Exports:** dataset dumps, reports, share links, or snapshots intended for use outside immediate developer sandbox.
- **Authoritative persistence:** writing candidate/derived claims into authoritative namespaces/stores, unless clearly partitioned as draft/staging.

Usually not publishing:

- local-only experiments that do not persist into shared semantic contexts,
- explicit debug/experimental outputs that are clearly labeled non-authoritative.

---

## 3) Governance Principles (v0.1)

1. **Human accountability at publication boundary**
   - Agents assist; humans approve what becomes semantically authoritative.

2. **Provenance-first attribution**
   - Agent outputs are attributable artifacts (producer/version/context/time), not implicit truth.

3. **Non-escalation and neutrality**
   - Automation must not convert structural signals into narrative conclusions (intent, motive, wrongdoing).

4. **Temporal traceability**
   - Review and revision decisions must preserve record-time traceability and revision history.

5. **Contestability and correction**
   - Semantic changes remain reviewable, challengeable, and revisable without erasing prior states.

6. **Replaceability of implementation**
   - Governance commitments remain valid regardless of specific tools, engines, or interface choices.

---

## 4) v0.1 Guardrails (Allowed, Must-Review, Prohibited)

### 4.1 Allowed without explicit human review (v0.1)
Allowed only when outputs remain non-authoritative, clearly labeled, and reversible:

- doc/repo maintenance (formatting, linting, link checks, doc stubs without semantic assertions),
- extraction/linking into draft/staging candidate areas with explicit unreviewed labels and provenance,
- dry-run ingestion, previews, diffs, and validation checks,
- on-demand navigation/metric aids that are labeled derived and do not write back as authoritative semantic primitives.

### 4.2 Must have explicit human review before publishing (v0.1)

- any action that publishes new or revised semantic content,
- any transition from candidate/unreviewed to authoritative/approved state,
- confidence upgrades/downgrades that change epistemic interpretation,
- supersession, retraction, or materially revised claim interpretation,
- entity resolution merge/split decisions affecting authoritative identity semantics,
- exports or API/UI exposure of content represented as shared semantic record.

Guiding rule: **If it changes what users may believe about the world, it needs an attributable review event.**

### 4.3 Not allowed without review (v0.1)

- unsupervised publishing,
- silent semantic state changes (including confidence or supersession changes without review trail),
- implicit conversion of agent output into authoritative truth state,
- irreversible overwrite behavior that erases revision history.

---

## 5) Auditability & Minimum Review Record (Conceptual)

For each review-governed semantic change, the system should preserve at minimum:

- reviewer identity (human or accountable role),
- time of review (record-time),
- decision (approved / rejected / needs changes),
- what was reviewed (candidate artifacts/claims/derivation references),
- rationale or notes,
- change type (new claim, confidence update, supersession, merge/split, etc.),
- traceability to provenance/evidence context where applicable.

Review records are revision events, not destructive overwrites.

---

## 6) Risks & Failure Modes (v0.1 posture)

Primary risks this governance boundary addresses:

- **Automation bias:** over-trusting machine output without review,
- **Authority laundering:** presenting generated output as fact by default,
- **Feedback loops / Goodhart effects:** optimizing toward proxy signals detached from evidence quality,
- **Defamation-by-ordering / ranking harm:** presenting derived ordering as implied truth,
- **Silent drift:** untraceable semantic mutations over time.

v0.1 mitigation posture: high-risk or publication-boundary actions require explicit human review and attributable records.

---

## 7) Relationship to Risk Modeling (Forward Alignment)

This governance document defines control posture and guardrails. A future risk model document should refine this with explicit risk catalog and severity handling.

- **Governance charter:** policy boundary and control expectations
- **Risk model:** structured description of failure modes, severity, and escalation paths

Until risk modeling is expanded, this v0.1 governance posture remains the default boundary for agent behavior.

---

## 8) Non-Goals (v0.1)

This document does **not**:

- define implementation tooling or infrastructure plan for agents,
- define RBAC/permissions schemas,
- prescribe exhaustive process scenarios,
- lock project into a single workflow orchestration pattern.

---

## 9) Versioning & Ongoing Oversight

This is a versioned governance draft for v0.1 and should be updated as:

- semantic invariants evolve,
- risk modeling is formalized,
- contributor workflows mature,
- umbrella agent/automation principles are refined.

Governance is a maintained boundary artifact, not a one-time policy note.
