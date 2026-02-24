# Pipelines (scripts-first Neo4j workflows)

This directory is the scripts-first workspace for:

- `ingest/` — ingestion scripts
- `query/` — query/report scripts
- `experiment/` — exploratory scripts
- `runs/` — structured run outputs/artifacts
- `logs/` — script run logs

## Neo4j configuration

All scripts should read Neo4j settings from environment variables loaded from the repository `.env`:

- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`

## Developer workflow

From the repository root:

```bash
cp .env.example .env  # once
# set a strong NEO4J_PASSWORD and any local overrides
set -a && source .env && set +a

# run scripts (examples)
python pipelines/ingest/<script>.py
python pipelines/query/<script>.py
python pipelines/experiment/<script>.py
```

Write run outputs under `pipelines/runs/` and logs under `pipelines/logs/`.
