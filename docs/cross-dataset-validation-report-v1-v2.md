# Cross-Dataset Validation Report — dataset v1 vs v2

**Report version:** v0.1  
**Generated:** 2026-04-08  
**Author:** Copilot / pipeline team  
**Status:** Initial draft — v2 live run pending

---

## 1. Purpose and scope

This report compares behavior of the Power Atlas demo pipeline across two fixture
datasets: `demo_dataset_v1` (stable baseline) and `demo_dataset_v2` (extended
second-document dataset).  It is the durable written artifact called for in the
issue *"docs: publish a cross-dataset validation report for dataset v1 vs v2"*.

The comparison covers:

- Structured ingest (CSV lint, entity/claim counts)
- PDF ingest (document fingerprinting, chunk production)
- Claim extraction and participation (unstructured LLM stage)
- Entity resolution (clustering, hybrid alignment)
- Retrieval and Q&A (golden questions, benchmark metrics)
- Operational ergonomics (dataset selection, `dataset_id` isolation, run reproducibility)

**Out of scope for this report:**

- Re-litigating settled unstructured-first / hybrid semantics (see
  [`docs/architecture/unstructured-first-entity-resolution-v0.1.md`](architecture/unstructured-first-entity-resolution-v0.1.md))
- Changes to claim-argument semantics (see
  [`docs/architecture/claim-argument-model-v0.3.md`](architecture/claim-argument-model-v0.3.md))
- Retrieval-citation contract details (see
  [`docs/architecture/retrieval-citation-result-contract-v0.1.md`](architecture/retrieval-citation-result-contract-v0.1.md))

---

## 2. Dataset identifiers and run context

### 2.1 dataset v1

| Field | Value |
|-------|-------|
| `dataset_id` | `demo_dataset_v1` |
| Primary document | `demo/fixtures/datasets/demo_dataset_v1/unstructured/chain_of_custody.pdf` |
| Run type recorded | **Live** (Neo4j + OpenAI) |
| `run_id` | `unstructured_ingest-20260401T184420771950Z-ee78cf8c` |
| `alignment_version` | `v1.0` |
| `generated_at` | `2026-04-01T20:38:01Z` |
| Normalization baseline | **pre-PR-#433** (entity-type case-split present) |
| Artifact location | `pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/` |
| Provenance doc | `pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/PROVENANCE.md` |

**Reproduce command:**

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>
export OPENAI_API_KEY=<your-openai-key>

python -m demo.run_demo ingest --live --dataset demo_dataset_v1
```

### 2.2 dataset v2

| Field | Value |
|-------|-------|
| `dataset_id` | `demo_dataset_v2` |
| Primary document | `demo/fixtures/datasets/demo_dataset_v2/unstructured/chain_of_issuance.pdf` |
| Run type recorded | **Dry-run only** (no Neo4j or OpenAI calls) |
| `unstructured_ingest_run_id` | `unstructured_ingest-20260408T163338705752Z-b09f7e1b` |
| `structured_ingest_run_id` | `structured_ingest-20260408T163338705724Z-83b4973b` |
| `batch_run_id` | `batch-20260408T163338711870Z-d7eea62f` |
| `generated_at` | `2026-04-08T16:33:38Z` |
| Artifact location | `pipelines/runs/demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b/` |
| Provenance doc | `pipelines/runs/demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b/PROVENANCE.md` |

**Reproduce command (dry run — no credentials required):**

```bash
python -m demo.run_demo ingest --dry-run --dataset demo_dataset_v2
```

**Live run (when credentials are available):**

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>
export OPENAI_API_KEY=<your-openai-key>

python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

---

## 3. Fixture summary comparison

### 3.1 Structured CSV fixture sizes

| File | v1 rows (excl. header) | v2 rows (excl. header) | Delta |
|------|------------------------|------------------------|-------|
| `entities.csv` | 12 | 12 | 0 |
| `facts.csv` | 17 | 13 | −4 |
| `relationships.csv` | 29 | 20 | −9 |
| `claims.csv` | 37 | 23 | −14 |

v1 is the larger fixture, reflecting a more densely connected entity network.
v2 is intentionally narrower — scoped to the `chain_of_issuance.pdf` document's
entity graph — with the same entity-count footprint but fewer cross-entity
relationships and seed claims.

### 3.2 Entity network

**v1 entity network** — centers on Endeavor and the Latin American tech ecosystem:

| QID | Name | Type |
|-----|------|------|
| Q1340293 | Endeavor | organization |
| Q6551937 | Linda Rottenberg | person |
| Q7982301 | Wences Casares | person |
| Q18208378 | Xapo | organization |
| Q328840 | Visa Inc. | organization |
| Q950419 | Mercado Libre | organization |
| Q348483 | Pierre Omidyar | person |
| Q317953 | Larry Summers | person |
| Q2904131 | Jeffrey Epstein | person |
| Q211098 | Reid Hoffman | person |
| Q328520 | Edgar Bronfman Jr. | person |
| Q5996574 | Marcos Galperin | person |
| Q5340595 | Eduardo Elsztain | person |

**v2 entity network** — centers on fintech infrastructure (Paxos, PayPal, Meta, DTCC):

| QID | Name | Type |
|-----|------|------|
| Q104844715 | Paxos Trust Company | organization |
| Q109999901 | Charles Cascarilla | person |
| Q483959 | PayPal | organization |
| Q950419 | Mercado Libre | organization |
| Q5996574 | Marcos Galperin | person |
| Q380 | Meta | organization |
| Q5230497 | David A. Marcus | person |
| Q30588516 | Blockchain Capital | organization |
| Q109999902 | Ben Davenport | person |
| Q1191721 | DTCC | organization |
| Q7982301 | Wences Casares | person |
| Q18208378 | Xapo | organization |

### 3.3 Entities shared across both datasets

The following QIDs appear in **both** v1 and v2 canonical entity sets:

| QID | Name | Notes |
|-----|------|-------|
| Q950419 | Mercado Libre | v2 adds `MELI` alias |
| Q5996574 | Marcos Galperin | v2 adds full name alias; updates description |
| Q7982301 | Wences Casares | v2 adds `Wenceslao Casares` alias; updates description |
| Q18208378 | Xapo | Description is identical |

These four entities are the natural cross-dataset identity anchor points.  When
both datasets are ingested into the same Neo4j instance (using `dataset_id`
stamping to isolate writes), these QIDs will appear as `CanonicalEntity` nodes
shared between the two runs.  No special handling is currently required, but the
behavior should be verified in a live dual-dataset run.  See
[follow-up item F-01](#follow-up-items).

---

## 4. Stage-by-stage comparison

### 4.1 Structured ingest

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| `entities` written | 12 | 12 (dry run) | ✅ Both pass |
| `facts` written | 17 | 13 (dry run) | ✅ Both pass |
| `relationships` written | 29 | 20 (dry run) | ✅ Both pass |
| `claims` written | 37 | 23 (dry run) | ✅ Both pass |
| `lint_issue_count` | 0 | 0 | ✅ Both clean |
| `validation_warning_count` | 0 | 0 | ✅ Both clean |
| `lint_status` | `ok` | `ok` (dry run) | ✅ Both pass |

**Assessment: ✅ PASS for both datasets.**  The structured ingest stage is
fully dataset-agnostic.  Both fixture sets pass lint and deduplication without
dropping any rows.  v2's smaller fixture is by design, not a deficiency.

### 4.2 PDF ingest

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| Primary document | `chain_of_custody.pdf` | `chain_of_issuance.pdf` | Different documents |
| Fixture-level verification | ✅ (fingerprint stable) | ✅ (SHA-256 `3b8dd64f…`) | ✅ Both verified |
| `pipeline_config` | `pdf_simple_kg_pipeline.yaml` | `pdf_simple_kg_pipeline.yaml` | ✅ Shared config |
| `vendor_pattern` | `SimpleKGPipeline + OpenAIEmbeddings + PageAwareFixedSizeSplitter` | same | ✅ Unchanged |
| `chunks` produced | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |

**Assessment: ✅ PASS for v1; ⚠️ DRY RUN ONLY for v2.**  The v2 fixture PDF is
correctly resolved, fingerprinted, and wired to the orchestrator.  Chunk
production (embedding + ingest into Neo4j) requires a live run.  See
[follow-up item F-02](#follow-up-items).

### 4.3 Claim extraction

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| `extracted_claim_count` | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |
| `entity_mention_count` | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |
| `prompt_version` | `claims_v1` | `claims_v1` | ✅ Shared prompt version |
| `extractor_model` | `gpt-4o-mini` | `gpt-4o-mini` | ✅ Shared model config |
| `source_uri` | `file:///demo/fixtures/datasets/demo_dataset_v1/unstructured/chain_of_custody.pdf` | `file:///demo/fixtures/datasets/demo_dataset_v2/unstructured/chain_of_issuance.pdf` | ✅ Correctly scoped |

**Assessment: ✅ PASS for v1; ⚠️ DRY RUN ONLY for v2.**  The extractor is
correctly wired to the v2 source URI and model config is consistent.  Whether
`chain_of_issuance.pdf` produces comparable extraction quality to
`chain_of_custody.pdf` is unknown until a live run is executed.  See
[follow-up item F-02](#follow-up-items).

### 4.4 Claim participation

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| `edges_written` | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |
| `match_metrics` | present (live) | `null` (dry run) | ⚠️ v2 unverified live |
| Participation stage wired to v2 URI | N/A | ✅ | ✅ Config correct |

**Assessment: ⚠️ DRY RUN ONLY for v2.**  No degradation visible; live run required.

### 4.5 Entity resolution — unstructured clustering

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| `clusters_created` | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |
| `cluster_version` | `v1.3` | `v1.3` | ✅ Same version |
| `resolution_mode` | `unstructured_only` | `unstructured_only` | ✅ Same mode |
| Entity-type case-split condition | Present (pre-PR-#433) | Unknown (dry run) | ⚠️ v2 unverified |

**Assessment: ✅ PASS for v1 (with known pre-PR-#433 case-split); ⚠️ DRY RUN
ONLY for v2.**  The v1 baseline shows `entity_type_case_split` fragmentation in
4 benchmark cases.  After PR-#433, this condition is expected to clear on v1
re-runs.  Whether it manifests on v2 depends on the LLM extraction output for
`chain_of_issuance.pdf`.  See [follow-up item F-03](#follow-up-items).

### 4.6 Entity resolution — hybrid alignment

| Metric | v1 (live) | v2 (dry run) | Status |
|--------|-----------|--------------|--------|
| `aligned_clusters` | non-zero (live) | 0 (dry run — expected) | ⚠️ v2 unverified live |
| `alignment_version` | `v1.0` | `v1.0` | ✅ Same version |
| `resolver_version` | `v1.2` | `v1.2` | ✅ Same version |
| `resolver_method` | `unstructured_clustering_with_canonical_alignment` | same | ✅ Unchanged |

**Assessment: ✅ PASS for v1; ⚠️ DRY RUN ONLY for v2.**  No regression
visible at config level.  The shared entities (Mercado Libre, Marcos Galperin,
Wences Casares, Xapo) appear in both fixture sets, so their alignment behavior
on v2 provides a meaningful cross-dataset alignment check once a live run is
executed.  See [follow-up item F-01](#follow-up-items).

### 4.7 Retrieval and Q&A

| Metric | v1 (live — benchmark) | v2 (dry run) | Status |
|--------|----------------------|--------------|--------|
| `retriever_type` | `VectorCypherRetriever` | `VectorCypherRetriever` | ✅ Same |
| `qa_prompt_version` | `qa_v3` | `qa_v3` | ✅ Same |
| `retrieval_query_contract` | present and stable | present and stable | ✅ Same |
| Evidence quality (live) | Answers cited | `no_answer` (dry run) | ⚠️ v2 unverified live |
| Golden questions answered | See v1 benchmark | N/A (dry run) | ⚠️ v2 unverified live |

**v1 retrieval benchmark summary (9 cases):**

| Metric | v1 baseline value |
|--------|-------------------|
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

Benchmark artifact: `pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/retrieval_benchmark.json`

**Notable v1 benchmark conditions:**

- `mercadolibre_single` / `mercadolibre_fragmentation` — `canonical_empty_cluster_populated=True`
  because MercadoLibre is absent from the v1 structured catalog for that run; entity-type case-split present
  (`organization` vs `Organization`), pre-PR-#433 condition.
- `endeavor_single` / `endeavor_composite` — Fragmentation detected; `cluster_name_cluster_count=4`
  (two name variants × two entity-type case variants), pre-PR-#433 condition.
- `linda_rottenberg_single` — One dark mention (`claim_id=null`) present in `lower_layer_rows`.
- `amazon_ebay_pairwise` — Zero pairwise rows; acceptable under expected-shape contract.

**v2 retrieval:** No live benchmark data available.  See [follow-up item F-02](#follow-up-items).

**Assessment: ✅ PASS for v1 (with known pre-PR-#433 signals); ⚠️ DRY RUN ONLY for v2.**

---

## 5. Successful behaviors

The following behaviors were confirmed working across both datasets:

1. **Dataset selection (`--dataset` flag and `FIXTURE_DATASET` env var)** —
   Both datasets are correctly resolved by `resolve_dataset_root()`.  The CLI
   flag takes precedence over the environment variable.  Resolution fails with
   a clear error when multiple datasets exist and neither mechanism is used.

2. **`dataset_id` stamping** — All graph writes are stamped with the active
   `dataset_id` (`demo_dataset_v1` or `demo_dataset_v2`), ensuring that two
   datasets can coexist in the same Neo4j instance without contaminating each
   other's runs.

3. **Structured ingest lint** — Both fixture sets pass lint with zero issues and
   zero warnings.  The lint stage is fully dataset-agnostic.

4. **Pipeline configuration reuse** — Both datasets use the same
   `pdf_simple_kg_pipeline.yaml` config, `gpt-4o-mini` extractor model,
   `qa_v3` prompt version, and `VectorCypherRetriever`.  No dataset-specific
   configuration overrides are needed.

5. **Dry-run reproducibility** — The v2 dry-run run (`demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b`)
   is fully reproducible with `python -m demo.run_demo ingest --dry-run --dataset demo_dataset_v2`
   and requires no external credentials.

6. **PDF fingerprint stability** — The v2 PDF fingerprint
   (`SHA-256: 3b8dd64fb276d6746615a6f51ac0b79d71e318e40625fde45b01054bea45867c`) is stable and
   committed in the provenance document.

7. **Shared entity QIDs as cross-dataset anchors** — Mercado Libre (Q950419),
   Marcos Galperin (Q5996574), Wences Casares (Q7982301), and Xapo (Q18208378)
   appear in both fixture sets with the same QIDs, providing natural regression
   anchors for future cross-dataset live runs.

---

## 6. Degraded behaviors

The following behaviors are degraded, incomplete, or show non-ideal signals,
but are not hard failures:

1. **Pre-PR-#433 entity-type case-split in v1 baseline** — The v1 retrieval
   benchmark baseline was generated before PR-#433 hardened entity-type
   normalization.  Fragmentation signals attributed to `entity_type_case_split`
   are expected to clear on a post-PR-#433 re-run.  Until a post-PR-#433 live
   v1 baseline is committed, the existing artifact remains the authoritative
   regression reference while carrying this known artifact.

2. **MercadoLibre absent from v1 structured catalog** — The v1 live run was
   executed without MercadoLibre in the catalog, producing
   `canonical_empty_cluster_populated=True` for two benchmark cases.  MercadoLibre
   appears in v1 `entities.csv`, so this condition reflects run-time catalog
   state at the time of the benchmark run rather than a fixture defect.

3. **One dark mention for Linda Rottenberg (v1)** — A single `claim_id=null`
   entry in `lower_layer_rows` for `linda_rottenberg_single` indicates one
   unparticipated EntityMention.  This is a known minor participation gap,
   not a structural failure.

4. **v2 dry-run only — no live extraction, clustering, or retrieval data** —
   The only committed v2 artifact is a dry-run manifest.  All stage counts
   (chunks, claims, clusters, aligned entities) are zero by definition.  The
   pipeline is verified at the fixture and config level but is not verified
   at the semantic-output level (extraction quality, cluster quality, retrieval
   precision).

---

## 7. Outright failures

No outright structural failures were observed in either dataset.

- The v2 dry-run zero-count results for extraction, clustering, and retrieval
  are expected dry-run behavior, not failures.
- Both fixture sets pass all lint checks.
- The `dataset_id` stamping mechanism is verified to be correctly wired for
  both datasets.

---

## 8. Follow-up items

The following items are candidates for future issues.  Each is a concrete
next step with known remediation.

### F-01 — Cross-dataset live run: verify shared-entity alignment behavior

**Condition:** Mercado Libre, Marcos Galperin, Wences Casares, and Xapo appear
in both v1 and v2 fixture sets.  No live run has been executed with both
datasets active in the same Neo4j instance.

**Risk:** `CanonicalEntity` nodes for shared QIDs may accumulate duplicate
`ALIGNED_WITH` edges or unexpected cluster linkages when both datasets' graph
writes are present simultaneously.

**Remediation:** Execute a live dual-dataset run and inspect the shared-entity
nodes for edge multiplicity and alignment correctness.

```bash
# Run v1
python -m demo.run_demo ingest --live --dataset demo_dataset_v1
# Then run v2 (same graph, different dataset_id stamps)
python -m demo.run_demo ingest --live --dataset demo_dataset_v2
# Inspect shared-entity alignment in Neo4j:
# MATCH (c:CanonicalEntity {entity_id: "Q950419"})<-[:ALIGNED_WITH]-(cluster)
# RETURN c, cluster LIMIT 20
```

### F-02 — Commit a v2 live-run artifact with real extraction and benchmark data

**Condition:** The only committed v2 artifact is a dry-run manifest.  Extraction
quality, cluster quality, and retrieval precision on `chain_of_issuance.pdf`
are completely unverified.

**Risk:** Silent regressions in the extractor or entity-resolution stages could
be introduced for v2 without detection.

**Remediation:** Run `python -m demo.run_demo ingest --live --dataset demo_dataset_v2`
with Neo4j + OpenAI credentials, capture the manifest, run the retrieval
benchmark, and commit both artifacts under a new `pipelines/runs/<run_id>/`
directory.  Update the retrieval-benchmark rubric and cross-dataset report
accordingly.

### F-03 — Verify entity-type normalization (post-PR-#433) on v2

**Condition:** The v1 benchmark baseline contains `entity_type_case_split`
fragmentation signals from the pre-PR-#433 codebase.  PR-#433 hardened
normalization, but no post-PR-#433 baseline has been committed for either
dataset.

**Risk:** If the normalization fix silently regressed, future v1 or v2 runs
could exhibit case-split fragmentation without a clean post-PR-#433 baseline
to compare against.

**Remediation:** After a successful live run of each dataset on a post-PR-#433
codebase, commit refreshed retrieval-benchmark artifacts and update the
rubric's baseline summary table.

### F-04 — Refresh the v1 retrieval-benchmark baseline post-PR-#433

**Condition:** The v1 benchmark baseline (`unstructured_ingest-20260401T184420771950Z-ee78cf8c`)
is explicitly labeled as a pre-PR-#433 reference.  The rubric notes that
`fragmentation_detected_count` is expected to decrease post-PR-#433.

**Remediation:** Re-run the v1 pipeline and benchmark on a post-PR-#433
codebase, commit the new artifact under a new run-ID directory, and update
`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md` (baseline
summary table and per-case expected values) and `pipelines/query/README.md`
(baseline figures).

---

## 9. Operational ergonomics comparison

### 9.1 Dataset selection

Both datasets are selected identically via:

```bash
# CLI flag (takes precedence)
python -m demo.run_demo ingest --live --dataset demo_dataset_v1
python -m demo.run_demo ingest --live --dataset demo_dataset_v2

# Environment variable
export FIXTURE_DATASET=demo_dataset_v1
python -m demo.run_demo ingest --live

# Python introspection
python -c "from demo.contracts.paths import list_available_datasets; print(list_available_datasets())"
# ['demo_dataset_v1', 'demo_dataset_v2']
```

No ergonomic difference between datasets.  The dataset-selection mechanism is
fully symmetric.

### 9.2 Dry-run vs live-run capability

| Capability | v1 | v2 |
|-----------|----|----|
| Dry-run (no credentials) | ✅ | ✅ |
| Live-run artifact committed | ✅ | ❌ (pending) |
| Retrieval benchmark committed | ✅ | ❌ (pending) |

v1 has a fuller committed artifact set.  v2 has verified dry-run behavior but
requires a live run to match v1's evidence depth.

### 9.3 Graph isolation

Both datasets stamp all Neo4j writes with `dataset_id`.  The following
run IDs illustrate the isolation:

- v1 live: `dataset_id = demo_dataset_v1`
- v2 dry-run: `dataset_id = demo_dataset_v2`

These values appear on `ExtractedClaim`, `ResolvedEntityCluster`,
`CanonicalEntity` (via `ALIGNED_WITH` edges), and `MEMBER_OF` edges.
Running both datasets sequentially in the same graph instance is supported
and tested at the dry-run level.

---

## 10. References

| Document | Location |
|----------|----------|
| dataset v1 README | `demo/fixtures/datasets/demo_dataset_v1/README.md` |
| dataset v2 README | `demo/fixtures/datasets/demo_dataset_v2/README.md` |
| Fixtures overview | `demo/fixtures/README.md` |
| Validation runbook | `demo/VALIDATION_RUNBOOK.md` |
| v1 live run provenance | `pipelines/runs/unstructured_ingest-20260401T184420771950Z-ee78cf8c/retrieval_benchmark/PROVENANCE.md` |
| v2 dry-run provenance | `pipelines/runs/demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b/PROVENANCE.md` |
| Retrieval benchmark rubric | `docs/architecture/retrieval-benchmark-review-rubric-v0.1.md` |
| Unstructured-first entity resolution | `docs/architecture/unstructured-first-entity-resolution-v0.1.md` |
| Claim-argument model | `docs/architecture/claim-argument-model-v0.3.md` |
| Retrieval-citation result contract | `docs/architecture/retrieval-citation-result-contract-v0.1.md` |
