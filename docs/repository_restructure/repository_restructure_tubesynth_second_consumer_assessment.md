# TubeSynth Second-Consumer Assessment

**Status:** active  
**Owner:** Ash  
**Date context:** 2026-05-16  
**Related documents:**
- `docs/repository_restructure/repository_restructure_target_shape_roles.md`
- `docs/repository_restructure/repository_restructure_target_shape_extraction_sequence.md`
- `docs/repository_restructure/repository_restructure_second_domain_pilot_contract.md`
- `docs/repository_restructure/repository_restructure_second_domain_gap_inventory.md`
- `tubesynth/docs/architecture/tubesynth_2_domain_model.md`
- `tubesynth/docs/architecture/tubesynth_2_service_map.md`
- `tubesynth/docs/architecture/tubesynth_2_end_to_end_example.md`
- `tubesynth/docs/architecture/video_processing_lifecycle.md`

## Purpose

This note evaluates TubeSynth's future-state architecture as a candidate second
consumer of the emerging Power Atlas research system.

The goal is not to decide immediate implementation work in TubeSynth. The goal
is to ask a narrower question: if TubeSynth eventually adopts shared research
runtime capabilities, what kind of consumer would it be, and what does that
imply for the current Power Atlas extraction order?

## Verdict

TubeSynth is a **strong conceptual second-consumer candidate** for the
emerging reusable research kernel.

It is **not** yet the right near-term executable proof target for the current
restructure lane, because the TubeSynth materials reviewed here describe a
future-state architecture rather than a currently implemented consumer.

More precisely:

- TubeSynth looks like a plausible **second application shell** over a shared
  research kernel.
- TubeSynth does **not** look like a simple second-domain pack that can be
  judged only through today's constrained retrieval-policy pilot.
- TubeSynth therefore strengthens the case for the kernel/domain-pack/app-shell
  model, while also strengthening the case **against** a premature broad shared
  namespace split.

## Strongest evidence for fit

The conceptual overlap with the Power Atlas target shape is real.

### 1. Evidence-first operating model

TubeSynth 2.0 defines the system of record as source artifacts, evidence
segments, claims, entities, event signals, and lineage back to evidence.

That aligns closely with the kind of reusable kernel responsibilities Power
Atlas is already trying to isolate:

- artifact routing,
- execution envelopes,
- retrieval over evidence units,
- provenance and citation handling,
- reusable diagnostics and agent-facing research primitives.

### 2. Multi-stage research workflow

TubeSynth's future-state service map is explicitly multi-stage:

- Acquisition,
- Normalization,
- Evidence Indexing,
- Extraction,
- Calendar Resolution,
- Synthesis,
- Research Orchestration,
- Prioritization,
- Delivery API.

That is not just a content pipeline. It is a research workflow system with
clear stage ownership, lineage, and downstream serving surfaces.

### 3. Hybrid retrieval posture

TubeSynth explicitly calls for object storage, relational state, vector
retrieval, graph traversal, full-text search, and analytics storage as
complementary surfaces.

That is materially compatible with the emerging Power Atlas kernel posture,
which is already converging on runtime/bootstrap mechanics, graph/vector
session helpers, retrieval execution, and reusable evidence-facing support
logic.

### 4. Explicit time and event semantics

TubeSynth makes publication time, validity windows, event windows, dormancy,
revival, and staleness first-class concepts.

That is important because it exposes a consumer need that is broader than the
current Power Atlas domain pack but still plausible for a shared kernel to
support via workflow primitives and diagnostics.

### 5. Downstream agent and repo delivery model

TubeSynth's delivery layer explicitly serves dashboards, agents, and downstream
algorithmic repos through query bundles and execution-facing knowledge objects.

That is useful pressure on the Power Atlas target shape because it matches the
planned distinction between a reusable kernel and application shells that serve
humans or agents.

## Strongest evidence against a direct near-term fit

The fit is real, but it is not simple.

### 1. TubeSynth is described as a future-state architecture, not a current consumer

The reviewed documents are explicitly conceptual. They are not current
implementation contracts.

That means TubeSynth is strong as a design pressure test, but weak as an
immediate executable proof.

### 2. TubeSynth is broader than the current second-domain pilot contract

The current Power Atlas second-domain pilot contract is intentionally narrow:
it focuses on proving that a materially different retrieval policy/domain pack
can ride existing package seams.

TubeSynth is not only a different retrieval policy. It proposes:

- new bounded contexts,
- evidence-native system-of-record objects,
- canonical event resolution,
- cross-source synthesis,
- research-orchestration loops,
- prioritization outputs,
- delivery APIs for downstream consumers.

That makes TubeSynth a better test of a future **second app shell** than of the
current constrained domain-pack proof.

### 3. TubeSynth's conceptual substrate is richer than current Power Atlas seams

TubeSynth's target model assumes first-class objects such as `SourceFeed`,
`SourceDocument`, `DocumentRevision`, `EvidenceSegment`, `CanonicalEvent`,
`IdeaCluster`, `SynthesizedIdea`, `ResearchQuestion`, `ResearchFinding`,
`RiskFlag`, and `ExecutionCandidate`.

Current Power Atlas extraction work has only partly reached the point where
those kinds of reusable runtime carriers and authority boundaries are explicit.

### 4. TubeSynth would immediately stress ambient authority problems

A TubeSynth-style consumer would need to supply its own:

- source-feed model,
- event-resolution policy,
- prioritization logic,
- delivery contracts,
- environment naming,
- storage and source conventions,
- domain prompts and semantics.

That is exactly the area where Power Atlas still has active restructuring work:
default authority, context ownership, dataset/source authority, and shell-side
posture are not fully disentangled yet.

## How TubeSynth should be classified

TubeSynth should currently be treated as a **future second application shell
candidate**, not merely as a second domain pack.

That classification matters.

If TubeSynth were only another domain pack, the current market/trade-style
pilot would be a sufficient model.

It is not. TubeSynth is describing a distinct operator-facing research product
with its own pipeline, its own bounded contexts, and its own downstream serving
contracts.

The most honest interpretation is:

- Power Atlas remains the first reference application shell,
- TubeSynth is a plausible future second application shell,
- each shell would likely need one or more domain packs of its own,
- both would sit above an eventual shared kernel if the kernel becomes real.

## What this means for current extraction priorities

TubeSynth does **not** justify jumping to a broad shared-kernel namespace split.

It supports the opposite conclusion.

A TubeSynth-like future consumer would immediately need the following
boundaries to be explicit:

1. default and policy authority,
2. kernel runtime carriers versus app-owned context,
3. dataset/source authority,
4. reusable diagnostics/workflow primitives versus domain-specific graph and
   synthesis policy.

That is the same order already captured in the current extraction sequence.

So TubeSynth increases confidence that the present sequence is correct:

- first make Power Atlas defaults explicit,
- then thin app-owned context away from kernel-facing runtime carriers,
- then externalize dataset/source authority,
- only after that widen reusable workflow or adapter extraction.

## Smallest plausible cross-repo pilot

The smallest honest pilot is **not** "run TubeSynth on Power Atlas" and not
"treat TubeSynth as the next executable domain-pack proof."

The smallest plausible cross-repo pilot is a design-level contract exercise
that asks whether both repos can name a shared kernel slice around:

- evidence-unit lineage and citation expectations,
- retrieval/execution runtime carriers,
- graph/vector/search session mechanics,
- artifact and manifest conventions,
- agent-facing query-bundle or workflow-primitives shape.

That pilot can remain doc-first until TubeSynth's future-state architecture is
closer to implementation.

## Recommendation

Treat TubeSynth as:

- strong evidence that a second application shell may eventually exist,
- useful design pressure for kernel boundaries now,
- but not yet the next executable reuse proof.

The immediate effect on Power Atlas should be architectural, not promotional:
use TubeSynth to validate the target shape and extraction order, while keeping
the next implementation slice focused on explicit default/domain authority.