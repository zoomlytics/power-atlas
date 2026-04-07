# Stage 1 Prompt — Canonical Entity Curation for Power Atlas Structured Fixtures

You are helping curate a **small, high-signal canonical entity set** for a Power Atlas demo structured dataset.

Use the **attached unstructured source document** as the **primary scope boundary**. Your job is **not** to generate CSVs yet. Your job is to identify the best canonical entities to use later when generating a mock Wikidata-derived structured fixture set.

The goal is to produce a shortlist of entities that will lead to a **narrative-aligned, demo-useful, relationship-rich** structured dataset.

---

## Objective

From the **attached unstructured source document**:

1. Identify candidate entities mentioned in or clearly central to the document’s narrative.
2. Evaluate them for:
   - narrative centrality
   - likely usefulness in a structured demo dataset
   - ability to support high-signal Wikidata-backed relationships
3. Produce an **approved canonical shortlist** plus a list of **excluded candidates** with reasons.
4. Recommend the strongest relationship types to prioritize later for each approved entity.

This is a **curation step**, not a CSV-generation step.

---

## Important constraints

- The attached document is the **main scope boundary**.
- Prefer entities that are central to the document’s narrative, not merely easy to retrieve from Wikidata.
- Prefer durable narrative actors:
  - people
  - organizations
  - institutions
  - companies
  - foundations
  - government bodies
- Avoid promoting the following into the canonical set unless the document clearly treats them as primary actors:
  - products
  - apps
  - services
  - platforms
  - brands
  - websites
- Do **not** choose entities mainly because they have rich Wikidata pages.
- Do **not** try to maximize graph connectivity at the expense of narrative fidelity.
- Do **not** include tangential entities just because they create convenient ownership chains.

---

## Canonical entity quality criteria

Approved canonical entities should ideally satisfy most of the following:

- clearly central to the attached document’s narrative
- likely to exist in Wikidata with a valid QID
- likely to support at least **2 high-signal relationship rows**, or at least **1 high-signal relationship row plus strong narrative centrality**
- likely to help answer demo questions about:
  - founders
  - executives
  - employers
  - affiliations
  - ownership
  - memberships
  - institutional ties
- likely to form a meaningful part of a curated demo fixture, not just a generic corporate profile

Reject or deprioritize entities that mainly contribute:
- inception
- official website
- country
- headquarters location
- citizenship
without stronger leadership, governance, founding, ownership, or affiliation structure.

---

## High-signal relationship priorities

When evaluating whether an entity is worth including, prioritize entities likely to support rows such as:

### For people
- `P108` employer
- `P39` position held
- `P463` member of
- `P69` educated at
- `P102` member of political party
- `P1416` affiliation
- `P27` country of citizenship only as supporting context

### For organizations
- `P169` chief executive officer
- `P112` founded by
- `P127` owned by
- `P1830` owner of
- `P749` parent organization
- `P355` subsidiary
- `P159` headquarters location only as supporting context
- `P17` country only as supporting context

---

## Required working method

Internally perform these steps before producing your answer:

1. Draft a broader candidate list from the attached document.
2. Remove tangential or weak-fit candidates.
3. Remove entities that are primarily products, services, apps, or platforms unless the document clearly treats them as primary actors.
4. Remove entities that seem likely to yield mostly generic metadata rather than strong relationships.
5. Keep the best **8–15** canonical entities, unless the document strongly justifies a slightly different number.

Do not output your hidden chain-of-thought. Output only the requested final structure below.

---

## Output format

Return your answer in the following markdown structure.

### 1. Approved canonical entities

Provide a markdown table with these columns:

| Entity | Likely type | Why central to the document | Why good for structured demo use | Likely high-signal Wikidata relationships |
|---|---|---|---|---|

Guidance:
- `Entity` should be the best human-readable label.
- `Likely type` should be one of: person, organization, institution, company, government body, foundation, other.
- `Why central to the document` should be brief and document-focused.
- `Why good for structured demo use` should explain why the entity is likely to support a strong structured fixture.
- `Likely high-signal Wikidata relationships` should list the most promising predicates or relationship themes.

### 2. Excluded candidates

Provide a markdown table with these columns:

| Entity | Why excluded |
|---|---|

Include candidates that were plausible but should **not** be canonical because they are:
- tangential
- too weakly connected
- mostly products/platforms/services
- too dependent on generic metadata
- likely to create a misleading or low-value demo fixture

Also exclude candidates that are likely to tempt the next stage into generating low-signal or generic corporate-profile rows.

### 3. Recommended canonical shortlist

Provide a final numbered list of the **recommended canonical entities only**.

For each one, include:
- label
- likely type
- short reason for inclusion

### 4. Optional warning notes

If needed, add a short bullet list of warning notes, for example:
- ambiguous entity matches that may require careful Wikidata disambiguation
- entities that are central to the document but may have sparse structured coverage
- entities that are tempting to include but should probably remain relationship objects instead

---

## Output rules

- Do **not** generate CSVs.
- Do **not** invent QIDs if you are uncertain.
- It is acceptable to omit QIDs entirely at this stage if unsure.
- Keep the answer concise but useful.
- Favor curation quality over completeness.

## Shortlist closure rule

The final recommended canonical shortlist should be treated as a **closed set** for the next stage.

- Only include entities in the final shortlist if you believe they are strong enough to appear in `entities.csv`.
- Do not include “maybe” entities in the final shortlist.
- If an entity is plausible but uncertain, move it to **Excluded candidates** or mention it only in **Optional warning notes**.
- The next stage should not need to add newly discovered canonical entities if this shortlist is well curated.