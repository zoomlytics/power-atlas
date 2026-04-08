# Demo Validation Runbook

This runbook is a **manual end-to-end validation companion** for the demo. It is intentionally narrower than [`demo/README.md`](./README.md) and does **not** repeat the full setup guide, CLI reference, graph model explanation, or Neo4j workbook.

Use this document when you want to answer:

- Did the demo work end to end on a fresh graph?
- Are the **unstructured-first** guarantees holding?
- Are **v0.3 participation edges** present and queryable?
- Is **hybrid alignment** visible in retrieval without breaking citation quality?
- Are the recent retrieval-reviewability improvements actually observable in a live run?

For the canonical setup and conceptual background, see:

- [`demo/README.md`](./README.md)
- [`pipelines/query/README.md`](../pipelines/query/README.md)
- [`docs/architecture/retrieval-semantics-v0.1.md`](../docs/architecture/retrieval-semantics-v0.1.md)
- [`docs/architecture/unstructured-first-entity-resolution-v0.1.md`](../docs/architecture/unstructured-first-entity-resolution-v0.1.md)
- [`docs/architecture/retrieval-citation-result-contract-v0.1.md`](../docs/architecture/retrieval-citation-result-contract-v0.1.md)
- [`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`](../docs/architecture/retrieval-benchmark-review-rubric-v0.1.md)
- [`docs/architecture/claim-argument-model-v0.3.md`](../docs/architecture/claim-argument-model-v0.3.md)

---

## 1. Scope of this runbook

This runbook validates these properties:

1. **Clean reset behavior**
2. **Unstructured ingest** writes a run-scoped lexical layer
3. **Claim extraction** writes `ExtractedClaim`, `EntityMention`, and `HAS_PARTICIPANT`
4. **Participation-edge traversal** works in Neo4j
5. **Unstructured clustering** is complete and non-destructive
6. **Plain retrieval** works before structured ingest
7. **Graph-expanded retrieval** exposes participation-edge context
8. **Structured ingest** adds canonical entities cleanly
9. **Hybrid alignment** creates `ALIGNED_WITH` edges without changing the unstructured-first semantics
10. **Cluster-aware retrieval** surfaces cluster and canonical alignment context while preserving citation quality
11. Targeted post-hybrid questions behave conservatively and remain fully cited

This runbook is especially useful when validating changes related to:

- entity-type normalization / reviewability
- v0.3 participation edges
- hybrid alignment visibility
- retrieval path diagnostics
- benchmark-style comparison questions

---

## 2. Prerequisites

Do **not** use this section as the primary setup guide. Follow the canonical setup instructions in [`demo/README.md`](./README.md).

Before running this validation, ensure:

- Neo4j is reachable
- required environment variables are set for `--live` mode
- you can run `python -m demo.run_demo ...`

Minimum required environment variables for live runs:

```bash
export OPENAI_API_KEY='your-openai-api-key'
export NEO4J_PASSWORD='your-neo4j-password'
```

Optional:

```bash
export NEO4J_URI='neo4j://localhost:7687'
export NEO4J_USERNAME='neo4j'
export NEO4J_DATABASE='neo4j'
```

---

## 2a. Selecting a dataset

The demo supports multiple fixture datasets. The two available datasets are:

| Dataset | Primary PDF | Intended scope |
|---------|-------------|----------------|
| `demo_dataset_v1` | `chain_of_custody.pdf` | Stable baseline; used by default in most CI and manual runs. Entity network centers on Endeavor / MercadoLibre / Wikidata-backed Latin American tech ecosystem. |
| `demo_dataset_v2` | `chain_of_issuance.pdf` | Extended dataset with a second primary document. Use to exercise multi-document ingest or to validate that pipeline stages are dataset-agnostic. |

**Default behavior when multiple datasets exist**

When more than one dataset directory is present under `demo/fixtures/datasets/`, commands that require fixture paths cannot auto-discover a dataset and will raise an `AmbiguousDatasetError`. You **must** select a dataset explicitly for `ingest`, `structured`, `pdf`, `extract`, and `resolve`, and for `ask` unless you use `--all-runs`.

**How to select a dataset**

Pass `--dataset <name>` to any `run_demo.py` command:

```bash
# Run the full pipeline against dataset v1
python -m demo.run_demo ingest --live --dataset demo_dataset_v1

# Run the full pipeline against dataset v2
python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

Alternatively, export `FIXTURE_DATASET` once and omit `--dataset` from subsequent commands:

```bash
export FIXTURE_DATASET=demo_dataset_v1
python -m demo.run_demo ingest --live

# Switch to v2
export FIXTURE_DATASET=demo_dataset_v2
python -m demo.run_demo ingest --live
```

**How `FIXTURE_DATASET` interacts with `--dataset`**

`--dataset` takes precedence over `FIXTURE_DATASET`. Resolution order is:

1. `--dataset <name>` CLI flag
2. `FIXTURE_DATASET` environment variable
3. Auto-discovery (only when exactly **one** dataset directory exists)

If neither is set and multiple datasets exist, the command fails with a clear error listing the available dataset names.

**Listing available datasets**

```python
from demo.contracts.paths import list_available_datasets
print(list_available_datasets())
# ['demo_dataset_v1', 'demo_dataset_v2']
```

**Recommendation for this runbook**

All step-by-step commands in Section 4 can be run against either dataset. Set `FIXTURE_DATASET` before beginning a validation session so that the same dataset is used consistently throughout:

```bash
# Choose one:
export FIXTURE_DATASET=demo_dataset_v1   # stable baseline (recommended for first run)
export FIXTURE_DATASET=demo_dataset_v2   # second document, extended scenario
```

For fixture documentation and per-dataset README files, see:

- [`demo/fixtures/README.md`](./fixtures/README.md)
- [`demo/fixtures/datasets/demo_dataset_v1/README.md`](./fixtures/datasets/demo_dataset_v1/README.md)
- [`demo/fixtures/datasets/demo_dataset_v2/README.md`](./fixtures/datasets/demo_dataset_v2/README.md)

---

## 3. Validation flow overview

The intended order is:

1. reset
2. ingest PDF
3. extract claims
4. validate participation edges
5. resolve entities (`unstructured_only`)
6. ask baseline (`plain`)
7. ask baseline (`--expand-graph`)
8. ingest structured CSV
9. resolve entities (`hybrid`)
10. ask post-hybrid (`--cluster-aware`)
11. targeted post-hybrid questions
12. optional multi-entity stress test

---

## 4. Step-by-step validation

### Step 1 — Reset the demo graph

```bash
python -m demo.reset_demo_db --confirm
```

**Pass criteria**
- command exits successfully
- a reset report is written
- no unexpected errors

**Notes**
- For reset semantics and pre-v0.3 edge cleanup, see [`demo/README.md`](./README.md#reset-behavior).
- Old pre-v0.3 graphs are non-migratable; reset is the correct starting point.

---

### Step 2 — Run unstructured ingest

```bash
python -m demo.run_demo ingest-pdf --live
```

Record the emitted run id:

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
```

**Pass criteria**
- command exits successfully
- manifest exists at:

```text
demo/artifacts/runs/<run_id>/pdf_ingest/manifest.json
```

- run id is clearly printed and reusable

**Recommended checks**
- lexical layer written
- source fixture is the expected PDF
- no unexpected warnings

---

### Step 3 — Run claim extraction

```bash
python -m demo.run_demo extract-claims --live
```

**Pass criteria**
- command exits successfully
- manifest exists at:

```text
demo/artifacts/runs/$UNSTRUCTURED_RUN_ID/claim_and_mention_extraction/manifest.json
```

**Expected signals**
- non-zero extracted claim count
- non-zero entity mention count
- participation-edge statistics present

**Important**
- This stage runs in the same unstructured run scope as `ingest-pdf`.
- For exact semantics, see:
  - [`demo/README.md`](./README.md#mention-extraction)
  - [`docs/architecture/claim-argument-model-v0.3.md`](../docs/architecture/claim-argument-model-v0.3.md)

---

### Step 4 — Validate participation edges in Neo4j

Use the reference queries from [`pipelines/query/README.md`](../pipelines/query/README.md), especially the participation and entity-centric sections.

Recommended minimal checks:

```cypher
MATCH ()-[r:HAS_PARTICIPANT]->()
RETURN r.role AS role, count(r) AS total
ORDER BY role;
```

```cypher
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'object'}]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

**Pass criteria**
- subject and object participation edges exist
- `match_method` values are populated
- list-heavy claims show expected `list_split` behavior where applicable

**Expected interpretation**
- not every claim needs both subject and object
- `list_split` is expected on multi-entity lists
- `raw_exact` should still appear for simple direct matches

---

### Step 5 — Validate raw extractor type posture

This step exists to make sure raw extractor diversity is still visible before normalization is applied in clustering.

Recommended query:

```cypher
MATCH (m:EntityMention {run_id: $run_id})
RETURN m.entity_type AS entity_type, count(*) AS total
ORDER BY total DESC;
```

Optionally inspect specific names that may appear under multiple raw labels, for example:

```cypher
MATCH (m:EntityMention {run_id: $run_id})
WHERE toLower(m.name) = 'mercadolibre'
RETURN m.name, m.entity_type, count(*) AS total
ORDER BY total DESC;
```

**Pass criteria**
- raw entity types are present and inspectable
- raw extractor diversity is visible
- there is no evidence that raw labels were erased before resolution

**Important**
- Raw extractor outputs and clustering normalization are different layers.
- Do not expect raw type counts and normalized cluster type counts to be identical.

---

### Step 6 — Run unstructured-only entity resolution

```bash
python -m demo.run_demo resolve-entities --live
```

**Pass criteria**
- command exits successfully
- manifest exists at:

```text
demo/artifacts/runs/$UNSTRUCTURED_RUN_ID/entity_resolution/manifest.json
```

Inspect these fields:

- `resolution_mode`
- `resolved`
- `mentions_total`
- `mentions_clustered`
- `mentions_unclustered`
- `clusters_created`
- `resolution_breakdown`
- `entity_type_report`

**Expected values**
- `resolution_mode: "unstructured_only"`
- `mentions_clustered == mentions_total`
- `mentions_unclustered == 0`
- `resolved == 0`

**Important**
`resolved: 0` is **expected** here. In unstructured-only mode, mentions are clustered into `ResolvedEntityCluster` nodes; they are not directly linked via `RESOLVES_TO`.

See:
- [`demo/README.md`](./README.md#resolved-0-in-the-entity-resolution-manifest)
- [`docs/architecture/unstructured-first-entity-resolution-v0.1.md`](../docs/architecture/unstructured-first-entity-resolution-v0.1.md)

---

### Step 7 — Plain retrieval baseline

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --output-dir demo/artifacts_compare/pre_hybrid_plain \
  --question "What does the document say about Endeavor and MercadoLibre?"
```

Inspect:

- `all_answers_cited`
- `citation_fallback_applied`
- `citation_quality`
- `expand_graph`
- `cluster_aware`
- `hits`
- `retrieval_path_summary`

**Pass criteria**
- `all_answers_cited: true`
- `citation_fallback_applied: false`
- `citation_quality.evidence_level: "full"`
- `expand_graph: false`
- `cluster_aware: false`

**Expected interpretation**
- useful answer should be available before structured ingest
- retrieval diagnostics should not yet show graph expansion surfaces

---

### Step 8 — Graph-expanded baseline

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --expand-graph \
  --output-dir demo/artifacts_compare/pre_hybrid_expand \
  --question "What does the document say about Endeavor and MercadoLibre?"
```

Inspect:

- `all_answers_cited`
- `citation_fallback_applied`
- `citation_quality`
- `expand_graph`
- `cluster_aware`
- `retrieval_path_summary`
- one or two `retrieval_results[*].metadata.retrieval_path_diagnostics`

**Pass criteria**
- `all_answers_cited: true`
- `citation_fallback_applied: false`
- `citation_quality.evidence_level: "full"`
- `expand_graph: true`
- `cluster_aware: false`

**Expected interpretation**
- retrieval diagnostics should now show `HAS_PARTICIPANT`-grounded claim context
- cluster and canonical alignment fields should still be absent or empty

---

### Step 9 — Run structured ingest

```bash
python -m demo.run_demo ingest-structured --live
```

Inspect:

- `entities`
- `claims`
- `facts`
- `relationships`
- `lint_summary`
- `validation_warning_count`

**Pass criteria**
- command exits successfully
- structured ingest manifest is written
- lint status is OK
- validation warning count is zero or otherwise explained

---

### Step 10 — Run hybrid alignment

```bash
python -m demo.run_demo resolve-entities --live --resolution-mode hybrid
```

Inspect:

- `resolution_mode`
- `resolved`
- `aligned_clusters`
- `clusters_pending_alignment`
- `mentions_in_aligned_clusters`
- `alignment_breakdown`
- `mentions_clustered`
- `mentions_unclustered`
- warnings

**Pass criteria**
- `resolution_mode: "hybrid"`
- `mentions_clustered == mentions_total`
- `mentions_unclustered == 0`
- `aligned_clusters > 0`
- `alignment_breakdown` is present
- warnings are empty or explained

**Expected interpretation**
- `resolved == 0` remains correct
- `clusters_pending_alignment > 0` is not failure
- hybrid mode should preserve clustering and add `ALIGNED_WITH` enrichment

See:
- [`demo/README.md`](./README.md#hybrid-alignment-resolve-entities---resolution-mode-hybrid)
- [`docs/architecture/unstructured-first-entity-resolution-v0.1.md`](../docs/architecture/unstructured-first-entity-resolution-v0.1.md)

---

### Step 11 — Post-hybrid cluster-aware validation

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --cluster-aware \
  --output-dir demo/artifacts_compare/post_hybrid_cluster_aware \
  --question "What does the document say about Endeavor and MercadoLibre?"
```

Inspect:

- `all_answers_cited`
- `citation_fallback_applied`
- `citation_quality`
- `expand_graph`
- `cluster_aware`
- `retrieval_path_summary`
- selected `retrieval_results[*].metadata.retrieval_path_diagnostics`

**Pass criteria**
- `all_answers_cited: true`
- `citation_fallback_applied: false`
- `citation_quality.evidence_level: "full"`
- `expand_graph: true`
- `cluster_aware: true`

**Expected interpretation**
- retrieval path diagnostics should now show:
  - `cluster_memberships`
  - `cluster_canonical_via_aligned_with`
- there should still be no requirement for `RESOLVES_TO`

---

## 5. Targeted post-hybrid questions

These are recommended focused validations rather than generic demos.

### 5.1 Canonical bridging question

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --cluster-aware \
  --output-dir demo/artifacts_compare/post_hybrid_bridge \
  --question "How is MercadoLibre connected to Endeavor, MercadoPago, and Marcos Galperin?"
```

**Pass criteria**
- fully cited answer
- explicit connection among the requested entities
- no unsupported bridging
- retrieval diagnostics show alignment surfaces for relevant entities where available

---

### 5.2 Person / network disambiguation question

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --cluster-aware \
  --output-dir demo/artifacts_compare/post_hybrid_person \
  --question "Who is Marcos Galperin, and what role does he play in the Endeavor Argentina network?"
```

**Pass criteria**
- fully cited answer
- Marcos Galperin identified conservatively from retrieved evidence
- role described in terms actually supported by the source
- no unsupported biography inflation

---

### 5.3 Optional multi-entity stress test

```bash
python -m demo.run_demo ask --live \
  --run-id "$UNSTRUCTURED_RUN_ID" \
  --cluster-aware \
  --output-dir demo/artifacts_compare/q3/cluster_aware \
  --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"
```

**Pass criteria**
- fully cited answer
- direct links are stated only where supported
- unsupported pairwise links are **not** invented
- broader network overlap is described as overlap, not as an all-to-all direct relationship graph

This question is particularly useful when reviewing retrieval behavior against the benchmark rubric:

- [`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`](../docs/architecture/retrieval-benchmark-review-rubric-v0.1.md)

---

## 6. Known gotchas

### `graph-health` is not a `demo.run_demo` subcommand
If you try:

```bash
python -m demo.run_demo graph-health --live
```

that will fail because `graph-health` is not part of the CLI subcommand set.

Instead, use:

- the Neo4j workbook in [`pipelines/query/README.md`](../pipelines/query/README.md)
- supporting scripts under [`pipelines/query/`](../pipelines/query/)

### `resolved: 0` is often correct
In both `unstructured_only` and `hybrid` modes, `resolved` can remain `0` while the run is healthy.

### `clusters_pending_alignment > 0` is not failure
Structured ingest is smaller than the full unstructured mention universe; many clusters may remain unaligned.

### Cluster-aware retrieval should surface `MEMBER_OF` + `ALIGNED_WITH`
Do not expect hybrid mode to rely on direct `RESOLVES_TO` links.

### Citation quality matters more than answer length
A shorter fully cited answer is preferable to a longer partially supported one.

---

## 7. Suggested acceptance checklist

Use this checklist at the end of a manual run:

- [ ] Reset completed successfully
- [ ] Unstructured ingest completed and produced a reusable `UNSTRUCTURED_RUN_ID`
- [ ] Claim extraction completed with non-zero claims and mentions
- [ ] `HAS_PARTICIPANT` subject and object edges are queryable in Neo4j
- [ ] Raw extractor entity types remain inspectable before normalization
- [ ] Unstructured clustering completed with `mentions_clustered == mentions_total`
- [ ] Plain pre-hybrid Q&A returned a fully cited answer
- [ ] Graph-expanded pre-hybrid Q&A exposed participation-edge context
- [ ] Structured ingest completed cleanly
- [ ] Hybrid alignment produced `aligned_clusters > 0`
- [ ] Post-hybrid cluster-aware retrieval exposed `cluster_memberships`
- [ ] Post-hybrid cluster-aware retrieval exposed canonical alignment via `ALIGNED_WITH`
- [ ] Canonical bridging question returned a fully cited answer
- [ ] Person/network disambiguation question returned a fully cited answer
- [ ] Optional multi-entity stress test avoided unsupported pairwise claims
- [ ] All inspected Q&A manifests showed:
  - [ ] `all_answers_cited: true`
  - [ ] `citation_fallback_applied: false`
  - [ ] `citation_quality.evidence_level: "full"`

---

## 8. Suggested artifact capture

To make a validation run reviewable, retain:

- the key manifests under `demo/artifacts/` or `demo/artifacts_compare/`
- selected Neo4j query result exports
- the exact `UNSTRUCTURED_RUN_ID`
- any deviations or warnings observed during the run

A minimal retained artifact set is:

```text
demo/artifacts/runs/<UNSTRUCTURED_RUN_ID>/claim_and_mention_extraction/manifest.json
demo/artifacts/runs/<UNSTRUCTURED_RUN_ID>/entity_resolution/manifest.json
demo/artifacts_compare/pre_hybrid_plain/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
demo/artifacts_compare/pre_hybrid_expand/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
demo/artifacts_compare/post_hybrid_cluster_aware/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
demo/artifacts_compare/post_hybrid_bridge/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
demo/artifacts_compare/post_hybrid_person/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
demo/artifacts_compare/q3/cluster_aware/runs/<UNSTRUCTURED_RUN_ID>/retrieval_and_qa/manifest.json
```

---

## 9. Dataset v2 recorded run

This section documents the first committed end-to-end pipeline recording for
`demo_dataset_v2`.  The run was executed in dry-run mode (no Neo4j or OpenAI
calls) and its normalized manifest is committed at:

```
pipelines/runs/demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b/run_manifest.json
pipelines/runs/demo_dataset_v2-dryrun-20260408T163338Z-b09f7e1b/PROVENANCE.md
```

### Command used

```bash
python -m demo.run_demo ingest --dry-run --dataset demo_dataset_v2
```

### Summary of outcomes

| Stage | Status | Key metrics |
|-------|--------|-------------|
| Structured ingest | ✅ PASS | 12 entities, 13 facts, 20 relationships, 23 claims; 0 lint issues; 0 validation warnings |
| PDF ingest | ✅ Fixture verified | PDF fingerprint confirmed; chunks=0 (dry-run; no live embedding) |
| Claim extraction | ⚠️ Dry run | Skipped; LLM not called |
| Entity resolution (unstructured-only) | ⚠️ Dry run | Skipped; Neo4j not called |
| Entity resolution (hybrid) | ⚠️ Dry run | Skipped; Neo4j not called |
| Retrieval and Q&A | ⚠️ Dry run | Skipped; no vector index |

All dry-run `⚠️` outcomes are expected — no structural failures were found.

### Prerequisites for a live run

```bash
export OPENAI_API_KEY='your-openai-api-key'
export NEO4J_PASSWORD='your-neo4j-password'

# Optional (defaults shown):
export NEO4J_URI='bolt://localhost:7687'
export NEO4J_USERNAME='neo4j'
export NEO4J_DATABASE='neo4j'
```

### Running the full pipeline live against dataset v2

```bash
python -m demo.run_demo ingest --live --dataset demo_dataset_v2
```

Or using the environment variable:

```bash
export FIXTURE_DATASET=demo_dataset_v2
python -m demo.run_demo ingest --live
```

### Failures and follow-up items

The dry-run run does not produce live stage counts (PDF chunks, extracted
claims, entity clusters, retrieval answers).  A follow-up live-run recording
should be committed once an environment with Neo4j and OpenAI credentials is
available.  See the `PROVENANCE.md` file in the run directory for a per-stage
breakdown and the specific follow-up items.

### Relationship to dataset v1 baseline

The existing committed live run
`unstructured_ingest-20260401T184420771950Z-ee78cf8c` under `pipelines/runs/`
is a v1 run (`chain_of_custody.pdf`, `demo_dataset_v1`).  This dry-run
recording is the first committed artifact for v2 (`chain_of_issuance.pdf`,
`demo_dataset_v2`).

---

## 10. When to update this runbook

Update this file when:

- the intended manual validation flow changes
- new retrieval modes are added
- acceptance criteria change
- the preferred benchmark questions change
- the CLI subcommands or artifact paths change

Do **not** update this file just to restate README prose; update the README or architecture docs instead when conceptual or setup guidance changes.