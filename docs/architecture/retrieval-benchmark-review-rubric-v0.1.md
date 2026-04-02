# Retrieval Benchmark Review Rubric — Power Atlas v0.1

This rubric guides reviewers who compare a new `retrieval_benchmark.json` artifact
against the committed baseline.  It covers:

- where the baseline artifact lives and how to produce a new one
- what each benchmark case exercises and what "healthy" looks like
- per-signal red / yellow / green movement thresholds
- instructions for updating the baseline when a change is intentional

---

## Baseline artifact

### Real reviewed baseline (primary regression reference)

The real reviewed baseline artifact — derived from an actual post-hybrid run —
is committed at:

```
pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/retrieval_benchmark.json
```

See the accompanying provenance document at:

```
pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/PROVENANCE.md
```

> **⚠️ Pre-PR-#433 reference point.**  This baseline was generated *before*
> PR-#433 hardened `entity_type` normalization (lowercase-variant mapping,
> whitespace stripping, Cypher/Python policy sync).  The `entity_type_case_split`
> fragmentation signals present in this artifact reflect a now-addressed
> normalization gap.  A reduction in `fragmentation_detected_count` or the
> clearing of `entity_type_case_split` hints in a post-PR-#433 run is **expected
> normalization fallout, not a regression**.  When reviewing later movement
> tables in this rubric, do **not** treat a lower `fragmentation_detected_count`
> as suspicious if the decrease is explained by this PR-#433 normalization
> change and the accompanying disappearance of `entity_type_case_split` hints.
> See `PROVENANCE.md` § *Relationship to PR #433 — normalization hardening* for details.

**Run coordinates:**

| Field | Value |
|-------|-------|
| `run_id` | `unstructured_ingest-20260401T184420771950Z-ee78cf8c` |
| `alignment_version` | `v1.0` |
| `generated_at` | `2026-04-01T20:38:01Z` |
| `Normalization baseline` | **pre-PR-#433** (entity_type case-split present) |

**Baseline summary figures:**

| Metric | Baseline value |
|--------|---------------|
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

**Notable baseline conditions (see PROVENANCE.md for full details):**

- `mercadolibre_single` — canonical path returns zero rows because MercadoLibre
  is absent from the structured catalog for this run; fragmentation detected via
  `Organization` / `organization` entity-type split (**pre-PR-#433 case-split
  condition**); `canonical_empty_cluster_populated=True`,
  `fragmentation_type_hints=["entity_type_case_split", "catalog_absent_or_alignment_gap"]`.
- `endeavor_single` / `endeavor_composite` — fragmentation detected;
  `cluster_name_cluster_count=4` (two name variants × two entity-type case variants,
  **pre-PR-#433 case-split condition**);
  `canonical_empty_cluster_populated=False` (canonical coverage is present).
- `linda_rottenberg_single` — one dark mention (`claim_id=null`) present in
  `lower_layer_rows`.
- `amazon_ebay_pairwise` — zero pairwise rows; acceptable under expected-shape
  contract.

### Illustrative example artifact (schema reference only)

A synthetic illustrative example is also committed at:

```
pipelines/query/retrieval_benchmark_example_output.json
```

This artifact is **not** derived from a real pipeline run.  It is useful for:

- artifact shape / schema stability checking
- documentation and review training
- demonstrating interpretation conventions

Use the **real reviewed baseline** above for regression comparison.  Do not
use the illustrative example as a regression reference.

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
| 🟢 **Same as baseline (4)** | Fragmentation is stable; canonical deduplication is working as before. |
| 🟡 **Increased (e.g. 5–6)** | New entity-type or spelling splits appeared.  Inspect `fragmentation_check_rows` for the new cases — could be intentional data growth or a new alignment gap. |
| 🔴 **Decreased below baseline (0–3)** | Fragmentation no longer detected on previously-fragmented entities.  Either the alignment improved (good) or the entity is missing from the graph entirely (bad).  For entities that should have canonical coverage, verify `canonical_rows` is non-empty; for known empty-canonical baseline cases (e.g., MercadoLibre in this baseline), confirm the `cluster_name` path still returns rows and that the lack of canonical rows is still expected. |

### `canonical_empty_cluster_populated_count`

The number of non-pairwise cases where `canonical_claim_count == 0` **and**
`cluster_claim_count > 0`.  This is the primary signal for the
**canonical-empty / cluster-populated** result class described in the
[Canonical-empty / cluster-populated result class](#canonical-empty--cluster-populated-result-class)
section below.

**Baseline value: 2** (`mercadolibre_single` and `mercadolibre_fragmentation`).

| Movement | Interpretation |
|----------|---------------|
| 🟢 **2 (baseline)** | Both known empty-canonical cases remain in their expected state. |
| 🟡 **3–4** | One or two additional cases have lost canonical coverage.  Inspect `fragmentation_type_hints` on the affected cases to classify the cause. |
| 🔴 **≥ 5** | Widespread canonical coverage loss — likely an alignment stage failure or broken `ALIGNED_WITH` edges across multiple entities. |
| 🟡 **1 or 0** | MercadoLibre may now be in the structured catalog (canonical coverage improved).  Verify the new canonical rows are correct and update the baseline if intentional. |

### `entities_with_claims_canonical`

How many non-pairwise cases (single-entity and comparison) returned at least one claim via the canonical path.
Pairwise cases are excluded because they use a different query path and are tracked separately under `total_pairwise_claims`.

| Movement | Interpretation |
|----------|---------------|
| 🟢 **6 (baseline)** | Matches the baseline: two cases (`mercadolibre_single` and `mercadolibre_fragmentation`) have empty canonical rows because MercadoLibre is absent from the structured catalog in this run. |
| 🟡 **5** | One additional non-pairwise case lost canonical coverage.  Run the affected case manually and inspect `lower_layer_rows` for the dark path. |
| 🔴 **≤ 4** | Multiple non-pairwise cases dropped off.  Likely an alignment stage failure or a broken `ALIGNED_WITH` edge set. |
| 🟡 **7–8** | Canonical coverage improved beyond baseline (MercadoLibre may now be in the catalog).  Verify the extra canonical rows are correct and update the baseline if intentional. |

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

## Canonical-empty / cluster-populated result class

A case is in the **canonical-empty / cluster-populated** result class when:

- `canonical_claim_count == 0` (canonical path returned no claims), **and**
- `cluster_claim_count > 0` (cluster-name path returned at least one claim).

This pattern means the entity is reachable through unstructured cluster evidence
but is invisible to the canonical (structured catalog) traversal path.  It is
**not automatically a bug** — it is expected whenever an entity is absent from the
structured catalog.

### How to read the canonical-empty / cluster-populated diagnostic fields

Each `BenchmarkCaseResult` now carries four classification fields:

| Field | Type | Meaning |
|-------|------|---------|
| `canonical_empty_cluster_populated` | `bool` | `True` ↔ the case is in the canonical-empty / cluster-populated class |
| `fragmentation_type_hints` | `list[str]` | Zero or more cause tokens (see below) |
| `catalog_check_rows` | `list[dict]` | Rows from a direct `CanonicalEntity` existence check; empty = no node found |
| `canonical_catalog_present` | `bool` | `True` ↔ at least one `CanonicalEntity` node matches this entity name |

**Cause tokens in `fragmentation_type_hints`:**

| Token | Cause | Recommended action |
|-------|-------|--------------------|
| `"entity_type_case_split"` | Two or more `entity_type` values in `fragmentation_check_rows` differ only by case (e.g., `"Organization"` vs `"organization"`).  The same conceptual entity type was persisted under two case variants, producing separate clusters that are not collapsed by the canonical path. | Ensure the observed `entity_type` variants are covered by normalization (via `_normalize_entity_type` / `_ENTITY_TYPE_SYNONYMS`) and re-run entity resolution. If the mapping already exists, investigate why clusters were persisted with mixed-case `entity_type` and correct the underlying normalization or persistence issue. |
| `"catalog_absent"` | `canonical_rows` is empty while `cluster_rows` is non-empty, **and** `catalog_check_rows` is empty — confirming no `CanonicalEntity` node exists for this entity name.  The entity is genuinely absent from the structured catalog. | Add a `CanonicalEntity` node for this entity and create the corresponding `ALIGNED_WITH` edges to the relevant clusters. |
| `"catalog_present_canonical_empty"` | `canonical_rows` is empty while `cluster_rows` is non-empty, **and** `catalog_check_rows` is non-empty — confirming a `CanonicalEntity` node exists but the canonical traversal still returns no rows.  The mechanical evidence is that the catalog entry is present and canonical retrieval is empty; possible causes include missing or incomplete `ALIGNED_WITH` edges, a canonical-name filter mismatch, or multiple ambiguous catalog entries. | Inspect `ALIGNED_WITH` edge coverage between the `CanonicalEntity` node and the relevant `ResolvedEntityCluster` nodes (use `lower_layer_rows` or the graph health diagnostics).  Re-run the alignment stage or add the missing edges. |
| `"catalog_absent_or_alignment_gap"` | Legacy fallback token.  Emitted only when no catalog existence check was available (i.e., the benchmark was run against an older build that did not include the catalog check query).  When the current benchmark is used, this token is replaced by `"catalog_absent"` or `"catalog_present_canonical_empty"`. | Treat as `"catalog_absent"` until a full catalog existence check is available. |

**`catalog_absent` and `catalog_present_canonical_empty` are mutually exclusive.**  Only one of
the two specific tokens will appear for any given case.  Both are more actionable
than the legacy `catalog_absent_or_alignment_gap` combined token.

Multiple tokens from different categories may be present simultaneously (e.g.,
`entity_type_case_split` and `catalog_absent` may both appear if both conditions
hold).

**Baseline note:** The baseline artifact was produced before the catalog existence
check was added, so baseline cases that previously showed
`"catalog_absent_or_alignment_gap"` will show `"catalog_absent"` in new runs
once the catalog check query is executed.  This is an expected diagnostic
improvement, not a regression.

### Classification of the baseline cases

| Case | `canonical_empty_cluster_populated` | `canonical_catalog_present` | `fragmentation_type_hints` (new runs) | Classification |
|------|-------------------------------------|-----------------------------|---------------------------------------|----------------|
| `mercadolibre_single` | `True` | `False` | `["entity_type_case_split", "catalog_absent"]` | **Expected** — MercadoLibre is absent from the structured catalog; the type-case split is a known entity_resolution condition. |
| `mercadolibre_fragmentation` | `True` | `False` | `["entity_type_case_split", "catalog_absent"]` | **Expected** — same entity as above; this case exists to make fragmentation explicit in the summary count. |
| All other cases | `False` | `True` (if in catalog) | `[]` or `["entity_type_case_split"]` | Canonical path is present; any fragmentation is captured only by the `fragmentation_detected` signal. |

### Guidance for reviewers

1. **If `canonical_empty_cluster_populated_count` matches the baseline (2):**
   Both known empty-canonical cases remain stable.  No action required unless
   other signals changed.

2. **If `canonical_empty_cluster_populated_count` increased:**
   A previously-canonical case lost canonical coverage.  For the newly-affected
   cases, inspect:
   - `fragmentation_type_hints` to classify the cause:
     - `"catalog_absent"` → the entity is missing from the structured catalog; add it.
     - `"catalog_present_canonical_empty"` → the entity is in the catalog but canonical retrieval is empty; inspect `ALIGNED_WITH` edge coverage and investigate root cause.
     - `"catalog_absent_or_alignment_gap"` → legacy token; re-run the benchmark to get the specific token.
   - `lower_layer_rows` to check for dark mentions or a missing canonical link.
   - Graph health diagnostics for `ALIGNED_WITH` coverage.

3. **If `fragmentation_type_hints` contains only `"entity_type_case_split"` but
   `canonical_empty_cluster_populated` is `False`:**
   The entity has canonical coverage; the case-split is detectable at the cluster
   layer but the canonical path absorbs it.  This is **acceptable but noisy** —
   the entity_type normalisation gap is a known condition and should be addressed
   by extending `_ENTITY_TYPE_SYNONYMS` in a follow-up.

4. **If `fragmentation_type_hints` contains `"catalog_absent_or_alignment_gap"`
   (legacy token) but `canonical_empty_cluster_populated` is expected to be `False`:**
   An entity that should be in the catalog is missing or its alignment is broken.
   This is a **regression** — open an issue and investigate the alignment stage.
   Re-run the benchmark to get the specific `"catalog_absent"` or `"catalog_present_canonical_empty"` token.

5. **If `fragmentation_type_hints` contains `"catalog_present_canonical_empty"` and
   `canonical_catalog_present` is `True`:**
   The `CanonicalEntity` node exists but canonical retrieval returned no rows.
   Possible causes include missing `ALIGNED_WITH` edges, a canonical-name filter
   mismatch, or multiple ambiguous catalog entries.  Inspect `ALIGNED_WITH` edge
   coverage and re-run the alignment stage.

6. **If `fragmentation_type_hints` contains `"catalog_absent"` and
   `canonical_catalog_present` is `False`:**
   The entity is genuinely absent from the structured catalog.  This is expected
   for catalog-absent entities (e.g., MercadoLibre in the baseline) and is a
   regression only if the entity was previously in the catalog.

---

## Per-case review guide

### Case `mercadolibre_single` (single_entity)

**Exercises:** canonical → cluster → mention → claim for MercadoLibre, an org that
may appear under multiple surface forms and clusters.

**Baseline figures:** canonical_claim_count=0, cluster_claim_count=8,
canonical_cluster_count=0, cluster_name_cluster_count=2, fragmentation_detected=**True**,
canonical_empty_cluster_populated=**True**,
fragmentation_type_hints=`["entity_type_case_split", "catalog_absent_or_alignment_gap"]`

**Review notes:**

- `canonical_rows` is **empty** in the real baseline.  MercadoLibre is not
  present in the structured catalog for the baseline run, so the canonical path
  returns zero rows.  An increase in `canonical_claim_count` from 0 means
  MercadoLibre was added to the catalog (check alignment stage).
- `fragmentation_detected=True` is **expected** here.  The baseline graph
  contains both an `Organization` and an `organization` (lowercase) cluster for
  MercadoLibre — a case-sensitivity entity-type split.
- `canonical_empty_cluster_populated=True` is **expected** — see the
  [Canonical-empty / cluster-populated result class](#canonical-empty--cluster-populated-result-class)
  section above for the full classification.
- `lower_layer_rows` is empty because canonical traversal returns no results
  without a `CanonicalEntity` node.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 0 (baseline: not in catalog) | 1–4 (verify catalog addition) | Unexplained jump to > 4 |
| `cluster_claim_count` | 8 ± 3 | +/– 4–12 | 0 |
| `fragmentation_detected` | True | — | False **and** cluster_claim_count = 0 |
| `canonical_empty_cluster_populated` | True | False **and** cluster_claim_count > 0 (canonical coverage improved; verify catalog/alignment change) | False **and** cluster_claim_count = 0 |
| dark mentions in `lower_layer_rows` | 0 (empty, expected) | — | — |

---

### Case `xapo_single` (single_entity)

**Exercises:** canonical traversal for Xapo — a fintech entity that may appear
under abbreviated and full-name surface forms.

**Baseline figures:** canonical_claim_count=3, cluster_claim_count=3,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- Equal claim counts across both paths is the healthy baseline state (no
  fragmentation, no alignment gap).
- `fragmentation_detected=False` is the healthy state.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 3 ± 2 | +/– 2–6 | 0 |
| `cluster_name_cluster_count` | 1 | 2 | ≥ 3 |
| `fragmentation_detected` | False | — | True |

---

### Case `endeavor_single` (single_entity)

**Exercises:** canonical traversal for Endeavor — a well-known organisation
with alias mentions ("Endeavor Argentina").

**Baseline figures:** canonical_claim_count=10, cluster_claim_count=12,
canonical_cluster_count=2, cluster_name_cluster_count=4, fragmentation_detected=**True**,
canonical_empty_cluster_populated=**False**,
fragmentation_type_hints=`["entity_type_case_split"]`

**Review notes:**

- `fragmentation_detected=True` is expected in the baseline.  The baseline graph
  contains both `Organization` and `organization` (lowercase) clusters for
  "Endeavor" and "Endeavor Argentina" — four distinct cluster variants in total.
- `canonical_cluster_count=2` because the canonical entity resolves through both
  the "Endeavor" and "Endeavor Argentina" clusters.
- `cluster_claim_count > canonical_claim_count` is expected here due to
  fragmentation: cluster-name traversal picks up claims from the lowercase
  `organization` clusters that are not aligned to the canonical entity.
- `canonical_empty_cluster_populated=False` because canonical coverage is present;
  this case is in the **fragmented-but-covered** class, not the canonical-empty class.
- `fragmentation_type_hints=["entity_type_case_split"]` confirms the fragmentation
  is caused by the `Organization`/`organization` case-sensitivity split.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 10 ± 3 | +/– 7–14 | 0 |
| `canonical_cluster_count` | 2 | 1 or 3 | 0 |
| `fragmentation_detected` | True | — | False **and** cluster_claim_count unchanged |
| `canonical_empty_cluster_populated` | False | — | True |
| dark mentions in `lower_layer_rows` | 0–1 | 2–3 | > 3 |

---

### Case `linda_rottenberg_single` (single_entity)

**Exercises:** Person-type entity canonical traversal.  Verifies the Person path
is symmetric with Organisation cases.

**Baseline figures:** canonical_claim_count=4, cluster_claim_count=4,
canonical_cluster_count=1, cluster_name_cluster_count=1, fragmentation_detected=**False**

**Review notes:**

- All `cluster_type` values in `cluster_rows` should be `"Person"`.  If `"Organization"`
  appears, an entity_type normalisation regression occurred.
- One dark mention (`claim_id=null`) exists in `lower_layer_rows` in the baseline.
  An increase in dark mentions signals a participation gap.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `canonical_claim_count` | 4 ± 2 | +/– 3–6 | 0 |
| `cluster_type` values | "Person" only | "Person" + 1 other | "Organization" only |
| `fragmentation_detected` | False | — | True |
| dark mentions in `lower_layer_rows` | 1 (baseline) | 2–3 | > 3 |

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

**Baseline figures:** canonical_claim_count=0, cluster_claim_count=8,
canonical_cluster_count=0, cluster_name_cluster_count=2, fragmentation_detected=**True**,
canonical_empty_cluster_populated=**True**,
fragmentation_type_hints=`["entity_type_case_split", "catalog_absent_or_alignment_gap"]`

**Review notes:**

- This case runs the same queries as `mercadolibre_single`; it is kept as a
  separate named case so that fragmentation detection is reported explicitly in
  the `benchmark_summary.fragmentation_detected_count` figure.
- `fragmentation_detected=True` here means the tool is correctly detecting the
  known entity-type split (`Organization` vs `organization`).
- `canonical_rows` is empty (same as `mercadolibre_single`) because MercadoLibre
  is absent from the structured catalog in the baseline run.
- `canonical_empty_cluster_populated=True` and `fragmentation_type_hints` carry
  both cause tokens — this is the expected baseline state.  See the
  [Canonical-empty / cluster-populated result class](#canonical-empty--cluster-populated-result-class)
  section for a full explanation.
- A change to `fragmentation_detected=False` means either the fragmentation was
  resolved (investigate whether the duplicate clusters were merged/removed) or an
  entity disappeared from the graph.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `fragmentation_detected` | True | — | False (verify canonical coverage) |
| `canonical_empty_cluster_populated` | True | False **and** cluster_claim_count > 0 (canonical coverage improved; verify catalog/alignment change) | False **and** cluster_claim_count = 0 |
| `cluster_name_cluster_count` | 2 | 1 or 3 | 0 |
| `fragmentation_check_rows` entity_type values | Organization + organization | Organization only | empty |

---

### Case `endeavor_composite` (composite_claim)

**Exercises:** list-split match path — claims where a subject or object slot is
a compound expression joined by "and", "or", "/", etc.

**Baseline figures:** canonical_claim_count=10, cluster_claim_count=12,
canonical_cluster_count=2, cluster_name_cluster_count=4,
fragmentation_detected=**True**; `match_method="list_split"` present in
`canonical_rows` for the composite-slot claim.

**Review notes:**

- The primary health signal is `match_method="list_split"` appearing in at least one
  row of `canonical_rows`.  If it disappears, the list-split participation path may
  have regressed (check `participation_metrics.json` → `list_split_suppressed`).
- Counts match `endeavor_single` because the same entity is queried; this case
  focuses on the presence of `match_method="list_split"` as the regression signal.
- Fragmentation behaviour is the same as `endeavor_single` — see that case for
  fragmentation interpretation.

| Signal | 🟢 Green | 🟡 Yellow | 🔴 Red |
|--------|---------|----------|--------|
| `match_method="list_split"` present | Yes | Only in `cluster_rows`, not `canonical_rows` | Not present at all |
| `canonical_claim_count` | 10 ± 3 | +/– 7–14 | 0 |

---

### Case `xapo_canonical_vs_cluster` (canonical_vs_cluster)

**Exercises:** side-by-side claim-count comparison for Xapo — the primary
deduplication regression metric.

**Baseline figures:** canonical_claim_count=3, cluster_claim_count=3,
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
2. Copy the new artifact to
   `pipelines/runs/<new-run-id>/retrieval_benchmark/retrieval_benchmark.json`.
3. Ensure the baseline path is **not** excluded by `.gitignore`.  Note that
   `/pipelines/runs/*` is ignored by default, so you will need to update
   `.gitignore` to add explicit negation exceptions for the new run directory
   and its files (see the pattern already set for the current baseline).
   Confirm with `git status` that the new baseline and its `PROVENANCE.md`
   are tracked before committing.
4. Add a `PROVENANCE.md` in the same directory documenting run provenance,
   redaction status, and why the run is considered representative.
5. Update the **Baseline artifact** section in this rubric to point to the new
   run directory and reflect the new expected values.
6. Update the **Baseline artifact** section in `pipelines/query/README.md`
   similarly.
7. Add a brief note in your PR description explaining what changed and why.

---

## References

- Real reviewed baseline artifact: [`pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/retrieval_benchmark.json`](../../pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/retrieval_benchmark.json)
- Baseline provenance: [`pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/PROVENANCE.md`](../../pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/PROVENANCE.md)
- Illustrative example artifact (schema reference only): [`pipelines/query/retrieval_benchmark_example_output.json`](../../pipelines/query/retrieval_benchmark_example_output.json)
- Benchmark stage: [`demo/stages/retrieval_benchmark.py`](../../demo/stages/retrieval_benchmark.py)
- CLI runner: [`pipelines/query/retrieval_benchmark.py`](../../pipelines/query/retrieval_benchmark.py)
- Query workbook section 14: [`pipelines/query/README.md`](../../pipelines/query/README.md#14-post-hybrid-retrieval-benchmark)
- Graph health diagnostics: [`pipelines/query/graph_health_diagnostics.py`](../../pipelines/query/graph_health_diagnostics.py)
- Retrieval semantics: [`docs/architecture/retrieval-semantics-v0.1.md`](retrieval-semantics-v0.1.md)
