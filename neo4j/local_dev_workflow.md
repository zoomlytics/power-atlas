# Neo4j Local/Test Workflow

This document records the current local/test workflow for Neo4j-backed Power
Atlas development.

It is intentionally operational rather than architectural: it describes how the
repo is actually provisioned and validated today without claiming a finalized
migration runner or graph-ops automation layer.

## Prerequisites

- Docker and Docker Compose
- a populated `.env` derived from `.env.example`
- accepted Neo4j and GDS license terms for local use

## Required environment values

At minimum, local Neo4j provisioning depends on:

- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USERNAME=neo4j`
- `NEO4J_PASSWORD=<local password>`
- `NEO4J_ACCEPT_LICENSE_AGREEMENT=yes`

The compose setup also accepts:

- `NEO4J_UNRESTRICTED_PROCS`
- `NEO4J_ALLOWLIST_PROCS`

## Provision the local Neo4j server

Start the Neo4j service with:

```bash
docker compose up -d neo4j
```

Current local repo assumptions:

- Neo4j image: `neo4j:5.22.0`
- plugins: `graph-data-science`, `apoc`
- browser endpoint: `http://localhost:7474`
- bolt endpoint: `bolt://localhost:7687`
- ports are loopback-bound by default

## Basic verification

After the container is healthy, verify the database is reachable and GDS is
available.

In the Neo4j browser:

```cypher
CALL gds.version();
```

Or with `cypher-shell`:

```bash
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" \
  'CALL gds.version()'
```

## Optional reset before a demo run

To clear demo-owned graph content before a local validation run:

```bash
python -m demo.reset_demo_db --confirm
```

The current reset contract is documented at:

- `neo4j/diagnostics/demo_reset_scope.md`
- `neo4j/diagnostics/check_demo_reset_scope.cypher`

## Apply or verify the current vector-index contract

The current demo vector-index asset is:

- `neo4j/indexes/demo_chunk_embedding_index.cypher`

The fastest verification path is the read-only diagnostic:

```bash
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" \
  -f neo4j/diagnostics/check_demo_chunk_embedding_index.cypher
```

If you need to apply the current index asset manually:

```bash
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" \
  -f neo4j/indexes/demo_chunk_embedding_index.cypher
```

## Demo pipeline validation flow

The current practical local flow is:

1. `docker compose up -d neo4j`
2. `set -a && source .env && set +a`
3. `python -m demo.reset_demo_db --confirm` when a clean demo graph is needed
4. run the demo pipeline stages
5. run read-only diagnostics and retrieval validation

Typical sequence:

```bash
set -a && source .env && set +a
python -m demo.reset_demo_db --confirm
python -m demo.run_demo --live ingest-pdf
python -m demo.run_demo --live extract-claims
python -m demo.run_demo --live resolve-entities
python -m demo.run_demo --live ask --question "Your question here"
```

## Current ownership boundary

Today this workflow is still split across:

- `docker-compose.yml` for server provisioning
- `.env.example` for required env keys
- `demo/reset_demo_db.py` for the executable reset path
- `demo/run_demo.py` and stage entrypoints for ingest/query execution
- `neo4j/` for the repo-owned operational assets that are being externalized

That split is acceptable at the current checkpoint. Future Phase 6 work should
move stable operational contracts into `neo4j/` without duplicating runtime
ownership.