# Chain of Custody Demo (dataset v1)

Self-contained demo workflow under `demo/chain_of_custody/` for evidence-driven influence research with structured and unstructured artifacts.

## Workflow (golden path)

1. **Reset graph safely**
   ```bash
   python demo/chain_of_custody/reset_demo_db.py --confirm
   ```
2. **Run orchestrator**
   ```bash
   python demo/chain_of_custody/run_demo.py --dry-run
   ```
3. **Run smoke test**
   ```bash
   python demo/chain_of_custody/smoke_test.py
   ```
   By default this writes artifacts to an isolated temporary directory (pass `--output-dir` to override).

`--dry-run` keeps the workflow reproducible without requiring live OpenAI/Neo4j calls.

## What the orchestrator stages model

- PDF ingest (chunk/embed/store) using vendor-aligned component choices (`FixedSizeSplitter`, `OpenAIEmbeddings`, `OpenAILLM`)
- Structured CSV ingest with claims-first modeling (`Claim`, `CanonicalEntity`, evidence-linked relationships)
- Narrative claim extraction + mention resolution stages (deterministic canonical key resolution)
- Retrieval and GraphRAG Q&A stage with strict citation expectations
- Run artifacts written to `demo/chain_of_custody/artifacts/manifest.json`

## Fixtures and reproducibility

- `fixtures/structured/*.csv`: claim/evidence graph seed rows
- `fixtures/unstructured/chain_of_custody.pdf`: fixture pointer to canonical source PDF
- `fixtures/manifest.json`: dataset contract, provenance, and license note

Reset script deletes generic labels and drops the demo index `chain_custody_claim_embedding_index`; run it only against a dedicated demo database/graph to avoid wiping non-demo data.

## Vendor-resources alignment map

This demo intentionally mirrors upstream patterns in `vendor-resources`:

- KG pipeline composition: `vendor-resources/examples/build_graph/simple_kg_builder_from_pdf.py`
- Two-stage lexical/entity pattern: `vendor-resources/examples/customize/build_graph/pipeline/text_to_lexical_graph_to_entity_graph_two_pipelines.py`
- Retriever formatting and pre-filters: `vendor-resources/examples/customize/retrievers/result_formatter_vector_cypher_retriever.py`, `vendor-resources/examples/customize/retrievers/use_pre_filters.py`
- GraphRAG Q&A and message history patterns: `vendor-resources/examples/question_answering/graphrag.py`, `vendor-resources/examples/question_answering/graphrag_with_message_history.py`

Use these vendor examples as the first source of truth when evolving this demo.
