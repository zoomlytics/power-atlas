# Power Atlas

**Status:** Private research repository  
**Phase:** Active pipeline development — GraphRAG foundation operational

> ⚠️ **Not production ready**: Power Atlas is in an experimental research phase and is not suitable for production deployment or operational decision support.

## What This Repo Is

Power Atlas is a research platform for modeling networks of power, influence, and structural relationships using an **unstructured-first GraphRAG pipeline**. The core workflow is:

```
PDF / unstructured source
  → lexical graph (Document, Chunk nodes)
  → LLM claim + entity extraction (ExtractedClaim, EntityMention, HAS_PARTICIPANT edges)
  → entity clustering (ResolvedEntityCluster, MEMBER_OF edges)
  → [optional] canonical alignment (CanonicalEntity, ALIGNED_WITH edges)
  → citation-grounded Q&A (vector search + graph expansion, [CITATION|…] tokens required)
```

The pipeline has two resolution modes:

- **`unstructured_only`** (default) — fully operational end-to-end with only PDF input; clusters entity mentions across chunks without requiring any structured catalog.
- **`hybrid`** — adds a structured CSV ingest pass that creates `CanonicalEntity` nodes and `ALIGNED_WITH` edges, enabling cluster-aware retrieval (queries traverse entity clusters and canonical aliases to surface related mentions across the graph).

The working implementation lives in [`demo/`](demo/). The `backend/` and `frontend/` directories are minimal scaffolding and are **not connected to the pipeline** (see [Current Status](#current-status)).

---

## Core Design Principles

- **Evidence-first** — All modeled relationships must be supported by sources.
- **Source attribution required** — Provenance is not optional; all Q&A answers require `[CITATION|…]` tokens tracing to specific `Chunk` nodes (see [`docs/architecture/retrieval-semantics-v0.1.md`](docs/architecture/retrieval-semantics-v0.1.md)).
- **Structural analysis over narrative speculation** — Emphasis on relationships and topology rather than interpretation.
- **Political neutrality** — The system models structure, not ideology.
- **Architectural clarity over rapid productization** — Foundations precede features.
- **Modular experimentation** — Components are treated as replaceable until stabilized.

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- An OpenAI API key (for LLM extraction)

### 1. Clone and configure

```bash
git clone https://github.com/zoomlytics/power-atlas.git
cd power-atlas
cp .env.example .env
# Set NEO4J_PASSWORD (strong value), NEO4J_ACCEPT_LICENSE_AGREEMENT=yes,
# and OPENAI_API_KEY in .env
```

### 2. Start Neo4j

```bash
docker compose up neo4j -d
```

Neo4j will be available at:
- **Browser**: http://localhost:7474 (login with `NEO4J_USERNAME` / `NEO4J_PASSWORD`)
- **Bolt**: bolt://localhost:7687

#### Verify GDS

```cypher
CALL gds.version();
```

### 3. Run the demo pipeline

See **[`demo/README.md`](demo/README.md)** for the full walkthrough. A typical `unstructured_only` run:

```bash
set -a && source .env && set +a

# (Optional) reset graph
python demo/reset_demo_db.py

# Ingest PDF, extract claims, resolve entities, run Q&A
python demo/run_demo.py --mode unstructured_only
```

For the full `hybrid` pass (structured CSV → canonical alignment → cluster-aware retrieval):

```bash
python demo/run_demo.py --mode hybrid
```

Refer to [`demo/VALIDATION_RUNBOOK.md`](demo/VALIDATION_RUNBOOK.md) for a step-by-step validation checklist.

---

## Current Status

| Surface | Status |
|---------|--------|
| **`demo/` pipeline** | ✅ Operational — `unstructured_only` and `hybrid` modes working end-to-end |
| **`pipelines/`** | ✅ Operational — ingest/query/experiment scripts + run artifacts |
| **`backend/`** | 🚧 Disconnected scaffold — FastAPI stub with `/health` and placeholder `/graph/status` (HTTP 503); not connected to the GraphRAG pipeline |
| **`frontend/`** | 🚧 Disconnected scaffold — Next.js stub; not connected to the pipeline or backend |
| **Temporal modeling** | 📋 Planned — Architecture drafted ([`docs/architecture/temporal-modeling-v0.1.md`](docs/architecture/temporal-modeling-v0.1.md)) — not yet implemented in pipeline |
| **Confidence scoring** | 📋 Planned — Design in progress — not yet implemented |
| **HITL oversight** | 📋 Planned — Design in progress — not yet implemented |

---

## Repository Structure

```
power-atlas/
├── demo/                        # Self-contained GraphRAG pipeline (start here)
│   ├── README.md               # Full pipeline walkthrough and CLI reference
│   ├── VALIDATION_RUNBOOK.md   # Step-by-step end-to-end validation checklist
│   ├── run_demo.py             # Pipeline orchestrator CLI
│   ├── reset_demo_db.py        # Graph reset utility
│   ├── stages/                 # Pipeline stage modules
│   ├── fixtures/               # Sample PDF, CSV, and manifest
│   ├── tests/                  # Stage-level tests
│   └── config/                 # Pipeline configuration
├── pipelines/                   # Neo4j ingest/query/experiment scripts
│   ├── ingest/                 # Ingestion scripts
│   ├── query/                  # Query workbook + graph-health diagnostics
│   │   └── README.md          # Cypher query reference (v0.3)
│   ├── experiment/             # Exploratory scripts
│   └── runs/                   # Run artifacts (gitignored by default)
├── docs/                        # Versioned architecture and ontology documents
│   ├── architecture/
│   ├── ontology/
│   ├── provenance/
│   ├── metrics/
│   ├── agents/
│   ├── governance/
│   └── risk/
├── backend/                     # FastAPI stub (disconnected — see Current Status)
├── frontend/                    # Next.js stub (disconnected — see Current Status)
├── tests/                       # Repository-level tests
├── scripts/                     # Utility scripts (e.g., vendor sync)
├── studies/                     # Historical research and exploratory notes
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`demo/README.md`](demo/README.md) | Full pipeline walkthrough, CLI reference, and troubleshooting |
| [`demo/VALIDATION_RUNBOOK.md`](demo/VALIDATION_RUNBOOK.md) | Manual end-to-end validation checklist |
| [`pipelines/query/README.md`](pipelines/query/README.md) | Neo4j Browser Cypher query workbook (v0.3) |
| [`docs/architecture/v0.1.md`](docs/architecture/v0.1.md) | Core architecture design |
| [`docs/architecture/unstructured-first-entity-resolution-v0.1.md`](docs/architecture/unstructured-first-entity-resolution-v0.1.md) | Entity resolution architecture |
| [`docs/architecture/claim-argument-model-v0.3.md`](docs/architecture/claim-argument-model-v0.3.md) | Claim and participation model (v0.3) |
| [`docs/architecture/retrieval-semantics-v0.1.md`](docs/architecture/retrieval-semantics-v0.1.md) | Retrieval design and citation contract |
| [`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`](docs/architecture/retrieval-benchmark-review-rubric-v0.1.md) | Benchmark review rubric for regression comparison |
| [`docs/architecture/temporal-modeling-v0.1.md`](docs/architecture/temporal-modeling-v0.1.md) | Temporal relationship modeling (design only) |
| [`docs/ontology/v0.1.md`](docs/ontology/v0.1.md) | Ontology v0.1 |
| [`docs/provenance/v0.1.md`](docs/provenance/v0.1.md) | Provenance model v0.1 |
| [`docs/risk/risk-model-v0.1.md`](docs/risk/risk-model-v0.1.md) | Risk model |

---

## Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Key environment variables:

- `NEO4J_URI` — Neo4j Bolt URI (`bolt://localhost:7687` when connecting from the host; `bolt://neo4j:7687` when connecting from within the Docker Compose network)
- `NEO4J_USERNAME` — Neo4j username
- `NEO4J_PASSWORD` — Neo4j password (required; use a strong value)
- `NEO4J_ACCEPT_LICENSE_AGREEMENT` — Must be `yes` after reviewing [Neo4j and GDS license terms](#licensing)
- `NEO4J_UNRESTRICTED_PROCS` — Procedures allowed without restriction (defaults to `gds.*`)
- `OPENAI_API_KEY` — Required for LLM claim and entity extraction in the demo pipeline

---

## Development

### Vendor metadata sync

When the `vendor/neo4j-graphrag-python` submodule pin changes:

```bash
python scripts/sync_vendor_version.py
# Verify:
python scripts/sync_vendor_version.py --check
```

### Docker Compose services

```bash
# Start Neo4j only (sufficient for the demo pipeline)
docker compose up neo4j -d

# Start all services (includes disconnected backend/frontend stubs)
docker compose up --build

# Logs
docker compose logs -f neo4j
```

### Running pipeline scripts directly

```bash
set -a && source .env && set +a

python pipelines/ingest/<script>.py
python pipelines/query/<script>.py
```

Write run artifacts to `pipelines/runs/` and logs to `pipelines/logs/`.

---

## Licensing

By running this stack you accept the following license agreements:

- **Neo4j Community Edition**: [Neo4j Software License Agreement](https://neo4j.com/licensing/)
- **Neo4j Graph Data Science (GDS)**: [GDS License](https://neo4j.com/graph-data-science-software/) — GDS has a separate license from the Neo4j database. Review it before use.

The `NEO4J_ACCEPT_LICENSE_AGREEMENT` variable in `.env` must be set to `yes` to confirm acceptance.

---

## Contributing / Contact

Private repository — contributor model under consideration.

---

## License

**TBD**
