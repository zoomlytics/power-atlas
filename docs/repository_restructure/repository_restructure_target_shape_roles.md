# Target Shape Roles

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_reusable_core_boundary.md`
- `docs/repository_restructure/repository_restructure_generic_research_runner_feasibility.md`
- `docs/repository_restructure/repository_restructure_shared_mechanics_pilot_contract.md`
- `README.md`

## Purpose

This document clarifies the intended end-state roles in the repo so that the
current extraction work is evaluated against the right target shape.

The immediate question is not whether the repo has reusable pieces. It does.
The immediate question is how to distinguish:

- the reusable research kernel,
- a domain pack that teaches that kernel how to operate in one domain,
- and an application shell that turns those capabilities into a working
  product for humans or agents.

## Target shape

The intended long-term shape is a three-layer system.

### Layer 1: reusable research kernel

This layer owns the mechanics that should be reusable across multiple research
projects.

It should own responsibilities such as:

- runtime/bootstrap composition,
- request and execution envelopes,
- artifact routing and manifest conventions,
- graph/vector session mechanics,
- retrieval execution mechanics,
- citation normalization/repair/fallback,
- reusable diagnostics and evaluation primitives,
- agent-facing workflow primitives once those are explicit and stable.

This layer should not own any single project's ontology, fixture layout,
editorial voice, or branded operator posture.

### Layer 2: domain packs

A domain pack teaches the reusable kernel how to conduct research in one
domain.

It should own responsibilities such as:

- ontology labels and relationship semantics,
- retrieval policy and traversal posture,
- prompt pack and domain wording,
- entity-resolution rules and canonical alignment posture,
- structured ingest assumptions that are truly domain-specific,
- domain-specific evaluation cases or diagnostic query packs.

A domain pack is not primarily about transport, deployment, or user-facing app
operations. It is about domain semantics and policy.

### Layer 3: application shells

An application shell turns the kernel plus one or more domain packs into an
operating product.

It should own responsibilities such as:

- CLI, API, frontend, and operator workflows,
- environment naming and deployment posture,
- dataset roots, source connectors, and storage conventions,
- app-specific benchmarks and validation workflows,
- branded docs, editorial voice, and human-facing guidance,
- auth, tenancy, monitoring, and future agent orchestration UX.

The shell is where the system becomes a real working app rather than only a
reusable package plus domain semantics.

## How to classify current repo surfaces

The cleanest classification question is: what remains if the current Power
Atlas research topic disappears?

If the surface still makes sense as reusable runtime or workflow plumbing, it
belongs in the kernel.

If the surface still makes sense only because the project is about influence,
institutions, claims, mentions, and the current graph semantics, it belongs in
the Power Atlas domain pack.

If the surface is about how operators or future agents run the system in this
repo, it belongs in the Power Atlas application shell.

## Current interpretation of `power_atlas`

At the current checkpoint, `power_atlas` should be understood as **both** a
domain pack and an application shell, with an emerging reusable kernel inside
it.

That is why a rename is still premature.

The current package still contains:

- reusable mechanics that look like kernel material,
- Power Atlas-specific semantics that look like domain-pack material,
- Power Atlas-specific defaults and operator posture that look like
  application-shell material.

So the current repo is not yet in a state where one name can describe one clean
role.

## Recommended long-term interpretation

The recommended destination is:

1. a reusable research kernel,
2. `power_atlas` as the first reference application shell,
3. a Power Atlas domain pack used by that shell,
4. additional domain packs for other research projects,
5. future agentic research workflows built as shell/orchestration behavior on
   top of the same kernel.

This destination preserves the current investment while giving the future
agentic system the right home: above the kernel, not tangled into one domain
pack.

## What this means for naming

The current repo should not yet be renamed as if it were already the generic
research system.

A rename becomes justified only when all of the following are true:

- the reusable kernel has a stable identity and composition model,
- Power Atlas-specific defaults are no longer ambient in that reusable layer,
- at least one additional non-Power-Atlas consumer works through the same
  kernel without compatibility theater,
- the remaining Power Atlas-specific semantics can stay cleanly in the domain
  pack and/or application shell.

Until then, the clearest working model is:

- `power_atlas` is the first serious consumer of the emerging reusable system,
- not yet the final generic system name,
- and not yet reducible to only one role.

## Implication for current restructuring work

This interpretation supports the current repo posture:

- keep extracting kernel-worthy mechanics where the boundary is real,
- keep making domain policy explicit through domain-pack style seams,
- keep Power Atlas defaults, operator posture, and app semantics in the app
  layer until another app proves otherwise,
- avoid rename-driven churn before the architecture is honest enough to carry
  it.