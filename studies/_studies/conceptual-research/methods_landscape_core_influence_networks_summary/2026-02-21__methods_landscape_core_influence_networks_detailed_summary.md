# Study Summary (Detailed) — Methods Landscape for Identifying Influential Entity Networks
Version: v0.1  
Status: Draft  
Track: methods-techniques  
Domain: network-theory; investigative-methods; identity; risk  
Author: Power Atlas Research (assistant-generated)  
Date: 2026-02-21  
Tags: influence, multiplex-graphs, provenance, uncertainty, centrality, diffusion, causal-graphs, systemic-risk  
Related studies:  
- Parent study: N/A  
- Follow-on studies: None yet  
- Related/branch studies: None yet  
- Notes: N/A  
- Brief summary: N/A  
- Memo: N/A  
---

## 1. Scope

This study surveys established mathematical, scientific, and modeling methods that aim to identify influential entities or structures within complex systems. It focuses on core mechanics rather than specific implementations or vendors. It does not recommend a single theory of influence, nor does it evaluate tools.

---

## 2. What the Work Is (high-level)

- A structural mapping of method families relevant to identifying influence and power.
- A synthesis showing how multiple influence meanings coexist.
- A proposed backbone formalism and minimal reference architecture consistent with Power Atlas design principles.

---

## 3. Main Claims / Ideas

### Claim A: Influence is multi-dimensional
- Explanation: Positional prominence, control, coordination, systemic fragility, causal impact, and narrative authority represent distinct forms of influence.
- Evidence: Network science literature differentiates centrality, diffusion, block structure, and causal impact.
- Limitations: Requires parallel modeling and careful interpretation.

### Claim B: No single metric can represent “power”
- Explanation: Different methods operationalize different assumptions.
- Evidence: Empirical instability of rankings across methods.
- Limitations: Increases analytic complexity.

### Claim C: Provenance, time, and uncertainty must be first-class
- Explanation: Claims about influence depend on evidence quality and temporal scope.
- Evidence: Power Atlas core principles.
- Limitations: Higher storage and modeling overhead.

---

## 4. Methods / Mechanisms

### A. Structural Position Metrics
- Degree, betweenness, eigenvector, Katz, PageRank
- k-core decomposition

### B. Diffusion / Propagation Models
- Independent Cascade
- Linear Threshold
- Influence maximization

### C. Meso-scale Structure
- Stochastic block models
- Community detection
- Core–periphery models

### D. Causal Graphical Models
- Directed acyclic graphs
- Constraint-based causal discovery

### E. Systemic Impact Metrics
- Stress propagation
- Feedback-based impact scoring (e.g., DebtRank-style)

### F. Representation Learning
- Node embeddings
- Graph neural networks + explainability

### G. Identity & Entity Resolution
- Probabilistic record linkage

### H. Provenance & Temporal Modeling
- Claim-based graphs
- Time-scoped relations

---

## 5. Notes, Quotes, and Timestamps

N/A (high-level synthesis)

---

## 6. Relevance to Power Atlas (working view)

- Potentially relevant: All method families listed.
- Probably irrelevant: None at this stage.
- Risky or ambiguous: End-to-end black-box models without explainability.

---

## 7. Open Questions / Follow-ups

- Which influence types should be first-class in v0.1?
- What minimal robustness diagnostics are required?
- How should uncertainty propagate through influence scores?

---

## 8. Contested / debate map

- Major claim: Centrality ≠ influence.
- Strongest counterclaim: Centrality often correlates with influence in practice.
- Disagreement type: Empirical.
- Evidence that would change stance: Stable cross-domain validation showing single metric suffices.

---

## 9. Phase A/B decision record

- Phase A decision: Continue to Phase B
- Phase B decision: Continue in Phase B
- Rationale: Foundational relevance across Power Atlas core capabilities.

---

## 10. Sources

- Network science textbooks and surveys
- Causal inference literature
- Financial network systemic risk papers

---

# Appendix A — Candidate Mathematical Backbone

Temporal, multiplex, probabilistic claim graph:

c = (s, r, o, t, w, P)

Where P = provenance, w = confidence.

Influence defined as family of functions I_k over graph views.

---

# Appendix B — Minimal Reference Architecture

Layer A: Evidence & Provenance
Layer B: Identity Resolution
Layer C: Graph Views
Layer D: Influence Engines (plural)
Layer E: Robustness & Audit
Layer F: Presentation

---

# Appendix C — Example Query Family (US Oil Market)

- Structural positional influence
- Ownership/control influence
- Coordinating blocs
- Systemic disruption leverage
- Policy/regulatory leverage
- Narrative influence

Each treated as separate query template.

