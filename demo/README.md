# Demo Workflow (dataset v1)

Self-contained demo workflow under `demo/` for evidence-driven influence research with structured and unstructured artifacts.

---

## Overview

The demo exercises two independent ingestion pipelines — structured CSV ingest and unstructured PDF ingest — followed by claim extraction, entity resolution, and citation-grounded Q&A retrieval. All stages are orchestrated by `demo/run_demo.py` and produce run-scoped manifests for auditability.

---

## Conceptual model

- **Independent ingestion runs**: structured ingest and unstructured/PDF ingest are separate producer runs with separate `run_id` boundaries; neither implies the other must also run.
- **Two-pipeline unstructured flow**: `extract-claims` runs within the same `run_id` scope established by `ingest-pdf` — it is not a separate run. It reads the previously ingested chunks, adds derived nodes/edges, and does not rewrite the lexical layer.
- **Layered graph model**: source assertions are preserved as written (with provenance), while canonical/resolved views are derived in a separate layer and may be revised over time.
- **Explicit convergence**: cross-source links are an optional resolution step; they must be explainable and non-destructive (do not overwrite source assertions).
- **Batch mode is convenience only**: `ingest` runs all stages sequentially in one command. The batch manifest has its own `run_id`; internally, stages share two producer run scopes — a `structured_ingest_run_id` for the structured pipeline and an `unstructured_ingest_run_id` shared by PDF ingest, claim extraction, entity resolution, and retrieval.

### Graph layers

| Layer | Nodes | Written by | Mutable? |
| --- | --- | --- | --- |
| Lexical | `Document`, `Chunk` | `ingest-pdf` | Stable for the run — never overwritten by downstream stages |
| Extraction | `ExtractedClaim`, `EntityMention` | `extract-claims` | Non-destructive additions only |
| Resolution | `UnresolvedEntity` (fallback) | `resolve-entities` | Non-destructive additions only; creates `RESOLVES_TO` edges to existing `CanonicalEntity` nodes |
| Structured | `Claim`, `Fact`, `Relationship`, `Source`, `CanonicalEntity` | `ingest-structured` | Non-destructive additions only |

Every `Chunk` node includes ingest metadata fields such as `run_id`, `source_uri`, `dataset_id`, and positional provenance fields; `Document` nodes include the same ingest metadata (for example, `run_id`, `source_uri`, `dataset_id`). Operational metadata (timing, batch context, run summaries) belongs in manifest files, not in the graph.

---

## Recommended workflow

Use `--dry-run` to run all stages without live OpenAI or Neo4j calls (useful for CI and local exploration). Remove `--dry-run` and add `--live` for a real run.

### Step 1 — Reset the graph (optional but recommended before a clean run)

```bash
export NEO4J_PASSWORD='your-neo4j-password'
# Standalone reset script (recommended):
python demo/reset_demo_db.py --confirm

# Or via the CLI orchestrator:
python demo/run_demo.py --live reset --confirm
```

Without `--confirm`, the standalone script (`reset_demo_db.py`) exits with an error; the CLI orchestrator (`run_demo.py reset`) prints instructions only. Both paths write a JSON reset report to `demo/artifacts/` (override with `--output-dir`) when `--confirm` is supplied.

### Step 2 — Run ingestion stages independently (recommended)

```bash
python demo/run_demo.py --dry-run ingest-structured
python demo/run_demo.py --dry-run ingest-pdf
```

Producer stages (`ingest-structured`, `ingest-pdf`) each generate a new `run_id` and write a stage manifest to `runs/<run_id>/<stage_name>/manifest.json`.

### Step 3 — Run claim extraction (same run_id scope as ingest-pdf)

```bash
export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
python demo/run_demo.py --dry-run extract-claims
```

In live mode, `extract-claims` reads `Chunk` nodes scoped to the given `run_id`; in `--dry-run` mode it returns a stub summary without reading Neo4j. `UNSTRUCTURED_RUN_ID` is required in both modes when running this stage independently.

### Step 4 — Optional stages

These stages also require `UNSTRUCTURED_RUN_ID` (same env var as Step 3); they run within the existing unstructured run scope rather than creating a new one.

```bash
# Entity resolution (deterministic; uses same run_id as unstructured ingest):
python demo/run_demo.py --dry-run resolve-entities

# Retrieval and Q&A:
python demo/run_demo.py --dry-run ask
```

### Convenience batch mode (alternative to steps 2–4)

```bash
python demo/run_demo.py --dry-run ingest
```

Runs all stages sequentially with a single command. The batch manifest is written to `<output-dir>/manifest.json` with its own `run_id`; internally, structured stages share `structured_ingest_run_id` and unstructured stages (PDF ingest, claim extraction, entity resolution, retrieval) share `unstructured_ingest_run_id`.

### Step 5 — Run smoke test

```bash
python demo/smoke_test.py
```

By default, artifacts are written to an isolated temporary directory deleted on exit. Pass `--output-dir` to retain them. The smoke test runs structured, unstructured, and batch scenarios in sequence.

---

## Run scopes and manifests

### Run ID provenance

- The demo supplies its own stage run scope (`run_id`, plus `dataset_id`/`source_uri` when applicable) via `document_metadata` for PDF ingest, persisted on `Document`/`Chunk` nodes.
- Vendor pipelines also emit an orchestration `run_id` (`PipelineResult.run_id` / `RunContext.run_id`) for callbacks; the demo does **not** inject that vendor-orchestration id into graph nodes.
- Entity resolution uses the same `run_id` as the unstructured/PDF ingest stages — it is part of the unstructured run scope, not a separate run boundary. Conceptually, it is **run-scoped post-ingest normalization** over the previously ingested PDF-derived nodes: it adds resolved entities and links while preserving the original lexical layer and its provenance.
- Retrieval is **run-scoped by default**: vector search is constrained to `Chunk` nodes matching the active `run_id`. Retrieving across multiple runs requires explicit opt-in. `source_uri` filtering is supported for narrowing within a run.

### Manifest layout

| Mode | Manifest path | Key fields |
| --- | --- | --- |
| Batch (`ingest`) | `<output-dir>/manifest.json` | `run_id`, `run_scopes.structured_ingest_run_id`, `run_scopes.unstructured_ingest_run_id` |
| Independent stage (`ingest-structured`, `ingest-pdf`) | `runs/<run_id>/<stage_name>/manifest.json` | `run_id`, `run_scopes.batch_mode: single_independent_run`, one of `structured_ingest_run_id` / `unstructured_ingest_run_id` |

Each stage records a `run_id` in its manifest. Producer stages generate a new run scope; derived stages (`extract-claims`, `resolve-entities`, `ask`) intentionally share the producer run scope (`unstructured_ingest_run_id`) rather than generating a new one. Entity resolution is part of the unstructured run scope and shares `run_scopes.unstructured_ingest_run_id`.

---

## Citation behavior

Q&A answers must:

- use **retrieved context only** — no hallucinated or uncited claims
- emit **project citation tokens** for each piece of answer content (format: `[CITATION|chunk_id=...|run_id=...|source_uri=...|chunk_index=...|page=...|start_char=...|end_char=...]`)
- trace every assertion back to a `Chunk` node in the lexical layer

The citation contract (token format, required fields, validation expectations) is defined in [zoomlytics/power-atlas#159](https://github.com/zoomlytics/power-atlas/issues/159).

**Post-generation validation** (`_check_all_answers_cited` in `demo/stages/retrieval_and_qa.py`) enforces that every sentence and bullet ends with at least one citation token. When uncited segments are detected:

- `citation_quality.evidence_level` is set to `"degraded"`
- the `answer` field is replaced with a fallback prefixed `"Insufficient citations detected: "` (original output preserved in `raw_answer`)
- a warning is appended to `citation_quality.citation_warnings`

**Message history** is passed to the LLM for conversational context only and is never a source of answer evidence. Uncited answers stored in history use only the bare refusal prefix, not the full response, to prevent under-cited content from conditioning subsequent turns.

---

## Reset behavior

`demo/reset_demo_db.py` (and `run_demo.py reset --confirm`) performs a **demo-scoped full graph wipe** of the configured database.

### What is deleted

All nodes with the following labels and **all their relationships** (`DETACH DELETE`):

| Label | Written by |
| --- | --- |
| `Document` | `ingest-pdf` (lexical layer) |
| `Chunk` | `ingest-pdf` (lexical layer) |
| `CanonicalEntity` | `ingest-structured` (structured layer) |
| `Claim` | `ingest-structured` (structured layer; claims.csv) |
| `Fact` | `ingest-structured` (structured layer; facts.csv) |
| `Relationship` | `ingest-structured` (structured layer; relationships.csv) |
| `Source` | `ingest-structured` (structured layer; dataset source nodes) |
| `ExtractedClaim` | `extract-claims` (extraction layer) |
| `EntityMention` | `extract-claims` (extraction layer) |
| `UnresolvedEntity` | `resolve-entities` (resolution layer; fallback nodes for unresolved mentions) |

The index `demo_chunk_embedding_index` (vector, `Chunk.embedding`, 1536 dims) is also dropped if present.

### What is preserved

- Nodes with labels not in the list above.
- Indexes and constraints not named above.
- Other Neo4j databases on the same server.

### Idempotency

Reset is safe to run repeatedly. If the graph is already empty or the index is absent the script completes without error and records warnings in the reset report. Each run writes a JSON report to `<output-dir>/reset_report_<timestamp>.json`.

---

## Fixtures and reproducibility

- `fixtures/structured/*.csv` — claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf` — canonical source PDF; the name is intentionally stable and serves as a consistent demo artifact
- `fixtures/manifest.json` — dataset contract, provenance, and license note

---

## CLI reference

The orchestrator CLI exposes the following subcommands:
`lint-structured`, `ingest-structured`, `ingest-pdf`, `extract-claims`,
`resolve-entities`, `ask`, `reset`, and `ingest`.

- `lint-structured` performs pre-ingest validation (headers, IDs, value type enums, parseable dates, common PID label sanity) and deterministic dedup for entities/facts/relationships before any graph write stage.

### Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes (live) | Required for live `ingest-pdf`, `extract-claims`, and `ask` |
| `NEO4J_URI` | No | Defaults to `neo4j://localhost:7687` |
| `NEO4J_USERNAME` | No | Defaults to `neo4j`. Note: `NEO4J_USERNAME`, not `NEO4J_USER` |
| `NEO4J_PASSWORD` | Yes (live) | |
| `NEO4J_DATABASE` | No | Defaults to `neo4j` |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o-mini` if unset |
| `UNSTRUCTURED_RUN_ID` | Yes (for independent `extract-claims`, `resolve-entities`, `ask`) | Must match `run_id` from a prior `ingest-pdf` run |

Demo vector index: `demo_chunk_embedding_index` (label: `Chunk`, property: `embedding`, dimensions: `1536`). Deterministic naming keeps `reset_demo_db.py` and retrieval scripts aligned.

---

## Maintainer notes

> This section is for contributors implementing or extending the demo.

### Two-pipeline unstructured flow

Pipeline 1 (`ingest-pdf`) writes the **lexical layer**:
- loads and splits the PDF into chunks (`FixedSizeSplitter`)
- embeds chunks and writes vector-index-ready chunk data (`OpenAIEmbeddings`)
- writes `Document` and `Chunk` nodes with run-scoped provenance; these are **append-only for the run**

Vendor anchor: `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` (`build_lexical_graph` pipeline).

Pipeline 2 (`extract-claims`) reads the lexical layer for the same `run_id` and adds the **derived graph**:
- reads `Chunk` nodes via `RunScopedNeo4jChunkReader` (see `demo/io/run_scoped_chunk_reader.py`)
- runs `LLMEntityRelationExtractor(use_structured_output=True)` over those chunks
- writes `ExtractedClaim` and `EntityMention` nodes linked to `Chunk` via `SUPPORTED_BY` / `MENTIONED_IN`
- does **not** modify or re-embed any `Document` or `Chunk` nodes

Vendor anchors: same two-pipelines file (`build_entity_graph` pipeline); `vendor-resources/examples/customize/build_graph/components/chunk_reader/neo4j_chunk_reader.py` for the chunk reader pattern.

### Vendor alignment map

> Before adding custom code, check the relevant vendor example first.

| Demo stage | Vendor anchor(s) | Notes |
| --- | --- | --- |
| **Ingest / lexical graph** (`ingest-pdf`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config.yaml`<br>`vendor-resources/examples/database_operations/create_vector_index.py` | Config-driven in live mode via `demo/config/pdf_simple_kg_pipeline.yaml`. Creates `demo_chunk_embedding_index` on `:Chunk(embedding)` (1536 dims). Uses `NEO4J_USERNAME` (not `NEO4J_USER`). |
| **Chunk reading** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/chunk_reader/neo4j_chunk_reader.py` | Demo wraps `Neo4jChunkReader` in `RunScopedNeo4jChunkReader` to filter by `run_id` and optionally `source_uri`. |
| **Extraction** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/extractors/llm_entity_relation_extractor_with_structured_output.py`<br>`vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | Uses `LLMEntityRelationExtractor(use_structured_output=True)` with a demo-owned claim schema. Dry-run uses deterministic stubs. |
| **Retrieval** (`ask`) | `vendor-resources/examples/retrieve/vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py` | `VectorCypherRetriever` with run-scoped pre-filtering. Returns citation provenance fields (`chunk_id`, `run_id`, `source_uri`, `chunk_index`, `page`, `start_char`, `end_char`). |
| **GraphRAG / Q&A** (`ask`) | `vendor-resources/examples/question_answering/graphrag.py`<br>`vendor-resources/examples/customize/answer/custom_prompt.py`<br>`vendor-resources/docs/source/user_guide_rag.rst` | Standard `GraphRAG(retriever, llm, prompt_template=...)` contract with a citation-oriented prompt suffix. |
| **Structured ingest** (`ingest-structured`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | Follows two-stage lexical/entity modeling with curated CSV fixtures to enforce the `Claim`/`CanonicalEntity` schema. |

### Config-driven vs custom checklist

- [x] **Config-driven**: PDF ingest pipeline shape (`SimpleKGPipeline` via `PipelineRunner`) declared in `demo/config/pdf_simple_kg_pipeline.yaml`, aligned to vendor `from_config_files` examples.
- [x] **Config-driven**: Retrieval/citation index contract uses `demo_chunk_embedding_index` on `Chunk.embedding` (1536 dims), pinned via `OpenAIEmbeddings` model `text-embedding-3-small` and `contract.chunk_embedding.dimensions`.
- [x] **Config-driven**: `run_demo.py ingest-pdf --live` executes `PipelineRunner.from_config_file(...)` against `demo/config/pdf_simple_kg_pipeline.yaml`.
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
