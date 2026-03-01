# Power Atlas Demo (Synthetic PDFs)

This README documents the end-to-end demo in `/examples` for:

- ingesting the synthetic PDFs into Neo4j,
- validating the graph with Cypher,
- running retrieval + QA with strict citations.

## Prerequisites

Run all commands below from the repository root (the directory containing `.env.example` and `examples/`).

1. **Python environment** with repository dependencies installed.
2. **Neo4j 5.x** running and reachable.
3. **Environment variables** configured in `.env` (copy from `.env.example`) and exported for retrieval:

```bash
cp .env.example .env

# Ingestion script loads .env automatically.
# Retrieval script reads environment variables from the shell.
# Ensure .env values are exported to child processes.
set -a
source .env
set +a
```

Minimum values for this demo:

- `NEO4J_URI` (default in scripts: `neo4j://localhost:7687`)
- `NEO4J_USERNAME` (default: `neo4j`)
- `NEO4J_PASSWORD` (default in scripts: `testtesttest`; when running Neo4j via docker-compose or in any non-demo setup, set a real password and ensure it matches your Neo4j configuration)
- `NEO4J_DATABASE` (default: `neo4j`)
- `OPENAI_API_KEY` (required for ingestion, retrieval, and QA)

Optional tuning values used by scripts:

- `CHUNK_SIZE` (default `1000`)
- `CHUNK_OVERLAP` (default `100`)
- `CHUNK_APPROXIMATE` (default `true`)
- `NEO4J_VECTOR_INDEX` (default `chunk_embedding_index`)
- `TOP_K` (default `5`)
- `RETRIEVAL_CORPUS`, `RETRIEVAL_DOC_TYPE`, `RETRIEVAL_DOCUMENT_PATH`
- `RETRIEVAL_INSPECT` (default `false`; enables retrieval inspection output, mirroring `--inspect-retrieval`)
- Two-pipeline toggles for ingestion (default shown): `RUN_LEXICAL_PIPELINE=true`, `RUN_ENTITY_PIPELINE=true`, `RESET_LEXICAL_GRAPH=true`, `RESET_ENTITY_GRAPH=false`

### Vector index check (required for retrieval)

Before running retrieval, ensure the vector index configured by `NEO4J_VECTOR_INDEX` exists (default: `chunk_embedding_index`). If you changed `NEO4J_VECTOR_INDEX`, replace the value in the query below:

```cypher
SHOW INDEXES
YIELD name, type, state
WHERE name = 'chunk_embedding_index'  // replace with your NEO4J_VECTOR_INDEX value if different
RETURN name, type, state;
```

## Ingestion usage (both synthetic PDFs)

Script:

```bash
python examples/build_graph/simple_kg_builder_from_pdf.py
```

What it ingests:

- `examples/data/power_atlas_factsheet.pdf`
- `examples/data/power_atlas_analyst_note.pdf`

Metadata written per document:

- factsheet: `corpus=power_atlas_demo`, `doc_type=facts`
- analyst note: `corpus=power_atlas_demo`, `doc_type=narrative`

Two-pipeline flow (aligned with the upstream vendor example):

- **Pipeline A (lexical only)**: builds `Document` + `Chunk` nodes and embeddings. Controlled by `RUN_LEXICAL_PIPELINE` and `RESET_LEXICAL_GRAPH` (per-document reset only deletes the lexical graph; entity nodes remain).
- **Pipeline B (entity)**: reads chunks from Neo4j via `Neo4jChunkReader` and runs extraction with `create_lexical_graph=False`, reusing the stored lexical graph and writing provenance (`FROM_CHUNK`, `FROM_DOCUMENT`, `document_path`). Controlled by `RUN_ENTITY_PIPELINE`; set `RESET_ENTITY_GRAPH=true` to drop only the extracted entity subgraph for a document before re-running extraction.
- Entity extraction now uses a schema-with-properties pattern (`PropertyType`) for `Person`, `Organization`, `Event`, `FactSheet`, and `AnalystNote` plus relationship properties (for example `RELATED_TO.type`, `RELATED_TO.date`, `MENTIONED_IN.source_type`). Deduplication runs after both PDFs are processed, using label-specific keys (`name`, `firm_name`, `subject`) for consistent cross-document resolution.
- Provenance chain to validate in graph queries: `Entity -[:FROM_CHUNK]-> Chunk -[:FROM_DOCUMENT]-> Document`.
- Resolver pre-filter pattern now scopes to document provenance relationships (vendor-aligned): `WHERE (entity)-[:FROM_CHUNK]->(:Chunk)-[:FROM_DOCUMENT]->(doc:Document) AND doc.path IN [...]`.
- Use `reset_document_derived_graph(...)` when you need a single safe utility call to reset both lexical (`Document`/`Chunk`) and entity-derived data for one document path.

## Retrieval + QA usage

Script:

```bash
python examples/retrieve/local_pdf_graphrag.py \
  --query "Summarize links between Lina Park, Northbridge Energy Cooperative, and the Harbor Grid Upgrade Hearing." \
  --corpus power_atlas_demo \
  --doc-type all \
  --inspect-retrieval
```

Useful filter examples:

```bash
# Facts only
python examples/retrieve/local_pdf_graphrag.py \
  --doc-type facts --corpus power_atlas_demo --query "List key people."

# Narrative only
python examples/retrieve/local_pdf_graphrag.py \
  --doc-type narrative --corpus power_atlas_demo --query "What sequence of events is described?"
```

Behavior notes:

- Retrieval uses `TOP_K` for `top_k` and `NEO4J_VECTOR_INDEX` for the vector index (default: `chunk_embedding_index`).
- Retriever pre-filters support corpus/doc-type/path filtering via `filters=` when searching.
- Context snippets are built via a dedicated retriever `result_formatter` for deterministic `[source ...]` headers and neighbor windows.
- QA uses a `RagTemplate` with **strict citations**: each answer bullet must include a source header like `[source: ... | hitChunk: ... | score: ...]`.

## Cypher validation queries

### 1) Count Documents and Chunks

```cypher
MATCH (d:Document {corpus: 'power_atlas_demo'})
OPTIONAL MATCH (d)<-[:FROM_DOCUMENT]-(c:Chunk)
RETURN count(DISTINCT d) AS documents, count(DISTINCT c) AS chunks;
```

### 2) Show chunk indices per document

```cypher
MATCH (d:Document {corpus: 'power_atlas_demo'})<-[:FROM_DOCUMENT]-(c:Chunk)
RETURN d.path AS path, min(c.index) AS min_chunk, max(c.index) AS max_chunk, count(c) AS chunk_count
ORDER BY path;
```

### 3) Top Person/Organization/Event nodes and relationships

```cypher
MATCH (n)
WHERE n:Person OR n:Organization OR n:Event
OPTIONAL MATCH (n)-[r]-()
RETURN labels(n)[0] AS label, coalesce(n.name, '<no-name>') AS name, count(r) AS degree
ORDER BY degree DESC, label, name
LIMIT 25;
```

```cypher
MATCH (a)-[r]->(b)
WHERE (a:Person OR a:Organization OR a:Event)
  AND (b:Person OR b:Organization OR b:Event)
RETURN labels(a)[0] AS src_label, coalesce(a.name, '<no-name>') AS src,
       type(r) AS rel,
       labels(b)[0] AS dst_label, coalesce(b.name, '<no-name>') AS dst,
       count(*) AS occurrences
ORDER BY occurrences DESC, src_label, src, rel, dst_label, dst
LIMIT 50;
```

### 4) Cross-document entity resolution sanity check

```cypher
MATCH (d:Document {corpus: 'power_atlas_demo'})<-[:FROM_DOCUMENT]-(c:Chunk)-[]->(e)
WHERE e:Person OR e:Organization OR e:Event
WITH coalesce(e.name, '<no-name>') AS entity, labels(e)[0] AS label, collect(DISTINCT d.path) AS docs
WHERE size(docs) > 1
RETURN label, entity, docs
ORDER BY label, entity;
```

Expected signal: key entities (for example `Lina Park`, `Northbridge Energy Cooperative`, and `Harbor Grid Upgrade Hearing`) should appear with `docs` containing both synthetic PDF paths.

### 5) Provenance chain sanity check

```cypher
MATCH (d:Document {corpus: 'power_atlas_demo'})<-[:FROM_DOCUMENT]-(c:Chunk)<-[:FROM_CHUNK]-(e)
RETURN labels(e)[0] AS entity_label, coalesce(e.name, e.firm_name, e.subject, '<no-key>') AS entity_key,
       d.path AS document_path, c.index AS chunk_index
ORDER BY entity_label, entity_key, document_path, chunk_index
LIMIT 50;
```

## Example QA output (shape)

Example strict-citation answer format:

```text
- Lina Park is linked to Northbridge Energy Cooperative in the extracted context. [source: .../power_atlas_factsheet.pdf | hitChunk: 2 | score: 0.83]
- The Harbor Grid Upgrade Hearing is referenced alongside those actors in the narrative timeline. [source: .../power_atlas_analyst_note.pdf | hitChunk: 4 | score: 0.81]
- ...
```

## Troubleshooting

- **`OPENAI_API_KEY` missing**: ingestion/retrieval will fail at model calls.
- **No retrieval hits**: confirm ingest succeeded and the vector index named by `NEO4J_VECTOR_INDEX` exists (default: `chunk_embedding_index`).
- **Unexpected empty results with filters**: verify `Document.corpus`, `Document.doc_type`, and `Document.path` values.
- **Duplicate contexts in retrieval output**: the retrieval script de-duplicates normalized contexts before trace printing.

## Licensing / distribution note (synthetic PDFs)

The demo PDFs in `/examples/data` are synthetic test artifacts created for repository examples and validation. Keep them with this repository context; do not represent them as real-world source documents.
