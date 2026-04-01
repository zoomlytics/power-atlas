# Retrieval Benchmark Baseline — Provenance

## Run identification

| Field | Value |
|-------|-------|
| `run_id` | `unstructured_ingest-20260401T184420771950Z-ee78cf8c` |
| `alignment_version` | `v1.0` |
| `generated_at` | `2026-04-01T20:38:01Z` |
| Environment | Local post-hybrid run generated from scratch |

## Why this run is considered representative

- Captures a real semantic drift / fragmentation condition rather than only
  happy-path behaviour.
- Source text is the `chain_of_custody.pdf` fixture included in
  `demo/fixtures/unstructured/`, so the run is fully reproducible from the
  committed fixture set.
- Covers all five benchmark case types across nine cases: single_entity,
  fragmented_entity, composite_claim, pairwise_entity, and
  canonical_vs_cluster comparisons.

## Redaction

No redaction was applied.  All `claim_id` values are `file://` URIs that may
include machine-specific absolute paths (for example, a local filesystem
path) but contain no external or sensitive data and are treated as opaque
identifiers; all content is derived from the committed `chain_of_custody.pdf`
fixture.  The committed artifact normalizes these paths to repo-relative
`file:///demo/fixtures/...` URIs.

## Benchmark summary

| Metric | Value |
|--------|-------|
| `total_cases` | 9 |
| `single_and_comparison_cases` | 8 |
| `pairwise_cases` | 1 |
| `fragmentation_detected_count` | 4 |
| `entities_with_claims_canonical` | 6 |
| `entities_with_claims_cluster` | 8 |
| `total_canonical_claims` | 34 |
| `total_cluster_claims` | 54 |
| `total_pairwise_claims` | 0 |

## Notable conditions captured

- **`mercadolibre_single`** — `canonical_rows` is empty while `cluster_rows`
  is populated.  MercadoLibre is not present in the structured catalog for this
  run, so the canonical path returns zero rows.  Fragmentation is still
  detected (`entity_type` split between `Organization` and `organization`).
- **`endeavor_single` / `endeavor_composite`** — Fragmentation detected:
  `organization` (lowercase) and `Organization` clusters exist in parallel;
  `cluster_name_cluster_count=4` (two name variants × two case variants).
- **`linda_rottenberg_single`** — One dark mention (`claim_id=null`) in
  `lower_layer_rows` is present; all other mentions are fully participatory.
- **`amazon_ebay_pairwise`** — Zero pairwise rows returned; acceptable under
  the benchmark's expected-shape contract.
- **Neo4j deprecation warnings** — The benchmark emitted warnings for use of
  `id()` in Cypher but completed successfully.

## How to reproduce

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>

python pipelines/query/retrieval_benchmark.py \
    --run-id unstructured_ingest-20260401T184420771950Z-ee78cf8c \
    --alignment-version v1.0
```

Output will be written to
`pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/retrieval_benchmark.json`.

## Relationship to the illustrative example artifact

The file at `pipelines/query/retrieval_benchmark_example_output.json` is a
**synthetic illustrative example** — useful for artifact shape stability,
documentation, and review training — but it is **not** derived from a real
pipeline run.

This artifact (`retrieval_benchmark.json` in this directory) is the
**real reviewed baseline** for regression comparison.  Future benchmark runs
should be compared against this file's `benchmark_summary` figures and
per-case counts using the thresholds in
`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`.
