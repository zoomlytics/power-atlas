# Pipelines (scripts-first Neo4j workflows)

This directory is the scripts-first workspace for:

- `ingest/` — ingestion scripts
- `query/` — query/report scripts
- `experiment/` — exploratory scripts
- `runs/` — structured run outputs/artifacts
- `logs/` — script run logs

## Neo4j configuration

All scripts should read Neo4j settings from environment variables loaded from the repository `.env`:

- `NEO4J_URI` — use `bolt://localhost:7687` (the default in `.env.example`) when running scripts on the host. The Docker Compose backend uses `bolt://neo4j:7687` internally and does **not** rely on this value.
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `NEO4J_UNRESTRICTED_PROCS` (optional; used by the Docker Compose Neo4j service to allow specific procedures)

When connecting to an external Neo4j instance (not via Docker Compose), only `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` are required; `NEO4J_UNRESTRICTED_PROCS` can be omitted.
## Developer workflow

From the repository root:

```bash
cp .env.example .env  # once
# set a strong NEO4J_PASSWORD and any local overrides
set -a && source .env && set +a

# run scripts (examples - see each subdirectory for scripts as they are added)
python pipelines/ingest/<script>.py
python pipelines/query/<script>.py
python pipelines/experiment/<script>.py
```

> **Note:** Example scripts for each workflow stage are coming soon. Check `ingest/`, `query/`, and `experiment/` subdirectories as the migration progresses.

Write run outputs under `pipelines/runs/` and logs under `pipelines/logs/`.
