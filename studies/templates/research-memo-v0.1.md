# Research Memo — [Title]
Version: v0.1  
Status: Draft | In Review | Superseded | Abandoned  
Track: [conceptual-research | methods-techniques | tech-evaluation | data-source | case-study | similar-platforms | internal-spike | misc]  
Domain: [network-theory | sampling | investigative-methods | data-sources | identity | risk | other]  
Author:  
Reviewers:  
Reviewed on: YYYY-MM-DD  
Date: YYYY-MM-DD  
Tags:  
Concept classifications: []  
Related studies:  
- Parent study: [link or N/A]  
- Follow-on studies: [link(s) or None yet]  
- Related/branch studies (optional): [link(s) when a study splits]  
- Notes: [link(s) to /studies/notes/... if any, else `N/A`]  
- Guidance: keep this block in sync as studies split, branch, or supersede.  

---

## Template Usage Notes (Read First)

This memo template is designed to produce **comparable, governance-relevant research artifacts** for Power Atlas. These memos are *conceptual constraints and transferable insights*, not product requirements.

### How to Use This Template
- **Keep the header fields consistent** across memos so they remain easy to scan, search, and compare over time.
- Use the section structure as a **recommended skeleton**. If a section is not relevant, write `N/A` with a brief explanation rather than deleting it.
- Prefer **clear, technical-neutral language**. Avoid product framing, feature proposals, or UI prescriptions unless explicitly discussed as *risks/hazards*.

### Status Definitions (Controlled Set)
Use one of the following:
- **Draft** — incomplete, exploratory, may lack citations or internal consistency.
- **In Review** — ready for critique; core claims and sources are present.
- **Superseded** — replaced by a newer memo version (link to the newer memo near the top).
- **Abandoned** — intentionally discontinued (state why).

### Review Metadata
- Populate **Reviewers** and **Reviewed on** when moving to **In Review**.
- Review should reflect **critical reading**, not agreement.
- If review occurred in an issue/PR/discussion, add a link near the top of the memo.

### Concept Classifications (Header + Per-Concept)
- **Concept classifications (header)** should list the set of classification labels used anywhere in this memo. Use `[]` if none apply.
- **Section 3.1 tags** classify each individual concept. Prefer one primary classification per concept:
  - **Structural**
  - **Epistemic**
  - **Methodological**
  - **Analytical**
  - **Visual**
  - **Governance-related**

### Non-Goals
This memo is **not**:
- an endorsement of the work reviewed
- an implementation plan
- a product direction or roadmap commitment
- a substitute for Power Atlas governance documents

### Optional Appendix for Data Sources
If the memo evaluates a dataset or potential ingestion source, include **Appendix A — Data Source Assessment** to document licensing/terms, access method, update cadence, known bias limits, provenance granularity, identity risk, and misuse considerations.

---

## 0. At-a-Glance (Required)

**Scope (1–2 sentences):**  
[What specific aspect of the work this memo covers and what it does not cover.]

**Confidence / Maturity:** Exploratory | Informed | Well-cited  
*Note: “Confidence / Maturity” refers to this memo’s coverage and citation quality, not truth-claims about the subject.*

**Primary Takeaways (max 3):**
- [Takeaway 1]
- [Takeaway 2]
- [Takeaway 3]

**Key Risks / Cautions (max 3):**
- [Risk 1]
- [Risk 2]
- [Risk 3]

**If Superseded:**  
Superseded by: [link]

---

## 1. Purpose of This Memo

Briefly state why this body of work is being studied in relation to Power Atlas.

This memo exists to extract transferable concepts, constraints, and cautions
from [subject area] that may inform the design and architecture of Power Atlas.

This is a conceptual review. It is not an endorsement, implementation plan,
or product direction.

### 1.1 Non-Goals / Out of Scope (Required)
Explicitly state what this memo will *not* do.

Examples:
- This memo does not recommend adopting this framework as-is.
- This memo does not propose a scoring/ranking feature.
- This memo does not evaluate a specific dataset (unless Appendix A is included).

---

## 2. Overview of the Work

Concise explanation of:
- Who/what this work is
- Its primary domain
- Its stated goals
- Its historical or intellectual significance

Avoid excessive biography. Focus on ideas.

---

## 3. Core Concepts & Mechanisms

List the key ideas in clear, technical-neutral language.

### 3.1 Concept Classification (Recommended)
When listing concepts, optionally tag each with one primary classification to aid cross-memo comparison:

- **Structural**
- **Epistemic**
- **Methodological**
- **Analytical**
- **Visual**
- **Governance-related**

Example format:

- Preferential Attachment *(Structural)*:
  - Definition:
  - How it works:
  - What problem it solves:

- Authority Inference *(Epistemic)*:
  - Definition:
  - How it works:
  - What problem it solves:

Avoid product framing here.

---

## 4. Underlying Assumptions

Identify assumptions embedded in the work:

- Are networks treated as static or temporal?
- Are edges treated as uniform?
- Is structural prominence equated with influence?
- Is provenance modeled or assumed?
- Are uncertainty and contestability addressed?
- Is identity resolution formalized?
- Are descriptive and normative claims separated or blended?
- Are uncertainty and measurement error modeled explicitly, or assumed negligible?

Explicitly surface implicit philosophical or modeling assumptions.

---

## 5. Relevance to Power Atlas (Most Important Section)

For each relevant concept, answer:

*Guidance: depth is preferred over breadth; not every subsection requires equal length.*

### 5.1 Transferable Concepts
What conceptual tools or vocabulary may be useful?

### 5.2 Potential Alignment
Does this reinforce:
- Claim-mediated modeling?
- Temporal awareness?
- Provenance discipline?
- Human-in-the-loop governance?

### 5.3 Architectural Pressure Points
Would adopting this concept:
- Stress the ontology?
- Create ambiguity in claim vs relationship?
- Introduce metric authority risks?
- Collapse structure into interpretation?

### 5.4 Modeling Risks
Could misuse of this concept:
- Imply influence without evidence?
- Encourage deterministic narratives?
- Oversimplify contested domains?
- Create escalation through ranking?

### 5.5 Operationalization Hazards (Recommended)
Even if the concept is reasonable in research, what goes wrong when it becomes a system behavior?

Prompts:
- What would this tempt us to *compute*, *rank*, or *label*?
- What would be mistaken as “ground truth” in a UI?
- What failure modes appear at scale (automation bias, Goodharting, narrative lock-in)?
- What “shortcut interpretations” would users predictably make?

### 5.6 Misuse & Threat Notes (Recommended)
Lightweight threat-model hooks that can feed the project’s broader Risk & Misuse work.

Prompts:
- Who could misuse this concept or method?
- What harm becomes easier (harassment, doxxing, intimidation, reputational laundering)?
- What UI patterns would amplify misuse (leaderboards, “top actors,” badges, implied guilt)?
- What mitigations are implied (rate limits, friction, uncertainty displays, auditability)?

---

## 6. What We Might Borrow

List ideas that could be safely incorporated in abstract form:

- Analytical lenses
- Terminology
- Visualization styles
- Heuristic tools
- Framing metaphors (with caution)
- Exploration mechanics

Be explicit that borrowing ≠ copying.

---

## 7. What We Should Not Borrow

List elements that conflict with Power Atlas principles.

Examples:
- Equating centrality with power
- Collapsing correlation into control
- Ignoring temporal evolution
- Ignoring provenance
- Treating graph output as truth
- Blending descriptive structure with normative conclusions without clear labeling

Also:
- Avoid adopting interpretive language that implies causal or normative conclusions not supported by explicit evidence.

This section is as important as Section 6.

---

## 8. Open Questions

Questions raised by this research that require future consideration.

Examples:
- Should influence ever be computed directly?
- Can structural prominence be shown without implying authority?
- How do we prevent metric escalation?
- How should contestation/dispute be represented without turning into “both-sides” distortion?

---

## 8.1 Rhetorical Guardrails — “What not to say” (Required for Track A; recommended otherwise)

Capture phrases that overclaim, flatten uncertainty, or launder authority.

- Phrase to avoid:
  - Why it is risky:
  - Safer alternative phrasing:

---

## 8.2 Red-team misuse audit prompts (Required for Track A; recommended otherwise)

- How could this memo be misquoted to imply certainty, guilt, or authority it does not claim?
- What downstream misuse becomes easier if caveats are dropped?
- Which terms, labels, or visuals are easiest to weaponize?
- What friction/disclaimer should accompany high-risk claims?

---

## 9. Implications for Future Research (Optional)

What adjacent domains should be studied next?

Also include any explicit follow-ups:

### 9.1 Follow-ups / Actions (Optional)
*Note: follow-ups are exploratory research questions/tasks, not implementation tickets or roadmap commitments.*

- [ ] [Follow-up research task]
- [ ] [Question to resolve]
- [ ] [Risk to evaluate]

---

## 10. Sources (links-first)

Cite primary sources, papers, talks, platforms, or books.

Prefer links-first entries here too; include accessed dates for web sources when available.

Example:
- [Source title](https://example.com) — Accessed: YYYY-MM-DD

(Optional) Add a short note per source:
- why it matters
- what claim it supports
- relevant pages/sections/timestamps

---

## Appendix A — Data Source Assessment (Optional)

Include this appendix only when the memo evaluates a dataset or candidate source.

- **Source name & owner:**  
- **Access method:** (API / bulk download / scrape / manual / other)  
- **Terms/licensing constraints:** (redistribution, derivative works, attribution, revocation risk)  
- **Update cadence & versioning:**  
- **Coverage & known bias modes:**  
- **Provenance granularity:** (record-level vs aggregate; citations available?)  
- **Identity & linkage risk:** (PII, reidentification risk, sensitive attributes)  
- **Misuse considerations:** (who could weaponize it; what harms)  
- **Fit with Power Atlas principles:** (claim-mediated modeling, contestability, uncertainty)  

---

## Appendix B — Mini Example (Informative Only)

> This example is intentionally small and generic. It demonstrates tone, specificity, and how to separate transferable concepts from risks. Replace all bracketed placeholders in real memos.

# Research Memo — Snowball Sampling in Hidden Populations (Mini Example)
Version: v0.1  
Status: Draft  
Domain: sampling  
Author: [name]  
Reviewers: N/A  
Reviewed on: N/A  
Date: 2026-02-20  
Tags: sampling, bias, hidden-populations, network-effects  
Concept classifications: [Methodological, Epistemic]  

## 0. At-a-Glance (Required)

**Scope (1–2 sentences):**  
This memo reviews snowball sampling as a technique for discovering members of hard-to-observe populations via referrals. It does not evaluate a specific dataset or recommend operationalizing referrals as “influence.”

**Confidence / Maturity:** Exploratory  
*Note: “Confidence / Maturity” refers to this memo’s coverage and citation quality, not truth-claims about the subject.*

**Primary Takeaways (max 3):**
- Referral-based discovery can efficiently expand coverage, but it systematically over-represents well-connected nodes.
- “Who you can find” becomes a function of network position, not only relevance.
- Sampling mechanics can masquerade as structure if not explicitly modeled.

**Key Risks / Cautions (max 3):**
- Discovery pathways may be misread as endorsement, coordination, or power.
- Sampling bias can be mistaken for ground truth prominence.
- Temporal drift (who refers whom and when) can radically change inferred structure.

## 1. Purpose of This Memo

Extract constraints and cautions about referral-based discovery that could inform Power Atlas research and ingestion strategy.

### 1.1 Non-Goals / Out of Scope (Required)
- Not proposing any “referral score,” ranking, or automated inference of influence.
- Not asserting that discovered actors are “more important” than undiscovered actors.

## 3. Core Concepts & Mechanisms

- Snowball sampling *(Methodological)*:
  - Definition: A method that expands a sample by asking sampled participants to refer others.
  - How it works: Each wave of referrals increases reach, often rapidly.
  - What problem it solves: Access to populations that are not easily enumerated.

## 4. Underlying Assumptions

- Connectivity is treated as a practical proxy for discoverability.
- Referral edges are often treated instrumentally (as a method), not as meaningful social ties.
- Bias is acknowledged but not always quantifiable in practice; measurement error may not be modeled explicitly.

## 5. Relevance to Power Atlas (Most Important Section)

### 5.1 Transferable Concepts
- “Discoverability” as distinct from “importance.”
- Modeling “collection method” as provenance metadata (how a node/edge entered the graph).

### 5.3 Architectural Pressure Points
- If discovery method isn’t stored as provenance, users may read sampling artifacts as real structure.
- Referral links risk being confused with relationships unless explicitly typed/qualified.

### 5.4 Modeling Risks
- Over-representing highly connected actors may imply undue prominence.
- If surfaced visually without caveats, waves of discovery can suggest intentional coordination.

### 5.5 Operationalization Hazards (Recommended)
- UI temptation: “Most connected discovered actors” lists.
- System temptation: use referral pathways as a heuristic for “power,” which is not warranted.

_Sections 6–9 omitted for brevity in this mini example; see the full template above for all sections._
## 10. Sources
- [Primary paper/book] (add citation)
- [Secondary critique] (add citation)
