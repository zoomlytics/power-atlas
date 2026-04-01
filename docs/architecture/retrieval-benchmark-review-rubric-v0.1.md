# Retrieval Benchmark Review Rubric — Power Atlas v0.1

This rubric guides reviewers who compare a new `retrieval_benchmark.json` artifact
against the committed baseline.  It covers:

- where the baseline artifact lives and how to produce a new one
- what each benchmark case exercises and what "healthy" looks like
- per-signal red / yellow / green movement thresholds
- instructions for updating the baseline when a change is intentional

---

## Baseline artifact

The representative baseline artifact from a post-hybrid run is committed at:

```
pipelines/query/retrieval_benchmark_example_output.json
```

**Run coordinates embedded in the baseline:**

| Field | Value |
|-------|-------|
| `run_id` | `unstructured_ingest-20240601T120000000000Z-abcd1234` |
| `alignment_version` | `v1.0` |
| `generated_at` | `2024-06-01T12:00:00Z` |

**Baseline summary figures:**

| Metric | Baseline value |
|--------|---------------|
| `total_cases` | 9 |
| `single_and_comparison_cases` | 8 |
| `pairwise_cases` | 1 |
| `fragmentation_detected_count` | 2 |
| `entities_with_claims_canonical` | 8 |
| `entities_with_claims_cluster` | 8 |
| `total_canonical_claims` | 38 |
| `total_cluster_claims` | 40 |
| `total_pairwise_claims` | 0 |

The baseline was generated from representative synthetic post-hybrid data that
reflects the graph topology produced by a complete pipeline run (extraction →
clustering → alignment → participation).

---

## How to produce a new benchmark artifact

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>

# Scoped to a specific run (recommended)
python pipelines/query/retrieval_benchmark.py \
    --run-id <run-id> \
    --alignment-version v1.0

# Unscoped (aggregates across all runs)
python pipelines/query/retrieval_benchmark.py
```

Output is written to:

- **Scoped:** `pipelines/runs/<run-id>/retrieval_benchmark/retrieval_benchmark.json`
- **Unscoped:** `pipelines/runs/retrieval_benchmark/retrieval_benchmark.json`

---

## Global summary signals

Compare the `benchmark_summary` block first.  These aggregate numbers tell you
whether something broad changed before you investigate individual cases.

### `fragmentation_detected_count`

The number of cases where `cluster_name_cluster_count > canonical_cluster_count`.

| Movement | Interpretation |
|----------|---------------|
| 🟢 **Same as baseline (2)** | Fragmentation is stable; canonical deduplication is working as before. |
| 🟡 **Increased (e.g. 3–4)** | New entity-type or spelling splits appeared.  Inspect `fragmentation_check_rows` for the new cases — could be intentional data growth or a new alignment gap. |
| 🔴 **Decreased below baseline (0–1)** | Fragmentation no longer detected on previously-fragmented entities.  Either the alignment improved (good) or the entity is missing from the graph entirely (bad).  Verify `canonical_rows` is non-empty. |

### `entities_with_claims_canonical`

How many non-pairwise cases (single-entity and comparison) returned at least one claim via the canonical path.
Pairwise cases are excluded because they use a different query path and are tracked separately under `total_pairwise_claims`.

| Movement | Interpretation |
|----------|---------------|
| 🟢 **8 (all non-pairwise cases)** | Every single-entity and comparison case is reachable through the canonical chain. |
| 🟡 **7** | One non-pairwise case lost canonical coverage.  Run the affected single-entity or comparison case manually and inspect `lower_layer_rows` for the dark path. |
| 🔴 **≤ 6** | Multiple non-pairwise cases dropped off.  Likely an alignment stage failure or a broken `ALIGNED_WITH` edge set. |

### `total_canonical_claims` vs `total_cluster_claims`

Typically, for non-fragmented entities, canonical should be ≥ cluster: canonical traversal should
see at least what cluster-name traversal sees, and may pick up additional claims via alignment.
However, when `fragmentation_detected_count > 0`, the global total may legitimately show
`total_canonical_claims < total_cluster_claims` because cluster-name traversal can pick up claims
attached to spurious fragment clusters that are not aligned to the canonical entity.  In that
scenario, check per-case `canonical_claim_count` vs `cluster_claim_count` alongside
`fragmentation_detected` to distinguish healthy fragmentation effects from true regressions.

| Movement | Interpretation |
|----------|---------------|
| 🟢 **canonical ≥ cluster, delta within baseline range** | Normal; matches the baseline gap between canonical and cluster-name traversal (including any known fragmentation in the baseline). |
| 🟡 **canonical < cluster with a materially larger gap than baseline and `fragmentation_detected_count` not increased** | Cluster-name traversal is returning more claims than the canonical path beyond what the baseline already shows.  This is unexpected — investigate for new fragmentation or spuriously-named clusters. |
| 🔴 **canonical drops sharply (> 20% additional decrease vs baseline)** | Participation coverage may have regressed materially relative to baseline.  Check `participation_metrics.json` and `HAS_PARTICIPANT` edge counts. |

### `total_pairwise_claims`

The baseline records **0** pairwise claims for Amazon ↔ eBay.  This is normal for
a dataset that does not contain cross-entity subject/object claims.

| Movement | Interpretation |
|----------|---------------|
| 🟢 **0** | No cross-entity claims found — consistent with the baseline dataset scope. |
| 🟡 **1–5** | Some cross-entity claims appear.  Verify they are genuinely connecting the two entities and not a false positive from overly broad `CONTAINS` filtering. |
| 🔴 **> 20** | Likely a query correctness issue; the pairwise filter may have become too permissive. |

---

## Per-case review guide

### Case `mercadolibre_single` (single_entity)

**Exercises:** canonical → cluster → mention → claim for MercadoLibre, an org that
may appear under multiple surface forms and clusters.

**Baseline figures:** canonical_claim_count=4, cluster_claim_count=5,
canonical_cluster_count=2, cluster_name_cluster_count=3, fragmentation_detected=**True**

**Review notes:**

- `fragmentation_detected=True` is **expected** here.  MercadoLibre has both an
  Organization and a Person cluster in the baseline graph.  The canonical path still
  works correctly; it routes through a single `CanonicalEntity` node and deduplicates.
- Expect `lower_layer_rows` to contain one dark mention (`claim_id=null`) for
  `mercadolibre.com`.  An increase in dark mentions signals a participation gap.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 4 ± 2 | +/– 3–10 | 0 or > 3× baseline |
| `canonical_cluster_count` | 2 | 1 or 3 | 0 |
| `fragmentation_detected` | True | — | False **and** cluster_claim_count = 0 |
| dark mentions in `lower_layer_rows` | 0–1 | 2–3 | > 3 |

---

### Case `xapo_single` (single_entity)

**Exercises:** canonical traversal for Xapo — a fintech entity that may appear
under abbreviated and full-name surface forms.

**Baseline figures:** canonical_claim_count=5, cluster_claim_count=5,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- Xapo appears under "Xapo" and "Xapo Bank" mentions, both within the same cluster.
  If a new run produces `canonical_cluster_count=2`, verify the ALIGNED_WITH edges
  still point to a single CanonicalEntity node.
- `fragmentation_detected=False` is the healthy state.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 5 ± 2 | +/– 3–8 | 0 |
| `cluster_name_cluster_count` | 1 | 2 | ≥ 3 |
| `fragmentation_detected` | False | — | True |

---

### Case `endeavor_single` (single_entity)

**Exercises:** canonical traversal for Endeavor — a well-known organisation
with alias mentions ("Endeavor Global").

**Baseline figures:** canonical_claim_count=6, cluster_claim_count=6,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- All claims route through a single cluster.  A second cluster appearing would
  indicate a new "Endeavor" alias cluster was created outside the aligned canonical.
- Monitor for co-occurrence claims (e.g. "Endeavor and MercadoLibre co-hosted…")
  to verify list-split edges are generated (see `endeavor_composite`).

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 6 ± 3 | +/– 4–10 | 0 |
| `fragmentation_detected` | False | — | True |

---

### Case `linda_rottenberg_single` (single_entity)

**Exercises:** Person-type entity canonical traversal.  Verifies the Person path
is symmetric with Organisation cases.

**Baseline figures:** canonical_claim_count=4, cluster_claim_count=4,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- All `cluster_type` values in `cluster_rows` should be `"Person"`.  If `"Organization"`
  appears, an entity_type normalisation regression occurred.
- Fewer claims than orgs is expected for a named individual in this dataset.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 4 ± 2 | +/– 3–6 | 0 |
| `cluster_type` values | "Person" only | "Person" + 1 other | "Organization" only |
| `fragmentation_detected` | False | — | True |

---

### Case `amazon_ebay_pairwise` (pairwise_entity)

**Exercises:** bidirectional canonical claim lookup across two distinct entities
(Amazon and eBay).

**Baseline figures:** pairwise_claim_count=0

**Review notes:**

- Zero pairwise claims is the baseline for this dataset.  A change to **non-zero**
  means either new cross-entity claims were extracted or the query filter widened.
  Inspect `subject_canonical` and `object_canonical` columns to verify the matches
  are genuine (not false positives from the `toLower CONTAINS` filter).
- The key health check here is that the query completes without error even when
  zero rows are returned — verifying the canonical chain is traversable for both
  entities.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `pairwise_claim_count` | 0 | 1–5 (verify) | > 20 (filter bug?) |
| Query returns without error | Yes | — | No |

---

### Case `mercadolibre_fragmentation` (fragmented_entity)

**Exercises:** explicit fragmentation check for MercadoLibre — the canonical
fragmentation regression case.

**Baseline figures:** canonical_claim_count=4, cluster_claim_count=5,
canonical_cluster_count=2, cluster_name_cluster_count=3, fragmentation_detected=**True**

**Review notes:**

- This case runs the same queries as `mercadolibre_single`; it is kept as a
  separate named case so that fragmentation detection is reported explicitly in
  the `benchmark_summary.fragmentation_detected_count` figure.
- `fragmentation_detected=True` here means the tool is correctly detecting the
  known entity-type split.  A change to `False` means either the fragmentation was
  resolved (investigate whether the Person cluster was merged/removed) or an entity
  disappeared from the graph.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `fragmentation_detected` | True | — | False (verify canonical coverage) |
| `cluster_name_cluster_count` | 3 | 2 or 4 | 0 |
| `fragmentation_check_rows` entity_type values | Organization + Person | Organization only | empty |

---

### Case `endeavor_composite` (composite_claim)

**Exercises:** list-split match path — claims where a subject or object slot is
a compound expression joined by "and", "or", "/", etc.

**Baseline figures:** canonical_claim_count=6, cluster_claim_count=6,
fragmentation_detected=**False**; `match_method="list_split"` present in
`canonical_rows` for the co-hosted claim.

**Review notes:**

- The primary health signal is `match_method="list_split"` appearing in at least one
  row of `canonical_rows`.  If it disappears, the list-split participation path may
  have regressed (check `participation_metrics.json` → `list_split_suppressed`).
- A change from `list_split` to `raw_exact` is informative if the source text was
  edited to use a non-compound form; not necessarily a bug.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `match_method="list_split"` present | Yes | Only in `cluster_rows`, not `canonical_rows` | Not present at all |
| `canonical_claim_count` | 6 ± 3 | +/– 4–8 | 0 |

---

### Case `xapo_canonical_vs_cluster` (canonical_vs_cluster)

**Exercises:** side-by-side claim-count comparison for Xapo — the primary
deduplication regression metric.

**Baseline figures:** canonical_claim_count=5, cluster_claim_count=5,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- Equal claim counts across both paths is the healthy baseline state (no
  fragmentation, no alignment gap).
- `canonical_claim_count < cluster_claim_count` indicates the canonical path is
  missing some claims — investigate `ALIGNED_WITH` coverage for Xapo.
- `canonical_claim_count > cluster_claim_count` can occur when canonical traversal
  picks up additional aligned claims that the cluster-name query misses; treat this
  as a potential alignment improvement, but verify the extra canonical-only claims
  are correct and expected for the current alignment version (and not caused by a
  `cluster.canonical_name` mismatch or stale alignment).

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count == cluster_claim_count` | Yes | Differ by ≤ 2 | Differ by > 5 |
| `fragmentation_detected` | False | — | True |
| Both counts > 0 | Yes | — | Either count = 0 |

---

### Case `linda_rottenberg_canonical_vs_cluster` (canonical_vs_cluster)

**Exercises:** side-by-side comparison for Linda Rottenberg (Person type) — verifies
that the Person entity path benefits from canonical deduplication symmetrically.

**Baseline figures:** canonical_claim_count=4, cluster_claim_count=4,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- Same interpretation as `xapo_canonical_vs_cluster` but for a Person entity.
- If `cluster_type` values in `cluster_rows` include `"Organization"` a Person/Org
  entity_type split occurred and needs investigation.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count == cluster_claim_count` | Yes | Differ by ≤ 2 | Differ by > 5 |
| `fragmentation_detected` | False | — | True |
| `cluster_type` all "Person" | Yes | Mixed | "Organization" only |

---

## Lower-layer inspection guide

Every non-pairwise case includes `lower_layer_rows` from the full
`canonical → cluster → mention → claim` chain.  These rows expose structural
problems that the aggregate counts may mask.

### Dark mentions (`claim_id = null`)

A `null` `claim_id` in `lower_layer_rows` means an `EntityMention` exists in the
graph but has no `HAS_PARTICIPANT` edge.

| Count | Interpretation |
|-------|---------------|
| 0–1 dark mentions | Normal — typical of a healthy post-hybrid run. |
| 2–3 dark mentions | Investigate the `participation_metrics.json` for this run.  May be a new mention that wasn't matched. |
| > 3 dark mentions | Participation coverage gap.  Check `claim_participation` stage logs and `unmatched_slots` in `participation_metrics.json`. |

### `cluster_type` inconsistency

If `cluster_type` values within a single case are mixed (e.g., both `"Organization"`
and `"Person"`), a cluster-level entity_type split exists.  The canonical path handles
this via the `CanonicalEntity` node, but the cluster layer is fragmented.

---

## Workflow for comparing a new run to the baseline

1. **Run the benchmark** for the new run:
   ```bash
   python pipelines/query/retrieval_benchmark.py \
       --run-id <new-run-id> \
       --alignment-version <version>
   ```

2. **Compare `benchmark_summary`** blocks side-by-side.  Any change warrants
   inspection.

3. **Check per-case counts** using the thresholds in this rubric.  Focus first on
   `fragmentation_detected_count` and `entities_with_claims_canonical`.

4. **Inspect `lower_layer_rows`** for any case where counts changed to count dark
   mentions and verify `cluster_type` homogeneity.

5. **Check `match_method` distribution** in `canonical_rows` for the
   `endeavor_composite` case to confirm list-split coverage.

6. **Triage movement:**
   - 🟢 Green — no action required; document in your PR if the counts changed due
     to intentional data growth.
   - 🟡 Yellow — investigate and explain in your PR.  If intentional, update the
     baseline (see below).
   - 🔴 Red — fix before merging.  Open a separate issue if the root cause is
     outside the scope of the current PR.

---

## Updating the baseline

When a change is **intentional** (e.g. data source expanded, alignment improved,
new entities added to the structured catalog), update the baseline artifact as part
of your PR:

1. Run the benchmark against the new representative run.
2. Copy the new artifact to `pipelines/query/retrieval_benchmark_example_output.json`.
3. Update the **Baseline summary figures** table in this rubric to reflect the new
   expected values.
4. Add a brief note in your PR description explaining what changed and why.

---

## References

- Baseline artifact: [`pipelines/query/retrieval_benchmark_example_output.json`](../../pipelines/query/retrieval_benchmark_example_output.json)
- Benchmark stage: [`demo/stages/retrieval_benchmark.py`](../../demo/stages/retrieval_benchmark.py)
- CLI runner: [`pipelines/query/retrieval_benchmark.py`](../../pipelines/query/retrieval_benchmark.py)
- Query workbook section 14: [`pipelines/query/README.md`](../../pipelines/query/README.md#14-post-hybrid-retrieval-benchmark)
- Graph health diagnostics: [`pipelines/query/graph_health_diagnostics.py`](../../pipelines/query/graph_health_diagnostics.py)
- Retrieval semantics: [`docs/architecture/retrieval-semantics-v0.1.md`](retrieval-semantics-v0.1.md)
