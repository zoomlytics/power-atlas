# Vendor Contract: neo4j-graphrag-python

## Role in Power Atlas

`neo4j-graphrag-python` is the vendored GraphRAG backbone used for experimental knowledge-graph construction from unstructured inputs (text/PDF) into Neo4j. In this repository, it is currently used in example pipelines that validate KG-building workflows and LLM-driven extraction patterns.

## Upstream Source and Pinned Version

- Upstream repository: https://github.com/neo4j/neo4j-graphrag-python
- Vendored path: `vendor/neo4j-graphrag-python` (git submodule)
- Pinned commit: `74bb97ca3cf9a04bf69e68b1504b17a90c5ec029`
- Version metadata file: [`/docs/vendor/neo4j-graphrag-python.version.json`](/docs/vendor/neo4j-graphrag-python.version.json)
- Upstream README at pinned commit: https://github.com/neo4j/neo4j-graphrag-python/blob/74bb97ca3cf9a04bf69e68b1504b17a90c5ec029/README.md
- Upstream docs root at pinned commit: https://github.com/neo4j/neo4j-graphrag-python/tree/74bb97ca3cf9a04bf69e68b1504b17a90c5ec029/docs
- Upstream examples folder at pinned commit: https://github.com/neo4j/neo4j-graphrag-python/tree/74bb97ca3cf9a04bf69e68b1504b17a90c5ec029/examples

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

- Submodule declaration: `.gitmodules`
- Python dependency declaration: `requirements.txt`
- Example integrations:
  - `examples/build_graph/simple_kg_builder_from_text.py`
  - `examples/build_graph/simple_kg_builder_from_pdf.py`
- Neo4j runtime/plugin config: `docker-compose.yml`

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
2. Bump the submodule pin and stage it:
   - `git submodule update --remote vendor/neo4j-graphrag-python`
   - `git add vendor/neo4j-graphrag-python`
   - verify the new SHA with `git submodule status -- vendor/neo4j-graphrag-python`.
3. Regenerate version metadata so docs and gitlink stay aligned:
   - run `python scripts/sync_vendor_version.py`
   - review `docs/vendor/neo4j-graphrag-python.version.json` and confirm `pinned_commit_sha` matches step 2 (update `tag` in the same file when moving to a new upstream release tag).
4. Update links in this vendor contract page to stable commit-pinned URLs:
   - update `Pinned commit`
   - update `Upstream README at pinned commit`
   - update `Upstream docs root at pinned commit`
   - always use `/blob/<sha>/...` or `/tree/<sha>/...` links (not branch-based links like `main`) so references remain stable over time.
5. Verify Power Atlas integration points still match upstream API:
   - `examples/build_graph/simple_kg_builder_from_text.py`
   - `examples/build_graph/simple_kg_builder_from_pdf.py`
6. Validate local runtime assumptions (Neo4j connectivity, APOC availability, `OPENAI_API_KEY`).
7. If upstream changes require dependency constraints, update `requirements.txt` accordingly.
8. Verify CI consistency before/after pushing:
   - local check: `python scripts/sync_vendor_version.py --check`
   - confirm `.github/workflows/vendor-version-consistency.yml` passes in GitHub Actions for the PR.
