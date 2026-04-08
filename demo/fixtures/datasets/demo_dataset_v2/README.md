# Demo Fixtures (dataset v2)

This directory is **dataset v2** (`demo_dataset_v2`). It extends the demo with a
second primary document and is used to exercise multi-document ingest and to
verify that pipeline stages are dataset-agnostic.

## Purpose and scope

- **Primary document:** `unstructured/chain_of_issuance.pdf`
- **Supplementary document:** `unstructured/chain_of_issuance_full_text.pdf`
  (full-text variant; not used as the primary ingest source)
- **Entity network:** shares the same Wikidata-backed canonical entity set as v1
  (Endeavor, MercadoLibre, MercadoPago, Globant, Ripio, Xapo, and related
  founders/leaders), but sourced from a different primary PDF
- **Intended use:**
  - Validate that pipeline stages operate correctly on a second document
  - Exercise multi-dataset workflows (running v1 and v2 back-to-back)
  - Verify that `dataset_id` stamping correctly isolates graph writes by dataset

## When to use v2

Use `demo_dataset_v2` when you want to:

- Confirm that a code change does not accidentally hard-code v1 paths
- Test a multi-document or multi-dataset scenario end to end
- Reproduce or isolate a bug that appears only on `chain_of_issuance.pdf`

For routine first-time onboarding and CI validation, prefer `demo_dataset_v1`.

## Running the pipeline against this dataset

```bash
# Using the --dataset flag
python -m demo.run_demo run-all --live --dataset demo_dataset_v2

# Using the environment variable
export FIXTURE_DATASET=demo_dataset_v2
python -m demo.run_demo run-all --live
```

To run both datasets sequentially and compare results:

```bash
# Run v1 first
python -m demo.run_demo run-all --live --dataset demo_dataset_v1

# Then run v2 (dataset_id stamps on graph writes keep the two runs isolated)
python -m demo.run_demo run-all --live --dataset demo_dataset_v2
```

For dataset selection rules and how `--dataset` interacts with `FIXTURE_DATASET`,
see [`demo/fixtures/README.md`](../../README.md) or
[`demo/VALIDATION_RUNBOOK.md`](../../../VALIDATION_RUNBOOK.md) (Section 2a).

## Data provenance

- `unstructured/chain_of_issuance.pdf`: primary demo PDF for v2 pipeline runs.
- `unstructured/chain_of_issuance_full_text.pdf`: full-text variant;
  supplementary, not used as the primary ingest source.
- `structured/entities.csv`: canonical entities for deterministic mention
  resolution (same Wikidata-backed entity set as v1).
- `structured/facts.csv`: scalar facts (dates/URLs/attributes) attached to
  entity subjects.
- `structured/relationships.csv`: graph edges between entities and external
  nodes.
- `structured/claims.csv`: seed claims used by dry-run structured ingest.
- `manifest.json`: dataset contract, provenance inventory, and attribution
  pointers.

## License and attribution

- Demo fixtures are provided for research/demo use in this repository.
- Structured rows are curated from Wikidata references; Wikidata content is
  available under **CC0 1.0**: https://creativecommons.org/publicdomain/zero/1.0/
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

- `structured/claims.csv` is a curated, high-signal fixture for
  retrieval/citation demos and GraphRAG evidence linking.
- Every claim is deterministically auditable via `source_row_id`, which must
  reference exactly one row in either:
  - `structured/relationships.csv` (`rel_id`) for `claim_type=relationship`
  - `structured/facts.csv` (`fact_id`) for `claim_type=fact`
- `subject_id` is always a canonical entity from `entities.csv`.
- Relationship-derived claims are prioritized; selected fact claims cover core
  dates/URLs used in demo Q&A.

## Canonical entity notes

- `entity_id` is the canonical key used by the demo for entity identity.
- For Wikidata-backed rows, canonical IDs are Wikidata QIDs (e.g. `Q6551937`).
- `aliases` is pipe-delimited (`|`) and optional.
- Some relationship objects may reference external QIDs that are not included as
  canonical rows in `entities.csv`; this is expected for demo breadth.

## Golden questions for the demo

Use these to sanity-check retrieval and citation behavior with dataset v2:

1. Which organization is Linda Rottenberg associated with?
2. Who is listed as the founder of Xapo?
3. What positions are recorded for Larry Summers?
4. Which entities in the fixtures link to the Council on Foreign Relations?
5. What source URL supports the claim that Linda Rottenberg is CEO of Endeavor?
