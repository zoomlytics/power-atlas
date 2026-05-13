# Generic Research Runner Feasibility

## Purpose

This memo evaluates whether the current `power-atlas` codebase is a good
candidate to evolve into a reusable Neo4j-backed research runner that could be
shared across multiple domain applications.

The current execution boundary for that follow-up now lives in
`docs/repository_restructure/repository_restructure_reusable_core_boundary.md`.
Read this memo as the assessment and that companion document as the active
boundary for the next extraction slices. The concrete proof target for the
first non-Power-Atlas validation step now also lives in
`docs/repository_restructure/repository_restructure_second_domain_pilot_contract.md`.

The central question is not whether the repo is already generic. It is not.
The question is whether the repo has accumulated enough reusable runtime value
above `neo4j-graphrag` that extracting an internal multi-app package would be a
high-leverage next step.

## Short answer

Yes, with an important qualification.

The repo is a credible foundation for an **internal reusable research runner
core**. It is not yet a credible **domain-agnostic GraphRAG package**.

The best interpretation of the current code is:

- `neo4j-graphrag` provides the vendor substrate,
- `power_atlas` already adds meaningful orchestration, provenance, and research
  workflow behavior on top of that substrate,
- but much of the ontology, retrieval semantics, prompt policy, and benchmark
  shape are still specific to the current Power Atlas worldview.

That means the highest-value path is to extract a reusable kernel and keep
domain packs or thin app shells on top of it.

## Why this repo is worth extracting at all

If the code only wrapped `neo4j-graphrag` with a few scripts, reuse would not be
worth the maintenance overhead. The current repo now contains more than that.

The package-owned layer under `src/power_atlas/` already provides reusable
behavior in at least five categories.

### 1. Runtime and composition boundaries

The repo already has installable packaging and explicit runtime context objects:

- `pyproject.toml` packages `src/power_atlas`
- `power_atlas.settings.AppSettings` centralizes model, dataset, output, and
  Neo4j settings
- `power_atlas.context.AppContext` and `RequestContext` give a coherent runtime
  container for settings, pipeline contract state, and request scope
- `power_atlas.bootstrap` acts as an actual composition root rather than a thin
  convenience wrapper

That is reusable infrastructure and would still be useful outside the current
power/influence domain.

### 2. Research-oriented orchestration

The repo has already pulled significant orchestration behavior into package
modules, including:

- request-context construction,
- CLI dispatch and stage planning,
- ask-scope resolution,
- artifact routing and manifest writing,
- independent-stage and orchestrated runner support.

This matters because many research apps need repeatable scoped runs, traceable
artifacts, and deliberate live vs dry-run behavior, not just graph access.

### 3. Provenance and citation discipline

One of the clearest sources of incremental value above the vendor package is the
repo's evidence discipline:

- run-scoped and source-scoped retrieval behavior,
- citation token handling,
- citation repair / fallback behavior,
- retrieval result contracts and debug views,
- manifestable stage outputs.

That posture is portable across domains even when the underlying ontology
changes.

### 4. Hybrid structured + unstructured research flow

The code already supports a useful research pattern:

- ingest unstructured source material,
- extract claims and mentions,
- cluster mentions,
- optionally align clusters to a curated structured catalog,
- retrieve with graph expansion and citation grounding.

That pattern is not specific to political or influence research. It could apply
equally to market, regulatory, corporate, trade, or event research if the graph
model is made configurable.

### 5. Operational graph diagnostics

The package also contains reusable operational ideas:

- graph-health queries,
- retrieval benchmark hooks,
- explicit run scope queries,
- reset/runtime utilities,
- package-owned Neo4j adapter seams.

These capabilities are useful whenever the graph is part of an iterative
research workflow rather than a static serving layer.

## Why the repo is not generic yet

The genericity problem is not packaging. The package foundation is already in
place. The genericity problem is that the package still embeds a specific graph
worldview.

### 1. Ontology is hard-coded into core contracts

The core contracts assume a specific graph layer made of:

- `ExtractedClaim`,
- `EntityMention`,
- `ResolvedEntityCluster`,
- `CanonicalEntity`,
- `HAS_PARTICIPANT`,
- `SUPPORTED_BY`,
- `MENTIONED_IN`,
- `MEMBER_OF`,
- `ALIGNED_WITH`.

Those are reasonable defaults, but they are not neutral. A generic package would
need these to come from an ontology or policy layer, not from package-global
constants and fixed query builders.

### 2. Prompt policy is branded and workflow-specific

The package prompt layer currently assumes a specific operator posture:

- evidence analyst language,
- Power Atlas branding,
- a specific citation token format,
- provisional cluster wording conventions,
- current QA answer style.

The evidence-first posture should remain reusable. The exact prompt pack should
not.

### 3. Structured ingest contract is currently Wikidata-shaped

The structured layer is one of the largest portability blockers.

The current contract assumes:

- fixed CSV files,
- `Q*` / `P*` style identifiers,
- `wikidata_url`,
- current predicate conventions,
- current claim/relationship/fact row semantics.

That is workable for the current app, but a future trade tracker may want

- equities,
- tickers,
- exchanges,
- earnings events,
- regulatory filings,
- calendars,
- macro events,
- custom identifiers.

Those should be described by a pluggable structured schema rather than adapted
through ad hoc compatibility shims.

### 4. Retrieval semantics assume the current graph expansion path

The retrieval logic is strong, but it is not ontology-neutral. The current query
builders assume a particular traversal from chunks to claims to mentions to
clusters to canonicals.

That may still be the right default for future apps, but it should be expressed
as a retrieval expansion policy, not as the only supported runtime shape.

### 5. Benchmarks and diagnostics are partially fixture-specific

Some operational surfaces are already useful in principle but are implemented in
ways that remain tied to current fixtures and named entities. These should move
to domain-owned benchmark packs rather than stay in a purportedly generic core.

## Assessment by package area

This is the practical boundary audit: what looks ready for extraction, what
needs abstraction first, and what should remain app-specific.

### Good candidates for a reusable core now

These areas already look structurally reusable with relatively small naming and
surface cleanup.

- `power_atlas.settings`
- `power_atlas.context`
- `power_atlas.bootstrap`
- `power_atlas.contracts.runtime`
- `power_atlas.contracts.manifest`
- `power_atlas.contracts.paths`
- `power_atlas.orchestration.*`
- `power_atlas.run_scope_queries`
- `power_atlas.adapters.neo4j.*` runtime seams that only manage driver/session
  lifecycle or query execution envelopes
- `power_atlas.retrieval_postprocessing`
- `power_atlas.retrieval_result_prelude`
- `power_atlas.retrieval_request_helpers`
- `power_atlas.retrieval_path_diagnostics` as a pattern, though likely with a
  more configurable field taxonomy
- `power_atlas.neo4j_io`

These modules mostly solve packaging, runtime wiring, scope control, artifacts,
or citation handling rather than domain modeling.

### Reusable only after introducing extension seams

These areas contain good logic, but the logic is mixed with the current ontology
or domain-specific assumptions.

- `power_atlas.contracts.prompts`
- `power_atlas.contracts.claim_schema`
- `power_atlas.retrieval_query_builders`
- `power_atlas.extraction_rows`
- `power_atlas.extraction_writes`
- `power_atlas.entity_resolution_queries`
- `power_atlas.entity_resolution_writes`
- `power_atlas.structured_ingest_writes`
- stage runtimes that currently assume one ontology path even after the driver
  lifecycle was extracted

These are the right places to introduce domain policy objects rather than trying
to duplicate the whole package for each app.

### Should remain Power Atlas specific

These should stay in the Power Atlas app layer unless and until another app has
the same exact semantics.

- benchmark cases tied to current named entities,
- fixture-specific validation expectations,
- operator-facing copy that names Power Atlas explicitly,
- any current prompt wording tied to the project's editorial voice,
- documentation framed around the current research theme.

## Proposed target shape

The likely end state is not one package. It is three layers.

### Layer 1: reusable research runner core

This layer would own:

- settings and bootstrap,
- request/app context,
- artifact routing and manifests,
- run-scoped execution model,
- Neo4j driver/session envelopes,
- generic retrieval execution scaffolding,
- citation normalization / repair / fallback,
- graph-health and benchmark framework primitives,
- interface shells for CLI/API integration.

This is the layer multiple apps could install.

### Layer 2: ontology and policy packs

This layer would own plug-in surfaces such as:

- extraction schema provider,
- structured ingest schema provider,
- prompt pack,
- retrieval expansion policy,
- entity-resolution policy,
- graph label / relationship names,
- benchmark case pack,
- graph-health query pack.

The current Power Atlas ontology would become one policy pack.

### Layer 3: app shells

Each app would provide:

- its dataset fixtures or source connectors,
- branded docs and operator workflows,
- app-specific benchmarks,
- app-specific prompt defaults,
- app-specific API/UX surfaces.

In that model, `power-atlas` remains an app, not the generic package itself.

## What a second app would likely need

For a hypothetical market or trade research app, the extension surface is not
just new entities. It likely needs new graph semantics in a few places.

### Example additional concepts

- `Stock` or `Security`
- `Exchange`
- `CalendarEvent`
- `EarningsCall`
- `Filing`
- `InstrumentMention`
- `RegulatoryBody`

### Example additional relations

- `LISTED_ON`
- `REPORTS_AT`
- `FILED_WITH`
- `TRADES_WITH`
- `GUIDES_ON`
- `AFFECTED_BY_EVENT`

### Example runtime/policy hooks required

- different structured ingest row contracts,
- different cluster-to-canonical alignment strategy,
- retrieval expansion over event timelines,
- domain-specific ranking heuristics,
- prompt wording that distinguishes quoted guidance, rumors, official filings,
  and scheduled events.

The current repo can support these ideas conceptually, but not yet as first-
class configuration.

## Recommended migration path

This should be treated as an extraction program, not a rewrite.

### Phase A: declare the intended split

Decision:

- keep `power_atlas` as the current domain app,
- identify a new internal package boundary for the reusable core,
- define the minimum plugin surfaces before moving files.

Acceptance criteria:

- the repo has a written boundary document,
- reusable-core candidates are explicitly named,
- app-specific surfaces are explicitly named.

### Phase B: make policy surfaces explicit before moving more code

Introduce explicit provider objects or protocols for:

- prompt packs,
- graph ontology labels/relations,
- structured ingest schemas,
- retrieval expansion policies,
- benchmark packs.

Acceptance criteria:

- retrieval and extraction no longer depend on package-global ontology values,
- at least one domain policy object can be swapped in tests without monkeypatching
  implementation modules.

### Phase C: extract the internal reusable kernel

Move the already-generic surfaces into a new internal package namespace or
subpackage while keeping compatibility wrappers in `power_atlas`.

Acceptance criteria:

- a second thin app package can import the shared runtime,
- no package-owned runtime module depends directly on Power Atlas fixtures or
  benchmark entities,
- current Power Atlas CLI behavior remains unchanged.

### Phase D: prove reuse with one concrete second domain

Do not call the package generic until a second app exists and works.

The best proof would be a constrained second app, not a large rewrite. A market
or trade-tracker pilot with a smaller ontology is enough.

Acceptance criteria:

- second app uses the shared runtime package,
- second app provides its own prompt pack and structured schema,
- second app does not require copying package core modules,
- both apps can run side by side without divergent forks of the runtime layer.

## What not to do

The main failure mode would be over-abstracting too early.

Avoid:

- replacing all domain terms with vague generic names immediately,
- introducing dozens of plugin interfaces before a second app exists,
- forcing every query through a dynamic factory if only one query shape is
  actually proven,
- turning benchmark and fixture logic into fake generic frameworks.

The repo already has one successful domain implementation. The right next step
is to generalize only the surfaces that a second app demonstrably needs.

## Recommendation

Proceed, but proceed as an internal kernel extraction program.

The codebase appears strong enough to justify the following working decision:

> Build a reusable Neo4j research runner core from this repo for internal multi-
> app use, while keeping Power Atlas as the first domain implementation and
> refusing to call the result generic until a second app proves the abstraction.

That is a materially lower-risk and higher-value move than either of the two
extremes:

- doing nothing and rebuilding similar research logic in each app, or
- prematurely trying to turn the current repo into a broad public GraphRAG
  framework.

## Immediate next slice

The next implementation slice should be a narrow design-and-seam pass, not a
large move.

Recommended first follow-up:

1. Define an explicit ontology/policy interface for prompt pack, structured
   schema, and retrieval expansion.
2. Refactor one concrete runtime surface to consume that policy object.
3. Preserve the current Power Atlas behavior by providing a default
   `PowerAtlasPolicy` implementation.

That slice would test whether the repo can actually support a second domain with
bounded changes, which is the real question behind this feasibility review.