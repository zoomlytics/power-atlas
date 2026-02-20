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
- **Database**: PostgreSQL + Apache AGE (graph extension)
- **Frontend**: Next.js (React + TypeScript) + Tailwind CSS
- **Orchestration**: Docker Compose

Apache AGE is being used as an experimental graph laboratory and is not considered a long-term commitment.

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

### 2. Start the stack

```bash
docker compose up --build
```

This will:
- Start PostgreSQL with Apache AGE extension
- Initialize the `power_atlas` database
- Start the FastAPI backend on port 8000
- Start the Next.js frontend on port 3000

### 3. Access the application

Open your browser and navigate to:
- **Frontend**: http://localhost:3000
- **Backend API Docs**: http://localhost:8000/docs

### 4. Run a demo

1. Click the **"Seed Demo Graph"** button to create sample data
   - This creates 3 Person nodes (Alice, Bob, Charlie)
   - Adds KNOWS relationships between them

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
  {"status": "ok", "message": "Backend and database are healthy"}
  ```

- **POST /cypher** - Execute Cypher queries
  ```json
  {
    "query": "MATCH (n:Person) RETURN n",
    "params": {}
  }
  ```

- **POST /seed** - Seed demo graph data
  ```json
  {
    "status": "success",
    "message": "Demo graph created with 3 persons and 2 relationships"
  }
  ```

---

## Repository Structure (Evolving)

Current layout:

```
power-atlas/
├── backend/              # FastAPI application
│   ├── main.py          # Main API endpoints
│   ├── age_helper.py    # Apache AGE integration
│   ├── requirements.txt # Python dependencies
│   └── Dockerfile       # Backend container
├── frontend/            # Next.js application
│   ├── app/            # Next.js app directory
│   │   ├── page.tsx    # Main UI page
│   │   ├── layout.tsx  # Root layout
│   │   └── globals.css # Global styles
│   ├── Dockerfile      # Frontend container
│   └── package.json    # Node dependencies
├── infra/              # Infrastructure scripts
│   └── init-age.sh     # Database initialization
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

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

### Environment Variables

- `DATABASE_URL` - PostgreSQL connection string
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password
- `POSTGRES_DB` - Database name
- `GRAPH_NAME` - Apache AGE graph name
- `NEXT_PUBLIC_BACKEND_URL` - Backend API URL for frontend

---

## Development

### Running services individually

**Backend only:**
```bash
docker compose up postgres backend
```

**Frontend only** (requires backend):
```bash
docker compose up postgres backend frontend
```

### Accessing the database directly

```bash
docker compose exec postgres psql -U postgres -d power_atlas
```

Then in psql:
```sql
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- List all graphs
SELECT * FROM ag_catalog.ag_graph;

-- Run a Cypher query
SELECT * FROM cypher('power_atlas_graph', $$
    MATCH (n:Person) RETURN n
$$) as (result agtype);
```

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
docker compose logs -f postgres
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

### Apache AGE extension not found

**Error**: `extension "age" does not exist`

**Solution**: Ensure you're using the correct Apache AGE Docker image:
```yaml
postgres:
  image: apache/age:release_PG16_1.6.0
```

### Shared preload libraries error

**Error**: `shared_preload_libraries not configured`

**Solution**: The docker-compose.yml already includes this configuration:
```yaml
command: 
  - "postgres"
  - "-c"
  - "shared_preload_libraries=age"
```

### Backend can't connect to database

**Error**: `could not connect to server`

**Solution**: 
- Ensure PostgreSQL is healthy: `docker compose ps`
- Check logs: `docker compose logs postgres`
- Wait for the health check to pass (may take 30-60 seconds on first start)

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

### Database initialization issues

**Solution**: Clean up and restart:
```bash
docker compose down -v  # Remove volumes
docker compose up --build
```

### Query execution errors

**Error**: `syntax error in Cypher query`

**Solution**: 
- Verify Cypher syntax matches Apache AGE documentation
- Check that node labels and property names are correct
- Ensure graph exists: queries run against `power_atlas_graph`

---

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

- [Apache AGE Documentation](https://age.apache.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
