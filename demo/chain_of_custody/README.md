# Chain of Custody Demo (dataset v1)

Self-contained demo workflow under `demo/chain_of_custody/` for evidence-driven influence research with structured and unstructured artifacts.

## Conceptual model

- **Independent ingestion runs**: structured ingest and unstructured/PDF ingest are separate producer runs with separate `run_id` boundaries; neither implies the other must also run.
- **Layered graph model**: source assertions are preserved as written (with provenance), while canonical/resolved views are derived in a separate layer and may be revised over time.
- **Explicit convergence**: cross-source links are an optional resolution step; they must be explainable and non-destructive (do not overwrite source assertions).
- **Batch mode is convenience only**: `ingest` is documented as sequential independent runs in one command, each retaining its own `run_id`.

## Workflow (golden path)

1. **Reset graph safely**
   ```bash
   export NEO4J_PASSWORD='your-neo4j-password'  # or pass --neo4j-password to the script
   python demo/chain_of_custody/reset_demo_db.py --confirm
   ```
2. **Run independent ingestion runs (recommended)**
   ```bash
   python demo/chain_of_custody/run_demo.py --dry-run ingest-structured
   python demo/chain_of_custody/run_demo.py --dry-run ingest-pdf
   ```
3. **Optional: run convenience batch orchestrator**
   ```bash
   python demo/chain_of_custody/run_demo.py --dry-run ingest
   ```
4. **Run smoke test**
   ```bash
   python demo/chain_of_custody/smoke_test.py
   ```
   By default this writes artifacts to an isolated temporary directory that is deleted when the process exits; pass `--output-dir` to retain artifacts in a persistent directory.

`--dry-run` keeps the workflow reproducible without requiring live OpenAI/Neo4j calls.

## What the orchestrator stages model

- PDF ingest (chunk/embed/store) using vendor-aligned component choices (`FixedSizeSplitter`, `OpenAIEmbeddings`, `OpenAILLM`)
- Structured CSV ingest with claims-first modeling (`Claim`, `CanonicalEntity`, evidence-linked relationships)
- Narrative claim extraction + mention resolution stages (deterministic canonical key resolution)
- Retrieval and GraphRAG Q&A stage with strict citation expectations
- Run artifacts written to `<output-dir>/manifest.json` with clean run boundaries (for the default orchestrator run this is typically `demo/chain_of_custody/artifacts/manifest.json`; override with `--output-dir`, and note that `smoke_test.py` uses an isolated temporary directory by default)

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

## Fixtures and reproducibility

- `fixtures/structured/*.csv`: claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf`: canonical source PDF fixture used in this demo
- `fixtures/manifest.json`: dataset contract, provenance, and license note

Reset script deletes generic labels and drops the demo index `chain_custody_chunk_embedding_index`; run it only against a dedicated demo database/graph to avoid wiping non-demo data.

## Vendor-resources alignment map

This demo intentionally mirrors upstream patterns in `vendor-resources`; use these local vendored files as the first source of truth:

| Demo workflow part | Vendor-resources implementation(s) | Alignment + rationale for divergence |
| --- | --- | --- |
| PDF loader/split/embed/write (`ingest-pdf`) | `vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config.yaml`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config_url.json` (upstream filename: `config_url.json`)<br>`vendor-resources/examples/build_graph/simple_kg_builder_from_pdf.py`<br>`vendor-resources/examples/database_operations/create_vector_index.py` | **Now config-driven in live mode.** `run_demo.py` calls `PipelineRunner.from_config_file(...)` with `demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml`, creates the deterministic demo-owned index `chain_custody_chunk_embedding_index` on `:Chunk(embedding)` (1536 dimensions) before ingest, and then enforces run-scoped provenance (`run_id`, `source_uri`, stable chunk order/id, page number) on `Document`/`Chunk`. Note: vendor examples use `NEO4J_USER`; this demo intentionally uses `NEO4J_USERNAME` to stay consistent with the demo CLI/env contract. |
| Structured ingest (`ingest-structured`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | We follow the two-stage lexical/entity modeling idea, but diverge by loading curated CSV fixtures first to enforce a deterministic `Claim`/`CanonicalEntity` schema for chain-of-custody provenance assertions. |
| Claim extraction + resolver (`extract-claims`, `resolve-entities`) | `vendor-resources/examples/customize/build_graph/components/extractors/llm_entity_relation_extractor.py`<br>`vendor-resources/examples/customize/build_graph/components/resolvers/simple_entity_resolver_pre_filter.py` | Vendor examples are LLM-first; this demo keeps deterministic canonical key resolution in dry-run mode to make smoke tests stable while still documenting the planned `LLMEntityRelationExtractor` + resolver path for live runs. |
| Retrieval (`ask`) | `vendor-resources/examples/retrieve/vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/use_pre_filters.py` | We align on `VectorCypherRetriever` (+ optional `Text2CypherRetriever`) and result formatting/pre-filter patterns, then add graph expansion and evidence-link traversal so answers stay tied to explicit claim/evidence nodes. |
| GraphRAG pipeline and prompting (`ask`) | `vendor-resources/examples/question_answering/graphrag.py`<br>`vendor-resources/examples/question_answering/graphrag_with_message_history.py`<br>`vendor-resources/examples/customize/answer/custom_prompt.py`<br>`vendor-resources/docs/source/user_guide_rag.rst` (see "GraphRAG Configuration", "Configuring the Prompt", and "Retriever Configuration") | We keep the standard `GraphRAG(retriever, llm, prompt_template=...)` contract from the user guide, but use a stricter citation-oriented prompt suffix so demo outputs cite provenance artifacts instead of producing uncited narrative text. |

## Config-driven vs custom workflow checklist

- [x] **Config-driven**: PDF ingest pipeline shape (`SimpleKGPipeline` via `PipelineRunner`) is declared in `demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml`, aligned to vendor `from_config_files` examples.
- [x] **Config-driven**: Demo retrieval/citation index contract uses `chain_custody_chunk_embedding_index` on label `Chunk` property `embedding` with dimensions `1536` (deterministic naming keeps reset + retrieval scripts aligned), pinned via `OpenAIEmbeddings` model `text-embedding-3-small` in the demo config plus `demo_contract.chunk_embedding.dimensions`.
- [x] **Config-driven**: `run_demo.py ingest-pdf --live` executes `PipelineRunner.from_config_file(...)` against `demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml` and passes run-scoped provenance via `pdf_loader.metadata`.
- [ ] **Custom (planned follow-up, scoped in [zoomlytics/power-atlas#151](https://github.com/zoomlytics/power-atlas/issues/151))**: Structured ingest live path should emit run-scoped provenance metadata (`run_id`, source URI, method/extractor, timestamps, confidence) without mutating source assertions.
- [ ] **Planned retrieval/GraphRAG issue alignment**: Retrieval and answer synthesis should consume explicit run-scoped provenance links and avoid implicit structured↔unstructured coupling.
- [ ] **Planned reset semantics alignment**: Reset behavior must remain run-scoped/non-destructive by default (targeted cleanup over blanket deletion when run IDs are available).
- [x] **Custom by design**: Structured CSV ingest, deterministic canonical key resolution, and provenance-specific graph expansion remain demo-owned logic.

## CLI scaffold and configuration

The orchestrator CLI exposes the following subcommands:
`lint-structured`, `ingest-structured`, `ingest-pdf`, `extract-claims`,
`resolve-entities`, `ask`, `reset`, and `ingest`.

Environment/configuration values used by this demo:

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (database defaults to `neo4j`)
- `OPENAI_MODEL` (required for config-driven runs; the demo CLI defaults to `gpt-4o-mini` if unset)
- Demo vector index used by retrieval/reset flow: `chain_custody_chunk_embedding_index` (label: `Chunk`, embedding property: `embedding`, dimensions: `1536`)
- Deterministic index naming intentionally diverges from earlier claim-oriented naming so `reset_demo_db.py` can safely clean the exact demo-owned citation index.
- Unstructured/PDF ingest remains independent from structured ingest: every run has its own `run_id`; live ingest writes `pdf_loader.metadata.run_id/source_uri` and then propagates those fields onto all `Chunk` nodes for citation/retrieval provenance.
