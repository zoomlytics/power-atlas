# Chain of Custody Fixtures (dataset v1)

This directory is the stable dataset root used by `demo/chain_of_custody/run_demo.py` with default settings (no custom fixture flags).

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
  `claim_id,claim_text,confidence,source_uri`

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
