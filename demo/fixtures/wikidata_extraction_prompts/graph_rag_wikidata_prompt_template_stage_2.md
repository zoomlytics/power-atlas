# Stage 2 Prompt — CSV Generation from Approved Canonical Shortlist

You are generating a **mock structured dataset that stands in for a Wikidata-derived export** for the Power Atlas demo.

Use:
1. the **attached unstructured source document**, and
2. the **approved canonical shortlist provided below**

to generate a **compact, curated, demo-friendly structured fixture set**.

Your job in this stage is to generate the final CSV files only.

---

## Inputs

You are given two inputs:

### Input A — attached unstructured source document
Use it as the narrative scope anchor and relevance check.

### Input B — approved canonical shortlist
Use this shortlist as the **authoritative canonical set** for `entities.csv`.

Do **not** add new canonical entities outside the approved shortlist.

You may include additional non-canonical Wikidata entities as `object_id` values in `relationships.csv` when useful and supported.

---

## Canonical shortlist lock

The approved shortlist is **authoritative and closed**.

- `entities.csv` must contain **only** entities from the approved canonical shortlist.
- Do **not** add newly discovered canonical entities during CSV generation.
- Do **not** promote supporting entities into `entities.csv` just because they have rich Wikidata coverage.
- Additional entities may appear only as **non-canonical relationship objects** in `relationships.csv`.
- If an approved shortlist entity cannot be matched confidently to Wikidata, omit it rather than replacing it with a guessed entity.

---

## Entity and QID verification rule

Do not invent QIDs, labels, aliases, descriptions, or entity records.

- Include a canonical entity only if you are confident it has a real Wikidata QID.
- If a shortlist entity cannot be matched confidently to a real Wikidata entity, omit it rather than fabricating a QID.
- Do not synthesize placeholder-like or speculative QIDs.
- Do not create rows for uncertain entities.
- Do not guess aliases or descriptions when the underlying Wikidata entity match is uncertain.

---

## Objective

Generate a Power Atlas-compatible structured fixture set that:

- stays tightly aligned to the attached document
- uses the approved canonical shortlist exactly
- looks like a curated Wikidata-derived export
- emphasizes leadership, governance, affiliation, employment, ownership, founding, and institutional context
- avoids generic corporate-profile drift
- remains compact, selective, and demo-friendly

---

## Critical Output Constraint

Your final response must contain **only the CSV contents** for the required files, in this exact order:

1. `entities.csv`
2. `facts.csv`
3. `relationships.csv`
4. `claims.csv`

Do **not** include:

- explanatory text
- summaries
- reasoning
- markdown commentary
- JSON
- code fences
- notes

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

## Canonical set rule

The approved shortlist is authoritative.

- `entities.csv` must contain **only** the approved canonical entities.
- Do **not** promote additional entities into the canonical set.
- `relationships.csv` may reference additional non-canonical QIDs as objects when useful.

If an approved canonical entity has sparse structured coverage, keep it only if you can still support it cleanly. Do not compensate by inventing rows.

---

## High-signal row selection rule

When deciding which Wikidata-backed rows to include, prioritize:

1. leadership, governance, founding, ownership, employment, affiliation, membership, parent/subsidiary structure
2. institutional or jurisdictional context that helps interpret the document
3. supporting context such as inception, official website, country, headquarters location, and citizenship

Rows from category 3 must remain a **minority** of the dataset.

Do **not** allow low-signal metadata to dominate.

## Surprising-row rejection rule

Reject any row that is technically plausible but would feel surprising, weakly relevant, or difficult to justify in a demo without extra explanation.

If a row would likely make a reviewer ask, “Why is this here?”, omit it.

---

## Generic metadata cap

Treat these as low-signal supporting metadata:

- inception
- official website
- country
- headquarters location
- citizenship

These may be included only sparingly.

Rules:
- Do not rely on these rows to carry the dataset.
- Relationship rows should substantially outnumber fact rows.
- Relationship claims should substantially outnumber fact claims.
- Exclude low-value metadata claims unless they are especially useful in the document context.

---

## File 1 — `entities.csv`

### Exact header

`entity_id,name,entity_type,aliases,description,wikidata_url`

### Rules

- One row per approved canonical entity only.
- `entity_id` must be the Wikidata QID
- `name` must be the English Wikidata label
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

### Alias rule

Populate aliases where useful for entity resolution:
- acronyms
- common short forms
- alternate spellings
- legal names
- former names

Do not fabricate aliases.
Do not repeat the primary label.
Remove duplicates.

### Description quality rule

- Use a clean, neutral English description if available.
- If the description is awkward, noisy, editorially strange, or missing, leave it empty.
- Do not copy low-quality description text into the output.

---

## File 2 — `facts.csv`

### Exact header

`fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at`

### Rules

- One row per literal-valued fact only.
- `fact_id` format like `F0001`
- `subject_id` must be one of the approved canonical entities
- `subject_label` must match the entity label
- `predicate_pid` must be a valid PID
- `predicate_label` must exactly match the official English Wikidata property label
- `value` must be a true literal
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

Do **not** put entity-valued properties in `facts.csv`.

Disallowed:
- QIDs in `value`
- entity names flattened into strings
- entity-valued properties serialized as text

If the value is an entity, it belongs in `relationships.csv`.

### Good fact candidates

For people:
- `P569` date of birth
- `P570` date of death
- `P856` official website

For organizations:
- `P571` inception
- `P856` official website

Use facts selectively.

## Partial date preservation rule

When Wikidata supports only partial date precision:

- preserve the original precision
- use `YYYY` for year-only values
- use `YYYY-MM` only if month precision is truly supported
- use `YYYY-MM-DD` only if full date precision is truly supported
- do **not** coerce partial dates into `YYYY-01-01` or any other invented full date
- do **not** invent month or day precision

---

## File 3 — `relationships.csv`

### Exact header

`rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at`

### Rules

- One row per entity-to-entity relationship
- `rel_id` format like `R0001`
- `subject_id` must be one of the approved canonical entities
- `subject_label` must match the entity label
- `object_id` must be a valid QID
- `object_label` must be the English label
- `object_id` may be outside the canonical set
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

### Relationship priorities

For people, prefer:
- `P108` employer
- `P39` position held
- `P463` member of
- `P69` educated at
- `P102` member of political party
- `P1416` affiliation
- `P27` country of citizenship only as supporting context

For organizations, prefer:
- `P169` chief executive officer
- `P112` founded by
- `P127` owned by
- `P1830` owner of
- `P749` parent organization
- `P355` subsidiary
- `P159` headquarters location only as supporting context
- `P17` country only as supporting context

### Type normalization rules

- universities, colleges, schools, research institutes → `organization`
- companies, nonprofits, foundations, political parties, government agencies, government bodies → `organization`
- cities, countries, regions, geographic entities → `place`
- role or office entities → usually `other`
- if uncertain → `unknown`

### Important exclusion

Do **not** include `P31` (`instance of`) in either `facts.csv` or `relationships.csv`.

---

## File 4 — `claims.csv`

### Exact header

`claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id`

### Rules

- `claim_id` format like `C0001`
- `claim_type` must be either:
  - `fact`
  - `relationship`
- `subject_id` must be one of the approved canonical entities
- `subject_label` must match the entity label
- `predicate_pid` and `predicate_label` must match the supporting source row exactly
- `source` must always be `wikidata`
- `source_url` must match the source row
- `retrieved_at` must use `YYYY-MM-DD`
- `source_row_id` must reference exactly one supporting row

### For relationship claims

- populate `object_id` and `object_label`
- leave `value` empty
- leave `value_type` empty
- `source_row_id` must reference an existing `rel_id`

### For fact claims

- populate `value` and `value_type`
- leave `object_id` empty
- leave `object_label` empty
- `source_row_id` must reference an existing `fact_id`

### Claims selectivity rule

`claims.csv` is a **curated subset**, not a mirror of every row.

- Do not create claims for every row automatically.
- Relationship-derived claims should generally outnumber fact-derived claims.
- Prefer claims that are useful for demo retrieval and citation.
- Exclude low-signal claims unless they are especially useful in context.

## Low-signal claim exclusion rule

Do **not** include claims for the following unless they are unusually important to the document narrative:

- official website
- date of birth
- country
- headquarters location
- citizenship
- inception

These rows may remain in `facts.csv` or `relationships.csv` as supporting context, but they should usually **not** appear in `claims.csv`.

### Claim text rule

Use natural phrasing such as:
- `X was founded by Y`
- `X is chief executive officer of Y`
- `X worked for Y`
- `X is affiliated with Y`
- `X official website is Z`

Avoid robotic phrases like:
- `X country is Y`
- `X inception is YYYY`

unless unusually important.

### Confidence rule

- `confidence` must be between `0` and `1`
- straightforward rows typically `0.93–0.99`
- ambiguous or time-bounded rows may be lower

---

## Hard validation rules

Before returning the CSVs, validate all of the following:

### Exact headers

- `entities.csv`  
  `entity_id,name,entity_type,aliases,description,wikidata_url`

- `facts.csv`  
  `fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at`

- `relationships.csv`  
  `rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at`

- `claims.csv`  
  `claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id`

### IDs

- `entity_id` matches `Q\d+`
- `fact_id` matches `F\d+`
- `rel_id` matches `R\d+`
- `claim_id` matches `C\d+`
- `predicate_pid` matches `P\d+`

### PID-label consistency

Use the official English Wikidata label exactly.

Pay special attention to:
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
- `P1416` = `affiliation`

### Common label exactness reminders

Use the official English Wikidata label exactly, including for predicates that are commonly paraphrased.

Examples:
- `P749` = `parent organization`
- `P169` = `chief executive officer`
- `P112` = `founded by`
- `P108` = `employer`
- `P1416` = `affiliation`

Do not substitute near-synonyms or expanded variants.

### Facts vs relationships
- `facts.csv` must contain literal-valued rows only
- entity-valued rows belong only in `relationships.csv`
- no QIDs in `facts.csv.value`

### P31 exclusion
- zero rows using `P31` in `facts.csv` or `relationships.csv`

### Controlled vocabularies
- `entities.csv.entity_type`: `person | organization | place | event | other`
- `relationships.csv.object_entity_type`: `person | organization | place | event | other | unknown`
- `facts.csv.value_type`: `date | url | entity | string | number | boolean`
- `claims.csv.claim_type`: `fact | relationship`

### Claim linkage
- each `source_row_id` must reference exactly one existing row of the correct type

### Final shape check
Before returning the output, confirm that:
- the canonical set exactly matches the approved shortlist
- the dataset is relationship-rich
- low-signal metadata is a minority
- the output looks like a curated demo fixture rather than a generic mini corporate profile export

If not, revise before output.

### Partial date validation

Reject any row that converts an imprecise date into an arbitrary full date such as `YYYY-01-01`.

If the source precision is year-only, keep the value as `YYYY`.

---

### Final reviewer sanity check

Before returning the output, review the dataset as if a human curator were inspecting it for demo quality.

Revise or remove anything that would trigger any of these reactions:

- “This looks invented or uncertain.”
- “This entity should probably not be canonical.”
- “This row is technically true but not useful.”
- “This row feels like generic company metadata.”
- “This claim is too weak to deserve inclusion.”
- “This date appears to have fabricated precision.”

---

## Formatting rules

- Use standard comma-separated CSV
- Include a header row for each file
- Wrap **every field** in double quotes
- Escape internal double quotes by doubling them
- Do not insert blank lines
- Replace embedded line breaks with a single space
- Ensure each row has the same number of fields as the header
- Use plain UTF-8-safe text
- Output only the four CSV files in the required order