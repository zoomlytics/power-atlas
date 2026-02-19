# Power Atlas

A minimal local development stack for graph database experimentation with **Apache AGE** (A Graph Extension for PostgreSQL), **FastAPI**, and **Next.js**.

## Overview

Power Atlas provides a simple, reproducible environment for working with graph databases locally. It's designed for research and experimentation, not production use.

### Stack

- **Backend**: Python + FastAPI
- **Database**: PostgreSQL + Apache AGE (graph extension)
- **Frontend**: Next.js (React + TypeScript) + Tailwind CSS
- **Orchestration**: Docker Compose

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Docker Compose)
- That's it! Everything else runs in containers.

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

### Directory Structure

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

## Troubleshooting

### Apache AGE extension not found

**Error**: `extension "age" does not exist`

**Solution**: Ensure you're using the correct Apache AGE Docker image:
```yaml
postgres:
  image: apache/age:PG16_latest
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

## Resetting Everything

To completely reset the environment:

```bash
# Stop and remove containers, networks, and volumes
docker compose down -v

# Rebuild and start fresh
docker compose up --build
```

## Contributing

This is a minimal research scaffold. Feel free to extend it for your needs, but keep changes focused and well-documented.

## License

MIT

## Resources

- [Apache AGE Documentation](https://age.apache.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)