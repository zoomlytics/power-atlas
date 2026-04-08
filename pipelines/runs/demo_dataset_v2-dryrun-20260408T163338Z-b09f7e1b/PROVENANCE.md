# Dataset v2 — End-to-End Pipeline Dry Run — Provenance

## Run identification

| Field | Value |
|-------|-------|
| `run_id` (batch) | `batch-20260408T163338711870Z-d7eea62f` |
| `unstructured_ingest_run_id` | `unstructured_ingest-20260408T163338705752Z-b09f7e1b` |
| `structured_ingest_run_id` | `structured_ingest-20260408T163338705724Z-83b4973b` |
| `dataset_id` | `demo_dataset_v2` |
| `run_mode` | `dry_run` (no live Neo4j or OpenAI calls) |
| `generated_at` | `2026-04-08T16:33:38Z` |
| Environment | CI-equivalent: Python 3.x, no external services |

## Command used

```bash
python -m demo.run_demo ingest --dry-run --dataset demo_dataset_v2
```

For a live run (requires Neo4j and OpenAI), use:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>
export OPENAI_API_KEY=<your-openai-key>

python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

See [`demo/VALIDATION_RUNBOOK.md`](../../../demo/VALIDATION_RUNBOOK.md) for the
complete step-by-step validation guide.

## Purpose

This is the first committed end-to-end pipeline recording for `demo_dataset_v2`.
It confirms that:

- the dataset fixture is correctly wired to the orchestrator
- structured CSV fixtures pass lint and validation without errors
- all pipeline stages are exercised (structured ingest, PDF ingest, extraction,
  entity resolution, retrieval/Q&A) against the v2 fixture set
- dry-run mode produces a complete, reproducible manifest

A live run (with Neo4j + OpenAI) will produce non-zero counts for PDF chunks,
extracted claims, entity mentions, clusters, and aligned entities.  Follow-up
issue: schedule a live run and commit the resulting artifact (see
[Failures and follow-up items](#failures-and-follow-up-items) below).

## Stage outcomes

### Structured ingest — ✅ PASS

| Metric | Value |
|--------|-------|
| `entities` | 12 |
| `facts` | 13 |
| `relationships` | 20 |
| `claims` | 23 |
| `lint_issue_count` | 0 |
| `validation_warning_count` | 0 |
| `lint_status` | `ok` |
| `status` | `dry_run` |

All four structured CSVs (`entities.csv`, `facts.csv`, `relationships.csv`,
`claims.csv`) passed lint and deduplication without dropping any rows.

### PDF ingest — ✅ PASS (fixture verified)

| Metric | Value |
|--------|-------|
| `source_uri` | `file:///demo/fixtures/datasets/demo_dataset_v2/unstructured/chain_of_issuance.pdf` |
| `pdf_fingerprint_sha256` | `3b8dd64fb276d6746615a6f51ac0b79d71e318e40625fde45b01054bea45867c` |
| `pipeline_config` | `demo/config/pdf_simple_kg_pipeline.yaml` |
| `embedding_model` | `text-embedding-3-small` |
| `vendor_pattern` | `SimpleKGPipeline + OpenAIEmbeddings + PageAwareFixedSizeSplitter` |
| `status` | `dry_run` (Neo4j writes skipped) |
| `chunks` | 0 (dry run; no live embedding/ingest) |

The PDF source is correctly resolved to the v2 fixture and the fingerprint is
stable.  A live run will produce non-zero `chunks`, `documents`, and `pages`.

### Claim extraction — ⚠️ DRY RUN ONLY

| Metric | Value |
|--------|-------|
| `status` | `dry_run` |
| `extracted_claim_count` | 0 (dry run; LLM skipped) |
| `entity_mention_count` | 0 |
| `warnings` | `["claim extraction skipped in dry_run mode"]` |

Extraction is skipped in dry-run mode.  In a live run, this stage calls the
LLM extractor against each PDF chunk and writes `ExtractedClaim` and
`EntityMention` nodes with `HAS_PARTICIPANT` edges to Neo4j.

### Claim participation — ⚠️ DRY RUN ONLY

| Metric | Value |
|--------|-------|
| `status` | `dry_run` |
| `edges_written` | 0 |
| `warnings` | `["claim participation skipped in dry_run mode"]` |

### Entity resolution (unstructured-only) — ⚠️ DRY RUN ONLY

| Metric | Value |
|--------|-------|
| `resolution_mode` | `unstructured_only` |
| `status` | `dry_run` |
| `clusters_created` | 0 (dry run; Neo4j skipped) |
| `mentions_total` | 0 |

### Entity resolution (hybrid) — ⚠️ DRY RUN ONLY

| Metric | Value |
|--------|-------|
| `resolution_mode` | `hybrid` |
| `status` | `dry_run` |
| `aligned_clusters` | 0 (dry run; Neo4j skipped) |
| `alignment_version` | `v1.0` |
| `cluster_version` | `v1.3` |
| `resolver_version` | `v1.2` |

### Retrieval and Q&A — ⚠️ DRY RUN ONLY

| Metric | Value |
|--------|-------|
| `status` | `dry_run` |
| `retriever_type` | `VectorCypherRetriever` |
| `qa_prompt_version` | `qa_v3` |
| `retrieval_query_contract` | present and stable |
| `source_uri` | `file:///demo/fixtures/datasets/demo_dataset_v2/unstructured/chain_of_issuance.pdf` |

The retrieval query contract and citation format are correctly wired to the v2
source URI.  Live answers require a populated Neo4j vector index.

## Redaction

No redaction was applied.  All `source_uri` values are repo-relative
`file:///demo/fixtures/...` URIs containing no external or sensitive data.
Machine-specific absolute paths were normalized to repo-relative paths before
committing.

## Failures and follow-up items

| Stage | Condition | Follow-up |
|-------|-----------|-----------|
| PDF ingest | `chunks=0` (dry run; no live embedding) | Schedule a live run with Neo4j + OpenAI to capture real chunk counts |
| Claim extraction | `extracted_claim_count=0` (dry run; LLM skipped) | Live run required to validate extractor behavior on `chain_of_issuance.pdf` |
| Entity resolution | `clusters_created=0` (dry run; Neo4j skipped) | Live run required to validate clustering against v2 entity network |
| Retrieval/Q&A | `evidence_level=no_answer` (dry run; no vector index) | Live run required to validate golden questions from dataset v2 README |

None of these are structural failures — they are expected dry-run behavior.
A follow-up live-run recording should be committed once an environment with
Neo4j and OpenAI credentials is available.

## Relationship to dataset v1 baseline

The existing committed live run
`unstructured_ingest-20260401T184420771950Z-ee78cf8c` is a v1 run
(`chain_of_custody.pdf`, `demo_dataset_v1`).  This artifact is the first
committed run for v2 (`chain_of_issuance.pdf`, `demo_dataset_v2`).

The two datasets are designed to be run independently and compared:

```bash
# Run v1
python -m demo.run_demo ingest --live --dataset demo_dataset_v1

# Run v2
python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

`dataset_id` stamping on all graph writes keeps v1 and v2 data isolated in
the same Neo4j instance.

## How to reproduce

```bash
# Dry run (no credentials required)
python -m demo.run_demo ingest --dry-run --dataset demo_dataset_v2

# Live run (requires Neo4j + OpenAI)
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>
export OPENAI_API_KEY=<your-openai-key>

python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

The dry-run manifest is written to `demo/artifacts/manifest.json`.  The
normalized committed version is `run_manifest.json` in this directory.
