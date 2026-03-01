# Power Atlas — Metrics & Network Analysis Philosophy (v0.1, Draft)

**Status:** Experimental  
**Audience:** Contributors, architects, reviewers  
**Scope:** Semantic Core boundary protection for metrics and structural analysis outputs

## 1) Purpose & Scope

This document defines the v0.1 philosophy and guardrails for network metrics and structural analysis in Power Atlas.

It is aligned with:

- Architecture Overview v0.1: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
- Ontology Charter v0.1: [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md)
- Provenance & Confidence Charter v0.1: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
- Semantic Invariants v0.1: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)
- Epistemic Invariants v0.1: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)
- Temporal Modeling Principles v0.1: [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md)

v0.1 intent: metrics are **decision-support, navigation, and review aids**, not autonomous conclusions.

This document does **not** define algorithms, thresholds, engine choices, or required output formats.

**Key boundary statement:** metrics must not become a semantic backdoor for narrative conclusions (intent, motive, wrongdoing) or authority laundering via numeric outputs.

## 2) Definitions (v0.1)

- **Graph view / projection:** A constructed analysis view derived from claims under explicit filters (for example relationship categories, temporal scope, confidence posture, provenance scope, and contradiction handling).
- **Metric:** A derived structural summary from a selected claim-mediated graph view/projection (for example degree counts, reachability, or ranking scores). Metric outputs inherit the assumptions of that projection.
- **Centrality:** A family of topology-derived ranking heuristics over a chosen graph projection.
- **Ranking:** Any ordered output that compares entities/claims by a computed criterion.
- **Pathfinding:** Computed traversal output that shows one or more structural routes between selected nodes.
- **Cluster / component output:** Grouping output produced under explicit modeling assumptions.
- **Analysis output:** Any derived score, rank, path, grouping, delta, or anomaly indicator shown to users or systems.
- **Entity/relationship metric:** A derived summary over projected entities and structural relationships.
- **Claim-level metric:** A derived summary over claims as epistemic units (for example claim density, contradiction density, or confidence-state composition in a scope).

All definitions are conceptual and implementation-agnostic.

## 3) Permissible Uses (Allowed in v0.1)

Metrics may be used to support:

- navigation and exploration of structural neighborhoods,
- triage/prioritization for human review,
- anomaly or change surfacing for follow-up investigation,
- hypothesis generation that triggers evidence review,
- comparative structural views under explicit filters and time slices.

### Allowed example questions (good uses)

1. "What entities are within 2 hops of this entity in the selected time window?"
2. "What structural paths connect A and B under the current relationship-type filter?"
3. "Which entities have the highest degree for this relationship type in this dataset slice?"
4. "What changed between T1 and T2 (new claims, supersessions, confidence shifts)?"
5. "Which connected components appear in this scoped graph projection?"

## 4) Non-Goals / Prohibited Interpretations

Metrics outputs are structural and heuristic. They must not be interpreted as proof of:

- influence,
- intent,
- coordination,
- wrongdoing,
- leadership,
- moral/legal culpability,
- or real-world importance independent of evidence context.

### Disallowed conclusions (anti-patterns)

1. "High centrality proves this actor controlled the network."
2. "A short path between two entities proves collusion."
3. "Top-ranked entities are the most important in reality."
4. "Cluster membership proves faction membership or shared intent."
5. "A metric score alone is sufficient to assert misconduct."

## 5) Interpretation & Communication Guardrails

When presenting metrics output in docs/UI/API language:

- use non-escalatory wording ("may suggest", "under these assumptions", "requires evidence review"),
- label outputs as derived structural heuristics,
- state projection assumptions (included claim types, relationship filters, confidence filters, temporal scope),
- avoid causal or narrative framing unless supported by separately reviewable evidence,
- include confidence and provenance context where available.

## 6) Evidence / Provenance / Epistemic Linkage Expectations

For any analysis output, users should be able to inspect:

- **Inputs:** included claims/relationships/entities and exclusion criteria,
- **Time context:** valid-time and record-time scope used,
- **Evidence linkage:** what claim-level evidence underlies included edges/claims,
- **Provenance:** source origin and derivation context for included claims and derived result,
- **Confidence context:** epistemic status of participating claims,
- **Derivation context:** how the output was produced (at a conceptual/logical level sufficient for auditability).

Metrics should remain claim-mediated and must not bypass evidence/provenance requirements.

### Projection Disclosure Minimum (conceptual)

Any analysis output should be able to disclose, at minimum:

- **Time basis:** valid-time vs record-time and as-of/interval window,
- **Included claim/relationship categories,**
- **Confidence filter posture:** whether alleged/disputed/unknown claims are included,
- **Provenance scope:** which sources and ingestion/derivation processes are included or excluded,
- **Contradiction handling posture:** whether conflicting attributed claims were included side-by-side.

## 7) Temporal & Contradiction Handling

- Prefer time-sliced graph views; avoid collapsing incompatible windows into an "ever-graph."
- Respect valid-time vs record-time distinctions.
- Permit coexistence of contradictory attributed claims; metrics must not force hidden resolution.
- Treat temporal deltas as claim-state evolution (additions, supersessions, confidence revision), not eternal fact drift.

## 8) Risk & Ethics Considerations (v0.1)

Primary risks and mitigation posture:

- **Narrative escalation risk:** prevent semantics drift from structure to motive/culpability; require explicit non-implication language.
- **False precision / authority laundering:** require provenance, time scope, and confidence context around numeric outputs.
- **Coverage bias:** acknowledge that documentation density can inflate apparent centrality. High centrality may reflect documentation/ingestion density (what data is available), not real-world centrality.
- **Temporal collapse:** enforce explicit time windows and avoid indiscriminate aggregation across periods.
- **Feedback loops / Goodhart effects:** avoid using raw metric rankings as sole ingestion/review priority signals.
- **Ranking harms / defamation-by-ordering:** treat ordered outputs as heuristics under assumptions, not implied endorsement or judgment.
- **Privacy / harm risk:** minimize unnecessary linkage exposure and avoid outputs that materially increase re-identification or reputational harm.

## 9) Builder Anti-Patterns (v0.1)

- Do not label metric outputs as "influence score" or "power score" in Semantic Core language.
- Do not default analysis to an "ever-graph"; require explicit temporal scope.
- Do not present a score/rank without traceable linkage to inputs, filters, provenance scope, and time basis.

## 10) Review Checklist (v0.1 Guardrail Test)

- [ ] Replaceability test: if graph engine/API/UI changed tomorrow, would the meaning of this analysis output remain intact?
- [ ] Auditability test: can we trace why the result occurred (inputs, filters, time slice, provenance, derivation context)?
- [ ] Epistemic linkage test: does the output preserve mapping to claims/evidence/provenance/time/confidence?
- [ ] Non-escalation test: does the output avoid implying intent, motive, wrongdoing, or authority claims?
- [ ] Temporal integrity test: are valid-time and record-time boundaries explicit and non-collapsed?
- [ ] Contradiction handling test: are conflicting attributed claims represented without forced semantic resolution?

## 11) Communication Templates (Optional, Non-Binding)

- "Centrality here is computed on the selected projection and should be interpreted only as a structural heuristic; it does not imply influence, intent, or wrongdoing."
- "Paths shown reflect available claims under the selected time window and provenance scope; they do not imply coordination or causation."

## 12) Open Consumption Mode Question (Tracked)

v0.1 keeps both consumption modes open:

- **Graph UX / navigation-first**
- **Quant/network analysis-first**

These guardrails apply to both modes until later versions explicitly refine mode-specific policies.

## 13) Versioning & Forward Path

- This document is **Metrics & Network Analysis Philosophy v0.1**.
- v0.2+ may tighten review criteria, disclosure expectations, or output labeling requirements.
- Future versions should improve rigor without turning this philosophy into an implementation or algorithm specification.

## Non-Goals (v0.1)

This document does **not**:

- mandate specific centrality/pathfinding/community algorithms,
- mandate numeric thresholds or scoring policies,
- require specific output schemas or visualization formats,
- commit the project to continuous or autonomous analytics execution.

## Closing Note (Draft Status)

In v0.1, metrics are constrained to structural, evidence-linked decision support. They are useful for finding where to look next, not for deciding what is true about intent, motive, influence, or wrongdoing.
