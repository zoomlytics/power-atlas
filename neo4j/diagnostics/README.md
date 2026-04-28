# Diagnostics

Store repeatable operational graph diagnostics here when they are promoted out
of runtime/query scripts.

## Current concrete asset

- `check_demo_chunk_embedding_index.cypher`: verifies that the current demo
	vector index exists and returns its live metadata from the connected Neo4j
	database.
- `check_demo_reset_scope.cypher`: returns live node counts for the labels that
	the current demo reset treats as demo-owned wipe targets.
- `demo_reset_scope.md`: repo-owned inventory of the current demo reset wipe,
	stale-edge cleanup, and index-drop scope.

## Usage

Run this query in the Neo4j browser or via `cypher-shell` against the target
database after local provisioning or demo ingest.

This is intentionally read-only. It is meant to answer the operational question
“does the expected demo vector index exist in this database, and what metadata
is Neo4j currently exposing for it?”

`check_demo_reset_scope.cypher` is also intentionally read-only. It answers the
operational question “what footprint would the current demo reset remove if I
ran it against this database right now?”