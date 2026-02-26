# Vendor Contract: neo4j-graphrag-python

## Role in Power Atlas

`neo4j-graphrag-python` is the vendored GraphRAG backbone used for experimental knowledge-graph construction from unstructured inputs (text/PDF) into Neo4j. In this repository, it is currently used in example pipelines that validate KG-building workflows and LLM-driven extraction patterns.

## Upstream Source and Pinned Version

- Upstream repository: https://github.com/neo4j/neo4j-graphrag-python
- Vendored path: `/home/runner/work/power-atlas/power-atlas/vendor/neo4j-graphrag-python` (git submodule)
- Pinned commit: `74bb97ca3cf9a04bf69e68b1504b17a90c5ec029`
- Upstream README at pinned commit: https://github.com/neo4j/neo4j-graphrag-python/blob/74bb97ca3cf9a04bf69e68b1504b17a90c5ec029/README.md
- Upstream docs root at pinned commit: https://github.com/neo4j/neo4j-graphrag-python/tree/74bb97ca3cf9a04bf69e68b1504b17a90c5ec029/docs

## Features and APIs Used in Power Atlas

Current integration uses the following APIs:

- `neo4j_graphrag.experimental.pipeline.kg_builder.SimpleKGPipeline`
- `neo4j_graphrag.embeddings.OpenAIEmbeddings`
- `neo4j_graphrag.llm.OpenAILLM`
- `neo4j_graphrag.experimental.pipeline.pipeline.PipelineResult`
- `neo4j_graphrag.experimental.pipeline.types.schema` (`EntityInputType`, `RelationInputType`)

These are used for:

- schema-constrained entity/relationship extraction
- asynchronous KG ingestion via `run_async(...)`
- OpenAI-based embeddings and LLM orchestration during ingestion

## Local Integration Points (Paths, Adapters, Config)

### Paths

- Submodule declaration: `/home/runner/work/power-atlas/power-atlas/.gitmodules`
- Python dependency declaration: `/home/runner/work/power-atlas/power-atlas/requirements.txt`
- Example integrations:
  - `/home/runner/work/power-atlas/power-atlas/examples/build_graph/simple_kg_builder_from_text.py`
  - `/home/runner/work/power-atlas/power-atlas/examples/build_graph/simple_kg_builder_from_pdf.py`
- Neo4j runtime/plugin config: `/home/runner/work/power-atlas/power-atlas/docker-compose.yml`

### Adapters

- No dedicated internal adapter/wrapper layer is implemented yet; current usage is direct imports from `neo4j_graphrag` in example scripts.

### Configuration

- Neo4j connection variables: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- LLM provider variable: `OPENAI_API_KEY` (required for OpenAI-backed examples)
- Docker Neo4j plugin requirement: APOC is enabled because KG writer flows rely on APOC procedures.

## Operational / Execution Requirements

- Python dependency includes `neo4j-graphrag[openai]`.
- Neo4j 5.x must be reachable from the executing process.
- APOC must be available in the Neo4j instance for KG writer operations.
- OpenAI credentials must be provided for `OpenAILLM` / `OpenAIEmbeddings` examples.
- Execute examples from repository root so relative paths (e.g., PDF sample location) resolve as expected.

## Vendor Update Procedure

1. Inspect upstream release notes/changelog for API or behavior changes.
2. Update submodule reference:
   - `git submodule update --remote vendor/neo4j-graphrag-python`
   - confirm new pinned commit in `git submodule status`.
3. Verify Power Atlas integration points still match upstream API:
   - `examples/build_graph/simple_kg_builder_from_text.py`
   - `examples/build_graph/simple_kg_builder_from_pdf.py`
4. Validate local runtime assumptions (Neo4j connectivity, APOC availability, `OPENAI_API_KEY`).
5. If upstream changes require dependency constraints, update `/home/runner/work/power-atlas/power-atlas/requirements.txt` accordingly.
6. Update this document with the new pinned commit and refreshed upstream links.
