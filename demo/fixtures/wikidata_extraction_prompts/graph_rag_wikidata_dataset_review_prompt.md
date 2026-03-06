# GraphRAG + Wikidata Dataset Review & Improvement Prompt

You are reviewing structured datasets previously generated for ingestion into a Neo4j + GraphRAG pipeline.

The original extraction agent produced:
- `entities.csv`
- `facts.csv`
- `relationships.csv`
- A short summary section

Your task is to **audit, validate, and improve** these datasets where necessary — without fabricating information and without expanding scope beyond what is supported by Wikidata.

---

## Objective

Strengthen the datasets so they:
- Better support influence-research queries
- Strictly conform to schema and validation rules
- Eliminate structural errors and inconsistencies
- Improve alias coverage and relationship richness where justified
- Preserve evidence integrity (Wikidata-backed only)

You may:
- Correct errors
- Move rows between files if structurally incorrect
- Normalize formatting
- Add missing high-signal relationships (if clearly supported by Wikidata)
- Improve alias coverage

You must not:
- Invent facts
- Add entities outside the selected canonical set (unless fixing an obvious matching error)
- Introduce new predicate types not justified by Wikidata

---

## Step 1 — Structural Validation

### 1.1 Schema Compliance
Verify that:
- Column names match the required schemas exactly.
- No extra or missing columns exist.
- All CSV rows have consistent column counts.
- All fields are double-quoted.

### 1.2 facts.csv Literal-Only Enforcement
- Confirm that `facts.csv` contains **only true literals** (dates, numbers, short strings, URLs, identifiers).
- If any row contains an entity-valued property serialized as text, move it to `relationships.csv`.
- Ensure no QIDs appear in the `value` column.

### 1.3 Entity-Valued PID Guardrail
If `predicate_pid` is in `{P112, P69, P463, P39, P22, P25, P3373, P108, P169, P127, P1830}`:
- The row must appear in `relationships.csv`.
- The object must be a valid QID.

### 1.4 PID ↔ Label Validation
- Verify that `predicate_label` exactly matches the official English Wikidata label for the given PID.
- Correct any mismatches.

---

## Step 2 — Type Normalization

### 2.1 object_entity_type Standardization
Allowed values only:
`person | organization | place | event | other | unknown`

Rules:
- Universities and schools → `organization`
- Companies, NGOs, foundations, political parties, government agencies → `organization`
- Cities, countries, regions → `place`
- If uncertain → `unknown`

Correct any misclassified rows.

---

## Step 3 — Relationship Quality & Enrichment

### 3.1 High-Signal Relationship Coverage
Evaluate whether the dataset sufficiently includes high-signal predicates when available:
- P108 employer
- P169 chief executive officer
- P39 position held
- P463 member of
- P127 owned by
- P1830 owner of
- P112 founded by
- P749 parent organization
- P355 subsidiary

If clearly available in Wikidata for selected entities but missing, add them.

Aim for:
- Meaningful relationship density
- Leadership/ownership/affiliation predicates representing a substantial share of edges

Do not add speculative or weakly connected relationships.

---

## Step 4 — Alias Audit

For each canonical entity:
- Verify aliases include all relevant English altLabels.
- Ensure acronyms, legal names, and common variants are included when available.
- Remove duplicates.
- Ensure primary label is not repeated in aliases.

Do not fabricate aliases.

---

## Step 5 — Date & Formatting Normalization

- Dates must use ISO format.
- Full date → `YYYY-MM-DD`
- Year-only → `YYYY` (allowed as partial date)
- Do not fabricate precision.

Ensure:
- UTF-8 encoding
- No extra blank lines
- No markdown inside CSV

---

## Step 6 — Output Requirements

Return:

1. A short review summary including:
   - Issues found
   - Corrections made
   - Any enrichment added
   - Confirmation that validation checks now pass

2. The corrected CSV content in this order:
   - `entities.csv`
   - `facts.csv`
   - `relationships.csv`

All CSV content must be valid comma-separated CSV with strict quoting rules.

