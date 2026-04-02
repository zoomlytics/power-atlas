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
| `canonical_empty_cluster_populated_count` | 2 |
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
  Classification: `canonical_empty_cluster_populated=True`,
  `fragmentation_type_hints=["entity_type_case_split", "catalog_absent_or_alignment_gap"]`.
- **`mercadolibre_fragmentation`** — Same queries as `mercadolibre_single`;
  `canonical_empty_cluster_populated=True` with the same hints.  This case
  contributes to `canonical_empty_cluster_populated_count=2` in the baseline.
- **`endeavor_single` / `endeavor_composite`** — Fragmentation detected:
  `organization` (lowercase) and `Organization` clusters exist in parallel;
  `cluster_name_cluster_count=4` (two name variants × two case variants).
  `canonical_empty_cluster_populated=False` (canonical coverage is present);
  `fragmentation_type_hints=["entity_type_case_split"]`.
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

## Relationship to PR #433 — normalization hardening

**This baseline is a pre-PR-#433 reference point.**

PR **#433** hardened shared `entity_type` normalization in
`demo/stages/entity_resolution.py` and the companion Cypher helpers by:

- mapping lowercase casing variants (`organization → Organization`,
  `person → Person`, etc.) via `_normalize_entity_type` /
  `_ENTITY_TYPE_SYNONYMS`;
- stripping leading/trailing whitespace before normalization;
- keeping `build_entity_type_cypher_case` Cypher semantics in sync with the
  Python normalization policy.

Because this run was executed **before** those changes landed,
`ResolvedEntityCluster.entity_type` values were persisted with mixed casing
(e.g., `"organization"` alongside `"Organization"`), producing separate
clusters for the same conceptual entity type.  Those separate clusters are
what drive the `entity_type_case_split` fragmentation signals visible in the
Notable conditions section above.  Note that raw `EntityMention.entity_type`
values sourced from the extraction stage may still be mixed-case even after
#433; what #433 fixes is normalization at cluster-assignment and Cypher query
time, so that mixed-case mentions no longer fragment into separate clusters
or produce split hints.

### What this means for interpreting count movement

| Metric | Pre-#433 baseline value | Expected direction after #433 |
|--------|------------------------|-------------------------------|
| `fragmentation_detected_count` | 4 | May decrease (case-split clusters collapse) |
| `canonical_empty_cluster_populated_count` | 2 | Expected to remain unchanged from case normalization alone; only changes if canonical traversal starts matching MercadoLibre for non-normalization reasons (e.g., catalog/name-filter/alignment changes) |
| `fragmentation_type_hints` containing `"entity_type_case_split"` | Present for `mercadolibre_single`, `mercadolibre_fragmentation`, `endeavor_single`, `endeavor_composite` | Expected to clear for cases where the only fragmentation was a case variant |

A reduction in any of these figures in a post-#433 run is **expected
normalization fallout, not a regression**.  An increase would indicate a
new fragmentation condition and warrants review.

### Refreshing this baseline

If you re-run the benchmark after #433 merges and the figures change
materially, commit the new artifact under a new run-ID directory and update:

- `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md` — baseline
  summary table and per-case expected values;
- `pipelines/query/README.md` — baseline summary figures.

Until a post-#433 baseline is committed, treat this artifact as the
**authoritative regression reference** while acknowledging that the
`entity_type_case_split` signals it contains reflect a now-addressed
normalization gap.

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
