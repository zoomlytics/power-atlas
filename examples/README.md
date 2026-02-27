# Power Atlas Demo (Synthetic PDFs)

This README documents the end-to-end demo in `/examples` for:

- ingesting the synthetic PDFs into Neo4j,
- validating the graph with Cypher,
- running retrieval + QA with strict citations.

## Prerequisites

1. **Python environment** with repository dependencies installed.
2. **Neo4j 5.x** running and reachable.
3. **Environment variables** configured in `.env` (copy from `.env.example`):

```bash
cp .env.example .env
```

Minimum values for this demo:

- `NEO4J_URI` (default in scripts: `neo4j://localhost:7687`)
- `NEO4J_USERNAME` (default: `neo4j`)
- `NEO4J_PASSWORD` (default in scripts is placeholder; set a real one)
- `NEO4J_DATABASE` (default: `neo4j`)
- `OPENAI_API_KEY` (required for ingestion and QA)

Optional tuning values used by scripts:

- `CHUNK_SIZE` (default `1000`)
- `CHUNK_OVERLAP` (default `100`)
- `CHUNK_APPROXIMATE` (default `true`)
- `NEO4J_VECTOR_INDEX` (default `chunk_embedding_index`)
- `TOP_K` (default `5`)
- `RETRIEVAL_CORPUS`, `RETRIEVAL_DOC_TYPE`, `RETRIEVAL_DOCUMENT_PATH`

### Vector index check (required for retrieval)

Before running retrieval, ensure the vector index exists:

```cypher
SHOW INDEXES
YIELD name, type, state
WHERE name = 'chunk_embedding_index'
RETURN name, type, state;
```

## Ingestion usage (both synthetic PDFs)

Script:

```bash
python /home/runner/work/power-atlas/power-atlas/examples/build_graph/simple_kg_builder_from_pdf.py
```

What it ingests:

- `/home/runner/work/power-atlas/power-atlas/examples/data/power_atlas_factsheet.pdf`
- `/home/runner/work/power-atlas/power-atlas/examples/data/power_atlas_analyst_note.pdf`

Metadata written per document:

- factsheet: `corpus=power_atlas_demo`, `doc_type=facts`
- analyst note: `corpus=power_atlas_demo`, `doc_type=narrative`

Reset logic: the ingest script calls `reset_document_lexical_graph(...)` for each document path before writing, deleting prior `Document` and connected `Chunk` nodes for that same path.

## Retrieval + QA usage

Script:

```bash
python /home/runner/work/power-atlas/power-atlas/examples/retrieve/local_pdf_graphrag.py \
  --query "Summarize links between Lina Park, Northbridge Energy Cooperative, and the Harbor Grid Upgrade Hearing." \
  --corpus power_atlas_demo \
  --doc-type all \
  --inspect-retrieval
```

Useful filter examples:

```bash
# Facts only
python /home/runner/work/power-atlas/power-atlas/examples/retrieve/local_pdf_graphrag.py \
  --doc-type facts --corpus power_atlas_demo --query "List key people."

# Narrative only
python /home/runner/work/power-atlas/power-atlas/examples/retrieve/local_pdf_graphrag.py \
  --doc-type narrative --corpus power_atlas_demo --query "What sequence of events is described?"
```

Behavior notes:

- Retrieval uses `top_k` from `TOP_K` and `chunk_embedding_index` (or `NEO4J_VECTOR_INDEX`).
- Query params support corpus/doc-type/path filtering.
- Prompt enforces **strict citations**: each answer bullet must include a source header like `[source: ... | hitChunk: ... | score: ...]`.

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
RETURN labels(n)[0] AS label, coalesce(n.name, '<no-name>') AS name
LIMIT 25;
```

```cypher
MATCH (a)-[r]->(b)
WHERE (a:Person OR a:Organization OR a:Event)
  AND (b:Person OR b:Organization OR b:Event)
RETURN labels(a)[0] AS src_label, coalesce(a.name, '<no-name>') AS src,
       type(r) AS rel,
       labels(b)[0] AS dst_label, coalesce(b.name, '<no-name>') AS dst
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

## Example QA output (shape)

Example strict-citation answer format:

```text
- Lina Park is linked to Northbridge Energy Cooperative in the extracted context. [source: .../power_atlas_factsheet.pdf | hitChunk: 2 | score: 0.83]
- The Harbor Grid Upgrade Hearing is referenced alongside those actors in the narrative timeline. [source: .../power_atlas_analyst_note.pdf | hitChunk: 4 | score: 0.81]
- ...
```

## Troubleshooting

- **`OPENAI_API_KEY` missing**: ingestion/retrieval will fail at model calls.
- **No retrieval hits**: confirm ingest succeeded and `chunk_embedding_index` exists.
- **Unexpected empty results with filters**: verify `Document.corpus`, `Document.doc_type`, and `Document.path` values.
- **Duplicate contexts in retrieval output**: the retrieval script de-duplicates normalized contexts before trace printing.

## Licensing / distribution note (synthetic PDFs)

The demo PDFs in `/examples/data` are synthetic test artifacts created for repository examples and validation. Keep them with this repository context; do not represent them as real-world source documents.
