# Power Atlas — Risk & Misuse Model (v0.1, Draft)

**Status:** Experimental  
**Audience:** Contributors, architects, reviewers  
**Scope:** Conceptual risk taxonomy, misuse scenarios, and governance posture for v0.1 boundary docs  
**Review labels:** documentation, risk, governance

---

## 1) Purpose & Scope (v0.1)

This document defines the v0.1 **risk and misuse posture** for Power Atlas as a boundary artifact.

It is intentionally implementation-agnostic and aligned with:

- Governance / HITL boundary: [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md)
- Architecture boundary: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
- Temporal posture: [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md)
- Provenance & confidence semantics: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Epistemic invariants: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)
- Metrics non-escalation posture: [`/docs/metrics/analysis-philosophy-v0.1.md`](/docs/metrics/analysis-philosophy-v0.1.md)
- Entity resolution harm-minimization posture: [`/docs/ontology/entity-resolution-v0.1.md`](/docs/ontology/entity-resolution-v0.1.md)
- Semantic invariants / validation posture: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)
- Repository framing and non-goals context: [`/README.md`](/README.md)

This is a posture artifact, **not** an assurance claim, implementation plan, moderation tooling specification, or legal/compliance guarantee.

---

## 2) System framing (what Power Atlas is / is not)

In v0.1, Power Atlas is an experimental semantic modeling project focused on structural relationships, evidence linkage, provenance, temporality, and uncertainty representation.

Power Atlas is **not**:

- a production-ready decision platform,
- a legal/compliance determination system,
- an autonomous truth-adjudication or accusation system.

Core boundary reminder: structural modeling does not imply intent, motive, wrongdoing, or culpability.

Private-research status does not remove risk categories below; privacy, misuse, and interpretation harms can still occur in private or limited-access contexts.

---

## 3) Definitions (v0.1, compact)

- **Misuse:** harmful or policy-violating use that may be accidental, negligent, or context-stripping.
- **Abuse:** intentional harmful use, including adversarial manipulation or deliberate misrepresentation.
- **Harm:** privacy, reputational, epistemic, or downstream decision harm from incorrect, decontextualized, or over-interpreted outputs.
- **Publishing (v0.1):** making semantic content available in shared contexts; follows governance boundary language in [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md).
- **Candidate output vs authoritative output:** unreviewed proposals versus review-gated shared semantic record, per governance boundary in [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md).
- **Export / sharing:** dataset/report/snapshot/API/UI-visible output intended for use outside immediate draft context.
- **Risk posture:** declared boundary and review stance for reducing harm likelihood.
- **Mitigation (v0.1):** partial, documented guardrail posture; not a guarantee that harms cannot occur.

---

## 4) Risk taxonomy (conceptual, v0.1)

1. **Privacy & re-identification risk**
   - Linking records across contexts can increase re-identification exposure.
   - Combined metadata may reveal sensitive relationships not obvious in source artifacts alone.

2. **Defamation / reputational harm / implied wrongdoing by ordering**
   - Structural rankings or ordering may be interpreted as implied wrongdoing or importance.
   - Ambiguous links may be over-read as factual endorsement.

3. **Narrative escalation risk**
   - Outputs may be reframed from "structural signal" into claims about intent, motive, collusion, or guilt.

4. **Authority laundering risk**
   - Derived outputs may be presented as settled fact because they appear technical, scored, or system-generated.

5. **Automation bias / over-trust**
   - Reviewers or downstream consumers may over-trust candidate outputs and under-audit evidence/provenance.

6. **Data poisoning / adversarial input risk**
   - Misleading, forged, coordinated, or selectively edited source material can drive incorrect claims.
   - Malicious inputs can exploit confidence or ranking assumptions.

7. **Misuse of exports / downstream republishing**
   - Snapshots, exports, or excerpts can be stripped of provenance/time/confidence context and reused as decontextualized "facts."

8. **Security/abuse risk (conceptual)**
   - Unauthorized access, tampering, or abuse of system interfaces can affect trust and attribution integrity.
   - v0.1 acknowledges integrity/access risk conceptually without prescribing security controls in this document.
   - Security failures can undermine audit trail and attribution integrity commitments even when semantic posture is otherwise correct.

9. **Feedback loops / Goodhart effects**
   - If metrics/rankings drive ingestion or review priorities, the system can over-optimize toward proxy signals and drift from evidence quality.

---

## 5) Misuse & abuse scenarios (illustrative, non-exhaustive)

1. **Privacy & re-identification**
   - A contributor links sparse records across datasets and unintentionally creates a high-confidence profile of a private individual.

2. **Defamation-by-ordering**
   - A ranked list is shared externally; recipients treat rank position as implied culpability rather than topology under assumptions.

3. **Narrative escalation**
   - A pathfinding output is described as proof of coordination, despite being only a structural route over scoped claims.

4. **Authority laundering**
   - A generated summary is cited as fact without exposing source lineage, confidence state, or contradiction context.

5. **Automation bias**
   - Candidate entity merges are accepted in bulk with minimal review, causing conflation and downstream reputational harm.

6. **Data poisoning**
   - A forged document enters ingestion and causes derived claims to appear supported until contested evidence arrives.

7. **Export misuse**
   - A CSV export is republished without caveats, removing temporal scope and confidence posture from the original context.

8. **Goodhart loop**
   - Review prioritization favors high-centrality entities only, reducing coverage of lower-visibility but high-impact evidence.

9. **Temporal collapse**
   - An "ever-graph" export mixes 2008 and 2024 claims, implying contemporaneous relationships that never existed in one time window.

10. **Contradiction suppression**
   - A summary view hides conflicting claims and presents one statement as resolved fact, laundering uncertainty and dispute context.

---

## 6) Existing v0.1 mitigations / posture (mapped to boundary docs)

| Risk area | Primary v0.1 guardrail posture | v0.1 boundary posture |
| --- | --- | --- |
| Publication of potentially harmful semantic assertions | HITL review gate | HITL publication boundary, attributable review expectations, and non-authoritative candidate/authoritative distinction in [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md) |
| Authority laundering / hidden derivation | Provenance disclosure | Provenance-first attribution, claim mediation, and transparency requirements in [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md) |
| Silent revision / contested-state erasure | Non-erasure + contestability | Revision auditability and coexistence of contradiction in [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md) |
| Temporal collapse / decontextualized claims | Explicit time scoping | Valid-time vs record-time distinctions and revision trace posture in [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md) |
| Ranking harms / narrative escalation from metrics | Non-escalation language | Non-escalation language and heuristic-only framing in [`/docs/metrics/analysis-philosophy-v0.1.md`](/docs/metrics/analysis-philosophy-v0.1.md) |
| Identity conflation and re-identification risk | Conservative link-first posture | Conservative link-first entity resolution and harm-minimization posture in [`/docs/ontology/entity-resolution-v0.1.md`](/docs/ontology/entity-resolution-v0.1.md) |
| Semantic drift from infrastructure choices | Replaceability boundary | Semantic Core replaceability and boundary constraints in [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md) and [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md) |

Guiding rule alignment: **if it changes what users may believe about the world, it requires an attributable review event** (see governance boundary in [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md)).

v0.1 posture: these are conceptual guardrails and review expectations, not complete mitigations or enforcement guarantees.

---

## 7) Explicit non-goals / non-guarantees (v0.1)

This document does **not**:

- define defenses, moderation tooling, or security control implementations,
- provide exhaustive threat modeling or scenario simulation,
- define legal standards, liability positions, or compliance coverage,
- guarantee prevention of misuse, abuse, defamation, privacy harm, or re-identification,
- guarantee correctness of sourced or derived claims.
- provide safe-use certification,
- promise that outputs cannot cause harm.

v0.1 is a boundary-and-review posture; it is not a safety certification.

---

## 8) Review checklist (implementation-agnostic, v0.1)

- [ ] **Replaceability test:** Would risk posture remain valid if storage/API/UI/agent tooling changed?
- [ ] **Auditability/provenance trace test:** Can outputs be traced to source/derivation/review context?
- [ ] **Non-escalation language test:** Does wording avoid implying intent, motive, wrongdoing, or guilt?
- [ ] **Temporal scope clarity test:** Are valid-time and record-time assumptions explicit and not collapsed?
- [ ] **Candidate vs authoritative boundary test:** Is unreviewed output clearly non-authoritative before publication?
- [ ] **Context-preserving export test:** Are confidence/provenance/time assumptions preserved or disclosed when sharing outputs?
- [ ] **Contestability test:** Can conflicting or challenged claims remain visible without forced erasure?

---

## 9) Open questions (v0.2+ forward alignment)

- Should v0.2 introduce risk severity levels and explicit escalation paths?
- Should different claim/entity classes have differentiated review thresholds?
- What minimum disclosure should accompany exports used outside contributor contexts?
- How should recurring misuse patterns be tracked as a maintained risk register?
- What implementation-independent indicators should trigger additional review gates?

This artifact is expected to evolve with other boundary docs; risk modeling is an ongoing documentation practice, not a one-off milestone.

## 10) Versioning note

- This document is **Risk & Misuse Model v0.1**.
- v0.2+ may add severity cataloging, escalation paths, and refinement of review thresholds while remaining implementation-agnostic.
