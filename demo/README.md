# Demo Workflow (dataset v1)

Self-contained demo workflow under `demo/` for evidence-driven influence research with structured and unstructured artifacts.

---

## Quickstart for first-time users

If you are running the demo for the first time, start here.

### What this demo does

The demo supports:

- **structured ingest** from CSV fixtures
- **unstructured ingest** from a PDF fixture
- **claim extraction** from previously ingested PDF chunks
- **entity resolution** over extracted mentions
- **retrieval and citation-grounded Q&A** over ingested material

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

Run PDF ingest:

```bash
python -m demo.run_demo --live ingest-pdf
```

Then ask a question against the latest unstructured ingest run found in the database (use `--latest` to ensure this, even if `UNSTRUCTURED_RUN_ID` is set):

```bash
python -m demo.run_demo --live ask --latest --question "What does the document say about Endeavor and MercadoLibre?"
```

You can also ask across all ingested unstructured runs:

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

Successful runs also write manifests under:

```text
demo/artifacts/runs/<run_id>/<stage_name>/manifest.json
```

For successful Q&A runs, the manifest should normally show:

- `all_answers_cited: true`
- `citation_fallback_applied: false`
- `citation_quality.evidence_level: "full"`

---

## Overview

The demo exercises two independent ingestion pipelines — structured CSV ingest and unstructured PDF ingest — followed by claim extraction, entity resolution, and citation-grounded Q&A retrieval.

The most important idea for first-time users is:

- **producer stages** create or write new run-scoped data
- **derived stages** operate within an existing producer run scope
- **Q&A retrieval, in `--live` mode, uses `UNSTRUCTURED_RUN_ID` if set, otherwise the latest run by default**, and can also target a specific run or all runs

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
```

Without `--confirm`, the standalone script exits with an error and the CLI reset path prints instructions only.

Both reset paths write a JSON reset report to the demo artifacts directory.

### Step 2 — Run ingestion stages independently (recommended)

```bash
python -m demo.run_demo --dry-run ingest-structured
python -m demo.run_demo --dry-run ingest-pdf
```

Producer stages (`ingest-structured`, `ingest-pdf`) each generate a new `run_id` and write a stage manifest to:

```text
demo/artifacts/runs/<run_id>/<stage_name>/manifest.json
```

Here, `<stage_name>` is the on-disk stage directory name, which does not always match the CLI subcommand. The mappings are:

- `ingest-structured` → `structured_ingest`
- `ingest-pdf` → `pdf_ingest`
- `extract-claims` → `claim_and_mention_extraction`
- `resolve-entities` → `entity_resolution`
- `ask` → `retrieval_and_qa`

For a real unstructured workflow, use:

```bash
python -m demo.run_demo --live ingest-pdf
```

For a real structured workflow, use:

```bash
python -m demo.run_demo --live ingest-structured
```

### Step 3 — Run claim extraction (same run scope as `ingest-pdf`)

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
python -m demo.run_demo --dry-run extract-claims
```

`extract-claims` runs within the existing unstructured ingest run scope established by `ingest-pdf`. It does not create a separate producer run.

In live mode, `extract-claims` reads `Chunk` nodes for the selected `run_id`. In `--dry-run` mode it returns a stub summary.

### Step 4 — Optional stages

These stages also operate within an existing unstructured ingest run scope.

- For `resolve-entities` (and `extract-claims` if you rerun it), set `UNSTRUCTURED_RUN_ID` when running them independently (without first running Step 3 in the same process) so they know which unstructured ingest run to target.
- For `ask`, retrieval scope is selected as described below; you can optionally set `UNSTRUCTURED_RUN_ID` if you want to target a specific unstructured run without passing `--run-id`.

```bash
# Reuse the run id from `ingest-pdf` / `extract-claims`
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf or extract-claims output>

# Entity resolution
python -m demo.run_demo --dry-run resolve-entities

# Retrieval and Q&A
python -m demo.run_demo --dry-run ask
```

#### Retrieval scope selection for `ask`

The `ask` command supports explicit retrieval scope flags:

| Flag | Behavior |
| --- | --- |
| *(none)* | Default: if `UNSTRUCTURED_RUN_ID` is set, use that run; otherwise same as `--latest` in `--live` mode |
| `--latest` | In `--live` mode: retrieve from the latest successful unstructured ingest run. In `--dry-run` mode: behaves like the default (uses `UNSTRUCTURED_RUN_ID` if set; otherwise no run id is used and the CLI prints `run=(none — dry-run placeholder)`). |
| `--run-id <RUN_ID>` | Retrieve from a specific ingest run |
| `--all-runs` | Retrieve across all ingested data with no run filter |

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

**Precedence:** `--run-id` / `--latest` / `--all-runs` CLI flags → `UNSTRUCTURED_RUN_ID` env var → implicit latest successful unstructured ingest run (default).

For first-time users, prefer the CLI flags over environment-variable-based run selection.

**All-runs mode note:** citations in `--all-runs` mode may refer to chunks from different ingest runs. Each citation includes its own `run_id`.

### Convenience batch mode (alternative to steps 2–4)

```bash
python -m demo.run_demo --dry-run ingest
```

Runs all stages as sequential independent runs with a single command. The batch manifest has its own `run_id`, while producer stages still preserve separate structured and unstructured run scopes internally.

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

### Ask across all ingested unstructured runs

```bash
python -m demo.run_demo --live ask --all-runs --question "What does the document say about Endeavor and MercadoLibre?"
```

### Inspect the output manifest

```text
demo/artifacts/runs/<run_id>/retrieval_and_qa/manifest.json
```

Useful Q&A manifest fields include:

- `all_answers_cited`
- `citation_fallback_applied`
- `citation_quality`
- `retrieval_scope`
- `retrieval_results`

---

## Troubleshooting

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

### I want to query everything, not just one run

Use:

```bash
python -m demo.run_demo --live ask --all-runs --question "..."
```

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

- **Independent ingestion runs**: structured ingest and unstructured/PDF ingest are separate producer runs with separate `run_id` boundaries; neither implies the other must also run.
- **Two-pipeline unstructured flow**: `extract-claims` runs within the same `run_id` scope established by `ingest-pdf` — it is not a separate run.
- **Layered graph model**: source assertions are preserved as written (with provenance), while canonical/resolved views are derived in a separate layer and may be revised over time.
- **Explicit convergence**: cross-source links are an optional resolution step; they must be explainable and non-destructive.
- **Batch mode is convenience only**: `ingest` runs all stages sequentially in one command. The batch manifest has its own `run_id`; internally, stages share two producer run scopes — a `structured_ingest_run_id` and an `unstructured_ingest_run_id`.

### Graph layers

| Layer | Nodes | Written by | Mutable? |
| --- | --- | --- | --- |
| Lexical | `Document`, `Chunk` | `ingest-pdf` | Stable for the run — never overwritten by downstream stages |
| Extraction | `ExtractedClaim`, `EntityMention` | `extract-claims` | Non-destructive additions only |
| Resolution | `UnresolvedEntity` (fallback) | `resolve-entities` | Non-destructive additions only; creates `RESOLVES_TO` edges to existing `CanonicalEntity` nodes |
| Structured | `Claim`, `Fact`, `Relationship`, `Source`, `CanonicalEntity` | `ingest-structured` | Non-destructive additions only |

Every `Chunk` node includes ingest metadata fields such as `run_id`, `source_uri`, `dataset_id`, and positional provenance fields. `Document` nodes include the same ingest metadata.

---

## Run scopes and manifests

### Run ID provenance

- The demo supplies its own stage run scope (`run_id`, plus `dataset_id`/`source_uri` when applicable) via `document_metadata` for PDF ingest, persisted on `Document`/`Chunk` nodes.
- Vendor pipelines also emit an orchestration `run_id` (`PipelineResult.run_id` / `RunContext.run_id`) for callbacks; the demo does **not** inject that vendor-orchestration id into graph nodes.
- Entity resolution uses the same `run_id` as the unstructured/PDF ingest stages — it is part of the unstructured run scope, not a separate run boundary. Conceptually, it is **run-scoped post-ingest normalization** over the previously ingested PDF-derived nodes: it adds resolved entities and links while preserving the original lexical layer and its provenance.
- **Retrieval is run-scoped by default**: vector search is constrained to `Chunk` nodes matching the active `run_id`. The `ask` command defaults to using `UNSTRUCTURED_RUN_ID` when set and otherwise queries the latest run (or when `--latest` is specified); you can also pass `--run-id <RUN_ID>` or `--all-runs` to override the scope.

### Manifest layout

| Mode | Manifest path | Key fields |
| --- | --- | --- |
| Batch (`ingest`) | `<output-dir>/manifest.json` | `run_id`, `run_scopes.structured_ingest_run_id`, `run_scopes.unstructured_ingest_run_id` |
| Independent stage (`ingest-structured`, `ingest-pdf`) | `<output-dir>/runs/<run_id>/<stage_name>/manifest.json` | `run_id`, `run_scopes.batch_mode: single_independent_run`, one of `structured_ingest_run_id` / `unstructured_ingest_run_id` |
| Derived stage (`extract-claims`, `resolve-entities`, `ask`) | `<output-dir>/runs/<run_id>/<stage_name>/manifest.json` | `run_id`, `run_scopes.unstructured_ingest_run_id` or explicit ask scope fields |

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
| `UnresolvedEntity` | `resolve-entities` |

The index `demo_chunk_embedding_index` (vector, `Chunk.embedding`, 1536 dims) is also dropped if present.

### What is preserved

- nodes with labels not in the list above
- indexes and constraints not named above
- other Neo4j databases on the same server

### Idempotency

Reset is safe to run repeatedly. If the graph is already empty or the index is absent, the script completes without error and records warnings in the reset report.

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
