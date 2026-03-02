# Chain of Custody Demo (dataset v1)

Self-contained demo workflow under `demo/chain_of_custody/` for evidence-driven influence research with structured and unstructured artifacts.

## Workflow (golden path)

1. **Reset graph safely**
   ```bash
   export NEO4J_PASSWORD='your-neo4j-password'  # or pass --neo4j-password to the script
   python demo/chain_of_custody/reset_demo_db.py --confirm
   ```
2. **Run orchestrator**
   ```bash
   python demo/chain_of_custody/run_demo.py --dry-run ingest
   ```
3. **Run smoke test**
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
- Run artifacts written to `<output-dir>/manifest.json` (for the default orchestrator run this is typically `demo/chain_of_custody/artifacts/manifest.json`; override with `--output-dir`, and note that `smoke_test.py` uses an isolated temporary directory by default)

## Fixtures and reproducibility

- `fixtures/structured/*.csv`: claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf`: canonical source PDF fixture used in this demo
- `fixtures/manifest.json`: dataset contract, provenance, and license note

Reset script deletes generic labels and drops the demo index `chain_custody_chunk_embedding_index`; run it only against a dedicated demo database/graph to avoid wiping non-demo data.

## Vendor-resources alignment map

This demo intentionally mirrors upstream patterns in `vendor-resources`; use these local vendored files as the first source of truth:

| Demo workflow part | Vendor-resources implementation(s) | Alignment + rationale for divergence |
| --- | --- | --- |
| PDF loader/split/embed/write (`ingest-pdf`) | `vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file.py`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config.yaml`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_config_url.json`<br>`vendor-resources/examples/build_graph/from_config_files/simple_kg_pipeline_from_config_file_with_url.py` | **Now config-driven.** We align on `PipelineRunner.from_config_file(...)` + `SimpleKGPipeline` and keep demo defaults in `demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml`. This gives task agents one deterministic config entrypoint for local fixture ingest and URL/file-path ingest variants while preserving `--dry-run` reproducibility. Note: vendor examples use `NEO4J_USER`; this demo intentionally uses `NEO4J_USERNAME` to stay consistent with the demo CLI/env contract. |
| Structured ingest (`ingest-structured`) | `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py` | We follow the two-stage lexical/entity modeling idea, but diverge by loading curated CSV fixtures first to enforce a deterministic `Claim`/`CanonicalEntity` schema for chain-of-custody provenance assertions. |
| Claim extraction + resolver (`extract-claims`, `resolve-entities`) | `vendor-resources/examples/customize/build_graph/components/extractors/llm_entity_relation_extractor.py`<br>`vendor-resources/examples/customize/build_graph/components/resolvers/simple_entity_resolver_pre_filter.py` | Vendor examples are LLM-first; this demo keeps deterministic canonical key resolution in dry-run mode to make smoke tests stable while still documenting the planned `LLMEntityRelationExtractor` + resolver path for live runs. |
| Retrieval (`ask`) | `vendor-resources/examples/retrieve/vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py`<br>`vendor-resources/examples/customize/retrievers/use_pre_filters.py` | We align on `VectorCypherRetriever` (+ optional `Text2CypherRetriever`) and result formatting/pre-filter patterns, then add graph expansion and evidence-link traversal so answers stay tied to explicit claim/evidence nodes. |
| GraphRAG pipeline and prompting (`ask`) | `vendor-resources/examples/question_answering/graphrag.py`<br>`vendor-resources/examples/question_answering/graphrag_with_message_history.py`<br>`vendor-resources/examples/customize/answer/custom_prompt.py`<br>`vendor-resources/docs/source/user_guide_rag.rst` (see "GraphRAG Configuration", "Configuring the Prompt", and "Retriever Configuration") | We keep the standard `GraphRAG(retriever, llm, prompt_template=...)` contract from the user guide, but use a stricter citation-oriented prompt suffix so demo outputs cite provenance artifacts instead of producing uncited narrative text. |

## Config-driven vs custom workflow checklist

- [x] **Config-driven**: PDF ingest pipeline shape (`SimpleKGPipeline` via `PipelineRunner`) is declared in `demo/chain_of_custody/config/pdf_simple_kg_pipeline.yaml`, aligned to vendor `from_config_files` examples.
- [x] **Config-driven**: Demo retrieval/citation index contract uses `chain_custody_chunk_embedding_index` on label `Chunk` property `embedding` with dimensions `1536` (deterministic naming keeps reset + retrieval scripts aligned), pinned via `OpenAIEmbeddings` model `text-embedding-3-small` in the demo config.
- [ ] **Custom (planned follow-up, blocked by [#150](https://github.com/zoomlytics/power-atlas/issues/150))**: Wire `run_demo.py ingest-pdf` live path to execute the config file through `PipelineRunner` instead of the current `NotImplementedError`.
- [x] **Custom by design**: Structured CSV ingest, deterministic canonical key resolution, and provenance-specific graph expansion remain demo-owned logic.

## CLI scaffold and configuration

The orchestrator CLI exposes the following scaffolded subcommands:
`lint-structured`, `ingest-structured`, `ingest-pdf`, `extract-claims`,
`resolve-entities`, `ask`, `reset`, and `ingest`.

Environment/configuration values used by this demo:

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (database defaults to `neo4j`)
- `OPENAI_MODEL` (defaults to `gpt-4o-mini`)
- Demo vector index used by retrieval/reset flow: `chain_custody_chunk_embedding_index` (label: `Chunk`, embedding property: `embedding`, dimensions: `1536`)
- Deterministic index naming intentionally diverges from earlier claim-oriented naming so `reset_demo_db.py` can safely clean the exact demo-owned citation index.
