# Power Atlas

**Status:** Private research repository  
**Phase:** Experimental architecture & semantic foundation design

> ⚠️ **Not production ready**: Power Atlas is in an experimental research phase and is not suitable for production deployment or operational decision support.

Power Atlas is a research-first initiative to design and build an evidence-based platform for modeling networks of power, influence, and structural relationships across time.

The project explores how influence propagates through complex systems — including people, organizations, institutions, capital flows, ideas, and events — while preserving transparency, source attribution, and ethical safeguards.

Power Atlas combines elements of:

- Structured knowledge systems  
- Knowledge graph modeling  
- Investigative research tooling  
- Network science  
- AI-assisted research workflows  

The current focus is on establishing a trustworthy structural and semantic foundation before product-level development.

## Documentation Philosophy (v0.1)

Current documentation is intentionally architecture-first and versioned as **v0.1** while core models are still unstable.

- Prioritize principles, constraints, and system boundaries over implementation detail.
- Keep ontology/provenance semantics explicit and reviewable before scaling features.
- Use lightweight, versioned artifacts that can evolve without implying production guarantees.

Documentation artifacts are planned under `/docs` and will be aligned to these principles:

- `/docs/architecture`
  - Initial draft: [`/docs/architecture/v0.1.md`](/docs/architecture/v0.1.md)
  - Temporal modeling draft: [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md)
- `/docs/ontology`
  - Initial draft: [`/docs/ontology/v0.1.md`](/docs/ontology/v0.1.md)
  - Direction draft (forward-looking, not part of v0.1 baseline): [`/docs/ontology/v0.2-direction.md`](/docs/ontology/v0.2-direction.md)
  - Entity resolution draft: [`/docs/ontology/entity-resolution-v0.1.md`](/docs/ontology/entity-resolution-v0.1.md)
  - Semantic invariants draft: [`/docs/ontology/validation/semantic-invariants-v0.1.md`](/docs/ontology/validation/semantic-invariants-v0.1.md)
- `/docs/provenance`
  - Initial draft: [`/docs/provenance/v0.1.md`](/docs/provenance/v0.1.md)
  - Epistemic invariants draft: [`/docs/provenance/epistemic-invariants-v0.1.md`](/docs/provenance/epistemic-invariants-v0.1.md)
- `/docs/metrics`
  - Analysis philosophy draft: [`/docs/metrics/analysis-philosophy-v0.1.md`](/docs/metrics/analysis-philosophy-v0.1.md)
- `/docs/agents`
  - Governance draft: [`/docs/agents/governance-v0.1.md`](/docs/agents/governance-v0.1.md)
- `/docs/risk`
  - Initial draft: [`/docs/risk/risk-model-v0.1.md`](/docs/risk/risk-model-v0.1.md)

---

## Core Design Principles

Power Atlas is guided by the following principles:

- **Evidence-first** — All modeled relationships must be supported by sources.
- **Source attribution required** — Provenance is not optional.
- **Time-aware modeling** — Relationships are temporally scoped.
- **Confidence scoring** — Distinguish between verified fact, allegation, and inference.
- **Human-in-the-loop oversight** — Automated systems assist but do not autonomously publish.
- **Structural analysis over narrative speculation** — Emphasis on relationships and topology rather than interpretation.
- **Political neutrality** — The system models structure, not ideology.
- **Architectural clarity over rapid productization** — Foundations precede features.
- **Modular experimentation** — Components are treated as replaceable until stabilized.

---

## Current Technical Scaffold (Experimental)

This repository currently contains a minimal experimental stack used to explore semantic modeling and graph capabilities:

### Stack

- **Backend**: Python + FastAPI
- **Database**: Neo4j 5.x with Graph Data Science (via Docker Compose)
- **Frontend**: Next.js (React + TypeScript) + Tailwind CSS
- **Orchestration**: Docker Compose

The focus at this stage is on ontology formalization, provenance modeling, temporal semantics, and graph experimentation — not UI polish or production readiness.

---

## Current Focus Areas

- Ontology formalization
- Provenance and confidence schema design
- Temporal relationship modeling
- Graph capability experiments (centrality, pathfinding, multiplex tagging)
- Dataset ingestion spikes
- Entity resolution strategy
- Agent workflow architecture

---

## Non-Goals (Current Phase)

Power Atlas is not currently:

- A public investigative platform
- A journalism outlet
- A political advocacy tool
- A production-ready analytics platform

The present goal is foundational research and architectural clarity.

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/zoomlytics/power-atlas.git
cd power-atlas
```

### 2. Configure environment

Copy `.env.example` to `.env` and set strong Neo4j connection values (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`).

### 3. Start the stack

```bash
docker compose up --build
```

This will:
- Start the FastAPI backend on port 8000
- Start the Next.js frontend on port 3000
- Start Neo4j 5.x with the Graph Data Science plugin on ports 7474 (Browser) and 7687 (Bolt)

### 4. Access the application

Open your browser and navigate to:
- **Frontend**: http://localhost:3000
- **Backend API Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (user from `NEO4J_USERNAME`, password from `NEO4J_PASSWORD`)

> ⚠️ Set a strong `NEO4J_PASSWORD` before running in any shared or production-like environment. The example value is a placeholder and must be replaced.

#### Verify Neo4j + GDS

1. Open Neo4j Browser at http://localhost:7474 and log in with `NEO4J_USERNAME` and `NEO4J_PASSWORD`.
2. Ensure GDS procedures are available (defaults allow `gds.*` for local use). If you overrode `NEO4J_UNRESTRICTED_PROCS`, set it to `gds.*` for this step.
3. Run:
   ```cypher
   CALL gds.version();
   ```
4. You should see a version string confirming the Graph Data Science plugin is loaded.

### 5. Run a demo (Neo4j Browser)

Run these in Neo4j Browser to create and query demo data:

1. Seed sample nodes and relationships:
   ```cypher
   CREATE (a:Person {name: 'Alice', age: 30}),
          (b:Person {name: 'Bob', age: 35}),
          (c:Person {name: 'Charlie', age: 28}),
          (a)-[:KNOWS {since: 2020}]->(b),
          (b)-[:KNOWS {since: 2021}]->(c);
   ```

2. Try example queries:
   ```cypher
   MATCH (n:Person) RETURN n
   ```
   
   ```cypher
   MATCH (a:Person)-[r:KNOWS]->(b:Person) RETURN a, r, b
   ```
   
   ```cypher
   MATCH (p:Person) WHERE p.age > 30 RETURN p
   ```

---

## Architecture

### Backend API Endpoints

- **GET /health** - Health check endpoint
  ```json
  {"status": "ok", "message": "Backend is healthy"}
  ```

- **GET /graph/status** - Placeholder graph integration status (**HTTP 503**)
  ```json
  {
    "detail": "Graph integration is not configured yet"
  }
  ```

---

## Repository Structure (Evolving)

Current layout:

```
power-atlas/
├── backend/              # FastAPI application
│   ├── main.py          # Main API endpoints
│   ├── requirements.txt # Python dependencies
│   └── Dockerfile       # Backend container
├── frontend/            # Next.js application
│   ├── app/            # Next.js app directory
│   │   ├── page.tsx    # Main UI page
│   │   ├── layout.tsx  # Root layout
│   │   └── globals.css # Global styles
│   ├── Dockerfile      # Frontend container
│   └── package.json    # Node dependencies
├── pipelines/           # Scripts-first Neo4j workflows (ingest/query/experiment)
│   ├── ingest/         # Ingestion scripts
│   ├── query/          # Query/report scripts
│   ├── experiment/     # Exploratory scripts
│   ├── runs/           # Run artifacts
│   └── logs/           # Script logs
├── docker-compose.yml  # Container orchestration
├── .env.example        # Environment variables template
└── README.md          # This file
```

Planned documentation areas include:

- `/docs/architecture`
- `/docs/ontology`
- `/docs/provenance`
- `/docs/metrics`
- `/docs/agents`
- `/docs/risk`
- `/research` (separate from versioned `/docs` artifacts; for exploratory notes)

Each area will evolve as versioned architectural artifacts.

### Documentation Roadmap (Summary)

- **v0.1 (current):** Establish principles, constraints, and structural vocabulary.
- **Next:** Expand `/docs/*` artifacts with clearer cross-links between architecture, ontology, provenance, and risk assumptions.
- **Later:** Introduce tighter contributor onboarding once documentation baselines stabilize.

---

## Upgrading from Apache AGE

> ⚠️ **Breaking change**: This version replaces the previous PostgreSQL + Apache AGE database with Neo4j + Graph Data Science (GDS).

If you previously ran the stack with the Apache AGE / PostgreSQL configuration:

- The `postgres_data` Docker volume is **no longer used** and will not be migrated automatically.
- Any graph data stored in the old PostgreSQL/AGE volume must be exported and re-ingested manually if needed.
- Run `docker compose down -v` to remove the old volumes once you no longer need that data.

No automated migration path is provided. This stack is experimental scaffolding; data migration is out of scope.

---

## Licensing

By running this stack you accept the following license agreements:

- **Neo4j Community Edition**: [Neo4j Software License Agreement](https://neo4j.com/licensing/)
- **Neo4j Graph Data Science (GDS)**: [GDS License](https://neo4j.com/graph-data-science-software/) — GDS has a separate license from the Neo4j database. Review it before use.

The `NEO4J_ACCEPT_LICENSE_AGREEMENT` variable in `.env` must be set to `yes` to confirm acceptance. The placeholder value in `.env.example` will cause Docker Compose to fail until you explicitly change it after reviewing the license terms.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

### Environment Variables

- `BACKEND_PORT` - Host port for the backend service (defaults to `8000`)
- `FRONTEND_PORT` - Host port for the frontend service (defaults to `3000`)
- `NEXT_PUBLIC_BACKEND_URL` - Backend API URL for frontend
- `NEO4J_URI` - Neo4j Bolt URI used by services (for Docker Compose backend defaults, `bolt://neo4j:7687`)
- `NEO4J_USERNAME` - Neo4j username (defaults to `neo4j` in Compose)
- `NEO4J_PASSWORD` - Neo4j password (required; set a strong value in `.env`)
- `NEO4J_ACCEPT_LICENSE_AGREEMENT` - Must be set to `yes` after reviewing [Neo4j and GDS license terms](#licensing)
- `NEO4J_UNRESTRICTED_PROCS` - Procedures allowed without restriction (defaults to `gds.*` for local GDS/graph verification; clear or tighten for hardened environments)

---

## Development

### Running services individually

**Backend only:**
```bash
docker compose up backend
```

> **Note:** Starting the backend requires a `.env` file with `NEO4J_PASSWORD` set (used by Docker Compose variable substitution). Copy `.env.example` to `.env` and set a password before running.

**Frontend only** (requires backend):
```bash
docker compose up backend frontend
```

### Scripts-first Neo4j workflow

The `pipelines/` directory is the standard location for ingest/query/experiment scripts and run artifacts.

```bash
cp .env.example .env
# set a strong NEO4J_PASSWORD, then:
set -a && source .env && set +a

python pipelines/ingest/<script>.py
python pipelines/query/<script>.py
python pipelines/experiment/<script>.py
```

Write run artifacts to `pipelines/runs/` and logs to `pipelines/logs/`.

> Studies under `/studies` and versioned architecture/ontology docs under `/docs` remain unchanged by this stack update; they continue to capture historical research and should be referenced as-is.

### Vendor metadata sync

When the `vendor/neo4j-graphrag-python` submodule pin changes, run:

```bash
python scripts/sync_vendor_version.py
```

Use `python scripts/sync_vendor_version.py --check` to verify it is in sync.

### Rebuilding after changes

```bash
docker compose down
docker compose up --build
```

### Viewing logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Cypher Query Examples

### Create nodes

```cypher
CREATE (:Person {name: 'Alice', age: 30})
```

### Create relationships

```cypher
MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'})
CREATE (a)-[:KNOWS {since: 2020}]->(b)
```

### Query patterns

```cypher
MATCH (n:Person) RETURN n
```

```cypher
MATCH (a:Person)-[r:KNOWS]->(b:Person) RETURN a.name, b.name, r.since
```

```cypher
MATCH (p:Person) WHERE p.age > 30 RETURN p.name, p.age
```

### Delete data

```cypher
MATCH (n) DETACH DELETE n
```

---

## Troubleshooting

### Backend health check fails

**Error**: `Cannot connect to backend`

**Solution**:
- Verify backend is running: http://localhost:8000/health
- Check backend logs: `docker compose logs backend`

### Frontend can't connect to backend

**Error**: `Cannot connect to backend`

**Solution**:
- Verify backend is running: http://localhost:8000/health
- Check CORS configuration in `backend/main.py`
- Ensure `NEXT_PUBLIC_BACKEND_URL` is set correctly

### Port already in use

**Error**: `port is already allocated`

**Solution**: Change ports in `docker-compose.yml`:
```yaml
ports:
  - "3001:3000"  # Use 3001 instead of 3000
  - "8001:8000"  # Use 8001 instead of 8000
```

## Philosophy

Power Atlas models structural relationships.

It does not assert intent, motive, or wrongdoing.

It aims to provide clarity about how entities connect over time, while preserving transparency, uncertainty representation, and ethical restraint.

---

## Contributing / Contact

Private repository — contributor model under consideration.

---

## License

**TBD**

---

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
