# Demo Workflow (dataset v1)

Self-contained demo workflow under `demo/` for evidence-driven influence research with structured and unstructured artifacts.

---

## Quickstart for first-time users

If you are running the demo for the first time, start here.

### What this demo does

The demo follows an **unstructured-first** approach:

1. Ingest a PDF and build a lexical graph
2. Extract claims and entity mentions from the document
3. Resolve entities using **`unstructured_only`** mode — mentions are clustered against each other; no structured data required
4. Ask citation-grounded questions and see meaningful answers from unstructured data alone
5. *(Optional)* Ingest structured CSV data as additive enrichment
6. *(Optional)* Re-resolve entities using **`hybrid`** mode — existing clusters gain `ALIGNED_WITH` links to canonical entities where matches exist
7. *(Optional)* Ask questions again to see the enriched graph

Structured ingest is **optional verification and enrichment**, not a prerequisite for entity resolution or Q&A.

The demo supports:

- **unstructured ingest** from a PDF fixture
- **claim extraction** from previously ingested PDF chunks
- **entity resolution** in `unstructured_only` mode (default), `hybrid` mode (after structured ingest), or `structured_anchor` mode
- **retrieval and citation-grounded Q&A** over ingested material, available after unstructured ingest alone
- **structured ingest** from CSV fixtures (additive enrichment)

### What you need

For a real (`--live`) run, you need:

- a reachable Neo4j instance
- `OPENAI_API_KEY`
- `NEO4J_PASSWORD`

Optional environment variables:

- `NEO4J_URI` — defaults to `neo4j://localhost:7687`
- `NEO4J_USERNAME` — defaults to `neo4j`
- `NEO4J_DATABASE` — defaults to `neo4j`
- `OPENAI_MODEL`

### Recommended first live run

Set the required environment variables:

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

Start from a clean graph:

```bash
python -m demo.reset_demo_db --confirm
```

**Phase 1 — Unstructured-only pass** (no structured data required):

```bash
# Ingest the PDF
python -m demo.run_demo ingest-pdf --live

# Extract claims and entity mentions
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
python -m demo.run_demo extract-claims --live

# Cluster entity mentions (unstructured_only mode is the default)
# Expected: resolved=0 (correct — no canonical entities needed), mentions_clustered=<count>
python -m demo.run_demo resolve-entities --live

# Ask questions — meaningful answers are available before structured ingest
python -m demo.run_demo ask --live --run-id $UNSTRUCTURED_RUN_ID --question "What does the document say about Endeavor and MercadoLibre?"
```

**Phase 2 — Structured enrichment pass** (optional, additive):

```bash
# Ingest structured CSV data as optional enrichment/verification
python -m demo.run_demo ingest-structured --live

# Re-resolve entities in hybrid mode to align clusters with canonical entities
# Expected: resolved=0 (still correct), aligned_clusters=<count>, clusters_pending_alignment=<count>
python -m demo.run_demo resolve-entities --live --resolution-mode hybrid

# Validate post-hybrid enrichment with explicit run-id and cluster-aware retrieval
# Using --run-id ensures validation targets the exact run just enriched
python -m demo.run_demo ask --live --run-id $UNSTRUCTURED_RUN_ID --cluster-aware --question "What does the document say about Endeavor and MercadoLibre?"
```

You can also ask across the whole database (all runs and all source documents):

```bash
python -m demo.run_demo --live ask --all-runs --question "What does the document say about Endeavor and MercadoLibre?"
```

### What success looks like

A successful `ask` run prints the resolved retrieval scope before query execution:

```text
Using retrieval scope: run=unstructured_ingest-20260312T221631097539Z-d821ea28
```

or:

```text
Using retrieval scope: all runs in database
```

**Example Q&A output (citation-grounded):**

```text
Endeavor is a global entrepreneurship network that supports high-impact entrepreneurs
through mentoring, access to capital, and market expansion.
[CITATION|chunk_id=chunk-42|run_id=unstructured_ingest-20260312T221631097539Z-d821ea28|source_uri=file:///chain_of_custody.pdf|chunk_index=3|page=2|start_char=140|end_char=310]

MercadoLibre is a Latin American e-commerce and fintech platform mentioned in the
document as a portfolio company with regional growth ambitions.
[CITATION|chunk_id=chunk-17|run_id=unstructured_ingest-20260312T221631097539Z-d821ea28|source_uri=file:///chain_of_custody.pdf|chunk_index=1|page=1|start_char=520|end_char=680]
```

In successful runs, answer sentences are expected to be backed by `[CITATION|...]` tokens that trace directly to
`Chunk` nodes in the lexical graph. The `chunk_id`, `run_id`, `source_uri`, `page`, and character offsets help you
verify each claim against the source document; if a citation is missing, the system emits an explicit fallback or
warning marker rather than an unlabeled claim.

Non-interactive successful independent stage runs (for example, `ask`, `ingest-pdf`, etc.) also write manifests under:

```text
<output-dir>/runs/<run_id>/<stage_name>/manifest.json
```

Here, `<output-dir>` is the directory specified via `--output-dir` (default: `demo/artifacts`).

Batch `ingest` runs instead write their manifest to the specified output directory as `<output-dir>/manifest.json`.

Note: interactive Q&A sessions (for example, using `ask --interactive`) do not write a manifest; rely on the console output or your shell history instead.

For successful Q&A runs, the manifest should normally show:

- `stages.retrieval_and_qa.all_answers_cited: true`
- `stages.retrieval_and_qa.citation_fallback_applied: false`
- `stages.retrieval_and_qa.citation_quality.evidence_level: "full"`

---

## Overview

The demo follows an **unstructured-first** posture: unstructured PDF ingest, claim extraction, entity resolution, and Q&A retrieval form a complete standalone workflow. Structured CSV ingest is an optional, additive enrichment layer — not a prerequisite.

The most important ideas for first-time users:

- **producer stages** create or write new run-scoped data
- **derived stages** operate within an existing producer run scope
- **entity resolution defaults to `unstructured_only`** — mentions are clustered against each other without requiring structured ingest; structured canonical entity lookup is available as an explicit enrichment step
- **Q&A retrieval, in `--live` mode, uses `UNSTRUCTURED_RUN_ID` if set, otherwise the latest run by default**, and can also target a specific run or all runs
- **structured ingest is optional enrichment**, not the identity anchor — the graph is meaningful before it runs

You do **not** need to understand every graph layer before running the demo successfully. Use the Quickstart first, then return to the sections below as needed.

---

## Recommended workflow

Use `--dry-run` to run stages without live OpenAI or Neo4j calls. Use `--live` for real graph writes, retrieval, and citations.

### Step 1 — Reset the graph (optional but recommended before a clean run)

```bash
export NEO4J_PASSWORD='your-neo4j-password'

# Standalone reset script (recommended):
python -m demo.reset_demo_db --confirm

# Or via the CLI orchestrator:
python -m demo.run_demo --live reset --confirm
# The CLI's own output currently shows the equivalent script-path form:
#   python demo/run_demo.py --live reset --confirm
```

Without `--confirm`, the standalone script exits with an error and the CLI reset path prints instructions only.

Both reset paths write a JSON reset report to `<output-dir>/reset_report_<timestamp>.json`, with `demo/artifacts` used as the default `--output-dir`.

> **⚠ v0.2 graph model — old graphs are non-migratable.**
> v0.2 renamed participation edges from `:HAS_SUBJECT`/`:HAS_OBJECT` to
> `:HAS_SUBJECT_MENTION`/`:HAS_OBJECT_MENTION`.  Graphs produced by a
> pre-v0.2 run **cannot be migrated in place**.  The reset script automatically
> removes any surviving stale `:HAS_SUBJECT`/`:HAS_OBJECT` edges and records
> the count in the report under `stale_participation_edges_deleted`.
> After reset, re-run the full pipeline (Steps 2–5 below) to produce a clean
> v0.2 graph with the correct edge types.

### Step 2 — Run the unstructured-only pass (no structured data required)

```bash
python -m demo.run_demo --dry-run ingest-pdf
```

`ingest-pdf` generates a new `run_id` and writes a stage manifest to:

```text
<output-dir>/runs/<run_id>/<stage_name>/manifest.json
```

Here, `<stage_name>` is the on-disk **manifest folder name** under `runs/<run_id>/`, which does not always match the CLI subcommand. The mappings are:

- `ingest-pdf` → `pdf_ingest`
- `extract-claims` → `claim_and_mention_extraction` (manifest directory; stage artifacts are written under `<output-dir>/runs/<run_id>/claim_extraction/`)
- `resolve-entities` → `entity_resolution`
- `ask` → `retrieval_and_qa`
- `ingest-structured` → `structured_ingest` (optional enrichment)

For a real unstructured run:

```bash
python -m demo.run_demo --live ingest-pdf
```

### Step 3 — Run claim extraction (same run scope as `ingest-pdf`)

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
python -m demo.run_demo --dry-run extract-claims
```

`extract-claims` runs within the existing unstructured ingest run scope established by `ingest-pdf`. It does not create a separate producer run.

In live mode, `extract-claims` reads `Chunk` nodes for the selected `run_id`. In `--dry-run` mode it returns a stub summary.

After a live `extract-claims` run, validate the v0.2 participation edges in Neo4j Browser or the CLI:

```cypher
// Neo4j Browser — check HAS_SUBJECT_MENTION edges
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m:EntityMention)
RETURN c.claim_id, r.match_method, m.name
LIMIT 25;

// Neo4j Browser — check HAS_OBJECT_MENTION edges
MATCH (c:ExtractedClaim)-[r:HAS_OBJECT_MENTION]->(m:EntityMention)
RETURN c.claim_id, r.match_method, m.name
LIMIT 25;

// Neo4j Browser — combined summary count
MATCH ()-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->()
RETURN type(r) AS edge_type, count(r) AS total
ORDER BY edge_type;
```

```bash
# CLI — count participation edges via cypher-shell (if available)
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH ()-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->() RETURN type(r) AS edge_type, count(r) AS total ORDER BY edge_type;"
```

### Step 4 — Entity resolution and Q&A (unstructured-only)

These stages operate within an existing unstructured ingest run scope.

- For `extract-claims` and `resolve-entities`, you must set `UNSTRUCTURED_RUN_ID` whenever you run these stages as independent subcommands so they know which unstructured ingest run to target. Each `python -m demo.run_demo ...` invocation runs in its own process, so the environment variable is always required when calling these subcommands directly.
- For `ask`, retrieval scope is selected as described below; you can optionally set `UNSTRUCTURED_RUN_ID` if you want to target a specific unstructured run without passing `--run-id`.

```bash
# Reuse the run id from `ingest-pdf` / `extract-claims`
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf or extract-claims output>

# Entity resolution — defaults to unstructured_only mode (clusters mentions without structured ingest)
python -m demo.run_demo --dry-run resolve-entities

# Retrieval and Q&A — meaningful answers available before structured ingest
python -m demo.run_demo --dry-run ask
```

At this point you have a working graph and citation-grounded Q&A from unstructured data alone.

### Step 4b — Optional: structured enrichment pass

Structured ingest is optional additive enrichment. Run it *after* the unstructured pass to demonstrate its additive nature:

```bash
# Ingest structured CSV data as optional enrichment/verification
python -m demo.run_demo --dry-run ingest-structured

# Re-resolve entities in hybrid mode to align clusters with canonical entities
python -m demo.run_demo --dry-run resolve-entities --resolution-mode hybrid

# Ask with cluster-aware retrieval to validate post-hybrid graph enrichment
python -m demo.run_demo --dry-run ask --cluster-aware
```

The `hybrid` mode enriches existing `ResolvedEntityCluster` nodes with `ALIGNED_WITH` edges to `CanonicalEntity` nodes where label or alias matches exist. It gracefully degrades when no structured entities are present.

#### Retrieval scope selection for `ask`

The `ask` command supports explicit retrieval scope flags:

| Flag | Behavior |
| --- | --- |
| *(none)* | Default: if `UNSTRUCTURED_RUN_ID` is set, use that run; otherwise same as `--latest` in `--live` mode |
| `--latest` | In `--live` mode: retrieve from the latest successful unstructured ingest run. In `--dry-run` mode: behaves like the default (uses `UNSTRUCTURED_RUN_ID` if set; otherwise no run id is used and the CLI prints `run=(none — dry-run placeholder)`). |
| `--run-id <RUN_ID>` | Retrieve from a specific ingest run |
| `--all-runs` | Retrieve across the whole database — no `run_id` filter and no `source_uri` filter |

#### Retrieval mode selection for `ask`

The `ask` command also exposes flags to select the retrieval mode. These are independent of the scope flags above and may be combined with any scope flag.

| Flag | Retrieval mode | When to use |
| --- | --- | --- |
| *(none)* | **Plain run-scoped vector retrieval** — returns chunk text with basic metadata only | Default for ad-hoc questions before structured enrichment |
| `--expand-graph` | **Graph-expanded retrieval** — adds `ExtractedClaim`, `EntityMention`, and canonical entity context from the graph alongside each retrieved chunk | After entity resolution (`unstructured_only` mode) to include claim and mention context |
| `--cluster-aware` | **Cluster-aware retrieval** — full graph expansion plus `ResolvedEntityCluster` membership and `ALIGNED_WITH` edges to canonical entities (implies `--expand-graph`) | **Recommended post-hybrid validation step** — run after `resolve-entities --resolution-mode hybrid` to confirm that ALIGNED_WITH enrichment is surfaced during retrieval |

The manifest records both flags under `stages.retrieval_and_qa.cluster_aware` and `stages.retrieval_and_qa.expand_graph` so you can confirm which retrieval mode was active for any given run.

Examples (`--live` mode):

```bash
# Default: use UNSTRUCTURED_RUN_ID if set; otherwise latest successful unstructured ingest run
python -m demo.run_demo --live ask --question "What does the document say about Endeavor and MercadoLibre?"

# Explicit latest (ignores UNSTRUCTURED_RUN_ID)
python -m demo.run_demo --live ask --latest --question "What does the document say about Endeavor and MercadoLibre?"

# Explicit run
python -m demo.run_demo --live ask --run-id <RUN_ID> --question "What does the document say about Endeavor and MercadoLibre?"

# Whole database
python -m demo.run_demo --live ask --all-runs --question "What does the document say about Endeavor and MercadoLibre?"
```

The resolved scope is always printed before query execution.

**Precedence (for `--live` mode):** `--run-id` / `--latest` / `--all-runs` CLI flags → `UNSTRUCTURED_RUN_ID` env var → implicit latest successful unstructured ingest run (default).

In `--dry-run` mode, Neo4j is not queried; if `UNSTRUCTURED_RUN_ID` is set it will still be honored even when `--latest` is provided.

For first-time users, prefer the CLI flags over environment-variable-based run selection.

**All-runs mode note:** `--all-runs` removes both the `run_id` filter and the `source_uri` filter, querying the whole database. Citations returned may refer to chunks from different ingest runs and different source documents. Each citation includes its own `run_id` and `source_uri` for traceability.

### Convenience batch mode (alternative to steps 2–4b)

```bash
python -m demo.run_demo --dry-run ingest
```

Runs the full unstructured-first sequence as a single command: PDF ingest → claim extraction → entity resolution (`unstructured_only`) → Q&A → structured ingest → entity resolution (`hybrid`) → final Q&A. The batch manifest captures both passes so you can compare Q&A quality before and after structured enrichment.

To include live Q&A in both phases, pass a question:

```bash
python -m demo.run_demo --live ingest \
    --question "What does the document say about Endeavor and MercadoLibre?"
```

When `--question` is omitted, the Q&A stages are included in the manifest but skip vector retrieval in `--live` mode.

The batch manifest has its own `run_id`, while producer stages still preserve separate structured and unstructured run scopes internally.

### Step 5 — Run smoke test

```bash
python demo/smoke_test.py
```

By default, artifacts are written to a temporary directory deleted on exit. Pass `--output-dir` to retain them.

The smoke test runs structured, unstructured, and batch scenarios in sequence.

---

## Common ask patterns

Use these commands depending on what you want to query.

### Ask against the latest unstructured ingest

```bash
python -m demo.run_demo --live ask --latest --question "What does the document say about Endeavor and MercadoLibre?"
```

### Ask against a specific ingest run

```bash
python -m demo.run_demo --live ask --run-id <RUN_ID> --question "What does the document say about Endeavor and MercadoLibre?"
```

### Ask across the whole database

```bash
python -m demo.run_demo --live ask --all-runs --question "What does the document say about Endeavor and MercadoLibre?"
```

Removes both the `run_id` filter and the `source_uri` filter — retrieval spans all chunks in the database, across all runs and all source documents.

### Post-hybrid cluster-aware Q&A (recommended final validation step)

After running `resolve-entities --resolution-mode hybrid`, use `--cluster-aware` to confirm that the hybrid alignment is surfaced during retrieval. This is the **intended final validation step** for the unstructured-first ER architecture:

```bash
# Step 1: run hybrid alignment (if not already done)
python -m demo.run_demo --live resolve-entities --resolution-mode hybrid

# Step 2: ask with cluster-aware retrieval to validate post-alignment graph enrichment
python -m demo.run_demo --live ask --latest --cluster-aware \
    --question "What does the document say about Endeavor and MercadoLibre?"
```

The manifest will record `cluster_aware: true` and `expand_graph: true` under `stages.retrieval_and_qa`, confirming that cluster membership and `ALIGNED_WITH` edges were consulted during retrieval.

### Graph-expanded retrieval (without cluster awareness)

```bash
python -m demo.run_demo --live ask --latest --expand-graph \
    --question "What does the document say about Endeavor and MercadoLibre?"
```

Adds `ExtractedClaim`, `EntityMention`, and canonical entity context from the graph alongside each retrieved chunk. Use this after entity resolution in `unstructured_only` mode to include claim and mention context before structured enrichment is available.

### Retrieval mode comparison

| Mode | CLI flags | Manifest fields | When to use |
| --- | --- | --- | --- |
| Plain vector retrieval | *(none)* | `cluster_aware: false`, `expand_graph: false` | Ad-hoc questions, no graph context needed |
| Graph-expanded | `--expand-graph` | `cluster_aware: false`, `expand_graph: true` | After `unstructured_only` entity resolution |
| Cluster-aware | `--cluster-aware` | `cluster_aware: true`, `expand_graph: true` | After `hybrid` entity resolution — recommended final validation |

#### Example: comparing all three modes on a cross-entity relationship question

The following question is a strong test case for cluster-aware retrieval because it asks the model
to surface **direct and indirect relationships** among four distinct companies. Evidence for these
relationships may be spread across many document chunks with no direct co-occurrence.
Plain vector retrieval cannot aggregate graph-level co-occurrence; graph-expanded retrieval adds
claim and mention context; only cluster-aware retrieval additionally traverses `ALIGNED_WITH` edges
and `ResolvedEntityCluster` membership, which is where multi-entity relationship coherence lives.

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>

# Mode 1 — plain vector retrieval (no graph context)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --output-dir demo/artifacts_compare/q3/plain \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"

# Mode 2 — graph-expanded (claim + mention context, no cluster awareness)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --expand-graph \
    --output-dir demo/artifacts_compare/q3/expand_graph \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"

# Mode 3 — cluster-aware (full hybrid enrichment; run after hybrid entity resolution)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --cluster-aware \
    --output-dir demo/artifacts_compare/q3/cluster_aware \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"
```

**Why this question tests cluster-aware retrieval:** A four-company relationship question requires
aggregating evidence spread across many chunks where the companies may not co-occur directly.
Cluster-aware retrieval traverses `ALIGNED_WITH` edges linking each company's
`ResolvedEntityCluster` to its `CanonicalEntity`, surfacing indirect connections that plain or
graph-expanded retrieval cannot reach.

**What to look for in the output manifests**
(`demo/artifacts_compare/q3/<mode>/runs/<run_id>/retrieval_and_qa/manifest.json`):

| Field | Plain | Graph-expanded | Cluster-aware |
| --- | --- | --- | --- |
| `cluster_aware` | `false` | `false` | `true` |
| `expand_graph` | `false` | `true` | `true` |
| `citation_quality.evidence_level` | may be `"partial"` | `"partial"` or `"full"` | expect `"full"` |
| `all_answers_cited` | may be `false` | may be `false` | expect `true` |
| Network structure in answer | likely absent or fragmented | present but isolated per chunk | direct **and** indirect links across entities |

Focus on `stages.retrieval_and_qa.hits` (chunk count) and `stages.retrieval_and_qa.retrieval_results`
(content) to compare how many chunks were retrieved and whether the same companies appear together
in a single coherent answer across all three modes.

### Inspect the output manifest

```text
demo/artifacts/runs/<run_id>/retrieval_and_qa/manifest.json
```

Useful Q&A manifest fields include (all nested under `stages.retrieval_and_qa`):

- `stages.retrieval_and_qa.all_answers_cited`
- `stages.retrieval_and_qa.citation_fallback_applied`
- `stages.retrieval_and_qa.citation_quality`
- `stages.retrieval_and_qa.retrieval_results`
- `stages.retrieval_and_qa.cluster_aware` — `true` when `--cluster-aware` was passed
- `stages.retrieval_and_qa.expand_graph` — `true` when `--expand-graph` or `--cluster-aware` was passed

To diagnose which retrieval scope was actually applied (useful when debugging `--all-runs` or unexpected results), inspect:

- `stages.retrieval_and_qa.retrieval_scope.run_id` — the run id used (or `null` for all-runs)
- `stages.retrieval_and_qa.retrieval_scope.source_uri` — the source filter applied (or `null` for whole-database)
- `stages.retrieval_and_qa.retrieval_scope.all_runs` — whether all-runs mode was active

---

## Hybrid enrichment comparison tests

This section provides targeted comparison queries and a QA checklist to help you evaluate post-enrichment retrieval quality and confirm the value of the hybrid alignment pass.

### Before you start: capture a baseline

Run the same question **before** hybrid alignment (plain or graph-expanded mode) and again **after** hybrid alignment (cluster-aware mode). The two manifests let you compare citation quality, entity clustering, and answer focus side-by-side.

```bash
# Baseline — pre-hybrid (non-cluster-aware), graph-expanded (no hybrid alignment yet)
export UNSTRUCTURED_RUN_ID=<your_unstructured_run_id>
python -m demo.run_demo --live ask --run-id $UNSTRUCTURED_RUN_ID --expand-graph \
    --question "What does the document say about Endeavor and MercadoLibre?"

# Run hybrid alignment (reuses the same UNSTRUCTURED_RUN_ID as above)
python -m demo.run_demo --live resolve-entities --resolution-mode hybrid

# Post-hybrid — cluster-aware retrieval traverses ALIGNED_WITH edges
python -m demo.run_demo --live ask --run-id $UNSTRUCTURED_RUN_ID --cluster-aware \
    --question "What does the document say about Endeavor and MercadoLibre?"
```

**Important:** The `ask` command writes its Q&A manifest to  
`<output-dir>/runs/<run_id>/retrieval_and_qa/manifest.json` and will overwrite any existing
file at that path. To compare **baseline** vs **post-hybrid** Q&A manifests side-by-side, either:

- Copy the baseline manifest to a different location or filename immediately after running the
  baseline `ask`, for example:

  ```bash
  cp <output-dir>/runs/$UNSTRUCTURED_RUN_ID/retrieval_and_qa/manifest.json \
     <output-dir>/runs/$UNSTRUCTURED_RUN_ID/retrieval_and_qa/manifest.baseline.json
  ```

- **Or** run the post-hybrid `ask` with a different `--output-dir` so its manifest is written to a
  separate directory.

Once you have both files saved, compare
`stages.retrieval_and_qa.citation_quality` and `stages.retrieval_and_qa.retrieval_results`
across the two manifests to measure the impact of hybrid enrichment.

### Comparison query 1 — Canonical-entity bridging

Tests whether the hybrid pass surfaces canonical-entity connections across co-occurring mentions.

```bash
python -m demo.run_demo --live ask --run-id $UNSTRUCTURED_RUN_ID --cluster-aware \
    --question "How is MercadoLibre connected to Endeavor, MercadoPago, and Marcos Galperin?"
```

**What to look for after hybrid alignment:**
- Answer sentences reference relationships among all four entities rather than treating each mention in isolation.
- Citations span multiple chunks, showing that cluster-aware retrieval aggregated evidence across the document.
- `citation_quality.evidence_level` is `"full"` and `all_answers_cited` is `true`.

### Comparison query 2 — Ambiguous person / network context

Tests whether hybrid alignment resolves ambiguous person mentions and surfaces their network role.

```bash
python -m demo.run_demo --live ask --run-id $UNSTRUCTURED_RUN_ID --cluster-aware \
    --question "Who is Marcos Galperin, and what role does he play in the Endeavor Argentina network?"
```

**What to look for after hybrid alignment:**
- The answer identifies Marcos Galperin unambiguously (via the canonical entity) rather than returning fragmented or hedged results.
- The Endeavor Argentina network context is drawn from `ALIGNED_WITH` edges connecting the `ResolvedEntityCluster` for "Marcos Galperin" to its `CanonicalEntity` counterpart.
- Compare with the same query run without `--cluster-aware` to see whether the network context is absent or degraded in non-cluster-aware mode.

### Comparison query 3 — Cross-company relationship mapping

Tests whether hybrid alignment improves coherence when the question spans multiple canonical entities.
Run all three modes so you can compare manifests side-by-side (each `--output-dir` is distinct to
prevent overwriting):

```bash
# Mode 1 — plain vector retrieval (baseline, no graph context)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --output-dir demo/artifacts_compare/q3/plain \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"

# Mode 2 — graph-expanded (claim + mention context, no cluster awareness)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --expand-graph \
    --output-dir demo/artifacts_compare/q3/expand_graph \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"

# Mode 3 — cluster-aware (full hybrid enrichment; run after hybrid entity resolution)
python -m demo.run_demo --live ask \
    --run-id "$UNSTRUCTURED_RUN_ID" \
    --cluster-aware \
    --output-dir demo/artifacts_compare/q3/cluster_aware \
    --question "What relationships does the document describe among MercadoLibre, Globant, Ripio, and Xapo?"
```

**What to look for after hybrid alignment:**
- Distinct, non-overlapping answers for each company rather than a single merged or hallucinated summary.
- Each company's claim is independently cited; `citation_quality.citation_warnings` should be empty.
- Compare `stages.retrieval_and_qa.citation_quality` and `retrieval_results` across all three manifests
  to observe how answer focus and citation density improve with each mode.

### What improvements to look for

| Dimension | Before hybrid alignment | After hybrid alignment (`--cluster-aware`) |
| --- | --- | --- |
| **Citation quality** | Citations may reference isolated chunk snippets | Citations span richer multi-chunk evidence via cluster membership |
| **Entity clustering** | Mentions of "Marcos Galperin" and "Galperin" may surface as separate entities | Same surface forms are grouped under one `ResolvedEntityCluster` aligned to the canonical entity |
| **Answer focus** | Answers may mix unrelated entities present in the same chunks | Cluster-aware expansion scopes graph context to the queried entity's cluster, reducing topic bleed |
| **Canonical bridging** | Co-occurrence associations may be implicit | `ALIGNED_WITH` edges surface explicit canonical-entity connections as graph context |

### QA checklist

Use this checklist to confirm that hybrid enrichment is working correctly end-to-end:

- [ ] If you expect canonical alignment, you have already run structured ingest (e.g., `ingest-structured`) and canonical `CanonicalEntity` nodes exist.
- [ ] `resolve-entities --resolution-mode hybrid` completes successfully; when canonical entities are present, `aligned_clusters > 0` is expected.
- [ ] `aligned_clusters` in the entity resolution manifest is greater than `0` **when canonical entities are present**; `clusters_pending_alignment` is `0` or a small number (unmatched entity texts have no canonical counterpart — this is expected)
- [ ] `ask --cluster-aware` manifest records `cluster_aware: true` and `expand_graph: true`
- [ ] `citation_quality.evidence_level` is `"full"` for all three comparison queries above
- [ ] `all_answers_cited` is `true` for all three comparison queries
- [ ] `citation_fallback_applied` is `false` for all three comparison queries
- [ ] Comparison query 1 (bridging) mentions at least two of the four entities in a single coherent answer
- [ ] Comparison query 2 (person/network) names Marcos Galperin unambiguously with Endeavor Argentina context
- [ ] Comparison query 3 (cross-company) returns distinct claims for at least two of the four companies, each with its own citation
### CLI walkthrough reference

For the complete step-by-step CLI walkthrough, see [Recommended workflow](#recommended-workflow) and [Post-hybrid cluster-aware Q&A](#post-hybrid-cluster-aware-qa-recommended-final-validation-step).

Key flags for hybrid enrichment validation:

| Flag | Stage | Purpose |
| --- | --- | --- |
| `--resolution-mode hybrid` | `resolve-entities` | Run clustering plus ALIGNED_WITH edge creation to canonical entities |
| `--cluster-aware` | `ask` | Include `ResolvedEntityCluster` membership and `ALIGNED_WITH` edges during retrieval (implies `--expand-graph`) |
| `--run-id <RUN_ID>` | `ask` | Scope retrieval to the exact run that was enriched (recommended for validation) |
| `--expand-graph` | `ask` | Add graph context without cluster awareness — use as the pre-hybrid baseline |

> **Recommendation:** always pass `--run-id <UNSTRUCTURED_RUN_ID>` when running validation queries after hybrid alignment. This ensures retrieval targets the exact run that was enriched and avoids ambiguity from implicit latest-run selection.

---

## Troubleshooting

### `resolved: 0` in the entity resolution manifest

If the entity resolution manifest shows `resolved: 0`, this is **expected and correct** when running in `unstructured_only` or `hybrid` mode.

The `resolved` field counts `RESOLVES_TO` edges (direct mention-to-canonical-entity links), which are only created in `structured_anchor` mode. In `unstructured_only` mode, mentions are grouped into clusters via `MEMBER_OF` edges — not `RESOLVES_TO`.

To confirm clustering worked, check `mentions_clustered` (should equal `mentions_total`) and `mentions_unclustered` (should be `0`). See [Resolution and retrieval semantics](#resolution-and-retrieval-semantics) for the full manifest field reference.

### `ask` returned something unexpected

Check the printed retrieval scope first.

Examples:

```text
Using retrieval scope: run=unstructured_ingest-...
Using retrieval scope: all runs in database
```

If needed, force an explicit run:

```bash
python -m demo.run_demo --live ask --run-id <RUN_ID> --question "..."
```

### I want to query the whole database

Use:

```bash
python -m demo.run_demo --live ask --all-runs --question "..."
```

This removes both the `run_id` filter and the `source_uri` filter, querying all chunks in the database regardless of which run or document they came from.

### I want reproducible results for debugging

Use a fixed run id:

```bash
python -m demo.run_demo --live ask --run-id <RUN_ID> --question "..."
```

### `extract-claims` or `resolve-entities` needs a run id

Set:

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
```

These stages operate within an existing unstructured ingest scope rather than creating a new one.

### Where do I inspect artifacts?

Look under:

```text
demo/artifacts/runs/
```

The most useful file for Q&A debugging is typically:

```text
demo/artifacts/runs/<run_id>/retrieval_and_qa/manifest.json
```

---

## Conceptual model

- **Unstructured-first posture**: unstructured PDF ingest, claim extraction, entity resolution, and Q&A form a complete standalone workflow. Structured ingest is optional and additive.
- **Independent ingestion runs**: structured ingest and unstructured/PDF ingest are separate producer runs with separate `run_id` boundaries; neither implies the other must also run.
- **Two-pipeline unstructured flow**: `extract-claims` runs within the same `run_id` scope established by `ingest-pdf` — it is not a separate run.
- **Layered graph model**: source assertions are preserved as written (with provenance), while canonical/resolved views are derived in a separate layer and may be revised over time.
- **Structured ingest is additive enrichment**: `CanonicalEntity` nodes from structured ingest are not the sole identity anchor. Entity resolution can cluster mentions without them (`unstructured_only`), and structured alignment is an optional enrichment pass (`hybrid`).
- **Explicit convergence**: cross-source links are an optional resolution step; they must be explainable and non-destructive.
- **Batch mode is convenience only**: `ingest` runs the full unstructured-first sequence in one command. The batch manifest has its own `run_id`; internally, stages share two producer run scopes — a `structured_ingest_run_id` and an `unstructured_ingest_run_id`.

### Graph layers

| Layer | Nodes | Written by | Mutable? |
| --- | --- | --- | --- |
| Lexical | `Document`, `Chunk` | `ingest-pdf` | Stable for the run — never overwritten by downstream stages |
| Extraction | `ExtractedClaim`, `EntityMention` | `extract-claims` | Non-destructive additions only |
| Resolution | `ResolvedEntityCluster` (provisional), `UnresolvedEntity` (legacy/unused fallback; kept for cleanup/back-compat) | `resolve-entities` | Non-destructive additions only; creates `MEMBER_OF` edges (all modes) and optionally `ALIGNED_WITH` edges to `CanonicalEntity` nodes (hybrid mode) |
| Structured (optional) | `Claim`, `Fact`, `Relationship`, `Source`, `CanonicalEntity` | `ingest-structured` | Non-destructive additions only; structured ingest is optional enrichment |

Every `Chunk` node includes ingest metadata fields such as `run_id`, `source_uri`, `dataset_id`, and positional provenance fields. `Document` nodes include the same ingest metadata.

---

## Resolution and retrieval semantics

This section explains the exact meaning of each processing phase and the manifest fields that track it. Understanding these semantics prevents common misinterpretations — in particular, interpreting `resolved: 0` as a failure or assuming that the default `ask` command uses hybrid enrichment when it does not.

### Mention extraction

`extract-claims` reads `Chunk` nodes for the active `run_id` and creates `EntityMention` nodes linked back to their source chunk. No clustering or alignment occurs at this stage. Each mention is an independent assertion tied to a specific chunk, with full provenance.

### Unstructured clustering (`resolve-entities` — default mode)

`resolve-entities` in `unstructured_only` mode (the default) groups `EntityMention` nodes into `ResolvedEntityCluster` nodes via `MEMBER_OF` edges. Clustering is driven entirely by the extracted text — normalization, abbreviation detection, and fuzzy matching — with no canonical entity catalog required.

**Understanding `resolved: 0` in unstructured mode:**

The manifest field `resolved` counts `RESOLVES_TO` edges (direct mention-to-canonical-entity links). `RESOLVES_TO` edges are only created in `structured_anchor` mode. In `unstructured_only` mode **no `RESOLVES_TO` edges are created by design**, so `resolved: 0` is the **expected and correct value** — it is not an error or partial failure.

To confirm that clustering succeeded, check:

| Manifest field | What it means | Expected after a successful unstructured run |
| --- | --- | --- |
| `resolved` | Mentions linked directly to a `CanonicalEntity` via `RESOLVES_TO` | `0` (correct in unstructured mode) |
| `mentions_clustered` | Mentions assigned to a `ResolvedEntityCluster` via `MEMBER_OF` | Should equal `mentions_total` |
| `mentions_unclustered` | Mentions with no cluster assignment | Should be `0` |
| `clusters_created` | Number of distinct clusters formed | One per unique `(entity_type, normalized_text)` pair |

### Structured ingest (optional, additive)

`ingest-structured` creates `CanonicalEntity` nodes from CSV fixtures. These nodes are independent of any unstructured run and carry their own `run_id`. Structured ingest is entirely optional — the graph is meaningful and Q&A is available without it.

### Hybrid alignment (`resolve-entities --resolution-mode hybrid`)

Hybrid alignment is a two-stage process. First, it runs the full unstructured clustering pass (identical to `unstructured_only`). Second, it enriches each resulting `ResolvedEntityCluster` with an `ALIGNED_WITH` edge to a matching `CanonicalEntity` node where a label-exact or alias-exact match exists.

**What changes after hybrid alignment:**

| Manifest field | What it means |
| --- | --- |
| `aligned_clusters` | Clusters that received an `ALIGNED_WITH` edge to a canonical entity |
| `clusters_pending_alignment` | Clusters with no canonical match — not an error; means those cluster texts had no equivalent in the structured data |
| `mentions_in_aligned_clusters` | Mentions that belong to an aligned cluster (reachable via `MEMBER_OF → ALIGNED_WITH`) |
| `alignment_breakdown` | Count of `ALIGNED_WITH` edges grouped by alignment strategy (`label_exact`, `alias_exact`) |

**What does not change after hybrid alignment:**

- `resolved` remains `0` — hybrid mode still uses `MEMBER_OF` + `ALIGNED_WITH`, not `RESOLVES_TO`
- Clustering semantics are unchanged and **non-destructive**: hybrid reruns the same unstructured clustering and upserts `MEMBER_OF` edges, but does not delete any existing `MEMBER_OF` relationships
- `Chunk` and `EntityMention` nodes from the unstructured run are not deleted or remapped — their text and identifiers remain stable across `unstructured_only` and `hybrid` runs for the same `run_id`
- Plain vector retrieval (without `--cluster-aware`) does **not** traverse `ALIGNED_WITH` edges — see below

### Evidence-grounded retrieval and final Q&A mode

The default `ask` command uses **plain run-scoped vector retrieval** over `Chunk` text. It does **not** automatically use cluster membership or hybrid enrichment, even after hybrid alignment has run.

| `ask` flag | Retrieval mode | Graph layers consulted |
| --- | --- | --- |
| *(none)* | Plain vector retrieval | `Chunk` text only |
| `--expand-graph` | Graph-expanded | `Chunk` + `ExtractedClaim`, `EntityMention`, canonical entity context (when `RESOLVES_TO` edges exist) |
| `--cluster-aware` | Cluster-aware (implies `--expand-graph`) | All of the above + `ResolvedEntityCluster` membership and canonical entities via `ALIGNED_WITH` edges (no `RESOLVES_TO` in unstructured/hybrid flows) |

To confirm that hybrid alignment is surfaced during retrieval, pass `--cluster-aware`. The manifest records `cluster_aware: true` and `expand_graph: true` when this flag is active, confirming that cluster and alignment context was consulted.

**Recommended validation flow:**

```bash
# 1. Run hybrid alignment against the unstructured-only run
UNSTRUCTURED_RUN_ID=<UNSTRUCTURED_RUN_ID> \
  python -m demo.run_demo --live resolve-entities --resolution-mode hybrid

# 2. Validate with explicit run id and cluster-aware retrieval
python -m demo.run_demo --live ask --run-id <UNSTRUCTURED_RUN_ID> --cluster-aware \
    --question "What does the document say about Endeavor and MercadoLibre?"
```

Using `--run-id` explicitly ensures the validation targets the exact run you just enriched rather than relying on implicit latest-run selection.

---

## Run scopes and manifests

### Run ID provenance

- The demo supplies its own stage run scope (`run_id`, plus `dataset_id`/`source_uri` when applicable) via `document_metadata` for PDF ingest, persisted on `Document`/`Chunk` nodes.
- Vendor pipelines also emit an orchestration `run_id` (`PipelineResult.run_id` / `RunContext.run_id`) for callbacks; the demo does **not** inject that vendor-orchestration id into graph nodes.
- Entity resolution uses the same `run_id` as the unstructured/PDF ingest stages — it is part of the unstructured run scope, not a separate run boundary. Conceptually, it is **run-scoped post-ingest normalization** over the previously ingested PDF-derived nodes: it adds resolved entities and links while preserving the original lexical layer and its provenance.
- **Retrieval is run-scoped by default**: vector search is constrained to `Chunk` nodes matching the active `run_id`. The `ask` command defaults to using `UNSTRUCTURED_RUN_ID` when set and otherwise queries the latest run (or when `--latest` is specified); you can also pass `--run-id <RUN_ID>` or `--all-runs` to override the scope.

#### Why structured ingest uses a separate run_id

`ingest-structured` creates `CanonicalEntity` nodes (and related structured nodes) from CSV fixtures. These entities are not derived from a specific unstructured document — they represent a standalone curated dataset that can be aligned to *any* unstructured run. Scoping them to a separate `run_id` preserves this independence: the structured catalog can be ingested once and then aligned to multiple unstructured runs over time without re-ingesting.

**Why hybrid alignment still targets the unstructured run_id:**

Hybrid alignment enriches `ResolvedEntityCluster` nodes that were created by a specific unstructured run. The `ALIGNED_WITH` edges it creates are scoped by the unstructured `run_id` (plus an `alignment_version` property), so alignment results remain traceable to the exact unstructured run they enrich. Targeting the unstructured `run_id` also means that validation steps (e.g. `ask --run-id <UNSTRUCTURED_RUN_ID> --cluster-aware`) consistently scope both retrieval and cluster expansion to the same run.

> **Recommendation:** Prefer passing `--run-id <UNSTRUCTURED_RUN_ID>` explicitly when running validation steps after hybrid alignment. This avoids ambiguity from implicit latest-run selection and helps ensure you are validating the exact run that was enriched, while still allowing `--latest` in workflows where implicit latest-run selection is desired.

### Manifest layout

| Mode | Manifest path | Key fields |
| --- | --- | --- |
| Batch (`ingest`) | `<output-dir>/manifest.json` | `run_id`, `run_scopes.structured_ingest_run_id`, `run_scopes.unstructured_ingest_run_id`; batch stages include `entity_resolution_unstructured_only`, `retrieval_and_qa_unstructured_only`, `entity_resolution_hybrid`, and `retrieval_and_qa` |
| Independent stage (`ingest-structured`, `ingest-pdf`) | `<output-dir>/runs/<run_id>/<stage_name>/manifest.json` | `run_id`, `run_scopes.batch_mode: single_independent_run`, one of `structured_ingest_run_id` / `unstructured_ingest_run_id` |
| Derived stage (`extract-claims`, `resolve-entities`, `ask`) | `<output-dir>/runs/<run_id>/<stage_name>/manifest.json` | `run_id`, `run_scopes.unstructured_ingest_run_id` (ingest run id for run-scoped stages; `null` for `--all-runs`); for `ask`, resolved retrieval scope under `stages.retrieval_and_qa.retrieval_scope.{run_id,all_runs,source_uri}` |

Each stage records a `run_id` in its manifest. Producer stages generate a new run scope; derived stages intentionally share the producer run scope where appropriate.

---

## Citation behavior

Q&A answers must:

- use **retrieved context only**
- avoid hallucinated or uncited claims
- emit **project citation tokens** for each piece of answer content
- trace every assertion back to a `Chunk` node in the lexical layer

Citation token format:

```text
[CITATION|chunk_id=...|run_id=...|source_uri=...|chunk_index=...|page=...|start_char=...|end_char=...]
```

The citation contract is defined in [zoomlytics/power-atlas#159](https://github.com/zoomlytics/power-atlas/issues/159).

### Post-generation validation

Post-generation validation in `demo/stages/retrieval_and_qa.py` enforces that every sentence and bullet ends with at least one citation token.

When uncited segments are detected:

- `citation_quality.evidence_level` is set to `"degraded"`
- the `answer` field is replaced with a fallback prefixed with `Insufficient citations detected: `
- the original output is preserved in `raw_answer`
- a warning is appended to `citation_quality.citation_warnings`

### Message history

Message history is passed to the LLM for conversational context only and is never a source of answer evidence.

---

## Reset behavior

`demo/reset_demo_db.py` (and `python -m demo.run_demo --live reset --confirm`) performs a **demo-scoped full graph wipe** of the configured database.

### What is deleted

All nodes with the following labels and **all their relationships** (`DETACH DELETE`):

| Label | Written by |
| --- | --- |
| `Document` | `ingest-pdf` |
| `Chunk` | `ingest-pdf` |
| `CanonicalEntity` | `ingest-structured` |
| `Claim` | `ingest-structured` |
| `Fact` | `ingest-structured` |
| `Relationship` | `ingest-structured` |
| `Source` | `ingest-structured` |
| `ExtractedClaim` | `extract-claims` |
| `EntityMention` | `extract-claims` |
| `ResolvedEntityCluster` | `resolve-entities` |
| `UnresolvedEntity` | `resolve-entities` (legacy/back-compat) |

The index `demo_chunk_embedding_index` (vector, `Chunk.embedding`, 1536 dims) is also dropped if present.

In addition to the node-level `DETACH DELETE`, the reset explicitly removes any
surviving stale `:HAS_SUBJECT` / `:HAS_OBJECT` edges left from pre-v0.2 demo
runs.  These relationship types were retired in v0.2 (replaced by
`:HAS_SUBJECT_MENTION` / `:HAS_OBJECT_MENTION`).  The count of removed stale
edges is reported under `stale_participation_edges_deleted` in the reset report.

> **⚠ Non-migratability of pre-v0.2 graphs.**  If your graph was produced
> before v0.2, it contains `:HAS_SUBJECT`/`:HAS_OBJECT` edges that cannot be
> automatically migrated.  Run a full reset and re-run the pipeline
> (ingest-pdf → extract-claims → resolve-entities) to produce a clean v0.2
> graph with `:HAS_SUBJECT_MENTION`/`:HAS_OBJECT_MENTION` edges.

### What is preserved

- nodes with labels not in the list above
- indexes and constraints not named above
- other Neo4j databases on the same server

### Idempotency

Reset is safe to run repeatedly. If the graph is already empty or the index is absent, the script completes without error and records warnings in the reset report.  The `idempotent` flag in the report is `true` only when no nodes, no stale participation edges, and no indexes were changed.

---

## Fixtures and reproducibility

- `fixtures/structured/*.csv` — claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf` — canonical source PDF
- `fixtures/manifest.json` — dataset contract, provenance, and license note

---

## CLI reference

The orchestrator CLI exposes the following subcommands:

- `lint-structured`
- `ingest-structured`
- `ingest-pdf`
- `extract-claims`
- `resolve-entities`
- `ask`
- `reset`
- `ingest`

### Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes (live) | Required for live `ingest-pdf`, `extract-claims`, and `ask` |
| `NEO4J_URI` | No | Defaults to `neo4j://localhost:7687` |
| `NEO4J_USERNAME` | No | Defaults to `neo4j`. Note: `NEO4J_USERNAME`, not `NEO4J_USER` |
| `NEO4J_PASSWORD` | Yes (live) | |
| `NEO4J_DATABASE` | No | Defaults to `neo4j` |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o-mini` if unset |
| `UNSTRUCTURED_RUN_ID` | Required for independent `extract-claims` and `resolve-entities`; optional for `ask` | For `ask`, `--run-id`, `--latest`, and `--all-runs` are preferred |

Demo vector index: `demo_chunk_embedding_index` (label: `Chunk`, property: `embedding`, dimensions: `1536`).

---

## Maintainer notes

> This section is for contributors implementing or extending the demo.

### Two-pipeline unstructured flow

Pipeline 1 (`ingest-pdf`) writes the **lexical layer**:

- loads and splits the PDF into chunks (`PageAwareFixedSizeSplitter`)
- embeds chunks and writes vector-index-ready chunk data (`OpenAIEmbeddings`)
- writes `Document` and `Chunk` nodes with run-scoped provenance
- treats lexical nodes as append-only for the run

Pipeline 2 (`extract-claims`) reads the lexical layer for the same `run_id` and adds the **derived graph**:

- reads `Chunk` nodes via `RunScopedNeo4jChunkReader`
- runs `LLMEntityRelationExtractor(use_structured_output=True)` over those chunks
- writes `ExtractedClaim` and `EntityMention` nodes linked to `Chunk`
- does **not** modify or re-embed any `Document` or `Chunk` nodes

### Vendor alignment map

> Before adding custom code, check the relevant vendor example first.

| Demo stage | Vendor anchor(s) | Notes |
| --- | --- | --- |
| **Ingest / lexical graph** (`ingest-pdf`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config.yaml`<br>`vendor-resources/examples/database_operations/create_vector_index.py` | Config-driven in live mode via `demo/config/pdf_simple_kg_pipeline.yaml`. Creates `demo_chunk_embedding_index` on `:Chunk(embedding)` (1536 dims). Uses `NEO4J_USERNAME` (not `NEO4J_USER`). |
| **Chunk reading** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/chunk_reader/neo4j_chunk_reader.py` | Demo wraps `Neo4jChunkReader` in `RunScopedNeo4jChunkReader` to filter by `run_id` and optionally `source_uri`. |
| **Extraction** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/extractors/llm_entity_relation_extractor_with_structured_output.py` | Uses `LLMEntityRelationExtractor(use_structured_output=True)` with a demo-owned claim schema. |
| **Retrieval** (`ask`) | `vendor-resources/examples/retrieve/vector_cypher_retriever.py` | `VectorCypherRetriever` with run-scoped pre-filtering. Returns citation provenance fields. |
| **GraphRAG / Q&A** (`ask`) | `vendor-resources/examples/question_answering/graphrag.py` | Standard `GraphRAG(retriever, llm, prompt_template=...)` contract with a citation-oriented prompt suffix. |
| **Structured ingest** (`ingest-structured`) | vendor examples adapted to demo-owned structured ingest logic | Demo retains custom provenance and canonicalization behavior. |

### Config-driven vs custom checklist

- [x] **Config-driven**: PDF ingest pipeline shape (`SimpleKGPipeline` via `PipelineRunner`) declared in `demo/config/pdf_simple_kg_pipeline.yaml`, aligned to vendor `from_config_files` examples.
- [x] **Config-driven**: Retrieval/citation index contract uses `demo_chunk_embedding_index` on `Chunk.embedding` (1536 dims), pinned via `OpenAIEmbeddings` model `text-embedding-3-small` and `contract.chunk_embedding.dimensions`.
- [x] **Config-driven**: `python -m demo.run_demo --live ingest-pdf` executes `PipelineRunner.from_config_file(...)` against `demo/config/pdf_simple_kg_pipeline.yaml`.
- [x] **Custom**: Structured ingest live path emits run-scoped provenance metadata without mutating source assertions (tracked from [zoomlytics/power-atlas#151](https://github.com/zoomlytics/power-atlas/issues/151)).
- [x] **Custom**: `extract-claims` uses `RunScopedNeo4jChunkReader` to constrain extraction input to the active `run_id`.
- [ ] **Planned**: Retrieval and answer synthesis should consume explicit run-scoped provenance links and avoid implicit structured↔unstructured coupling.
- [x] **Custom by design**: Structured CSV ingest, deterministic canonical key resolution, and provenance-specific graph expansion remain demo-owned logic.

### Citation validation internals

Post-generation validation (`_check_all_answers_cited` / `_split_into_segments` in `demo/stages/retrieval_and_qa.py`) applies sentence-level segmentation:

1. Split answer on newlines.
2. Bullet lines (`-`, `*`, `•`, or `N. `) are treated as atomic units — one citation at the end of the bullet is sufficient.
3. Non-bullet lines are further split into sentence-like segments at `[.!?]` boundaries followed by an uppercase letter or a non-citation bracket. `[CITATION|…]` tokens are not split-points (negative lookahead `(?!CITATION\|)`); non-citation brackets such as `[Note]` or `[1]` are.

Sentence-level splitting is needed because a multi-sentence paragraph ending with a single citation would pass a line-level check but fail sentence-level (the first sentence has no citation).

### Reset maintenance note

Keep `DEMO_NODE_LABELS` and `DEMO_OWNED_INDEXES` in `demo/reset_demo_db.py` in sync with `demo/config/pdf_simple_kg_pipeline.yaml` and `demo/contracts/pipeline.py` whenever new demo-owned labels or indexes are introduced.
