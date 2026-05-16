# Reusable Core Boundary

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-12  
**Related documents:**
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`
- `docs/repository_restructure/repository_restructure_shared_mechanics_pilot_contract.md`
- `docs/repository_restructure/repository_restructure_second_domain_pilot_contract.md`
- `docs/repository_restructure/repository_restructure_second_domain_gap_inventory.md`

## Purpose

This document turns the generic-research-runner feasibility memo into an
explicit working boundary for the current repo.

The migration question is no longer whether `power-atlas` is package-shaped.
That is already true. The current question is which package-owned surfaces are
ready to become an internal reusable research-runner core, which ones need
policy seams first, and which ones should remain Power Atlas application
surfaces.

## Current checkpoint

At this checkpoint:

- the package-first restructure is functionally closed,
- `src/power_atlas/` is installable and used through real consumer-facing
  proofs,
- the public backend import surface now exists through `power_atlas.api`,
- the remaining work for reuse is no longer packaging cleanup,
- the original policy-boundary extraction phase has now produced concrete
  package-owned seams plus a package-only second-domain proof,
- the next reuse step is to turn those seams into a coherent domain
  contribution model rather than continue abstracting one contract at a time.

This document defines the minimum extraction boundary for that next phase.

## Updated checkpoint direction

The repo is no longer missing a single obvious seam. Retrieval policy,
structured ingest contracts, entity-resolution graph shape, canonical lookup,
alignment strategy, and dataset selection now have package-owned seams and a
package-only market/trade proof.

That changes the next recommendation.

The next high-value implementation slice is not another narrow seam. The next
high-value slice is a first-class domain contribution model that makes those
already-extracted seams legible as one package-owned unit.

The current proposed anchor is a lightweight `DomainPackDescriptor` in
`power_atlas.bootstrap`, with `src/power_atlas/policy_packs/market_trade.py`
serving as the first concrete descriptor-backed pack.

That starter adoption path now also has a concrete proof:
`examples/domain_pack_starter.py` defines a fresh domain pack inline and wires
it through package-owned retrieval and entity-resolution request-context flows.
This means the repo now has both a descriptor-backed pack and a starter example
that shows how a new research-heavy project would begin adopting the package.

## Boundary defined in this checkpoint

### 1. Reusable core candidates now

These areas already look strong enough to be treated as reusable-core
candidates with naming cleanup and extraction work, but without first needing a
new abstraction program.

- `power_atlas.settings`
- `power_atlas.context`
- `power_atlas.bootstrap`
- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.contracts.paths`
- `power_atlas.orchestration.*`
- `power_atlas.run_scope_queries`
- `power_atlas.neo4j_io`
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_result_prelude`
- `power_atlas.retrieval_request_helpers`
- `power_atlas.retrieval_path_diagnostics` as a reusable pattern, though its
  field taxonomy may later need cleanup
- `power_atlas.adapters.neo4j.*` modules whose responsibility is driver,
  session, query-execution, or runtime-envelope management rather than domain
  traversal policy
- interface-shell patterns under `power_atlas.interfaces.cli.*` and the public
  facade pattern used by `power_atlas.api`, while not assuming that the current
  Power Atlas route contracts themselves are the final shared API shape

### 2. Reusable only after explicit policy seams

These areas contain real reusable value, but they still encode the current
Power Atlas ontology, prompt posture, or structured-data assumptions too
directly to be treated as shared core yet.

- `power_atlas.contracts.retrieval_policy`
- `power_atlas.retrieval_query_builders`
- `power_atlas.contracts.prompts`
- `power_atlas.contracts.claim_schema`
- `power_atlas.extraction_rows`
- `power_atlas.extraction_writes`
- `power_atlas.entity_resolution_queries`
- `power_atlas.entity_resolution_writes`
- `power_atlas.structured_ingest_writes`
- stage runtimes that still assume the current ontology path even after driver
  lifecycle and bootstrap concerns were extracted

These modules are the right extraction targets for domain policy providers or
protocols. They are not good candidates for immediate namespace moves while the
current Power Atlas defaults remain implicit.

### 3. Power Atlas application surfaces

These areas should remain with the Power Atlas app layer unless a second app
proves that the same exact semantics should be shared.

- `demo/` operator workflows and CLI docs
- Power Atlas fixture datasets and current fixture-backed validation posture
- benchmark cases tied to current named entities or current fixture families
- operator-facing copy and prompt wording that names Power Atlas explicitly
- the concrete backend route contracts exposed today through `power_atlas.api`
  and `backend/main.py`, even though the facade and shell pattern behind them
  may inform a shared integration layer later
- the current in-repo `frontend/` placeholder shell and its Power Atlas-specific
  documentation posture
- domain framing and editorial voice in the current docs set

## First composition recommendation

The first post-seam composition slice should be **domain-pack formalization**.

This is the highest-leverage next slice because it turns the extracted seams
into something a new research-heavy project can actually understand and adopt.

### Why this composition slice is the right next slice

- it does not require inventing a second runtime layer,
- it makes the current reusable posture legible without another domain
  implementation,
- it can be proven with focused package tests and the existing market/trade
  examples,
- it avoids introducing dynamic plugin discovery before the descriptor shape is
  stable.

### Evidence from the current code

The repo now has the pieces of a domain contribution model, but not yet the
model itself:

- `src/power_atlas/policy_packs/market_trade.py` already acts like a pack,
  but currently only exposes raw policy objects,
- `examples/market_trade_retrieval_policy_consumer.py` and
  `examples/market_trade_entity_resolution_consumer.py` already prove that a
  second-domain consumer can compose package-owned seams,
- the package root, bootstrap layer, and tests now have enough stable surface
  area to describe a domain contribution explicitly.

What is still missing is a single package-owned descriptor that says, in one
place, what a domain contributes.

The `DomainPackDescriptor` slice should remain intentionally small:

- metadata only,
- explicit pack name and version,
- explicit list of provided seams,
- explicit example entrypoints that prove the pack is consumable.

## Acceptance criteria for this first composition slice

The `DomainPackDescriptor` slice should be considered complete only when:

- the descriptor lives in a package-owned composition surface rather than in
  runtime modules,
- `market_trade` exports a real descriptor instance,
- package import tests pin the descriptor shape,
- the existing market/trade consumer proofs continue to run unchanged.

## Non-goals for this checkpoint

This boundary does **not** authorize the following yet:

- renaming `power_atlas` as if it were already a generic package,
- splitting files into a new shared namespace before the descriptor and starter
  path prove their value,
- introducing a dynamic plugin loader or registry framework,
- genericizing Power Atlas-specific docs or operator flows prematurely,
- treating the existence of many seams as proof that the broader reuse story is
  already coherent.

## Immediate sequence

The next bounded steps should proceed in this order:

1. treat this document as the working extraction boundary,
2. formalize the domain contribution model with a lightweight
  `DomainPackDescriptor`,
3. retrofit the market/trade pack as the first descriptor-backed pack,
4. add one starter/adoption path that shows how a new project would define its
  own pack without `demo.*`,
5. add one reusable operational feature with broad GraphRAG leverage,
6. only then re-evaluate whether the shared-core namespace split is justified.

## Success condition for the broader reuse plan

The repo should be considered ready for a shared-kernel extraction only after:

- the current seam set is described through an explicit domain contribution
  model,
- the reusable-core candidates above no longer depend implicitly on Power Atlas
  defaults,
- at least one non-`demo` consumer proof continues to work through that model,
- the follow-on starter/diagnostics path suggests real user leverage rather
  than abstract cleanliness alone.

## 2026-05-15 decision checkpoint

This checkpoint now has enough evidence to answer the namespace-split question.

The answer is: **do not start a broader shared-core namespace split yet**.

The reason is not lack of operational evidence. The repo now has the required
starter/adoption proof plus a reusable operational feature with broad leverage:

- `examples/domain_pack_starter.py` proves a fresh package-only domain pack can
  be defined without `demo.*`,
- the market/trade retrieval and entity-resolution examples continue to prove a
  second-domain consumer path,
- `examples/graph_health_diagnostics_consumer.py` and
  `examples/graph_health_diagnostics_standalone_consumer.py` now prove both the
  RequestContext-owned and standalone config-owned graph-health diagnostics
  paths through package surfaces only,
- installed-package tests now cover those example paths outside the repo root.

That means the “one reusable operational feature” requirement is satisfied.
Another operational proof is not the highest-value next step.

The remaining blocker is that several reusable-core candidates still encode
Power Atlas defaults too directly:

- `power_atlas.contracts.paths` still anchors dataset/config roots under the
  in-repo `demo/` tree,
- `power_atlas.settings` and orchestration helpers still privilege
  `POWER_ATLAS_*` / `FIXTURE_DATASET` environment naming as the ambient package
  configuration model,
- `power_atlas.contracts.pipeline` still loads its default contract from the
  Power Atlas PDF pipeline config path and falls back to Power Atlas-shaped
  embedding/index defaults,
- `build_app_context(...)` and related bootstrap helpers still auto-load those
  defaults as the package baseline rather than requiring an explicit host-app
  runtime descriptor.

Those defaults are acceptable while `power_atlas` remains the application
package. They are not yet strong evidence that a second shared namespace would
reduce coupling rather than merely relocate Power Atlas assumptions.

## Consequence for the next slice

The next extraction step should target **default-coupling removal**, not a new
namespace and not another operational feature.

The strongest next candidate is a small package-owned runtime/defaults seam
covering one or more of:

- dataset root and fixture/container path resolution,
- ambient environment variable naming for dataset/output selection,
- pipeline contract source/default loading.

Only after one of those default-bearing surfaces is externalized should the
repo re-evaluate whether a broader shared-core namespace split is justified.

## 2026-05-15 implementation checkpoint

That follow-up slice has now started and the composition root is materially
better than it was at the decision checkpoint.

The package now has a bootstrap-owned `AppBaseline` descriptor plus
`resolve_app_baseline(...)`, which composes the already-separated default
surfaces for:

- environment variable naming via `AppSettingsEnvNames`,
- repo-root/config/dataset path ownership via `RepoPaths`,
- pipeline contract source selection via `PipelineContractSource`.

`build_settings(...)`, `build_app_context(...)`, `dataset_env_selection(...)`,
`build_runtime_config(...)`, `build_request_context(...)`, and
`bootstrap_app(...)` now accept that baseline explicitly. When a non-default
baseline is supplied, bootstrap-owned runtime assembly loads contract state from
the explicit source rather than silently falling back to the Power Atlas repo
layout. The new `examples/app_baseline_consumer.py` subprocess proof also shows
that package bootstrap can run against a fabricated host-app tree using custom
`HOSTAPP_*` env names instead of the ambient `POWER_ATLAS_*` naming.

This does **not** mean a broader shared-core namespace split should start
immediately. It does mean the earlier blocker has moved. The next question is no
longer whether default-coupling must be externalized first; it is whether the
current explicit baseline surface is already sufficient to justify a split, or
whether one narrower adoption pass is still needed before paying namespace
churn.

## 2026-05-15 backend adoption checkpoint

That narrower first-party adoption pass has now landed.

The public backend facade and the mounted backend host examples now consume the
explicit baseline surface too:

- `build_backend_runtime(...)` and `create_backend_app(...)` accept
  `app_baseline=`,
- backend `/datasets` plus the current-run convenience routes now resolve
  dataset catalogs and inferred dataset ids against the baseline-owned
  `RepoPaths` rather than always assuming the in-repo fixture tree,
- focused backend tests now prove custom env-name, output-dir, pipeline-source,
  and dataset-root behavior through the supported backend package surfaces.

That means the checklist question has changed again. The repo no longer needs
another small first-party baseline-adoption slice before revisiting the
namespace-split decision. The next step should be the evaluation itself:
determine whether the remaining direct `resolve_dataset_root(...)` and related
Power-Atlas-shaped runtime calls are evidence that a shared namespace split is
still premature, or whether they are now localized enough to treat as
application-owned internals living above a reusable baseline.

## 2026-05-16 namespace evaluation

That explicit evaluation now has an answer.

The answer is still: **do not start a broader shared-core namespace split yet**.

The reason has changed. The repo is no longer blocked on the old composition
root/default-coupling problem. `AppBaseline` plus the backend adoption follow-up
mean the package now has an explicit host-app baseline surface with both
bootstrap and first-party backend proofs.

The remaining blocker is narrower and more concrete: a small set of
package-public runtime/default surfaces still derive dataset identity or fixture
roots from Power Atlas-owned defaults rather than from an explicit host-app
authority.

The highest-signal remaining examples are:

- `power_atlas.contracts.resolution._default_select_dataset_id(...)`, which
  still resolves dataset ids by calling `resolve_dataset_root(...)` directly
  inside a contracts module,
- `power_atlas.pdf_ingest_runner.resolve_pdf_dataset(...)`, which still falls
  back to `resolve_dataset_root(dataset_name)` when callers do not provide an
  explicit fixtures root,
- `power_atlas.structured_ingest_runner.resolve_structured_dataset(...)`, which
  still falls back to `resolve_dataset_root()` when callers do not provide an
  explicit fixtures root.

By contrast, the remaining orchestration call sites under
`power_atlas.orchestration.*` are less concerning for the split decision:
those paths are already visibly app-owned coordination layers, and several of
them take `resolve_dataset_root` as an injected dependency rather than owning
ambient lookup directly.

So the current no-go is not “the repo still lacks reusable evidence,” and it is
not “keep doing more generic baseline plumbing everywhere.” It is this:
starting a broader namespace split now would still relocate a few Power Atlas
dataset/default assumptions into the would-be shared namespace instead of
cleanly leaving them in the application layer.

That means the next deliberate step should be one of two narrower choices,
made explicitly rather than by drift:

1. keep those runner/default surfaces in the Power Atlas application namespace
   and scope any future extraction smaller than a broad namespace split, or
2. externalize dataset-root ownership in those specific runtime/default paths
   first, then re-run the namespace decision.

## 2026-05-16 scoped extraction recommendation

This checkpoint now chooses the first of those two narrower paths.

The recommended boundary is: keep the remaining dataset/default-owning runtime
surfaces in `power_atlas` and treat any future extraction as a smaller
shared-mechanics slice rather than a broad namespace move.

### Leave in `power_atlas` for now

The following modules or families should remain Power Atlas application
surfaces because they still own repo layout, environment naming, dataset
identity defaults, or current app route semantics:

- `power_atlas.settings`
- `power_atlas.contracts.paths`
- `power_atlas.contracts.pipeline`
- `power_atlas.contracts.resolution`
- `power_atlas.pdf_ingest_runner`
- `power_atlas.structured_ingest_runner`
- `power_atlas.retrieval_result_prelude`
- `power_atlas.orchestration.*`
- `power_atlas.api`
- `power_atlas.backend_app`
- `power_atlas.backend_dataset_catalog`
- `power_atlas.backend_run_catalog`

These are not all equally problematic for reuse. The point is narrower: they
still express the current host application's defaults or public semantics, so
moving them into a shared namespace now would mostly relocate Power Atlas
ownership rather than reduce it.

### Plausible smaller shared-core candidates later

If the repo wants a smaller extraction before externalizing those defaults, the
first candidate set should be limited to modules whose responsibility is runtime
mechanics rather than Power Atlas policy/default ownership:

- `power_atlas.context`
- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.adapters.neo4j.*`
- `power_atlas.neo4j_io`
- `power_atlas.run_scope_queries`
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_request_helpers`
- `power_atlas.retrieval_request_context_adapters`

That smaller set is intentionally conservative. It favors modules that already
look like reusable mechanics over modules that are only partly decoupled but
still carry Power Atlas dataset, pipeline, prompt, or route assumptions.

### Consequence for future extraction work

If another extraction slice starts before dataset-root ownership is
externalized, it should not be framed as “start the shared-core namespace
split.” It should be framed as a limited shared-mechanics pilot using only the
candidate set above while explicitly leaving dataset/default authority in the
Power Atlas app layer.

That pilot is now defined concretely in
`docs/repository_restructure/repository_restructure_shared_mechanics_pilot_contract.md`.