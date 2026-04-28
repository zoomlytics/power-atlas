# Diagnostics

Store repeatable operational graph diagnostics here when they are promoted out
of runtime/query scripts.

## Current concrete asset

- `check_demo_chunk_embedding_index.cypher`: verifies that the current demo
	vector index exists and returns its live metadata from the connected Neo4j
	database.

## Usage

Run this query in the Neo4j browser or via `cypher-shell` against the target
database after local provisioning or demo ingest.

This is intentionally read-only. It is meant to answer the operational question
“does the expected demo vector index exist in this database, and what metadata
is Neo4j currently exposing for it?”