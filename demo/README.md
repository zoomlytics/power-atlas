# Demo Workflow (dataset v1)

Self-contained demo workflow under `demo/` for evidence-driven influence research with structured and unstructured artifacts.

## Conceptual model

- **Independent ingestion runs**: structured ingest and unstructured/PDF ingest are separate producer runs with separate `run_id` boundaries; neither implies the other must also run.
- **Two-pipeline unstructured flow**: `extract-claims` runs within the same `run_id` scope established by `ingest-pdf` — it is not a separate run. It reads the previously ingested chunks, adds derived nodes/edges, and does not rewrite the lexical layer.
- **Layered graph model**: source assertions are preserved as written (with provenance), while canonical/resolved views are derived in a separate layer and may be revised over time.
- **Explicit convergence**: cross-source links are an optional resolution step; they must be explainable and non-destructive (do not overwrite source assertions).
- **Batch mode is convenience only**: `ingest` is documented as sequential independent runs in one command, each retaining its own `run_id`.

## Two-pipeline unstructured flow

The unstructured "golden path" uses two run-scoped pipelines that share a `run_id`:

### Pipeline 1 — `ingest-pdf`

Writes the lexical graph for the run:

- loads and splits the PDF into chunks (`FixedSizeSplitter`)
- embeds chunks and writes vector-index-ready chunk data (`OpenAIEmbeddings`)
- writes `Document` and `Chunk` nodes with run-scoped provenance fields (`run_id`, `source_uri`, `chunk_id`, `page_number`)
- establishes the stable lexical layer that all downstream stages read from

The lexical layer is treated as **append-only for the run**: downstream stages must not destructively rewrite `Document` or `Chunk` nodes.

Vendor anchor: `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` — specifically the `build_lexical_graph` pipeline.

### Pipeline 2 — `extract-claims`

Reads the lexical layer for the same `run_id` and adds the derived graph:

- reads `Chunk` nodes scoped to `run_id` (and optionally `source_uri`) using `RunScopedNeo4jChunkReader` (see `demo/io/run_scoped_chunk_reader.py`)
- runs `LLMEntityRelationExtractor` with `use_structured_output=True` over those chunks
- writes `ExtractedClaim` and `EntityMention` nodes with `SUPPORTED_BY` / `MENTIONED_IN` edges that link back to the originating `Chunk`
- does **not** modify or re-embed any `Document` or `Chunk` nodes from Pipeline 1

The run-scoped relationship is explicit: `extract-claims` reads chunks by `run_id`, so extraction always operates on the lexical layer produced by the corresponding `ingest-pdf` run; running `extract-claims` independently requires setting `UNSTRUCTURED_RUN_ID` to the `run_id` from that prior run.

Vendor anchors: `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` — specifically the `build_entity_graph` pipeline; and `vendor-resources/examples/customize/build_graph/components/chunk_reader/neo4j_chunk_reader.py` for the chunk reader pattern.

## Graph layers

### Lexical layer (stable, run-scoped)

Nodes: `Document`, `Chunk`

- written by `ingest-pdf` and treated as **stable for the run**
- each node carries `run_id`, `source_uri`, and positional provenance fields
- not destructively rewritten by extraction or any other derived stage
- forms the source-bearing evidence base for retrieval and citation

### Derived layers (non-destructive)

Written by downstream stages; must not modify the lexical layer:

- **Claim extraction** (`extract-claims`): `ExtractedClaim`, `EntityMention`, linked to `Chunk` via `SUPPORTED_BY` / `MENTIONED_IN`
- **Entity resolution** (`resolve-entities`): `CanonicalEntity` / `UnresolvedEntity` links, resolved from `EntityMention` nodes
- **Retrieval / Q&A** (`ask`): runtime retrieval output and citation artifacts

Operational and process metadata (timing, batch context, run summaries) belongs primarily in manifest files rather than in the graph. The graph preserves the source and evidence structure needed for retrieval and citation.

## Default retrieval behavior

Retrieval is **run-scoped by default**:

- the default retrieval scope is the `run_id` from the unstructured ingest run (`ingest-pdf`)
- vector search is constrained to `Chunk` nodes matching the active `run_id` so results are always traceable to a specific ingest run
- `source_uri` filtering is supported for narrowing within a run (e.g. to a single PDF)
- retrieving across multiple runs or without a `run_id` filter must be **explicit and opt-in**

This is a correctness and reproducibility behavior, not a maximal provenance system. The run scope ensures that answer evidence is always linked to a known, replayable ingest boundary.

## Citation expectations

Q&A answers are expected to:

- use **retrieved context only** — no hallucinated or uncited claims
- emit **project citation tokens** for each piece of answer content (format: `[CITATION|chunk_id=...|run_id=...|source_uri=...|chunk_index=...|page=...|start_char=...|end_char=...]`)
- keep answers **grounded in retrieved chunk evidence** so every assertion can be traced back to a `Chunk` node

The citation contract (token format, required fields, and validation expectations) is defined in [zoomlytics/power-atlas#159](https://github.com/zoomlytics/power-atlas/issues/159). The README does not redefine the citation format; treat #159 as the source of truth.

## Citation validation policy

Post-generation validation enforces that every sentence and bullet in an answer is cited.
The `_check_all_answers_cited` function in `demo/stages/retrieval_and_qa.py` splits the
answer into checkable segments and requires each segment to end with at least one
`[CITATION|…]` token.

**Segmentation rules** (implemented in `_split_into_segments`):

1. The answer is split on newlines first.
2. Bullet lines (starting with `-`, `*`, `•`, or a digit followed by `.` and a space) are
   treated as atomic units — one citation at the end of the entire bullet is sufficient.
3. Non-bullet paragraph lines are further split into sentence-like segments at `[.!?]`
   boundaries followed by an uppercase letter or a non-citation opening bracket.
   - `[CITATION|…]` tokens are **not** split-points — the negative lookahead
     `(?!CITATION\|)` keeps the token attached to its sentence.
   - Non-citation brackets such as `[Note]` or `[1]` **do** act as split-points, so
     `"Claim A. [Note] Claim B. [CITATION|…]"` correctly splits into `"Claim A."` (no
     citation → rejected) and `"[Note] Claim B. [CITATION|…]"`.
   - Each resulting segment must independently end with at least one citation token.
**Why sentence-level (not just line-level)?**  A multi-sentence paragraph like
`"Claim A. Claim B. [CITATION|...]"` would pass a line-level check (the line ends with a
citation) but fail a sentence-level check because `"Claim A."` has no citation.  The
sentence split catches this case.

**Outcome when uncited segments are detected:**

- `all_answers_cited` is set to `False` in the result dict.
- A warning is appended to `citation_quality.citation_warnings`.
- `citation_quality.evidence_level` is set to `"degraded"` instead of `"full"`.

## Workflow (golden path)

1. **Reset graph safely**
   ```bash
   export NEO4J_PASSWORD='your-neo4j-password'  # or pass --neo4j-password to the script
   python demo/reset_demo_db.py --confirm
   ```
2. **Run independent ingestion runs (recommended)**
   ```bash
   python demo/run_demo.py --dry-run ingest-structured
   python demo/run_demo.py --dry-run ingest-pdf
   ```
3. **Run extraction over the ingested chunks (same run_id scope)**
   ```bash
   export UNSTRUCTURED_RUN_ID=<run_id from ingest-pdf output>
   python demo/run_demo.py --dry-run extract-claims
   ```
4. **Optional: run convenience batch orchestrator** (runs all stages sequentially)
   ```bash
   python demo/run_demo.py --dry-run ingest
   ```
5. **Run smoke test**
   ```bash
   python demo/smoke_test.py
   ```
   By default this writes artifacts to an isolated temporary directory that is deleted when the process exits; pass `--output-dir` to retain artifacts in a persistent directory.

   `--dry-run` keeps the workflow reproducible without requiring live OpenAI/Neo4j calls.

## What the orchestrator stages model

- PDF ingest (chunk/embed/store) using vendor-aligned component choices (`FixedSizeSplitter`, `OpenAIEmbeddings`, `OpenAILLM`)
- Structured CSV ingest with claims-first modeling (`Claim`, `CanonicalEntity`, evidence-linked relationships)
- Structured pre-ingest lint + deterministic dedup writes run-scoped artifacts under `runs/<run_id>/structured_clean/` plus `lint_report.json`
- Claim extraction + entity mention stages driven by `LLMEntityRelationExtractor` with run-scoped chunk reading
- Entity resolution stage (deterministic canonical key resolution; `CanonicalEntity` / `UnresolvedEntity` links)
- Retrieval and GraphRAG Q&A stage with strict citation expectations
- Run artifacts written to `<output-dir>/manifest.json` with clean run boundaries (for the default orchestrator run this is typically `demo/artifacts/manifest.json`; override with `--output-dir`, and note that `smoke_test.py` uses an isolated temporary directory by default)

Manifest run-boundary notes:
- **Batch orchestrator manifest** (`manifest.json`, produced by `ingest`):
  - `run_id`: run boundary for the overall batch orchestrator run
  - `run_scopes.structured_ingest_run_id`: structured producer run boundary
  - `run_scopes.unstructured_ingest_run_id`: unstructured/PDF producer run boundary
  - `run_scopes.resolution_run_id`: optional convergence/resolution scope
- **Independent stage manifests** (named `{stage_name}_{stage_run_id}_manifest.json`, e.g. `structured_ingest_structured_ingest-..._manifest.json` and `pdf_ingest_unstructured_ingest-..._manifest.json`, produced by `ingest-structured` / `ingest-pdf`):
  - `run_id`: run boundary for that single producer run
  - `run_scopes.batch_mode`: `single_independent_run`
  - `run_scopes.structured_ingest_run_id` or `run_scopes.unstructured_ingest_run_id` (only the relevant producer scope key is present)
- In all modes, each stage emits its own `run_id` so provenance remains non-destructive and auditable across reruns

## Run ID provenance contract

- Vendor pipelines emit an orchestration `run_id` at execution time (`PipelineResult.run_id` / `RunContext.run_id`) for callbacks/notifications; the demo does **not** inject this orchestration id into graph nodes.
- The demo supplies its own stage run scope (`run_id`, plus `dataset_id`/`source_uri` when present) via `document_metadata` for PDF ingest and persists those fields on `Document`/`Chunk` nodes; post-ingest normalization still runs to keep reset/retrieval scripts aligned on the same persisted provenance.

## Fixtures and reproducibility

- `fixtures/structured/*.csv`: claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf`: canonical source PDF fixture used in this demo
- `fixtures/manifest.json`: dataset contract, provenance, and license note

Reset script deletes generic labels and drops the demo index `demo_chunk_embedding_index`; run it only against a dedicated demo database/graph to avoid wiping non-demo data.

## Vendor alignment map

> **Before adding custom code, check the relevant vendor example first.**

This demo intentionally mirrors upstream patterns in `vendor-resources`. The table below maps each demo stage to its primary vendor anchor(s) and notes where the demo diverges:

| Demo stage | Vendor anchor(s) | Notes |
| --- | --- | --- |
| **Ingest / lexical graph** (`ingest-pdf`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config.yaml`<br>`vendor-resources/examples/database_operations/create_vector_index.py` | Config-driven in live mode via `demo/config/pdf_simple_kg_pipeline.yaml`. Creates `demo_chunk_embedding_index` on `:Chunk(embedding)` (1536 dims). Enforces run-scoped provenance on `Document`/`Chunk`. Uses `NEO4J_USERNAME` (not `NEO4J_USER`). |
| **Chunk reading** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/chunk_reader/neo4j_chunk_reader.py` | Demo wraps `Neo4jChunkReader` in `RunScopedNeo4jChunkReader` (see `demo/io/run_scoped_chunk_reader.py`) to filter by `run_id` and optionally `source_uri`. |
| **Extraction** (`extract-claims`) | `vendor-resources/examples/customize/build_graph/components/extractors/llm_entity_relation_extractor_with_structured_output.py`<br>`vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | Uses `LLMEntityRelationExtractor(use_structured_output=True)` with a demo-owned claim schema. Dry-run mode uses deterministic stubs to keep smoke tests stable. |
| **Retrieval** (`ask`) | `vendor-resources/examples/retrieve/vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py` | Aligns on `VectorCypherRetriever` with run-scoped pre-filtering (`run_id` required; `source_uri` optional). Retrieval query returns citation provenance fields (`chunk_id`, `run_id`, `source_uri`, `chunk_index`, `page`, `start_char`, `end_char`). |
| **GraphRAG / Q&A** (`ask`) | `vendor-resources/examples/question_answering/graphrag.py`<br>`vendor-resources/examples/customize/answer/custom_prompt.py`<br>`vendor-resources/docs/source/user_guide_rag.rst` (sections: "GraphRAG Configuration", "Configuring the Prompt", "Retriever Configuration") | Keeps standard `GraphRAG(retriever, llm, prompt_template=...)` contract. Uses a citation-oriented prompt suffix so answers emit `[CITATION|...]` tokens grounded in retrieved chunks. |
| **Structured ingest** (`ingest-structured`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | Follows two-stage lexical/entity modeling but loads curated CSV fixtures to enforce the `Claim`/`CanonicalEntity` schema for deterministic evidence provenance. |

## Config-driven vs custom workflow checklist

- [x] **Config-driven**: PDF ingest pipeline shape (`SimpleKGPipeline` via `PipelineRunner`) is declared in `demo/config/pdf_simple_kg_pipeline.yaml`, aligned to vendor `from_config_files` examples.
- [x] **Config-driven**: Demo retrieval/citation index contract uses `demo_chunk_embedding_index` on label `Chunk` property `embedding` with dimensions `1536` (deterministic naming keeps reset + retrieval scripts aligned), pinned via `OpenAIEmbeddings` model `text-embedding-3-small` in the demo config plus `contract.chunk_embedding.dimensions`.
- [x] **Config-driven**: `run_demo.py ingest-pdf --live` executes `PipelineRunner.from_config_file(...)` against `demo/config/pdf_simple_kg_pipeline.yaml` with template-aligned `file_path` input only.
- [x] **Custom**: Structured ingest live path emits run-scoped provenance metadata (`run_id`, source URI, timestamps, confidence, source-row evidence links) without mutating source assertions (tracked from [zoomlytics/power-atlas#151](https://github.com/zoomlytics/power-atlas/issues/151)).
- [x] **Custom**: `extract-claims` uses `RunScopedNeo4jChunkReader` to constrain extraction input to the active `run_id`, matching the two-pipeline pattern in the vendor anchor.
- [ ] **Planned retrieval/GraphRAG issue alignment**: Retrieval and answer synthesis should consume explicit run-scoped provenance links and avoid implicit structured↔unstructured coupling.
- [ ] **Planned reset semantics alignment**: Reset behavior must remain run-scoped/non-destructive by default (targeted cleanup over blanket deletion when run IDs are available).
- [x] **Custom by design**: Structured CSV ingest, deterministic canonical key resolution, and provenance-specific graph expansion remain demo-owned logic.

## CLI scaffold and configuration

The orchestrator CLI exposes the following subcommands:
`lint-structured`, `ingest-structured`, `ingest-pdf`, `extract-claims`,
`resolve-entities`, `ask`, `reset`, and `ingest`.

- `lint-structured` performs pre-ingest validation (headers, IDs, value type enums, parseable dates, common PID label sanity) and deterministic dedup for entities/facts/relationships before any graph write stage.

Environment/configuration values used by this demo:

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (database defaults to `neo4j`)
- `OPENAI_MODEL` (required for config-driven runs; the demo CLI defaults to `gpt-4o-mini` if unset)
- `UNSTRUCTURED_RUN_ID` (required when running `extract-claims`, `resolve-entities`, or `ask` independently; must match the `run_id` from a prior `ingest-pdf` run)
- Demo vector index used by retrieval/reset flow: `demo_chunk_embedding_index` (label: `Chunk`, embedding property: `embedding`, dimensions: `1536`)
- Deterministic index naming intentionally diverges from earlier claim-oriented naming so `reset_demo_db.py` can safely clean the exact demo-owned citation index.
- Unstructured/PDF ingest remains independent from structured ingest: every run has its own `run_id`; live ingest uses run-scoped post-ingest normalization to propagate `run_id`/`source_uri` onto `Document` and `Chunk` nodes for citation/retrieval provenance.
