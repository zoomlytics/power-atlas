# Chain of Custody Fixtures (dataset v1)

This directory is the stable dataset root used by `demo/run_demo.py` with default settings (no custom fixture flags).

## Data provenance

- `unstructured/chain_of_custody.pdf`: demo source document used for PDF ingest stages.
- `structured/entities.csv`: canonical entities used for deterministic mention resolution.
- `structured/facts.csv`: scalar facts (dates/URLs/attributes) attached to entity subjects.
- `structured/relationships.csv`: graph edges between entities and external nodes.
- `structured/claims.csv`: seed claims used by dry-run structured ingest.
- `manifest.json`: dataset contract, provenance inventory, and attribution pointers.

## License and attribution

- Demo fixtures are provided for research/demo use in this repository.
- Structured rows are curated from Wikidata references; Wikidata content is available under **CC0 1.0**: https://creativecommons.org/publicdomain/zero/1.0/
- Keep source URLs and attribution fields intact when reusing these fixtures.

## CSV schemas

- `structured/entities.csv`  
  `entity_id,name,entity_type,aliases,description,wikidata_url`
- `structured/facts.csv`  
  `fact_id,subject_id,subject_label,predicate_pid,predicate_label,value,value_type,source,source_url,retrieved_at`
- `structured/relationships.csv`  
  `rel_id,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,object_entity_type,source,source_url,retrieved_at`
- `structured/claims.csv`  
  `claim_id,claim_type,subject_id,subject_label,predicate_pid,predicate_label,object_id,object_label,value,value_type,claim_text,confidence,source,source_url,retrieved_at,source_row_id`

## Claims curation contract

- `structured/claims.csv` is a curated, high-signal fixture for retrieval/citation demos and GraphRAG evidence linking.
- Every claim is deterministically auditable via `source_row_id`, which must reference exactly one row in either:
  - `structured/relationships.csv` (`rel_id`) for `claim_type=relationship`
  - `structured/facts.csv` (`fact_id`) for `claim_type=fact`
- `subject_id` is always a canonical entity from `entities.csv`.
- Relationship-derived claims are prioritized; selected fact claims cover core dates/URLs used in demo Q&A.

### Inclusion criteria

- Include relationship claims that are broadly useful for demo questions (organization ties, founders, roles, memberships).
- Include key fact claims with high retrieval value (`P571` inception, `P856` official website, selected life-event dates).
- Exclude low-signal, duplicated, or ungrounded claims.
- Keep claim text human-readable and directly aligned to predicate semantics.

### Confidence and ambiguity handling

- Confidence is assigned per claim for retrieval ranking (typically `0.93–0.99` for straightforward rows).
- Claims with potentially time-bounded or multi-value relationships (for example multiple `P26` spouse rows) are retained for auditability but assigned lower confidence.
- When multiple sourced rows exist for the same predicate, each claim remains separately linked to its own `source_row_id` rather than being merged.

## Canonical entity notes

- `entity_id` is the canonical key used by the demo for entity identity.
- For Wikidata-backed rows, canonical IDs are Wikidata QIDs (for example `Q6551937`).
- `aliases` is pipe-delimited (`|`) and optional.
- Some relationship objects may reference external QIDs that are not included as canonical rows in `entities.csv`; this is expected for demo breadth.

## Golden questions for the demo

Use these to sanity-check retrieval and citation behavior:

1. Which organization is Linda Rottenberg associated with?
2. Who is listed as the founder of Xapo?
3. What positions are recorded for Larry Summers?
4. Which entities in the fixtures link to the Council on Foreign Relations?
5. What source URL supports the claim that Linda Rottenberg is CEO of Endeavor?
