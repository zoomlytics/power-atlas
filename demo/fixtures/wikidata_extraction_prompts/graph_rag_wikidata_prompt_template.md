# GraphRAG + Wikidata Structured Extraction Prompt

You are generating a **mock structured dataset that stands in for a Wikidata-derived export** for the Power Atlas demo.

Use the **attached unstructured source document** as the scope anchor for entity selection, prioritization, and relevance. The attached document defines the narrative context for the dataset, but all structured rows you generate must be grounded in **Wikidata-style structured data** for the selected entities.

This dataset is intended for ingestion into the **Power Atlas** demo as an **optional additive structured enrichment layer**. It is **not** a Neo4j export and **not** a pre-built graph schema. Do **not** generate Cypher, graph-only join tables, or Neo4j-specific relationship columns beyond the required CSV files.

The application consuming this dataset will ingest the CSV fixtures and construct its own graph representation.

---

## Objective

From the **attached unstructured source document**:

1. Identify a **small, high-signal canonical set of entities** central to the document’s narrative.
2. Match those entities to the correct **Wikidata QIDs**.
3. Generate a **compact, demo-friendly structured fixture set** that mimics a curated Wikidata export.
4. Output the dataset in the exact **Power Atlas structured CSV fixture format**.

The dataset should support questions about:

- leadership
- affiliations
- memberships
- founders
- ownership
- institutional context
- jurisdictional and geographic context where useful

Prioritize **precision over recall**. It is better to return fewer correct, high-signal rows than a larger number of weak or questionable rows.

---

## Critical Output Constraint

Your final response must contain **only the CSV contents** for the required files, in this exact order:

1. `entities.csv`
2. `facts.csv`
3. `relationships.csv`
4. `claims.csv`

Do **not** include:

- explanatory text
- summary sections
- reasoning
- markdown commentary
- SPARQL
- JSON
- code fences
- notes on ambiguities
- validation notes

Output only the raw CSV text for the four files, each preceded by the filename on its own line exactly as shown:

entities.csv  
<csv content>

facts.csv  
<csv content>

relationships.csv  
<csv content>

claims.csv  
<csv content>

---

## Step 1 — Select the Canonical Entity Set

Read the **attached unstructured source document** and identify named entities that are central to its narrative.

### Selection requirements

- Select a **small, high-signal set of canonical entities**, typically **8–15**, unless the document strongly justifies a slightly different number.
- Prefer a **mix of people and organizations**.
- Choose entities that best support influence, affiliation, leadership, governance, ownership, and institutional-context queries.
- Avoid generic concepts unless the document clearly treats them as actors.
- Every selected canonical entity must have a valid **Wikidata QID**.
- Disambiguate carefully to avoid homonyms.
- If an important entity cannot be confidently matched to Wikidata, replace it with the next-best entity that can.

### Canonical-set rule

- `entities.csv` must contain **only the selected canonical entities**.
- `relationships.csv` may reference **additional object QIDs outside the canonical set** when useful and supported.

### Selection preference

Prefer entities that create meaningful cross-links with other selected entities when Wikidata supports those relationships. Favor entities that help produce a connected, demo-useful relationship graph rather than isolated biography rows.

---

## Step 2 — Gather Structured Data in Power Atlas Format

Generate a structured fixture set in four files:

- `entities.csv`
- `facts.csv`
- `relationships.csv`
- `claims.csv`

The result should look like a **curated, compact Wikidata-derived export** suitable for demo ingestion.

Do **not** fabricate facts.  
Do **not** infer unsupported relationships.  
If a property is absent or unclear, omit it.

---

## File 1 — `entities.csv`

### Exact header

`entity_id,name,entity_type,aliases,description,wikidata_url`

### Purpose

Defines the canonical entities used by the demo for structured enrichment and deterministic identity anchoring.

### Rules

- One row per canonical entity only.
- `entity_id` must be the Wikidata QID, e.g. `Q12345`
- `name` must be the English Wikidata label.
- `entity_type` must be one of:
  - `person`
  - `organization`
  - `place`
  - `event`
  - `other`
- `aliases` must be pipe-delimited using `|`
- `aliases` may be empty only if no useful English aliases are available
- `description` should be a short English description
- `wikidata_url` must be `https://www.wikidata.org/wiki/<QID>`

### Alias enrichment requirements

Aliases materially improve entity resolution and should be populated wherever Wikidata provides useful alternatives.

For each canonical entity, include relevant English aliases where available, such as:

- acronyms
- common short forms
- alternate spellings
- punctuation variants
- legal names
- former names
- branding variants

Rules:

- Do not fabricate aliases.
- Prefer English aliases.
- Remove duplicates.
- Do not repeat the primary label inside `aliases`.
- Avoid leaving organization aliases sparse when Wikidata provides meaningful altLabels.

---

## File 2 — `facts.csv`

### Exact header

`fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at`

### Purpose

Stores **literal-valued** facts attached to canonical subject entities.

### Rules

- One row per **literal-valued** fact only.
- `fact_id` must use a stable format like `F0001`, `F0002`, etc.
- `subject_id` must be one of the canonical entities from `entities.csv`
- `subject_label` must match the subject entity’s English label
- `predicate_pid` must be a valid Wikidata PID
- `predicate_label` must exactly match the official English Wikidata property label
- `value` must be a **true literal**
- `value_type` must be one of:
  - `date`
  - `url`
  - `entity`
  - `string`
  - `number`
  - `boolean`
- `source` must always be `wikidata`
- `source_url` must be the subject’s Wikidata page URL
- `retrieved_at` must use `YYYY-MM-DD`

### Strict literal-only rule

If a property’s value is an entity (a QID), it must **not** appear in `facts.csv`.

Disallowed in `facts.csv`:

- QIDs in the `value` field
- entity names serialized as plain strings in place of entity objects
- entity-valued properties flattened into text

If the value is an entity, it belongs in `relationships.csv`.

### Good fact candidates

For people:
- `P569` date of birth
- `P570` date of death
- `P856` official website

For organizations:
- `P571` inception
- `P856` official website

Use facts selectively. Literal facts should support identification and context, but should not dominate the dataset.

### Date normalization

- Full dates: `YYYY-MM-DD`
- Year-only dates: `YYYY` if Wikidata only provides year precision
- Do **not** invent missing precision
- Use ISO formatting only

---

## File 3 — `relationships.csv`

### Exact header

`rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at`

### Purpose

Stores entity-to-entity relationships that provide the structural backbone of the enrichment dataset.

### Rules

- One row per `(subject entity, predicate, object entity)` relationship.
- `rel_id` must use a stable format like `R0001`, `R0002`, etc.
- `subject_id` must be one of the canonical entities from `entities.csv`
- `subject_label` must match the subject entity’s English label
- `object_id` must be a valid QID
- `object_label` must be the English label for the object entity
- `object_id` may refer to entities outside the canonical set
- `predicate_pid` must be a valid Wikidata PID
- `predicate_label` must exactly match the official English Wikidata property label
- `object_entity_type` must be one of:
  - `person`
  - `organization`
  - `place`
  - `event`
  - `other`
  - `unknown`
- `source` must always be `wikidata`
- `source_url` must be the subject’s Wikidata page URL
- `retrieved_at` must use `YYYY-MM-DD`

### Type normalization rules

Use the following normalization rules strictly:

- universities, colleges, schools, law schools, research institutes → `organization`
- companies, nonprofits, foundations, political parties, government agencies, government bodies → `organization`
- cities, countries, regions, physical geographic entities → `place`
- role or office entities → usually `other`
- if uncertain → `unknown`

Use lowercase exactly as shown.

### Relationship priorities

This file is the **core** of the dataset. Prioritize relationships that support influence, governance, and institutional-context questions.

#### For people, prefer when available:
- `P108` employer
- `P39` position held
- `P463` member of
- `P69` educated at
- `P27` country of citizenship
- `P102` member of political party

#### For organizations, prefer when available:
- `P169` chief executive officer
- `P112` founded by
- `P127` owned by
- `P1830` owner of
- `P749` parent organization
- `P355` subsidiary
- `P159` headquarters location
- `P17` country

Additional relationship types are allowed if they clearly improve influence mapping or institutional context.

### Important exclusion

Do **not** include `P31` (`instance of`) in either `facts.csv` or `relationships.csv`.

It is low-signal for this fixture set and adds clutter without improving demo usefulness.

### Density guidance

- Relationships should substantially outnumber facts.
- Favor leadership, membership, affiliation, founding, ownership, and organizational structure over low-signal rows.
- Aim for a compact but meaningfully connected graph.
- If high-signal predicates exist for selected entities, include them.

---

## File 4 — `claims.csv`

### Exact header

`claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id`

### Purpose

Defines curated, high-signal claims derived from rows in `facts.csv` and `relationships.csv`.

These claims are used by the Power Atlas demo for retrieval, citation, and auditability.

### Rules

- `claim_id` must use a stable format like `C0001`, `C0002`, etc.
- `claim_type` must be either:
  - `fact`
  - `relationship`
- `subject_id` must be one of the canonical entities from `entities.csv`
- `subject_label` must match the subject entity’s English label
- `predicate_pid` and `predicate_label` must match the supporting source row exactly
- `source` must always be `wikidata`
- `source_url` must match the supporting source row
- `retrieved_at` must use `YYYY-MM-DD`
- `source_row_id` must reference exactly one supporting row

### For `relationship` claims

- Populate `object_id` and `object_label`
- Leave `value` empty
- Leave `value_type` empty
- `source_row_id` must reference an existing `rel_id` in `relationships.csv`

### For `fact` claims

- Populate `value` and `value_type`
- Leave `object_id` empty
- Leave `object_label` empty
- `source_row_id` must reference an existing `fact_id` in `facts.csv`

### Claim curation priorities

Prioritize claims that are broadly useful for demo questions, especially:

- founders
- chief executive officers
- employers
- positions held
- memberships
- ownership links
- parent/subsidiary relationships
- official websites
- key dates such as inception, birth, and death where useful

### Claim text requirements

`claim_text` must be:

- human-readable
- concise
- directly aligned to the source row
- useful for retrieval and citation demos

Examples of style:
- `Xapo was founded by Wences Casares`
- `Linda Rottenberg is chief executive officer of Endeavor`
- `Larry Summers holds the position United States Secretary of the Treasury`
- `Mercado Libre official website is https://www.mercadolibre.com`

### Confidence requirements

- `confidence` must be a numeric value between `0` and `1`
- straightforward Wikidata-backed rows typically fall between `0.93` and `0.99`
- potentially time-bounded, multi-value, or ambiguous rows may be slightly lower

Do not use values outside `[0,1]`.

---

## Hard Validation Rules

Before returning the final output, validate all of the following.

### 1. Exact schema compliance

Each file must use the exact required header and column order.

Required headers:

- `entities.csv`  
  `entity_id,name,entity_type,aliases,description,wikidata_url`

- `facts.csv`  
  `fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at`

- `relationships.csv`  
  `rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at`

- `claims.csv`  
  `claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id`

No extra columns. No missing columns. Every row must have the same number of fields as the header.

### 2. ID validation

- `entity_id` must match `Q\d+`
- `fact_id` must match `F\d+`
- `rel_id` must match `R\d+`
- `claim_id` must match `C\d+`
- `predicate_pid` must match `P\d+`

Zero-padded row IDs such as `F0001`, `R0001`, and `C0001` are preferred for readability.

### 3. PID ↔ label consistency

`predicate_label` must exactly match the official English Wikidata label for `predicate_pid`.

Pay special attention to these common labels:

- `P39` = `position held`
- `P108` = `employer`
- `P112` = `founded by`
- `P169` = `chief executive officer`
- `P463` = `member of`
- `P569` = `date of birth`
- `P570` = `date of death`
- `P571` = `inception`
- `P856` = `official website`
- `P1830` = `owner of`

Do not paraphrase property labels.

### 4. Facts vs relationships separation

- `facts.csv` must contain literal-valued facts only
- entity-valued properties must appear only in `relationships.csv`
- no QIDs may appear in `facts.csv.value`

### 5. P31 exclusion

There must be **zero rows** with `predicate_pid = P31` in:

- `facts.csv`
- `relationships.csv`

### 6. Controlled vocabulary compliance

`entities.csv.entity_type` must be one of:

- `person`
- `organization`
- `place`
- `event`
- `other`

`relationships.csv.object_entity_type` must be one of:

- `person`
- `organization`
- `place`
- `event`
- `other`
- `unknown`

`facts.csv.value_type` must be one of:

- `date`
- `url`
- `entity`
- `string`
- `number`
- `boolean`

`claims.csv.claim_type` must be one of:

- `fact`
- `relationship`

### 7. Date validation

- `retrieved_at` must use `YYYY-MM-DD`
- date literals must use ISO formatting
- year-only dates are allowed as `YYYY`

### 8. Canonical set integrity

- Every `subject_id` in `facts.csv`, `relationships.csv`, and `claims.csv` must refer to a canonical entity in `entities.csv`
- `relationships.csv.object_id` may point outside the canonical set

### 9. Claim linkage integrity

Every `claims.csv.source_row_id` must reference exactly one existing row:

- `claim_type = fact` → existing `fact_id`
- `claim_type = relationship` → existing `rel_id`

### 10. Deduplication and hygiene

- Deduplicate exact duplicate rows
- Remove duplicate aliases
- Do not repeat the primary label inside `aliases`
- Avoid inconsistent naming variants when the English Wikidata label is known

---

## Formatting Rules

These rules are mandatory for all CSV output:

- Use standard comma-separated CSV
- Include a header row for each file
- Wrap **every field** in double quotes
- Escape internal double quotes by doubling them
- Do not insert extra blank lines
- Replace embedded line breaks inside values with a single space
- Ensure each row has exactly the same number of columns as the header
- Use plain UTF-8-safe text
- Output only the four CSV files in the required order

---

## Dataset Quality Goal

Produce a **small, polished, high-signal structured fixture set** that:

- is scoped to the attached unstructured source document
- looks like a curated Wikidata-derived export
- is rich in leadership, affiliation, ownership, and institutional relationships
- is easy to ingest into the current Power Atlas demo
- supports entity resolution, retrieval, and citation-grounded demo questions
- remains auditable and schema-valid