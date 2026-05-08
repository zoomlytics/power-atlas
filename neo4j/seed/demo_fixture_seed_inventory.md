# Demo Fixture Seed Inventory

This note documents the current seed/reference-data posture for the local
candidate-graph workflow.

At the current checkpoint, the repo does **not** have a separate Neo4j-native
seed loader or checked-in graph seed bundle under `neo4j/seed/`. Instead, the
effective seed/reference inputs for local graph setup remain the maintained
fixture surfaces under `demo/fixtures/`.

## Current accepted posture

- dataset-scoped fixture inputs live under `demo/fixtures/datasets/`
- `demo_dataset_v1` is the stable baseline dataset for first-time runs and CI
  validation
- `demo_dataset_v2` is the secondary dataset used to exercise multi-document
  and multi-dataset flows
- the top-level `demo/fixtures/structured/`, `demo/fixtures/unstructured/`, and
  `demo/fixtures/manifest.json` paths remain legacy-compatible entry points,
  but the canonical dataset-owned assets live under
  `demo/fixtures/datasets/<dataset_name>/`
- `demo/fixtures/wikidata_extraction_prompts/` remains an accepted defer-in-place
  operator-facing prototyping template subtree rather than a runtime seed path

## What counts as seed-like input today

For the current local candidate graph, seed/reference inputs are the checked-in
fixture assets that feed demo ingest or deterministic structured enrichment:

- per-dataset `manifest.json` files under `demo/fixtures/datasets/<dataset_name>/`
- per-dataset `structured/` CSVs used by structured ingest
- per-dataset `unstructured/` PDFs used by PDF ingest
- the retained top-level compatibility paths in `demo/fixtures/` for older
  tooling that still references them directly

These inputs are reproducible repo-owned fixtures, but they are still owned by
the demo/operator workflow rather than by a separate graph-ops seed system.

## Why this remains under `demo/fixtures/`

This repo still treats the demo pipeline as the maintained operator shell over
the package-owned runtime core. Moving fixture datasets into `neo4j/seed/`
today would create split ownership between:

- dataset selection and operator runbooks in `demo/`
- graph operational assets under `neo4j/`

Until there is a dedicated seed-loading path that consumes Neo4j-owned assets
directly, `demo/fixtures/` remains the source of truth for these inputs.

## Current dataset inventory

- `demo/fixtures/datasets/demo_dataset_v1/`
  stable baseline centered on the Endeavor / MercadoLibre / Latin American tech
  network; recommended for first-time runs and CI validation
- `demo/fixtures/datasets/demo_dataset_v2/`
  secondary dataset used to exercise multi-document ingest and dataset-isolated
  graph writes

See:

- `demo/fixtures/README.md`
- `demo/fixtures/datasets/demo_dataset_v1/README.md`
- `demo/fixtures/datasets/demo_dataset_v2/README.md`

## Future promotion rule

Promote assets from `demo/fixtures/` into `neo4j/seed/` only when both are
true:

- the asset is owned primarily as graph setup/reference data rather than as a
  demo-operator input surface
- a dedicated seed-loading or migration path exists that can consume the asset
  without routing back through the demo shell

Until then, `neo4j/seed/` should document the current posture rather than copy
or relocate fixture data.