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

The pipeline supports three entity resolution modes:

- **`unstructured_only`** (default) — fully operational end-to-end with only PDF input; clusters entity mentions across chunks without requiring any structured catalog.
- **`hybrid`** — runs `ingest-structured` first to create `CanonicalEntity` nodes from a CSV catalog, then runs `resolve-entities --resolution-mode hybrid` to enrich existing `ResolvedEntityCluster` nodes with `ALIGNED_WITH` edges to matching `CanonicalEntity` nodes, enabling cluster-aware retrieval.
- **`structured_anchor`** — resolves entity mentions directly against `CanonicalEntity` nodes rather than clustering them against each other first.

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

### 2. Install Python dependencies

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### 3. Installed-package smoke check

Run this once after installation to confirm the new installed-package path is
working before you start the live pipeline:

```bash
python -m pytest tests/test_power_atlas_package.py
```

### 4. Start Neo4j

```bash
docker compose up -d neo4j
```

Neo4j will be available at:
- **Browser**: http://localhost:7474 (login with `NEO4J_USERNAME` / `NEO4J_PASSWORD`)
- **Bolt**: bolt://localhost:7687

#### Verify GDS

```cypher
CALL gds.version();
```

### 5. Run the demo pipeline

See **[`demo/README.md`](demo/README.md)** for the full walkthrough. A typical `unstructured_only` run:

```bash
set -a && source .env && set +a

# (Optional) reset graph
python -m demo.reset_demo_db --confirm

# Ingest PDF — note the run_id printed at the end of output
python -m demo.run_demo --live ingest-pdf
export UNSTRUCTURED_RUN_ID="<run_id_from_ingest_pdf_output>"

# Extract claims, resolve entities (unstructured_only mode), run Q&A
python -m demo.run_demo --live extract-claims
python -m demo.run_demo --live resolve-entities
python -m demo.run_demo --live ask --question "Your question here"
```

For the full `hybrid` pass (structured CSV → canonical alignment → cluster-aware retrieval):

```bash
# UNSTRUCTURED_RUN_ID must already be set from the unstructured_only steps above
python -m demo.run_demo --live ingest-structured
python -m demo.run_demo --live resolve-entities --resolution-mode hybrid
python -m demo.run_demo --live ask --cluster-aware --question "Your question here"
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
│   ├── fixtures/               # Datasets container (datasets/<name>/ per dataset)
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
├── neo4j/                       # Graph operational assets (constraints, indexes, migrations, diagnostics)
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

## Repository Map

Use this section to navigate from the root to the core implementation and validation assets.

### Running the demo pipeline

```bash
python -m demo.run_demo --live ingest-pdf
export UNSTRUCTURED_RUN_ID="<run_id_from_ingest-pdf_output>"
python -m demo.run_demo --live extract-claims
python -m demo.run_demo --live resolve-entities
python -m demo.run_demo --live ask --run-id $UNSTRUCTURED_RUN_ID --question "Your question here"
```

Full step-by-step walkthrough: [`demo/README.md`](demo/README.md)  
Manual validation checklist: [`demo/VALIDATION_RUNBOOK.md`](demo/VALIDATION_RUNBOOK.md)

### Pipeline stages — `demo/stages/`

| Module | Purpose |
|--------|---------|
| [`pdf_ingest.py`](demo/stages/pdf_ingest.py) | Ingest PDF sources into `Document` and `Chunk` nodes in the lexical graph |
| [`claim_extraction.py`](demo/stages/claim_extraction.py) | LLM-driven extraction of `ExtractedClaim` and `EntityMention` nodes |
| [`claim_participation.py`](demo/stages/claim_participation.py) | Build `HAS_PARTICIPANT` edges linking claims to their entity mentions |
| [`entity_resolution.py`](demo/stages/entity_resolution.py) | Cluster entity mentions into `ResolvedEntityCluster` nodes (`MEMBER_OF` edges) |
| [`structured_ingest.py`](demo/stages/structured_ingest.py) | Load a structured CSV catalog into `CanonicalEntity` nodes |
| [`retrieval_and_qa.py`](demo/stages/retrieval_and_qa.py) | Vector search + graph expansion for citation-grounded Q&A |
| [`retrieval_benchmark.py`](demo/stages/retrieval_benchmark.py) | Evaluate retrieval quality against a baseline; produce benchmark artifacts |
| [`graph_health.py`](demo/stages/graph_health.py) | Run read-only graph diagnostics and emit a scoped health report |

### Data contracts — `src/power_atlas/contracts/`

`demo/contracts/` remains as a compatibility shim layer during the migration, but
the package-owned implementations now live under `src/power_atlas/contracts/`.

| Module | Purpose |
|--------|---------|
| [`claim_schema.py`](src/power_atlas/contracts/claim_schema.py) | Pydantic schema for `ExtractedClaim` and related extraction types |
| [`manifest.py`](src/power_atlas/contracts/manifest.py) | Run manifest creation, loading, and validation |
| [`paths.py`](src/power_atlas/contracts/paths.py) | Canonical path resolution for pipeline artifacts |
| [`pipeline.py`](src/power_atlas/contracts/pipeline.py) | Pipeline-level contract refresh and consistency checks |
| [`prompts.py`](src/power_atlas/contracts/prompts.py) | LLM prompt templates for extraction and Q&A stages |
| [`resolution.py`](src/power_atlas/contracts/resolution.py) | Versioned alignment contract (`ALIGNMENT_VERSION`) for cluster-to-canonical alignment / `ALIGNED_WITH` edge filtering |
| [`retrieval_early_return_policy.py`](src/power_atlas/contracts/retrieval_early_return_policy.py) | Policy for short-circuiting retrieval under low-signal conditions |
| [`retrieval_metadata_policy.py`](src/power_atlas/contracts/retrieval_metadata_policy.py) | Citation metadata taxonomy and projection policy |
| [`runtime.py`](src/power_atlas/contracts/runtime.py) | Runtime configuration and environment variable bindings |
| [`structured.py`](src/power_atlas/contracts/structured.py) | Schema for structured CSV ingestion |

### Architecture documents and ADRs — `docs/architecture/`

| Document | Purpose |
|----------|---------|
| [`v0.1.md`](docs/architecture/v0.1.md) | Core graph schema and pipeline architecture |
| [`claim-argument-model-v0.3.md`](docs/architecture/claim-argument-model-v0.3.md) | Claim model, participation slots, and composite matching |
| [`unstructured-first-entity-resolution-v0.1.md`](docs/architecture/unstructured-first-entity-resolution-v0.1.md) | Entity resolution modes and cluster identity design |
| [`retrieval-semantics-v0.1.md`](docs/architecture/retrieval-semantics-v0.1.md) | Retrieval design and citation contract |
| [`retrieval-citation-result-contract-v0.1.md`](docs/architecture/retrieval-citation-result-contract-v0.1.md) | Result contract for citation-grounded Q&A responses |
| [`retrieval-benchmark-review-rubric-v0.1.md`](docs/architecture/retrieval-benchmark-review-rubric-v0.1.md) | **Benchmark review criteria** — rubric and scoring guidance for regression comparison |
| [`temporal-modeling-v0.1.md`](docs/architecture/temporal-modeling-v0.1.md) | Temporal relationship modeling (design only; not yet implemented) |

### Neo4j operational assets — `neo4j/`

The top-level `neo4j/` directory is the intended home for graph operational
assets and lifecycle documentation. Runtime Neo4j access code remains under
`src/power_atlas/adapters/neo4j/`.

| Path | Purpose |
|------|---------|
| [`neo4j/README.md`](neo4j/README.md) | Operational boundary, local/test workflow, and current graph-ops posture |
| [`neo4j/constraints/`](neo4j/constraints/) | Versioned constraint assets |
| [`neo4j/indexes/`](neo4j/indexes/) | Versioned index assets |
| [`neo4j/indexes/demo_chunk_embedding_index.cypher`](neo4j/indexes/demo_chunk_embedding_index.cypher) | Current demo vector-index contract for `:Chunk(embedding)` |
| [`neo4j/migrations/`](neo4j/migrations/) | Ordered migration assets or manifests |
| [`neo4j/diagnostics/`](neo4j/diagnostics/) | Repeatable graph diagnostics |
| [`neo4j/diagnostics/check_demo_chunk_embedding_index.cypher`](neo4j/diagnostics/check_demo_chunk_embedding_index.cypher) | Read-only check for the live demo vector-index contract |
| [`neo4j/diagnostics/check_demo_reset_scope.cypher`](neo4j/diagnostics/check_demo_reset_scope.cypher) | Read-only check for the live demo reset footprint |
| [`neo4j/diagnostics/demo_reset_scope.md`](neo4j/diagnostics/demo_reset_scope.md) | Current demo reset wipe/index-drop inventory |
| [`neo4j/seed/`](neo4j/seed/) | Seed data and seed-loading assets |

### Fixtures — `demo/fixtures/`

`demo/fixtures/` is the **datasets container**.  Each named dataset lives under
`demo/fixtures/datasets/<dataset_name>/` and is self-contained (manifest, CSVs, PDF).

Select a dataset with `--dataset <name>` or set `FIXTURE_DATASET=<name>`.  When
exactly one dataset directory exists the system auto-discovers it.

**Naming convention:** the directory name under `datasets/` is always identical to
the `"dataset"` field in that directory's `manifest.json`.  Pass the directory name
(e.g. `demo_dataset_v1`) to `--dataset`; it is also the `dataset_id` stamped on
graph writes during a pipeline run.

| Dataset | Directory | Primary PDF |
|---------|-----------|-------------|
| `demo_dataset_v1` | [`demo/fixtures/datasets/demo_dataset_v1/`](demo/fixtures/datasets/demo_dataset_v1/) | `chain_of_custody.pdf` |
| `demo_dataset_v2` | [`demo/fixtures/datasets/demo_dataset_v2/`](demo/fixtures/datasets/demo_dataset_v2/) | `chain_of_issuance.pdf` |

| Path | Purpose |
|------|---------|
| [`datasets/demo_dataset_v1/unstructured/chain_of_custody.pdf`](demo/fixtures/datasets/demo_dataset_v1/unstructured/chain_of_custody.pdf) | Primary demo PDF for end-to-end pipeline runs |
| [`datasets/demo_dataset_v1/structured/entities.csv`](demo/fixtures/datasets/demo_dataset_v1/structured/entities.csv) | Sample structured entity catalog for `ingest-structured` |
| [`datasets/demo_dataset_v1/structured/relationships.csv`](demo/fixtures/datasets/demo_dataset_v1/structured/relationships.csv) | Sample relationship definitions for structured mode |
| [`datasets/demo_dataset_v1/manifest.json`](demo/fixtures/datasets/demo_dataset_v1/manifest.json) | Per-dataset contract with dataset-root-relative paths |
| [`datasets/demo_dataset_v2/manifest.json`](demo/fixtures/datasets/demo_dataset_v2/manifest.json) | Per-dataset contract for `demo_dataset_v2` |
| [`manifest.json`](demo/fixtures/manifest.json) | Legacy container-level manifest (kept for backwards compatibility) |

### Tests

| Location | Purpose |
|----------|---------|
| [`demo/tests/test_pipeline_contract.py`](demo/tests/test_pipeline_contract.py) | Validates pipeline-level contract integrity |
| [`demo/tests/test_entity_resolution.py`](demo/tests/test_entity_resolution.py) | Unit tests for entity clustering and resolution |
| [`demo/tests/test_claim_participation.py`](demo/tests/test_claim_participation.py) | Unit tests for claim participation slot matching |
| [`demo/tests/test_retrieval_benchmark.py`](demo/tests/test_retrieval_benchmark.py) | Validates benchmark evaluation logic |
| [`demo/tests/test_graph_health.py`](demo/tests/test_graph_health.py) | Tests for graph diagnostics |
| [`demo/tests/test_retrieval_result_contract.py`](demo/tests/test_retrieval_result_contract.py) | Validates retrieval result contract |
| [`demo/tests/contract_fixtures/`](demo/tests/contract_fixtures/) | YAML fixtures for citation contract scenarios |
| [`tests/`](tests/) | Repository-level integration tests (PDF ingest helpers, vendor sync) |

### `ask --run-id` dataset-ownership validation

When `ask` is called with an explicit `--run-id` alongside a dataset selection
(`--dataset <name>` or `FIXTURE_DATASET=<name>`), the pipeline queries Neo4j to
verify that the run actually belongs to the selected dataset.

**Consistency check (mixed dataset_ids):** The query fetches up to two distinct
`dataset_id` values stamped on `Chunk` nodes for the run — enough to detect
single-dataset (clean) vs multi-dataset (inconsistently-ingested) runs without
a full-graph scan. If two distinct values are found, a `WARNING` is printed
naming both, and dataset-ownership validation continues using the first sorted
`dataset_id` returned for the run.

**Dataset resolution failure:** If `--dataset` or `FIXTURE_DATASET` specifies a
name that cannot be resolved (e.g. a typo), a `WARNING` is printed explaining that
dataset-ownership validation was skipped. The pipeline still proceeds with the
explicit `--run-id` so the request is not silently dropped.

Example warning output:
```
WARNING: run_id='unstructured_ingest-…' has Chunk nodes stamped with multiple
distinct dataset_ids (including 'dataset_a' and 'dataset_b'). The graph may have
been inconsistently ingested. Proceeding with dataset-ownership validation using
the first sorted dataset_id, 'dataset_a'.

WARNING: Could not resolve dataset 'nonexistent_typo' to validate --run-id
dataset ownership (Dataset 'nonexistent_typo' not found …). Dataset-ownership
check skipped.
```

### Benchmarks

| Asset | Purpose |
|-------|---------|
| [`docs/architecture/retrieval-benchmark-review-rubric-v0.1.md`](docs/architecture/retrieval-benchmark-review-rubric-v0.1.md) | **Review criteria** — rubric and scoring guidance for evaluating benchmark regressions |
| [`pipelines/query/retrieval_benchmark_example_output.json`](pipelines/query/retrieval_benchmark_example_output.json) | Synthetic example of benchmark output schema (for tooling and training) |
| [`demo/stages/retrieval_benchmark.py`](demo/stages/retrieval_benchmark.py) | Benchmark stage implementation |
| `pipelines/runs/<run_id>/retrieval_benchmark/` | Actual run baseline artifacts (gitignored by default; see `.gitignore`) |

#### Benchmark failure handling

The retrieval benchmark runs automatically at the end of every orchestrated `ingest` run.
If it fails (e.g. due to a Neo4j connection error or an unexpected exception), the orchestrator
**does not abort** — it catches the exception, logs the traceback, and continues to write the
manifest. The written manifest will include a `retrieval_benchmark` stage with:

```json
{
  "status": "error",
  "error": "<exception message>",
  "traceback": "<full Python traceback>"
}
```

All earlier successfully completed pipeline stages (QA/retrieval signals, structured ingest,
entity resolution, claim extraction, etc.) are preserved in the manifest so that partial
results are not lost and debugging incomplete runs is straightforward.

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
- `NEO4J_ACCEPT_LICENSE_AGREEMENT` — Must be `yes` after reviewing [Neo4j and GDS license terms](#third-party-licenses)
- `NEO4J_UNRESTRICTED_PROCS` — Procedures allowed without restriction (defaults to `gds.*`)
- `OPENAI_API_KEY` — Required for `--live` stages that call OpenAI: `ingest-pdf`, `extract-claims`, and `ask` (LLM claim/entity extraction and retrieval/Q&A)

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
docker compose up -d neo4j

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

## Third-party Licenses

By running this stack you accept the following license agreements:

- **Neo4j Community Edition**: [Neo4j Software License Agreement](https://neo4j.com/licensing/)
- **Neo4j Graph Data Science (GDS)**: [GDS License](https://neo4j.com/graph-data-science-software/) — GDS has a separate license from the Neo4j database. Review it before use.

The `NEO4J_ACCEPT_LICENSE_AGREEMENT` variable in `.env` must be set to `yes` to confirm acceptance.

---

## Contributing / Contact

Private repository — contributor model under consideration.

---

## Repository License

**TBD**
