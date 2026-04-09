# Power Atlas — Legacy `dataset_id` Migration Guide (v0.1)

**Status:** Accepted — applies to graphs created before dataset stamping was
consistently enforced (prior to PR #466)  
**Audience:** Operators, contributors, data engineers  
**Scope:** `CanonicalEntity` node repair, post-upgrade alignment diagnostics

---

## 1) Summary

Starting with PR #466, all entity-resolution queries filter `CanonicalEntity`
lookups with a strict equality predicate:

```cypher
WHERE canonical.dataset_id = $dataset_id
```

This is intentional: it prevents cross-dataset entity leakage when multiple
datasets share the same graph.  However, any `CanonicalEntity` nodes that were
written *before* dataset stamping was consistently enforced will have
`dataset_id = null` and will be silently excluded by this predicate, producing
**zero canonical alignments** for an otherwise healthy graph.

This guide explains how to identify affected nodes, diagnose the symptom
pattern, and choose a repair path.

---

## 2) Symptom pattern

After upgrading to a release that includes PR #466 (or later), operators may
observe:

- `entity_resolution_summary.json` → `aligned_clusters: 0` (hybrid mode) or
  `resolved: 0` (`structured_anchor` mode), even though structured ingest
  completed without errors in previous runs.
- A runtime warning in the entity-resolution logs:

  ```
  CanonicalEntity lookup returned zero rows for dataset_id='demo_dataset_v1'
  (hybrid alignment skipped); check that structured ingest has run for this
  dataset and that CanonicalEntity nodes carry a matching dataset_id property.
  ```

  or, for `structured_anchor` mode:

  ```
  CanonicalEntity lookup returned zero rows for dataset_id='demo_dataset_v1'
  (all mentions will be unresolved); check that structured ingest has run for
  this dataset and that CanonicalEntity nodes carry a matching dataset_id
  property.  If CanonicalEntity nodes already exist but have dataset_id=null,
  run the in-place repair Cypher or re-ingest from the structured fixture.
  ```

- Retrieval benchmark shows `canonical_empty_cluster_populated` result class
  for entities that previously resolved correctly.

**Root cause:** `CanonicalEntity` nodes in the graph have `dataset_id = null`
because they were written by an older version of structured ingest that did not
set `dataset_id`.  The strict filter introduced in PR #466 excludes them.

---

## 3) Diagnosing the issue

### 3.1 Check for null-dataset_id CanonicalEntity nodes

Connect to your Neo4j instance (e.g. via the Neo4j Browser at
`http://localhost:7474`) and run:

```cypher
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
RETURN c.entity_id, c.run_id, c.name
ORDER BY c.entity_id
LIMIT 50
```

If this returns rows, those nodes are the legacy nodes affected by the
upgrade.  Note the `run_id` values: they identify which structured-ingest run
produced the legacy nodes.

### 3.2 Check the total count

```cypher
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
RETURN count(c) AS legacy_count
```

A non-zero `legacy_count` confirms the legacy-node scenario.

### 3.3 Confirm stamped nodes also exist (optional)

If structured ingest has been re-run after the upgrade, both stamped and
legacy nodes may co-exist:

```cypher
MATCH (c:CanonicalEntity)
RETURN c.dataset_id AS dataset_id, count(*) AS node_count
ORDER BY dataset_id
```

A `null` row in the output indicates legacy nodes that still need repair.

---

## 4) Recommended operator paths

### Path A — Clean re-ingest (recommended for most cases)

The safest and most reliable option. This wipes the existing demo-owned
graph (all demo labels and relationships), then re-runs structured ingest
so that recreated nodes are written with the correct `dataset_id`.

```bash
# 1. Reset the graph (wipes all demo-owned nodes and relationships)
python -m demo.run_demo --live reset --confirm
# Alternative (direct script):
# NEO4J_PASSWORD=... python demo/reset_demo_db.py --confirm

# 2. Re-run the full pipeline for your dataset
python -m demo.run_demo ingest --live --dataset demo_dataset_v1
```

Re-ingest is also the correct path if you are unsure which `run_id` or
`dataset_id` value should be stamped on legacy nodes.

**When to prefer Path A:**
- You have no persistent user annotations or derived data on the nodes.
- You can afford the time to re-run the full pipeline.
- You have an authoritative fixture or source of truth to ingest from.

---

### Path B — In-place repair (Cypher backfill)

If re-ingest is impractical (e.g. the structured fixture is unavailable, or
you need to preserve the existing run graph), you can stamp legacy nodes
in-place with a `SET` query.

> ⚠️ **Always back up your database before running write queries in
> production.**

#### Step 1 — Identify the target `dataset_id`

Determine which dataset the legacy nodes belong to.  If all nodes in your
graph belong to a single dataset, use that dataset's name (e.g.
`"demo_dataset_v1"`).  If multiple datasets co-exist, you may need to inspect
node properties or run history to assign the correct value.

#### Step 2 — Dry-run (audit-only, no writes)

```cypher
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
RETURN count(c) AS nodes_to_repair, collect(c.run_id)[..5] AS sample_run_ids
```

Verify the count and sample `run_id` values before proceeding.

#### Step 3 — Apply the backfill

Replace `'demo_dataset_v1'` with the correct `dataset_id` for your graph:

```cypher
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
SET c.dataset_id = 'demo_dataset_v1'
RETURN count(c) AS repaired
```

If your graph contains `CanonicalEntity` nodes from multiple legacy runs that
belong to *different* datasets, scope the repair by `run_id`:

```cypher
// Repair only nodes from a specific run
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
  AND c.run_id = '<your-legacy-run-id>'
SET c.dataset_id = 'demo_dataset_v1'
RETURN count(c) AS repaired
```

#### Step 4 — Verify

```cypher
MATCH (c:CanonicalEntity)
WHERE c.dataset_id IS NULL
RETURN count(c) AS remaining_nulls
```

`remaining_nulls` should be `0` after a complete repair.

---

## 5) Validation after repair

After completing Path A or Path B, re-run entity resolution and confirm
alignment is restored.  `resolve-entities` requires the run ID from a prior
PDF ingest step; set `UNSTRUCTURED_RUN_ID` to the relevant run ID and pass
`--resolution-mode hybrid` (or `structured_anchor`):

```bash
UNSTRUCTURED_RUN_ID=<run_id_from_prior_ingest> \
  python -m demo.run_demo --live resolve-entities \
  --dataset demo_dataset_v1 \
  --resolution-mode hybrid
```

Alternatively, re-run the full pipeline end-to-end (which handles the run ID
automatically):

```bash
python -m demo.run_demo ingest --live --dataset demo_dataset_v1
```

Check `entity_resolution_summary.json` under
`<output_dir>/runs/<run_id>/entity_resolution/`:

- `aligned_clusters` should be greater than `0` (hybrid mode)
- `resolved` should be greater than `0` (`structured_anchor` mode)
- `warnings` should be empty or should not mention "zero rows"

For a deeper validation, run the retrieval benchmark:

```bash
python pipelines/query/retrieval_benchmark.py --live --dataset demo_dataset_v1
```

The result class `canonical_empty_cluster_populated` should no longer appear
for entities that were previously aligning before the upgrade.

---

## 6) Relationship to the dataset isolation guarantee

PR #466 introduced `WHERE canonical.dataset_id = $dataset_id` as a hard
isolation predicate.  This prevents `CanonicalEntity` nodes from one dataset
from being matched during entity resolution for a *different* dataset — a
correctness requirement for multi-dataset graphs.

Relaxing this predicate (e.g. falling back to `IS NULL OR = $dataset_id`)
would silently re-enable cross-dataset leakage.  The in-place repair approach
(Path B) is therefore the only safe way to recover legacy nodes without
loosening the isolation guarantee.

---

## 7) References

- `demo/stages/entity_resolution.py` — entity resolution stage; see
  `run_entity_resolution` for the `WHERE canonical.dataset_id = $dataset_id`
  predicate.
- `demo/stages/structured_ingest.py` — structured ingest stage; see
  `run_structured_ingest` for the `SET entity.dataset_id = $dataset_id`
  stamping.
- `docs/architecture/unstructured-first-entity-resolution-v0.1.md` — layered
  identity model and dataset isolation design rationale.
- PR #466 — original implementation of dataset-local alignment.
