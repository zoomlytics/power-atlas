# GraphRAG + Wikidata Structured Extraction Prompt

Produce structured datasets describing a small set of entities from the article, suitable for ingestion into a **Neo4j + GraphRAG** pipeline.

You must output **THREE CSV files** (as plain CSV text) plus a short **README-style summary**.

---

## Step 1 — Select the Canonical Entity Set

Read the PDF and identify named entities that are central to the narrative.

**Selection requirements:**
- Select a **small, high-signal set of canonical entities** (typically 8–15, unless the article strongly justifies a different number).
- The number of entities must be explicitly justified in the summary.
- Choose entities that best represent the story and are likely to exist in **Wikidata**.
- Prefer a mix of **persons** and **organizations**.
- Avoid generic categories (e.g., “government”, “Bitcoin”) unless explicitly treated as an actor in the article.

For each selected entity:
1. Find the best matching **Wikidata QID**.
2. If multiple candidates exist, choose the most appropriate and explain briefly.
3. If an important entity cannot be confidently matched to Wikidata, replace it with the next-best entity that can be matched.

---

## Step 2 — Gather Structured Statements from Wikidata

For each of the selected canonical entities, gather Wikidata statements in two categories.

**Important orientation:** The goal is to support *influence research* queries (leadership, affiliation, ownership, jurisdictional links, institutional context). Prioritize high-signal, entity-to-entity relationships over biographical trivia.

---

### A) Entity Profile Facts (True Literal Facts)

Collect a focused but selective set of **true literal** properties.
- Use what exists for the entity.
- **Do not fabricate.**
- Avoid over-weighting low-signal attributes (e.g., only birth dates and inception dates).
- Literal facts should support identification and contextual grounding, not dominate the dataset.

**Strict rule:** If a property’s value is an entity (QID), do **not** put it in `facts.csv` as a string. Put it in `relationships.csv`.

#### For Persons, Good Literal Candidates:
- `date of birth (P569)`

(If present and truly literal, also allow identifiers/URLs such as official websites, external IDs, etc.)

#### For Organizations, Good Literal Candidates:
- `inception (P571)`

(If present and truly literal, also allow identifiers/URLs such as official websites, external IDs, etc.)

**Do not include entity-valued properties in facts** (examples that must go to `relationships.csv`):
- `place of birth (P19)`
- `employer (P108)`
- `position held (P39)`
- `member of political party (P102)`
- `member of (P463)`
- `educated at (P69)`
- `country of citizenship (P27)`
- `country (P17)`
- `headquarters location (P159)`
- `parent organization (P749)`
- `subsidiary (P355)`
- `owned by (P127)`
- `owner of (P1830)`
- `CEO (P169)`
- `founded by (P112)`

#### Also Include:
- **Aliases / alternative names** (from `skos:altLabel` via Wikidata labels)

**Alias Enrichment Requirements (High Importance):**
- Populate aliases for **every canonical entity where available**.
- For organizations, explicitly review Wikidata `altLabel`, `also known as`, former names, legal names (e.g., "S.A.", "Inc.", "Ltd." variants), acronyms, and common short forms.
- Include common abbreviations (e.g., "CIA" for "Central Intelligence Agency").
- Include alternate spellings, spacing variants, punctuation variants, and branding variants when present in Wikidata (e.g., hyphenated vs non-hyphenated forms).
- Include well-known acronyms and short forms.
- Prefer English aliases; if multiple English variants exist, include all high-signal ones.
- Do not fabricate aliases; only use those supported by Wikidata labels/altLabels.
- Remove duplicates and do not repeat the primary label.
- Avoid leaving organization aliases sparse: when Wikidata provides multiple relevant altLabels, include them rather than selecting only one.

Aliases materially improve PDF mention → canonical entity resolution and are not optional when available.

Literal facts should typically represent a minority of total rows.

---

### B) Relationship Edges (Entity → Entity) — High Priority

This section is the core of the enrichment. Focus on entity-valued predicates that help answer questions such as:
- "What organizations are connected to X through leadership, founding, employment, or investment?"
- "Which entities are US-linked vs Argentina-linked?"
- "What institutional relationships contextualize the claims in the PDF?"

Prioritize high-signal predicates (when available):

**For People:**
- `employer (P108)`
- `position held (P39)`
- `member of (P463)`
- `member of political party (P102)`
- `educated at (P69)`
- `country of citizenship (P27)`
- `founded by (P112)` (if applicable in reverse context)

**For Organizations:**
- `parent organization (P749)`
- `subsidiary (P355)`
- `owned by (P127)`
- `owner of (P1830)`
- `headquarters location (P159)`
- `country (P17)`
- `CEO (P169)`
- `founded by (P112)`

**Explicit exclusion:** Do **not** include `instance of (P31)` in either `facts.csv` or `relationships.csv` for this exercise. It is typically low-signal and adds clutter.

Additional relationship types are allowed if they clearly contribute to influence mapping.

Additional relationship types are allowed if they clearly contribute to influence mapping.

**Density guidance (Influence-Focused):**
- Aim for a structurally rich relationship graph suitable for influence and power mapping.
- Target approximately **60–120 total relationship rows** when entity richness allows.
- As a heuristic, aim for **at least 5 high-signal relationships per canonical entity**, when available in Wikidata.
- Ensure explicit inclusion (when present) of the following high-signal predicates:
  - `P108` employer (person → organization)
  - `P169` chief executive officer (organization → person)
  - `P39` position held (person → role entity)
  - `P463` member of (person/org → organization)
  - `P127` owned by (organization → organization/person)
  - `P1830` owner of (organization → organization)
- Geographic and citizenship links are useful but should not dominate the relationship set.
- At least **40% of all relationship rows** should consist of leadership, ownership, employment, membership, or governance predicates (e.g., P108, P169, P39, P463, P127, P1830, P112, P749, P355).
- If necessary, expand relationship harvesting depth (while remaining within Wikidata) to meet this influence-focused ratio, provided the statements are directly attached to the selected canonical entities.
- Relationships should substantially outnumber literal biographical facts.

If these high-signal predicates exist for the selected entities, they must be included.

Deduplicate exact duplicate rows and prefer English labels.

---

## Step 3 — Produce CSV Outputs (Required Schemas)

### File 1: `entities.csv`

One row per canonical entity (the selected set).

**Columns (exact):**
```
entity_id (QID, e.g., Q123)
name (English label)
entity_type (one of: person, organization, place, event, other)
aliases (pipe-delimited English aliases; may be empty)
description (English short description; may be empty)
wikidata_url (https://www.wikidata.org/wiki/<QID>)
```

**Requirements:**
- The number of rows must match the number of selected canonical entities.
- `aliases` must not repeat the primary label.
- `aliases` should be populated for all entities where Wikidata provides altLabels.
- Use pipe (`|`) as the internal delimiter within the aliases field.
- Include abbreviations and common short forms when present in Wikidata.
- Avoid leaving `aliases` empty unless no alternative names exist in Wikidata.

---

### File 2: `facts.csv`

One row per (subject, predicate, **true literal**) fact.

**Columns (exact):**
```
fact_id (stable row id; format F0001, F0002, …)
subject_id (QID of one of the selected canonical entities)
subject_label
predicate_pid (e.g., P569)
predicate_label (English property label)
value (literal value as string)
value_type (one of: string, date, number, url, identifier, other)
source (always wikidata)
source_url (https://www.wikidata.org/wiki/<QID> for the subject entity; may optionally include a specific statement URL when available)
retrieved_at (YYYY-MM-DD)
```

**Rules (Strict Literal-Only):**
- Only include facts where `subject_id` is one of the selected canonical entities.
- **Literal-only rule:** `value` must be a true literal (date, number, short free text, URL, identifier). No QIDs, no entity names-as-strings, and no entity-valued properties serialized into text.
- If the Wikidata property is entity-valued (object is a QID), it **must** go to `relationships.csv`, not `facts.csv`.

**Hard guardrail (entity-valued PID set):**
- If `predicate_pid` is in `{P112, P69, P463, P39, P22, P25, P3373}` (and similar entity-valued properties), then the object must be a **QID entity** and the row belongs in `relationships.csv` (never `facts.csv`).
- This includes cases where the agent is tempted to write a person/org name as a string in `facts.csv` — that is disallowed.

- Use `facts.csv` primarily for: dates (ISO), numeric quantities, identifiers, URLs, and short descriptive strings.
- Use `facts.csv` primarily for: dates (ISO), numeric quantities, identifiers, URLs, and short descriptive strings.
- Ensure `predicate_pid` matches the correct `predicate_label` exactly as defined in Wikidata (copy the English label verbatim).
- `source_url` must resolve to a valid Wikidata page corresponding to the subject entity (or a specific statement URL when available).
- Date values must use ISO 8601 format.
  - If Wikidata provides a full date, use `YYYY-MM-DD`.
  - If Wikidata provides only a year, use **year-only** `YYYY` and keep `value_type = date` (treat as a partial date).
  - Do **not** coerce year-only values into `YYYY-01-01` or similar, as that fabricates precision.
- Deduplicate exact duplicate rows.
- Prefer English labels.

---

### File 3: `relationships.csv`

One row per (subject entity, predicate, object entity) relationship.

**Columns (exact):**
```
rel_id (stable row id; format R0001, R0002, …)
subject_id (QID of one of the selected canonical entities)
subject_label
predicate_pid (e.g., P108)
predicate_label
object_id (QID)
object_label
object_entity_type (controlled vocabulary: person | organization | place | event | other | unknown)
source (always wikidata)
source_url (https://www.wikidata.org/wiki/<QID> for the subject entity; may optionally include a specific statement URL when available)
retrieved_at (YYYY-MM-DD)
```

**Rules:**
- Only include relationships where `subject_id` is one of the selected canonical entities.
- `object_id` may be outside the selected set (allowed and encouraged).
- Ensure `predicate_pid` matches the correct `predicate_label` exactly as defined in Wikidata (copy the English label verbatim).
- `object_entity_type` must strictly use this controlled vocabulary:
  - `person`
  - `organization`
  - `place`
  - `event`
  - `other`
  - `unknown`
- **Type normalization rules (strict):**
  - Educational institutions (universities, schools, law schools, research institutes) must be labeled `organization`, not `place`.
  - Corporations, NGOs, foundations, government agencies, and political parties must be labeled `organization`.
  - Use `place` only for geographic entities (cities, regions, countries, physical geographic features).
  - Role/office entities (e.g., "President of X", "Minister of Y") should typically be classified as `other` unless clearly modeled as an organization in Wikidata.
- Do not introduce new category labels.
- Normalize capitalization to lowercase exactly as shown above.
- If the entity type cannot be confidently determined from Wikidata `instance of (P31)`, use `unknown`.
- `source_url` must resolve to a valid Wikidata page corresponding to the subject entity (or a specific statement URL when available).
- Deduplicate exact duplicate rows.
- Prefer English labels.

---

## Step 4 — Quality Constraints & Validation Checklist

- You must **not invent facts**; everything must be attributable to Wikidata.
- If a property is unavailable for an entity, omit it.
- If you are uncertain about a Wikidata match, flag it in the summary.

### Pre-Submission Validation Checklist (Mandatory)
Before returning the final output, verify the following:

1. **PID ↔ Label Consistency (Strict Validation Rule)**
   - **Validation rule:** `predicate_label` must exactly match the *known English label* for `predicate_pid` in Wikidata.
   - Do not infer or paraphrase labels.
   - When generating rows, **look up each PID’s English label** and copy it verbatim.
   - Reject / fix any row where the PID and label disagree.
   - Example checks: P19 = place of birth; P69 = educated at; P569 = date of birth.

1b. **P31 Exclusion Check (Mandatory)**
   - Confirm there are **zero rows** using `predicate_pid = P31` in both `facts.csv` and `relationships.csv`.

2. **Semantic Type Checks**
   - **facts.csv literal-only check:** no entity-valued properties serialized as strings; entity-valued statements appear only in `relationships.csv`.
   - **Entity-valued PID check:** if `predicate_pid` is in `{P112, P69, P463, P39, P22, P25, P3373}` then the row must appear in `relationships.csv` with a QID `object_id` (never in `facts.csv`).
   - `place of birth (P19)` objects are geographic entities.
   - `educated at (P69)` objects are educational institutions and must be classified as `organization` in `object_entity_type`.
   - Universities, schools, and academic institutions must not be labeled as `place`.
   - `country (P17)` and `country of citizenship (P27)` resolve to sovereign states.
   - Geographic locations (cities, countries, regions) are labeled `place`; institutions are labeled `organization`.

3. **Date Normalization (Partial Dates Allowed)**
   - All date fields use ISO format.
   - Full dates use `YYYY-MM-DD`.
   - **Year-only is allowed** as `YYYY` (partial date) and should remain `value_type = date`.
   - Do not convert partial dates to an arbitrary full date (e.g., `YYYY-01-01`).
   - No free-text date strings.

4. **Canonical Set Integrity**
   - The number of rows in `entities.csv` matches the declared canonical entity count in the summary.

5. **Alias Hygiene & Coverage**
   - No alias duplicates.
   - The primary label is not repeated in the `aliases` field.
   - Abbreviations, acronyms, legal-name variants, and common alternate spellings are included when available in Wikidata.
   - Organization entries have been checked against Wikidata `altLabel` and former/legal names to avoid under-population.
   - If an entity has no aliases in Wikidata, this has been explicitly confirmed before leaving the field empty.

6. **Name Standardization**
   - Entity names exactly match the English Wikidata label.
   - No inconsistent spacing or branding variants (e.g., avoid mixing "Mercado Libre" and "MercadoLibre").

7. **Controlled Vocabulary Compliance**
   - `object_entity_type` strictly uses: person | organization | place | event | other | unknown.
   - All values are lowercase.

If any of the above checks fail, correct the data before returning the output.

---

## Step 5 — Deliverables

Return, in this order:

### 1. Short Summary Section
- The selected entities with QIDs + one-line justification each (including justification for the total count)
- Any ambiguous matches and how you resolved them
- Retrieval date used

### 2. CSV Content (in this order)
- `entities.csv`
- `facts.csv`
- `relationships.csv`

Each CSV must be valid comma-separated CSV with a header row.

### CSV Formatting Requirements (Strict)
To ensure the files do not break when imported into spreadsheets or databases:

- Use standard comma (`,`) as the delimiter.
- Wrap **every field in double quotes** ("...") — including IDs and numeric values.
- Escape internal double quotes by doubling them (e.g., `"John ""Johnny"" Smith"`).
- Do not use additional delimiters (no semicolons or tabs).
- Do not insert extra blank lines.
- Ensure UTF-8 encoding.
- Ensure each row has exactly the same number of columns as the header.
- Do not include commentary, markdown formatting, or code fences inside the CSV output — only raw CSV text.
- If a value contains line breaks, replace them with a single space.

These rules are mandatory and apply to all three CSV files.

---

## Notes

- Favor **precision over recall**: it is better to have fewer correct statements than many questionable ones.
- The dataset will enrich a graph built from the PDF narrative, so prioritize properties that clarify:
  - Roles
  - Affiliations
  - Organizational structure
  - Location context

