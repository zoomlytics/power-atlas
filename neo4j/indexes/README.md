# Indexes

Store versioned Neo4j index assets here.

## Current concrete asset

- `demo_chunk_embedding_index.cypher`: the current demo vector-index contract
	for `:Chunk(embedding)` with `1536` dimensions.

## Current ownership note

The runtime/demo path still creates this index today during live PDF ingest,
and `demo/reset_demo_db.py` still owns the corresponding drop behavior.

This file is the first operational-source artifact for that contract. Any
future migration of index creation out of runtime code should keep this file as
the source-of-truth asset and move the runtime path to calling or referencing
it rather than re-declaring the contract separately.